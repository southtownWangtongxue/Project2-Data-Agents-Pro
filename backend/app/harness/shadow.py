"""影子双跑比对(Phase 1 验证基建 / Phase 2 决策数据源)。

HARNESS_MODE=shadow 时,data 模式的 legacy 响应照常返回;收尾后由
chat.py 以后台任务调用本模块:用**与真实请求完全一致的构造路径**跑一遍
Harness 主循环,记录回答与过程指标,写入 JSONL 比对日志
(默认 backend/configs/shadow_comparison.jsonl)。

设计约束:
- 影子失败(构建/执行/写盘任何异常)一律吞掉返回 None,绝不影响主流程;
- 构造路径必须与 stream_chat_harness 对齐(同 messages 序列、同 runtime_context、
  同 provider 锁定),否则比对出的差异是环境差异而非模型差异;
- 采样指标用于 Phase 2 决策:write_todos 使用率(决定步骤链方案)、
  工具调用数/SQL 条数(衡量 UNION 优化效果)、答案长度(口径差异)。
- 日志行数上限 SHADOW_LOG_MAX_LINES,超出保留最近部分,防无限增长。
"""
from __future__ import annotations

import json as _json
import json
import time

from app.core.answer_quality import check_dimensions, check_grounding
from app.core.config_manager import CONFIGS_DIR, get_config_manager
from app.core.llm import set_provider
from app.harness.agent_factory import build_harness_agent
from app.harness.sse_bridge import HarnessEventBridge
from app.utils.log_utils import log

# 绝对路径(与 ConfigManager 一致):相对路径会随后端进程 CWD 漂移
COMPARISON_LOG = CONFIGS_DIR / "shadow_comparison.jsonl"
SHADOW_LOG_MAX_LINES = 5000

SQL_TOOL = "run_sql"
TODO_TOOL = "write_todos"


