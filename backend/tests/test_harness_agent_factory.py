"""Harness Agent 装配工厂测试(monkeypatch 掉真实模型创建,只验装配参数)。"""
import pytest

from app.harness import agent_factory


def _fake_create(**kwargs):
    """记录 create_deep_agent 收到的参数;返回带计数的假 Agent。"""
    _fake_create.captured = kwargs
    _fake_create.calls = getattr(_fake_create, "calls", 0) + 1
    return f"agent-{_fake_create.calls}"


@pytest.fixture
def capture_create(monkeypatch):
    _fake_create.calls = 0
    _fake_create.captured = {}
    monkeypatch.setattr(agent_factory, "_create", _fake_create)
    agent_factory.reset_agent()
    yield _fake_create
    agent_factory.reset_agent()


def test_build_passes_data_tools(capture_create):
    agent_factory.build_harness_agent()
    names = [getattr(t, "__name__", "") for t in capture_create.captured["tools"]]
    assert names == ["get_table_schema", "run_sql", "search_knowledge", "make_chart", "web_search_tool"]


def test_build_passes_checkpointer(capture_create):
    """HITL Command(resume) 依赖 checkpointer;装配必须传入(非 None)。"""
    agent_factory.build_harness_agent()
    assert capture_create.captured.get("checkpointer") is not None


def test_build_includes_sql_gate_middleware(capture_create):
    from app.harness.sql_gate_middleware import SqlGateMiddleware

    agent_factory.build_harness_agent()
    mws = capture_create.captured["middleware"]
    assert any(isinstance(m, SqlGateMiddleware) for m in mws)


def test_build_has_system_prompt(capture_create):
    agent_factory.build_harness_agent()
    prompt = capture_create.captured.get("system_prompt") or ""
    assert "run_sql" in prompt
    assert "get_table_schema" in prompt


def test_build_no_subagents_in_phase1(capture_create):
    """Phase 1 不挂子 Agent(report/doc 智能化在 Phase 3)。"""
    agent_factory.build_harness_agent()
    assert capture_create.captured.get("subagents") in (None, [])


def test_singleton(capture_create):
    a = agent_factory.build_harness_agent()
    b = agent_factory.build_harness_agent()
    assert a is b
    assert capture_create.calls == 1


def test_provider_change_rebuilds_agent(capture_create, monkeypatch):
    """管理台切换模型后,下次调用应重建 Agent(无需重启后端)。"""
    agent_factory.build_harness_agent()
    assert capture_create.calls == 1

    # 模拟 provider 变更(模型换了)
    monkeypatch.setattr(
        agent_factory, "_provider_fingerprint", lambda: "other|model-x|https://b|sk-a…"
    )
    rebuilt = agent_factory.build_harness_agent()
    assert capture_create.calls == 2
    assert rebuilt != f"agent-{capture_create.calls - 1}"
