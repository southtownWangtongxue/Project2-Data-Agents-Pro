"""影子双跑比对(Phase 1 验证基建)。

HARNESS_MODE=shadow 时,data 模式的 legacy 响应照常返回;收尾后由
chat.py 以后台任务调用本模块:用同一问题跑 Harness 主循环,收集
回答文本/模型往返轮数/工具调用数,与 legacy 的对应指标一起写入
JSONL 比对日志(默认 configs/shadow_comparison.jsonl)。

设计约束:
- 影子失败(构建/执行任何异常)一律吞掉返回 None,绝不影响主流程;
- 只记录不自动判定(结果可用率由人审报告;自动阈值属 Phase 2);
- 日志行数上限 SHADOW_LOG_MAX_LINES,超出保留最近部分,防无限增长。
"""
from __future__ import annotations

import json
import time

from app.core.config_manager import CONFIGS_DIR, get_config_manager
from app.core.llm import set_provider
from app.harness.agent_factory import build_harness_agent
from app.harness.sse_bridge import HarnessEventBridge
from app.utils.log_utils import log

# 绝对路径(与 ConfigManager 一致):相对路径会随后端进程 CWD 漂移
COMPARISON_LOG = CONFIGS_DIR / "shadow_comparison.jsonl"
SHADOW_LOG_MAX_LINES = 5000


async def run_shadow_comparison(
    question: str,
    legacy_answer: str,
    legacy_metrics: dict,
    user_name: str = "shadow",
    model: str | None = None,
) -> dict | None:
    """跑一次 Harness 影子执行并写比对记录;任何失败返回 None(不抛)。

    model 传入请求所选模型:影子任务由 chat.py 以 create_task 调度,可能抢在
    legacy 流 set_provider 之前构建 Agent——此处按请求模型显式锁定 provider,
    避免误用进程启动时的默认 provider(无 key → 401 → 静默失败)。
    """
    try:
        if model:
            set_provider(get_config_manager().get_llm_config(model))

        agent = build_harness_agent()
        bridge = HarnessEventBridge()
        text_parts: list[str] = []
        tool_calls = 0
        llm_rounds = 0
        t0 = time.monotonic()

        config = {"configurable": {"thread_id": f"shadow:{user_name}:{time.time_ns()}"}}
        aiter = agent.astream(
            {"messages": [{"role": "user", "content": question}]},
            config, stream_mode=["updates", "messages"],
        ).__aiter__()
        while True:
            try:
                event = await aiter.__anext__()
            except StopAsyncIteration:
                break
            for sse in bridge.feed(event):
                if sse["type"] == "token":
                    text_parts.append(sse.get("content", ""))
                elif sse["type"] == "tool_call":
                    tool_calls += 1
            # 粗略的模型往返计数:每个 updates.agent/model 节点事件记一轮
            mode, data = event
            if mode == "updates" and isinstance(data, dict):
                llm_rounds += sum(1 for k in data if k in ("agent", "model"))

        record = {
            "ts": time.time(),
            "question": question[:200],
            "legacy": {
                "answer": (legacy_answer or "")[:2000],
                **legacy_metrics,
            },
            "harness": {
                "answer": "".join(text_parts)[:2000],
                "llm_rounds": llm_rounds,
                "tool_calls": tool_calls,
                "duration_ms": int((time.monotonic() - t0) * 1000),
            },
        }
        _append(record)
        return record
    except Exception as exc:  # noqa: BLE001 —— 影子失败绝不波及主流程
        log.warning("[Shadow] 比对执行失败(已忽略): %s", exc)
        return None


def _append(record: dict) -> None:
    COMPARISON_LOG.parent.mkdir(parents=True, exist_ok=True)
    with COMPARISON_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    _rotate()


def _rotate() -> None:
    try:
        lines = COMPARISON_LOG.read_text(encoding="utf-8").splitlines()
        if len(lines) > SHADOW_LOG_MAX_LINES:
            COMPARISON_LOG.write_text(
                "\n".join(lines[-SHADOW_LOG_MAX_LINES:]) + "\n", encoding="utf-8",
            )
    except OSError:
        pass


def shadow_report() -> dict:
    """聚合比对日志:总数 + harness 平均模型往返轮数(供人工审查)。"""
    if not COMPARISON_LOG.exists():
        return {"total": 0, "avg_llm_rounds": 0}
    records = []
    for line in COMPARISON_LOG.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    rounds = [r.get("harness", {}).get("llm_rounds", 0) for r in records]
    return {
        "total": len(records),
        "avg_llm_rounds": round(sum(rounds) / len(rounds), 2) if rounds else 0,
    }