async def run_shadow_comparison(
    question: str,
    legacy_answer: str,
    legacy_metrics: dict,
    user_name: str = "shadow",
    model: str | None = None,
    runtime_context: str = "",
    history: list[dict] | None = None,
    legacy_tool_payloads: list[str] | None = None,
) -> dict | None:
    """跑一次 Harness 影子执行并写比对记录;任何失败返回 None(不抛)。

    参数:
        question: 用户问题(= 真实请求 messages[-1])
        legacy_answer: legacy 侧回答(可为空占位)
        legacy_metrics: legacy 侧指标(耗时等)
        model: 请求所选模型;影子任务由 create_task 调度,可能抢在 legacy 流
              set_provider 之前构建 Agent,故按请求模型显式锁定 provider
        runtime_context: 与真实请求一致的运行时上下文 system 消息
        history: 与真实请求一致的历史消息
    """
    try:
        if model:
            set_provider(get_config_manager().get_llm_config(model))

        agent = build_harness_agent()
        bridge = HarnessEventBridge()
        text_parts: list[str] = []
        tool_payloads: list[str] = []
        tool_rows: list[dict] = []
        grounding_rows = 0
        tool_calls = 0
        sql_count = 0
        used_todos = False
        llm_rounds = 0
        t0 = time.monotonic()

        # 构造路径与 stream_chat_harness 保持一致:历史 + 用户问题,
        # 有运行时上下文时前置 system 消息(与真实请求同序)
        messages = [*(history or []), {"role": "user", "content": question}]
        if runtime_context:
            messages = [{"role": "system", "content": runtime_context}, *messages]

        config = {
            "configurable": {"thread_id": f"shadow:{user_name}:{time.time_ns()}"},
            "recursion_limit": 40,
        }
        aiter = agent.astream(
            {"messages": messages}, config, stream_mode=["updates", "messages"],
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
                    if sse.get("name") == SQL_TOOL:
                        sql_count += 1
                    elif sse.get("name") == TODO_TOOL:
                        used_todos = True
                elif sse["type"] == "tool_result":
                    tool_payloads.append(str(sse.get("content") or ""))
                elif sse["type"] == "result":
                    # 接地对账必须用真实行数据(result.data),不是摘要——
                    # 摘要只有「查询成功 · N 行」,拿它对账会把真实数字全判成幻觉
                    tool_payloads.append(_json.dumps(sse.get("data") or [], ensure_ascii=False))
                    grounding_rows += 1
                    tool_rows.extend(sse.get("data") or [])
            # 粗略的模型往返计数:每个 updates.agent/model 节点事件记一轮
            mode, data = event
            if mode == "updates" and isinstance(data, dict):
                llm_rounds += sum(1 for k in data if k in ("agent", "model"))

        answer = "".join(text_parts)
        # 答案质量指标(两臂共用同一纯函数,避免两把尺子悄悄漂移):
        # 接地是硬指标(幻觉一票否决),维度数是预筛(误判率有限,人工复核)
        grounding = check_grounding(answer, tool_payloads)
        dims = check_dimensions(answer, tool_payloads)
        lg = check_grounding(legacy_answer or "", list(legacy_tool_payloads or []))
        lg_dims = check_dimensions(legacy_answer or "", list(legacy_tool_payloads or []))

        record = {
            "ts": time.time(),
            "question": question[:200],
            "model": model or "",
            "legacy": {
                "answer": (legacy_answer or "")[:2000],
                "answer_len": len(legacy_answer or ""),
                "grounded": lg["grounded"],
                "ungrounded": lg["ungrounded"],
                "dimensions": lg_dims["hit"],
                "dim_count": lg_dims["count"],
                **legacy_metrics,
            },
            "harness": {
                "answer": answer[:2000],
                "answer_len": len(answer),
                "llm_rounds": llm_rounds,
                "tool_calls": tool_calls,
                "sql_count": sql_count,
                "used_todos": used_todos,
                "duration_ms": int((time.monotonic() - t0) * 1000),
                # 构造路径自证:有 runtime_context + 至少一轮模型调用。
                # 基线轮出现过「请求格式写错 → 模型收到空问题」的环境差异,
                # 该标记让噪声样本可事后排除(不必依赖人工推断)。
                "ctx_ok": bool(runtime_context) and llm_rounds >= 1,
                # 答案质量(指标 1/2)
                "grounded": grounding["grounded"],
                "ungrounded": grounding["ungrounded"],
                "grounded_details": grounding["details"][:20],
                "grounding_reason": grounding["reason"],
                "grounding_source": "result_rows" if grounding_rows else "none",
                "dimensions": dims["hit"],
                "tool_rows": tool_rows[:50],
                "dim_count": dims["count"],
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
    """聚合比对日志,并标注 legacy 接地的数据可信度。

    todo_rate 与 avg_sql_count 是 Phase 2 决策依据:
    - todo_rate 低 → 步骤链需兜底或强化 SOP(看具体分布再定)
    - avg_sql_count 偏高 → UNION 优化(已加 SOP 指引)效果如何

    legacy 接地的已知局限(Phase 2 方案 B,不阻塞核心决策):
    1. 嵌套派生不判定:如「占总量的 81.55%」= 1289/1604*100,而 1604 本身也是
       派生值,当前只支持一层派生,此类数字会被误判为未接地;
    2. legacy 侧偶发采不到正文(13 节点流超时/取消),此时维度与接地均为 0,
       属样本缺失而非质量差——已由 answer_len=0 标识,统计时应排除。
    出现第 1 类未接地数字时,报告输出
    legacy_grounding_reliability="degraded_nested_derivation" 显式降级标记,
    避免读者把尺子局限误读为「legacy 在幻觉」。
    门禁判定以 Harness 接地 + 人工复核为准。
    """
    empty = {"total": 0, "avg_llm_rounds": 0, "todo_rate": 0,
             "avg_sql_count": 0, "legacy_grounding_reliability": None}
    if not COMPARISON_LOG.exists():
        return empty
    records = []
    for line in COMPARISON_LOG.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if not records:
        return empty
    h = [r.get("harness", {}) for r in records]
    legacy_ungrounded = [
        v for r in records for v in (r.get("legacy", {}).get("ungrounded") or [])
    ]
    return {
        "total": len(records),
        "avg_llm_rounds": round(sum(x.get("llm_rounds", 0) for x in h) / len(h), 2),
        "todo_rate": round(sum(bool(x.get("used_todos")) for x in h) / len(h), 2),
        "avg_sql_count": round(sum(x.get("sql_count", 0) for x in h) / len(h), 2),
        "avg_tool_calls": round(sum(x.get("tool_calls", 0) for x in h) / len(h), 2),
        "legacy_grounding_reliability": (
            "degraded_nested_derivation" if legacy_ungrounded else None
        ),
    }
def _fmt_arm(name: str, arm: dict) -> str:
    """格式化一臂的质量摘要;早期样本无质量字段时标注「未采集」。"""
    if "grounded" not in arm:
        return f"- {name}:(早期样本,未采集质量指标)"
    dims = ", ".join(arm.get("dimensions") or [])
    return (f"- {name}:接地 `{arm.get('grounded')}` / 维度 `{arm.get('dim_count')}`"
            + (f" ({dims})" if dims else ""))

def build_review_document() -> str:
    """生成人工判定对照文件(Markdown),指标 3/4 的判定辅助。

    每个问题输出:原始提问全文 / 两臂答案 / 本轮工具行数据(run_sql result);
    legacy 接地旁标注可信度;样本缺失(legacy 空答案)保留「已排除」占位,
    使文件与采集批次一一对应,日后复查不迷路。
    """
    if not COMPARISON_LOG.exists():
        return "# Harness 两臂对照(人工判定用)\n\n暂无采集数据。\n"

    records = []
    for line in COMPARISON_LOG.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # 单条坏记录不阻塞整体导出

    out = [
        "# Harness 两臂对照(人工判定用)",
        "",
        f"- 样本数:{len(records)}(含已排除占位,与采集批次一一对应)",
        "- 判定说明:指标 3(子问题覆盖)对照原始提问逐项核对;"
        "指标 4(结论正确性)对照下方「工具行数据」核对答案中的数字。",
        "- 判定标记:`[ ]` 未判 / `[x] 过` / `[x] 不过`",
        "",
    ]
    for idx, r in enumerate(records, 1):
        h = r.get("harness", {})
        l = r.get("legacy", {})
        legacy_ungrounded = l.get("ungrounded") or []
        rows = h.get("tool_rows") or []
        out += [
            f"## {idx}. {r.get('question', '(未记录问题)')}",
            "",
            f"- 模型:`{r.get('model', '')}`",
            f"- HARNESS:接地 `{h.get('grounded')}` / 维度 `{h.get('dim_count')}` "
            f"({', '.join(h.get('dimensions') or [])})",
        ]
        if legacy_ungrounded:
            out.append(
                f"- LEGACY:接地 `{l.get('grounded')}` / 维度 `{l.get('dim_count')}` "
                f"— 注意:`legacy_grounding_reliability=degraded_nested_derivation`"
                f"(嵌套派生判不出来,未接地数字 {legacy_ungrounded} 不构成幻觉证据)"
            )
        else:
            out.append(
                f"- LEGACY:接地 `{l.get('grounded')}` / 维度 `{l.get('dim_count')}`"
            )

        if not l.get("answer_len"):
            out += ["", "> ⚠️ **已排除**:legacy 侧未采到答案(流超时/取消),"
                        "该样本不计入对比,保留占位以对齐采集批次。"]
        out += ["", "### 工具行数据(run_sql result)", ""]
        if rows:
            out.append("```json")
            out.append(json.dumps(rows, ensure_ascii=False, indent=2))
            out.append("```")
        else:
            out.append("(本轮未采集到工具行数据)")

        out += ["", "### 两臂答案", "", "**HARNESS:**", "", h.get("answer") or "(空)"]
        if l.get("answer"):
            out += ["", "**LEGACY:**", "", l["answer"]]
        out += ["", "### 人工判定", "",
                "- 指标 3 子问题覆盖:`[ ]`",
                "- 指标 4 结论正确性:`[ ]`", ""]
    return "\n".join(out)