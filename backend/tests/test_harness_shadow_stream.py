"""legacy 流「透传 + 收尾回调」helper 测试(TDD)。

背景:影子任务原先建在 async for 循环之后,流若以异常/取消结束
(客户端断开、legacy 超时)就永不触发——实测同一批 3 个问题只落盘 2 条。
改为 finally 兜底:无论流如何结束都回调一次(同步回调,避免 GeneratorExit
中 await 报错)。
"""
import json

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
async def test_tap_stream_passes_chunks_through_unchanged():
    """必须原样透传,不能改变 legacy 响应字节。"""
    chunks = [sse("token", content="a"), sse("done")]

    async def inner():
        for c in chunks:
            yield c

    got = []
    async for c in tap_stream(inner(), lambda a, t: None):
        got.append(c)
    assert got == chunks

@pytest.mark.asyncio
async def test_callback_exception_does_not_break_stream():
    """回调自身抛错不得影响已完成的 legacy 响应。"""

    def boom(_ans, _tools=None):
        raise RuntimeError("回调炸了")

    async def inner():
        yield sse("token", content="x")
        yield sse("done")

    got = []
    async for c in tap_stream(inner(), boom):
        got.append(c)
    assert len(got) == 2

@pytest.mark.asyncio
async def test_tap_stream_accepts_quality_hook():
    """tap_stream 收集 legacy 侧 tool_result 载荷,供同一把尺子做接地检测。"""
    fired = {}

    async def inner():
        yield sse("tool_result", content='{"row_count": 1107}')
        yield sse("token", content="共 1107 条")
        yield sse("done")

    got = []
    async for c in tap_stream(inner(), lambda a, t: fired.update(answer=a, tools=t)):
        got.append(c)
    assert len(got) == 3
    assert fired["answer"] == "共 1107 条"
    assert fired["tools"] == ['{"row_count": 1107}']


@pytest.mark.asyncio
async def test_tap_stream_tool_payloads_ignores_other_events():
    fired = {}

    async def inner():
        yield sse("sql", sql="SELECT COUNT(*) FROM t")
        yield sse("tool_result", content="查询成功 · 5 行")
        yield sse("done")

    async for _ in tap_stream(inner(), lambda a, t: fired.update(tools=t)):
        pass
    assert fired["tools"] == ["查询成功 · 5 行"]

@pytest.mark.asyncio
async def test_tap_stream_collects_legacy_result_rows():
    """legacy 侧的接地数据源:result.data(与 harness 同一把尺子)。

    实测 legacy 的 tool_result 只有 tool_name/row_count 没有 content,
    真正能对账的是 result 事件里的 data。
    """
    fired = {}

    async def inner():
        yield sse("result", data=[{"table_name": "chat_nodes", "record_count": 147}])
        yield sse("tool_result", tool_name="execute_sql", row_count=1)
        yield sse("token", content="共 147 条")
        yield sse("done")

    async for _ in tap_stream(inner(), lambda a, t: fired.update(tools=t)):
        pass
    assert any("chat_nodes" in t and "147" in t for t in fired["tools"]), fired["tools"]


@pytest.mark.asyncio
async def test_legacy_grounding_uses_result_rows():
    """端到端:legacy 侧真实行数据能让派生数字对账(合计/均值不被误判幻觉)。"""
    from app.core.answer_quality import check_grounding

    rows = json.dumps([{"t": "a", "n": 100}, {"t": "b", "n": 50}, {"t": "c", "n": 0}])
    rep = check_grounding("row_count 合计 150，均值 50", [rows])
    assert rep["grounded"] is True, rep["ungrounded"]