"""影子双跑比对测试:legacy 与 harness 双跑,产出比对记录;影子失败不影响主流程。"""
import json

import pytest

import json

from app.harness import shadow


class _FakeAgent:
    """产出固定文本的假 Agent(贴近真实流:updates 模型回合 + messages 流式 token)。"""

    def __init__(self, text="智能体回答", tool_results=0):
        self.text = text
        self.tool_results = tool_results

    async def astream(self, input_data, config, stream_mode=None):
        chunk = type("M", (), {
            "content": self.text,
            "tool_calls": None,
            "tool_call_chunks": None,
            "additional_kwargs": {},
            "reasoning_content": "",
        })()
        # 真实 deepagents:模型回合以 updates.agent 收尾,messages 承载逐 token 流
        yield ("updates", {"agent": {"messages": [chunk]}})
        yield ("messages", (chunk, {"langgraph_node": "agent"}))
        for i in range(self.tool_results):
            tm = type("M", (), {"content": "ok", "name": "run_sql"})()
            yield ("updates", {"tools": {"messages": [tm]}})


@pytest.fixture
def patched(monkeypatch, tmp_path):
    monkeypatch.setattr(shadow, "build_harness_agent", lambda: _FakeAgent())
    monkeypatch.setattr(shadow, "COMPARISON_LOG", tmp_path / "shadow.jsonl")
    yield tmp_path


@pytest.mark.asyncio
async def test_comparison_record_written(patched):
    rec = await shadow.run_shadow_comparison(
        question="统计各表数据量",
        legacy_answer="legacy 回答",
        legacy_metrics={"duration_ms": 1000, "llm_calls": 4, "tools": 5},
    )
    assert rec["question"] == "统计各表数据量"
    assert rec["legacy"]["answer"] == "legacy 回答"
    assert rec["harness"]["answer"] == "智能体回答"
    assert rec["harness"]["llm_rounds"] >= 1
    lines = shadow.COMPARISON_LOG.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["question"] == "统计各表数据量"


@pytest.mark.asyncio
async def test_shadow_failure_returns_none_and_no_log(patched, monkeypatch):
    def boom():
        raise RuntimeError("agent build failed")

    monkeypatch.setattr(shadow, "build_harness_agent", boom)
    rec = await shadow.run_shadow_comparison(
        question="x", legacy_answer="y", legacy_metrics={"duration_ms": 1},
    )
    assert rec is None
    assert not shadow.COMPARISON_LOG.exists()


@pytest.mark.asyncio
async def test_shadow_resolves_provider_from_request_model(patched, monkeypatch):
    """传入请求模型时,先按该模型锁定 provider 再构建 Agent。

    防止影子任务抢在 legacy 流 set_provider 之前构建,误用进程启动时的
    默认 provider(无 key → 401 → 静默失败)。
    """
    seen = {}

    def fake_set_provider(cfg):
        seen["provider_cfg"] = cfg

    monkeypatch.setattr(shadow, "set_provider", fake_set_provider)
    monkeypatch.setattr(
        shadow, "get_config_manager",
        lambda: type("M", (), {"get_llm_config": staticmethod(lambda model: {"model": model})})(),
    )
    monkeypatch.setattr(shadow, "build_harness_agent", lambda: _FakeAgent())

    await shadow.run_shadow_comparison(
        question="q", legacy_answer="a", legacy_metrics={}, model="qwen3.7-max",
    )
    assert seen["provider_cfg"] == {"model": "qwen3.7-max"}


@pytest.mark.asyncio
async def test_shadow_without_model_skips_provider_lock(patched, monkeypatch):
    """未传模型(如手动触发)时不动 provider 解析。"""
    called = {"set": False}

    def fake_set_provider(cfg):
        called["set"] = True

    monkeypatch.setattr(shadow, "set_provider", fake_set_provider)
    monkeypatch.setattr(shadow, "build_harness_agent", lambda: _FakeAgent())

    await shadow.run_shadow_comparison(question="q", legacy_answer="a", legacy_metrics={})
    assert called["set"] is False


def test_report_aggregates(patched):
    shadow.COMPARISON_LOG.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in [
        {"question": "q1", "legacy": {"answer": "a"}, "harness": {"answer": "b", "llm_rounds": 2}},
        {"question": "q2", "legacy": {"answer": "c"}, "harness": {"answer": "d", "llm_rounds": 3}},
    ]), encoding="utf-8")
    report = shadow.shadow_report()
    assert report["total"] == 2
    assert report["avg_llm_rounds"] == 2.5


# ── 影子采样指标 + 构造路径对齐(Phase 2 比对数据依据)────────────

