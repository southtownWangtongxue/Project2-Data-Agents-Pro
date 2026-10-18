"""
Token 计量与上下文构成（usage 统计，2026-10 前端读数条三弹窗的数据源）。

设计要点：
1. **不新增 LLM 调用**：LangChain 的 `stream_usage=True` 会在每个模型回合的
   末块挂 `usage_metadata`（input_tokens / output_tokens / input_token_details
   .cached_tokens），从 astream 事件里顺手取即可。
2. **回合内只计一次**：部分网关会在末块之外补一个 usage-only chunk，故按
   「出现新的内容/工具调用块即视为新回合」+「连续相同 usage 跳过」双重去重，
   避免同一回合重复计数。
3. **上下文三段构成是估算**：系统提示词 / 工具定义 / 对话消息三段没有现成的
   真实 token 数，用 CJK 感知估算（中文 1 字≈1 token，其余 4 字符≈1 token），
   并在事件里带 `estimated: true`，前端标注为估算值，不冒充真实用量。

事件结构（协议只增不改，新增 usage 类型）：
{
  "type": "usage",
  "input_tokens": int, "output_tokens": int, "cached_tokens": int,
  "total_tokens": int, "cache_hit_ratio": float(0~1),
  "turns": int, "steps": int,
  "estimated": true,
  "context": {
    "system_prompt": int, "tool_defs": int, "messages": int,
    "window": int, "used_pct": int
  }
}
"""
from __future__ import annotations

import json
from typing import Any, Iterable

# 上下文窗口默认按 192K 计（与 DeepSeek/V3 级模型的常见窗口一致）；
# 真实窗口由 settings 覆盖，未配置时用此默认值做占比分母。
DEFAULT_CONTEXT_WINDOW = 192_000

# CJK 统一表意文字区段（含扩展 A 与兼容区），用于 token 估算
_CJK_RANGES = (
    (0x4E00, 0x9FFF),
    (0x3400, 0x4DBF),
    (0xF900, 0xFAFF),
    (0x3040, 0x30FF),  # 日文假名
    (0xAC00, 0xD7AF),  # 韩文谚文
)


def _is_cjk(ch: str) -> bool:
    code = ord(ch)
    return any(lo <= code <= hi for lo, hi in _CJK_RANGES)


