"""影子双跑比对测试:legacy 与 harness 双跑,产出比对记录;影子失败不影响主流程。"""
import json

import pytest

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
