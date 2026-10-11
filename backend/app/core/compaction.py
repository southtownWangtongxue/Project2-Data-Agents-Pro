"""
上下文压缩（R21，对齐 Harness compaction 插件）

多轮对话的 messages 历史随会话轮数无限增长，最终导致 LLM 上下文爆炸、
延迟上升与费用失控。本模块在请求入口对历史消息做**确定性压缩**（不调用
LLM，零额外延迟）：

策略：
    - 消息数 ≤ CONTEXT_MAX_MESSAGES：原样返回（不触发）
    - 超限时：保留最近 CONTEXT_KEEP_RECENT 条完整消息；
      其余被丢弃的消息生成一条摘要（digest）置顶替代——
      digest 为各条消息的「角色 + 前 80 字符」逐行拼接，
      总长封顶 CONTEXT_DIGEST_MAX_CHARS，并以 "[历史压缩]" 标记开头

设计取舍：
    - 选择确定性摘要而非 LLM 总结：零延迟、零费用、结果可测试；
      LLM 语义摘要可作为后续增强（对齐 Harness compaction 的 LLM 路径）
    - 摘要 role 使用 "system"：明确标识为系统注入的上下文而非对话内容
    - 纯函数、无副作用，便于单元测试
"""
from __future__ import annotations

from app.core.config import settings
from app.utils.log_utils import log

DIGEST_MARKER = "[历史压缩]"


def _content_of(msg: dict) -> str:
    """安全取消息文本（容忍 None / 非字符串）。"""
    content = msg.get("content") if isinstance(msg, dict) else None
    return content if isinstance(content, str) else ("" if content is None else str(content))


def _digest_of(dropped: list[dict], max_chars: int) -> str:
    """将被丢弃的消息压缩为一段摘要文本。"""
    lines = []
    for msg in dropped:
        role = msg.get("role", "?")
        preview = _content_of(msg).replace("\n", " ").strip()[:80]
        lines.append(f"- {role}: {preview}" if preview else f"- {role}: (空)")
    digest = DIGEST_MARKER + f" 以下为更早 {len(dropped)} 条消息的摘要：\n" + "\n".join(lines)
    if len(digest) > max_chars:
        digest = digest[:max_chars] + "…"
    return digest


def compact_history(messages: list[dict]) -> tuple[list[dict], dict]:
    """
    按配置压缩对话历史。

    参数:
        messages: 历史消息列表（不含本轮用户提问），元素为 {"role", "content"}

    返回:
        (compacted, stats)
        - compacted: 压缩后的消息列表（未触发时为原列表的浅拷贝）
        - stats: {"triggered", "original", "kept", "dropped", "digest_chars"}
    """
    if not settings.CONTEXT_COMPACTION_ENABLED:
        return list(messages or []), {"triggered": False, "original": len(messages or [])}

    msgs = [m for m in (messages or []) if isinstance(m, dict)]
    total = len(msgs)
    max_msgs = max(settings.CONTEXT_MAX_MESSAGES, 1)
    keep = min(settings.CONTEXT_KEEP_RECENT, max_msgs - 1)  # 至少留 1 条给摘要位

    if total <= max_msgs:
        return list(msgs), {
            "triggered": False, "original": total, "kept": total, "dropped": 0, "digest_chars": 0,
        }

    dropped = msgs[: total - keep]
    kept = msgs[total - keep :]
    digest_text = _digest_of(dropped, settings.CONTEXT_DIGEST_MAX_CHARS)
    digest_msg = {"role": "system", "content": digest_text}

    compacted = [digest_msg, *kept]
    stats = {
        "triggered": True,
        "original": total,
        "kept": len(kept),
        "dropped": len(dropped),
        "digest_chars": len(digest_text),
    }
    log.info(
        f"[Compaction] 历史已压缩: {stats['original']} 条 → 摘要 1 条 + 保留 {stats['kept']} 条"
    )
    return compacted, stats