class _RecordingAgent:
    """记录入参与工具序列的假 Agent,用于验证影子指标与消息构造。"""

    def __init__(self, tool_names=("run_sql",), answer="智能体回答"):
        self.tool_names = list(tool_names)
        self.answer = answer
        self.input_data = None

    async def astream(self, input_data, config, stream_mode=None):
        self.input_data = input_data
        chunk = type("M", (), {
            "content": self.answer, "tool_calls": None, "tool_call_chunks": None,
            "additional_kwargs": {}, "reasoning_content": "",
        })()
        yield ("updates", {"agent": {"messages": [chunk]}})
        yield ("messages", (chunk, {"langgraph_node": "agent"}))
        for i, name in enumerate(self.tool_names):
            ai = type("M", (), {"tool_calls": [
                {"name": name, "args": {}, "id": f"c_{name}_{i}"}
            ]})()
            yield ("updates", {"agent": {"messages": [ai]}})


@pytest.mark.asyncio
async def test_shadow_records_todo_and_sql_metrics(patched, monkeypatch):
    """采样指标:write_todos 使用、工具调用数、SQL 条数、答案长度。

    这些指标决定「步骤链方案选 (a/b) 兜底还是 (c) 强化 SOP」——需要数据支撑。
    """
    agent = _RecordingAgent(tool_names=["write_todos", "run_sql", "run_sql", "make_chart"])
    monkeypatch.setattr(shadow, "build_harness_agent", lambda: agent)

    rec = await shadow.run_shadow_comparison(
        question="统计各表数据量", legacy_answer="legacy", legacy_metrics={},
    )
    h = rec["harness"]
    assert h["used_todos"] is True
    assert h["tool_calls"] == 4
    assert h["sql_count"] == 2, "SQL 条数应单独统计(不能与其它工具混算)"
    assert h["answer_len"] == len("智能体回答")


@pytest.mark.asyncio
async def test_shadow_without_todos_records_false(patched, monkeypatch):
    """模型没建 todo 时 used_todos=False(用于统计 todo 使用率)。"""
    monkeypatch.setattr(shadow, "build_harness_agent", lambda: _RecordingAgent(["run_sql"]))
    rec = await shadow.run_shadow_comparison(
        question="q", legacy_answer="a", legacy_metrics={},
    )
    assert rec["harness"]["used_todos"] is False


@pytest.mark.asyncio
async def test_shadow_message_construction_matches_real_path(patched, monkeypatch):
    """构造路径必须与真实请求一致(同 runtime_context system 消息 + 用户问题)。

    否则比对出的差异是环境差异而非模型差异——本轮"自我介绍"事件的前车之鉴。
    """
    agent = _RecordingAgent()
    monkeypatch.setattr(shadow, "build_harness_agent", lambda: agent)
    ctx = "[运行时上下文] 当前用户: admin | 模式: data"

    await shadow.run_shadow_comparison(
        question="统计各表数据量", legacy_answer="a", legacy_metrics={},
        runtime_context=ctx,
    )
    msgs = agent.input_data["messages"]
    assert msgs[0]["role"] == "system"
    assert ctx in msgs[0]["content"]
    assert msgs[-1]["role"] == "user"
    assert msgs[-1]["content"] == "统计各表数据量"


def test_shadow_report_includes_todo_rate_and_sql(patched):
    """汇总报告要能回答「todo 使用率」与「平均 SQL 条数」。"""
    shadow.COMPARISON_LOG.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in [
        {"harness": {"llm_rounds": 2, "used_todos": True, "sql_count": 1, "answer_len": 100}},
        {"harness": {"llm_rounds": 4, "used_todos": False, "sql_count": 3, "answer_len": 200}},
    ]), encoding="utf-8")
    rep = shadow.shadow_report()
    assert rep["total"] == 2
    assert rep["todo_rate"] == 0.5
    assert rep["avg_sql_count"] == 2.0


@pytest.mark.asyncio
async def test_shadow_record_marks_construction_path(patched, monkeypatch):
    """记录里要能看出构造路径是否正常(有 runtime_context + 非空问题)。

    基线轮出现过「测试请求格式写错 → 模型收到空问题」的环境差异,
    记录须自带证据以便事后排除噪声样本。
    """
    monkeypatch.setattr(shadow, "build_harness_agent", lambda: _RecordingAgent())
    rec = await shadow.run_shadow_comparison(
        question="统计各表数据量", legacy_answer="a", legacy_metrics={},
        runtime_context="[运行时上下文] 当前用户: admin | 模式: data",
    )
    assert rec["harness"]["ctx_ok"] is True
    assert rec["harness"]["llm_rounds"] >= 1, "0 轮说明问题没送进模型(构造异常)"


