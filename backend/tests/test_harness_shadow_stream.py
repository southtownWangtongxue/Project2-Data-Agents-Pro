"""legacy 流「透传 + 收尾回调」helper 测试(TDD)。

背景:影子任务原先建在 async for 循环之后,流若以异常/取消结束
(客户端断开、legacy 超时)就永不触发——实测同一批 3 个问题只落盘 2 条。
改为 finally 兜底:无论流如何结束都回调一次(同步回调,避免 GeneratorExit
中 await 报错)。
"""
import asyncio

import pytest

from app.harness.shadow_stream import tap_stream


def sse(t, **kw):
    import json
    return "data: " + json.dumps({"type": t, **kw}, ensure_ascii=False) + "\n\n"


@pytest.mark.asyncio
async def test_collects_token_text_and_fires_on_normal_end():
    fired = []

    async def inner():
        yield sse("token", content="答案")
        yield sse("done")

    async for _ in tap_stream(inner(), lambda a: fired.append(a)):
        pass
    assert fired == ["答案"]


@pytest.mark.asyncio
async def test_ignores_non_token_events():
    fired = []

    async def inner():
        yield sse("sql", sql="SELECT 1")
        yield sse("tool_result", content="5 行")
        yield sse("token", content="正文")

    async for _ in tap_stream(inner(), lambda a: fired.append(a)):
        pass
    assert fired == ["正文"]


@pytest.mark.asyncio
async def test_fires_even_when_inner_raises():
    """legacy 内部异常时也要触发(否则采集管线静默丢样本)。"""
    fired = []

    async def inner():
        yield sse("token", content="部分")
        raise RuntimeError("legacy 炸了")

    with pytest.raises(RuntimeError):
        async for _ in tap_stream(inner(), lambda a: fired.append(a)):
            pass
    assert fired == ["部分"]


@pytest.mark.asyncio
async def test_fires_even_when_consumer_stops_early():
    """客户端中途断开(生成器被关闭)也要触发。"""
    fired = []

    async def inner():
        yield sse("token", content="第一段")
        yield sse("token", content="第二段")
        yield sse("done")

    gen = tap_stream(inner(), lambda a: fired.append(a))
    async for _ in gen:
        break
    await gen.aclose()
    assert fired and fired[0] == "第一段"


@pytest.mark.asyncio
async def test_passes_chunks_through_unchanged():
    """必须原样透传,不能改变 legacy 响应字节。"""
    chunks = [sse("token", content="a"), sse("done")]

    async def inner():
        for c in chunks:
            yield c

    got = [c async for c in tap_stream(inner(), lambda a: None)]
    assert got == chunks


@pytest.mark.asyncio
async def test_callback_exception_does_not_break_stream():
    """回调自身抛错不得影响已完成的 legacy 响应。"""
    def boom(_ans):
        raise RuntimeError("回调炸了")

    async def inner():
        yield sse("token", content="x")
        yield sse("done")

    got = [c async for c in tap_stream(inner(), boom)]
    assert len(got) == 2
