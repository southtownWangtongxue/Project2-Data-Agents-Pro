"""legacy 流的「透传 + 收尾回调」helper(Phase 2 影子采集管线)。

为什么需要:影子任务原先建在 async for 循环之后,流若以异常/取消结束
(客户端断开、legacy 超时、生成器被提前关闭)就永不触发——实测同一批 3 个
问题只落盘 2 条,采集管线静默丢样本,却看不出丢了。

本 helper 用 finally 兜底:无论流如何结束都回调一次,回调是**同步**的
(内部只做 create_task)——async generator 在 GeneratorExit 阶段不得 await,
否则 RuntimeError。
"""
from __future__ import annotations

import json
from typing import Any, AsyncIterator, Callable


def _extract_token_text(chunk: str) -> str:
    """从 SSE 块里取 token 事件的正文(非 token 事件忽略)。"""
    out: list[str] = []
    for line in chunk.splitlines():
        if not line.startswith("data: "):
            continue
        try:
            ev = json.loads(line[6:])
        except ValueError:
            continue
        if isinstance(ev, dict) and ev.get("type") == "token":
            out.append(str(ev.get("content") or ""))
    return "".join(out)


def tap_stream(
    inner: AsyncIterator[str],
    on_finish: Callable[[str], Any],
) -> AsyncIterator[str]:
    """原样透传 inner 的 chunk,并在流结束时(任何结束方式)调用 on_finish(正文)。

    on_finish 必须是同步可调用(通常是创建后台任务);其异常被吞掉,
    绝不影响已经产出的 legacy 响应。
    """

    async def _gen() -> AsyncIterator[str]:
        parts: list[str] = []
        try:
            async for chunk in inner:
                parts.append(_extract_token_text(chunk))
                yield chunk
        finally:
            try:
                on_finish("".join(parts))
            except Exception:  # noqa: BLE001 —— 收尾回调失败不影响已发响应
                pass

    return _gen()