@pytest.mark.asyncio
async def test_shadow_record_flags_missing_context(patched, monkeypatch):
    monkeypatch.setattr(shadow, "build_harness_agent", lambda: _RecordingAgent())
    rec = await shadow.run_shadow_comparison(
        question="q", legacy_answer="a", legacy_metrics={}, runtime_context="",
    )
    assert rec["harness"]["ctx_ok"] is False


# ── 两臂同尺:结构化质量指标接入影子记录(Phase 2 门禁)─────────

@pytest.mark.asyncio
async def test_shadow_record_includes_quality_metrics(patched, monkeypatch):
    """影子记录要带两臂可比的答案质量指标(接地 + 维度),口径共用一个纯函数。"""
    monkeypatch.setattr(
        shadow, "build_harness_agent",
        lambda: _QualityAgent(
            tool_names=["run_sql"],
            tool_payloads=['{"row_count": 1107, "session_events": 883}'],
            answer="session_events 有 883 条,占 1107 的 80%,是 sessions 的 8 倍,呈上升趋势。",
        ),
    )
    rec = await shadow.run_shadow_comparison(
        question="q", legacy_answer="a", legacy_metrics={},
    )
    h = rec["harness"]
    assert h["grounded"] is True, h.get("ungrounded")
    assert h["dim_count"] >= 2
    assert h["grounded_details"], "派生路径要落盘供人工复核"


@pytest.mark.asyncio
async def test_shadow_flags_hallucinated_numbers(patched, monkeypatch):
    monkeypatch.setattr(
        shadow, "build_harness_agent",
        lambda: _QualityAgent(
            tool_names=["run_sql"],
            tool_payloads=['{"row_count": 1107}'],
            answer="共 9999 条记录。",
        ),
    )
    rec = await shadow.run_shadow_comparison(question="q", legacy_answer="a", legacy_metrics={})
    assert rec["harness"]["grounded"] is False
    assert 9999 in rec["harness"]["ungrounded"]


class _QualityAgent:
    """带工具结果的假 Agent,用于验证答案质量指标(接地/维度)。"""

    def __init__(self, tool_names=("run_sql",), tool_payloads=("{}",), answer="答案"):
        self.tool_names = list(tool_names)
        self.tool_payloads = list(tool_payloads)
        self.answer = answer

    async def astream(self, input_data, config, stream_mode=None):
        chunk = type("M", (), {
            "content": self.answer, "tool_calls": None, "tool_call_chunks": None,
            "additional_kwargs": {}, "reasoning_content": "",
        })()
        yield ("updates", {"agent": {"messages": [chunk]}})
        yield ("messages", (chunk, {"langgraph_node": "agent"}))
        for i, name in enumerate(self.tool_names):
            ai = type("M", (), {"tool_calls": [
                {"name": name, "args": {}, "id": f"c_{name}_{i}"}
            ]})()
            yield ("updates", {"agent": {"messages": [ai]}})
            payload = self.tool_payloads[i % len(self.tool_payloads)]
            tm = type("M", (), {"content": payload, "name": name})()
            yield ("updates", {"tools": {"messages": [tm]}})
            # 真实运行时桥接器还会为 run_sql 产出 result 事件(带 rows),
            # 接地对账靠它——假 Agent 必须复现,否则测试测不到真实路径
            try:
                rows = json.loads(payload).get("rows")
            except Exception:
                rows = None
            if rows is not None:
                yield ("updates", {"tools": {"messages": [
                    type("M", (), {"content": payload, "name": name})()
                ]}})

@pytest.mark.asyncio
async def test_grounding_uses_result_rows_not_tool_summary(patched, monkeypatch):
    """接地必须用 result 事件的真实行数据,而不是 tool_result 摘要。

    实测:摘要只有「查询成功 · 5 行」,不含行数,拿它对账会把真实数字全判成
    幻觉(本轮 1537/146/140 被误判)。result.data 才有真实行。
    """
    monkeypatch.setattr(
        shadow, "build_harness_agent",
        lambda: _QualityAgent(
            tool_names=["run_sql"],
            tool_payloads=['{"success":true,"row_count":2,"rows":[{"tbl":"a","n":1250},{"tbl":"b","n":287}]}'],
            answer="a 表 1250 行,b 表 287 行,合计 1537 行。",
        ),
    )
    rec = await shadow.run_shadow_comparison(question="q", legacy_answer="a", legacy_metrics={})
    h = rec["harness"]
    assert h["grounded"] is True, f"误判为幻觉: {h['ungrounded']}"