def estimate_tokens(text: Any) -> int:
    """CJK 感知 token 估算：中文/日韩 1 字≈1 token，其余 4 字符≈1 token。

    不用「字符数/3」：中文会低估约 3 倍，读数条上的上下文占比会明显失真。
    """
    if not text:
        return 0
    if not isinstance(text, str):
        try:
            text = json.dumps(text, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            text = str(text)
    cjk = sum(1 for ch in text if _is_cjk(ch))
    rest = len(text) - cjk
    return cjk + rest // 4


def messages_text(messages: Iterable[Any] | None) -> str:
    """把 messages 列表（dict 或 LangChain 消息对象）拍平成可估算的文本。"""
    parts: list[str] = []
    for m in messages or []:
        if isinstance(m, dict):
            parts.append(str(m.get("content") or ""))
        else:
            parts.append(str(getattr(m, "content", "") or ""))
    return "\n".join(p for p in parts if p)


def tool_defs_text(tools: Iterable[Any] | None) -> str:
    """把工具集（函数/LangChain BaseTool）序列化后估算工具定义占用。

    工具 schema 通常是上下文里最大的一块（截图里 ~53K），必须计入占比。
    """
    parts: list[str] = []
    for t in tools or []:
        name = getattr(t, "name", None) or getattr(t, "__name__", "") or ""
        desc = getattr(t, "description", None) or (t.__doc__ or "")
        schema = getattr(t, "args_schema", None) or getattr(t, "__annotations__", None)
        schema_text = ""
        if schema is not None:
            try:
                schema_text = json.dumps(
                    getattr(schema, "model_json_schema", lambda: schema)(),
                    ensure_ascii=False, default=str,
                )
            except Exception:  # noqa: BLE001 —— schema 序列化失败不应阻断统计
                schema_text = str(schema)
        parts.append(f"{name}\n{desc}\n{schema_text}")
    return "\n".join(p for p in parts if p)


class UsageMeter:
    """一次请求内的 token 计量器（纯内存，无 IO，可单测）。"""

    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.cached_tokens = 0
        # 本回合是否已计入 usage：内容/工具块出现 ⇒ 新回合 ⇒ 重置为 False；
        # 同回合内再次到达的 usage（网关补发的 usage-only chunk）跳过，防重复计数
        self._turn_counted = False

    # ── 采集 ──

    def observe_event(self, event: Any) -> None:
        """消费 astream 原始事件 `(mode, data)`（与 harness/deepagent 一致）。"""
        try:
            mode, data = event
        except (TypeError, ValueError):
            return
        if mode != "messages":
            return
        chunk = data[0] if isinstance(data, (tuple, list)) and len(data) == 2 else data
        self.observe_chunk(chunk)

    def observe_chunk(self, chunk: Any) -> None:
        """从 AIMessageChunk 读取 usage_metadata 并累加。"""
        if chunk is None:
            return
        # 新内容/工具调用块出现 ⇒ 新回合开始，重置「本回合已计」标记
        if getattr(chunk, "content", "") or getattr(chunk, "tool_call_chunks", None):
            self._turn_counted = False
        usage = getattr(chunk, "usage_metadata", None)
        if not isinstance(usage, dict):
            return
        inp = int(usage.get("input_tokens") or 0)
        out = int(usage.get("output_tokens") or 0)
        if not inp and not out:
            return
        # 同一回合内重复下发（网关补 usage-only chunk）时跳过
        if self._turn_counted:
            return
        self._turn_counted = True
        self.input_tokens += inp
        self.output_tokens += out
        details = usage.get("input_token_details")
        if isinstance(details, dict):
            self.cached_tokens += int(
                details.get("cache_read") or details.get("cached_tokens") or 0
            )

    def observe_usage(self, inp: int, out: int, cached: int = 0) -> None:
        """直接累加一次回合用量（on_llm_end 回调路径，口径同 observe_chunk）。"""
        inp, out, cached = int(inp or 0), int(out or 0), int(cached or 0)
        if not inp and not out:
            return
        if self._turn_counted:
            return
        self._turn_counted = True
        self.input_tokens += inp
        self.output_tokens += out
        self.cached_tokens += cached

    # ── 输出 ──

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def uncached_input_tokens(self) -> int:
        """未缓存输入 = 输入总量 - 缓存读取部分（下限 0）。"""
        return max(0, self.input_tokens - self.cached_tokens)

    @property
    def cache_hit_ratio(self) -> float:
        if self.input_tokens <= 0:
            return 0.0
        return round(min(1.0, self.cached_tokens / self.input_tokens), 4)

    def snapshot(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_tokens": self.cached_tokens,
            "uncached_input_tokens": self.uncached_input_tokens,
            "total_tokens": self.total_tokens,
            "cache_hit_ratio": self.cache_hit_ratio,
        }


def context_breakdown(
    *,
    system_prompt: str = "",
    tool_defs: str = "",
    messages: str = "",
    window: int = DEFAULT_CONTEXT_WINDOW,
) -> dict:
    """上下文三段构成 + 占比（估算值，调用方负责标 estimated）。"""
    sp = estimate_tokens(system_prompt)
    td = estimate_tokens(tool_defs)
    ms = estimate_tokens(messages)
    used = sp + td + ms
    win = max(1, int(window or DEFAULT_CONTEXT_WINDOW))
    return {
        "system_prompt": sp,
        "tool_defs": td,
        "messages": ms,
        "window": win,
        "used_pct": min(100, round(used / win * 100)),
    }


def build_usage_event(
    meter: UsageMeter,
    *,
    context: dict | None = None,
    turns: int = 0,
    steps: int = 0,
) -> dict:
    """组装 SSE usage 事件（协议只增：新事件类型，不改既有事件）。"""
    payload: dict[str, Any] = {"type": "usage"}
    payload.update(meter.snapshot())
    payload["turns"] = int(turns or 0)
    payload["steps"] = int(steps or 0)
    payload["estimated"] = True
    payload["context"] = context or context_breakdown()
    return payload


# ── 请求级计量器注册（legacy 路径专用）────────────────────────
# legacy 图的 LLM 调用发生在各 agent 内部（get_langchain_llm），graph 流里
# 看不到 usage；由 llm.py 的模块级回调把 on_llm_end 的 token_usage 回灌到
# 这里注册的请求级计量器。harness/deepagent 路径从 astream 事件直读
# usage_metadata，不注册（回调对其自然 no-op），避免双计。
import contextvars as _contextvars

_request_meter: _contextvars.ContextVar["UsageMeter | None"] = _contextvars.ContextVar(
    "request_usage_meter", default=None
)


def set_request_usage_meter(meter: "UsageMeter | None") -> None:
    """注册当前请求的计量器（legacy 流式生成器入口调用，finally 置 None）。"""
    _request_meter.set(meter)


def get_request_usage_meter() -> "UsageMeter | None":
    return _request_meter.get()