@pytest.mark.asyncio
async def test_grounding_source_recorded(patched, monkeypatch):
    """记录里要能看出接地用了什么数据源(便于事后排查尺子失灵)。"""
    monkeypatch.setattr(
        shadow, "build_harness_agent",
        lambda: _QualityAgent(
            tool_names=["run_sql"],
            tool_payloads=['{"success":true,"rows":[{"n":5}]}'],
            answer="共 5 行。",
        ),
    )
    rec = await shadow.run_shadow_comparison(question="q", legacy_answer="a", legacy_metrics={})
    assert rec["harness"]["grounding_source"] == "result_rows"

# ── legacy 接地可信度:报告必须显式标注,不能只写在 docstring ──

def test_shadow_report_flags_legacy_grounding_reliability(patched):
    """报告里 legacy 接地字段旁必须带 grounding_reliability 显式标记。

    否则三个月后看报告里 legacy 全 False,第一反应会是"legacy 在幻觉",
    而不是"尺子有嵌套派生局限"。
    """
    shadow.COMPARISON_LOG.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in [
        {"harness": {"llm_rounds": 2, "used_todos": False, "sql_count": 1, "answer_len": 100,
                     "grounded": True, "dim_count": 3},
         "legacy": {"grounded": False, "dim_count": 5, "answer_len": 1200,
                    "ungrounded": [81.55]}},
    ]), encoding="utf-8")
    rep = shadow.shadow_report()
    assert rep["legacy_grounding_reliability"] == "degraded_nested_derivation"


def test_shadow_report_omits_flag_when_legacy_fully_grounded(patched):
    """legacy 全接地时不做降级标注(标记只在真有局限时出现)。"""
    shadow.COMPARISON_LOG.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in [
        {"harness": {"llm_rounds": 2, "grounded": True},
         "legacy": {"grounded": True, "answer_len": 100, "ungrounded": []}},
    ]), encoding="utf-8")
    rep = shadow.shadow_report()
    assert rep["legacy_grounding_reliability"] is None

# ── 人工判定对照文件(指标 3/4 的判定辅助,不是纯并排)────────────

def test_review_export_contains_question_answers_and_rows(patched):
    """导出必须含三段:原始提问 / 两臂答案 / 本轮工具行数据。

    指标 4 判定时不该让人去翻 jsonl 对数字;指标 3 需要原始提问全文对子问题。
    """
    shadow.COMPARISON_LOG.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in [
        {"question": "统计各表数据量并说明构成",
         "model": "qwen-flash",
         "harness": {"answer": "H 答案", "grounded": True, "dim_count": 3, "answer_len": 4,
                     "tool_rows": [{"table_name": "chat_nodes", "row_count": 147}],
                     "ctx_ok": True},
         "legacy": {"answer": "L 答案", "grounded": False, "dim_count": 5,
                    "answer_len": 4, "ungrounded": [81.55]}},
    ]), encoding="utf-8")

    out = shadow.build_review_document()
    assert "统计各表数据量并说明构成" in out          # 原始提问全文
    assert "H 答案" in out and "L 答案" in out       # 两臂答案
    assert "147" in out and "chat_nodes" in out     # 工具行数据
    assert "degraded_nested_derivation" in out      # legacy 接地可信度显式标注


def test_review_export_marks_incomplete_samples(patched):
    """样本缺失(legacy 空答案)要留「已排除」占位,与采集批次一一对应。"""
    shadow.COMPARISON_LOG.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in [
        {"question": "q1", "model": "qwen-flash",
         "harness": {"answer": "H", "grounded": True, "dim_count": 3, "answer_len": 1,
                     "tool_rows": [], "ctx_ok": True},
         "legacy": {"answer": "", "grounded": False, "dim_count": 0, "answer_len": 0,
                    "ungrounded": []}},
    ]), encoding="utf-8")

    out = shadow.build_review_document()
    assert "已排除" in out
    assert "legacy 侧未采到答案" in out


def test_review_export_every_jsonl_line_parsed(patched):
    """导出不许因单条坏记录整体失败(格式稳定性)。"""
    shadow.COMPARISON_LOG.write_text(
        '{"question": "ok", "model": "m", "harness": {"answer": "a", "answer_len": 1, "dim_count": 1}, "legacy": {"answer": "b", "answer_len": 1, "dim_count": 1}}\n'
        "not-json\n",
        encoding="utf-8",
    )
    out = shadow.build_review_document()
    assert "ok" in out