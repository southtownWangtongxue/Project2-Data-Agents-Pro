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


def test_system_prompt_has_union_aggregation_guidance():
    """多表统计必须用单条 UNION ALL 查询(实测 5 条 run_sql 往返浪费)。"""
    from app.harness.agent_factory import SYSTEM_PROMPT

    assert "UNION" in SYSTEM_PROMPT.upper()
    assert "单条" in SYSTEM_PROMPT


# ── Agent 缓存指纹:覆盖全部行为影响参数(Phase 2 实测教训)──────
# 背景:指纹原先只看 provider,导致「改了 SOP 提示词但进程里还是旧的」——
# baseline 采集白跑一轮(UNION 指引未生效却已采样)。指纹必须与构建同源:
# 装配用到的每个行为影响参数都进 spec,加参数只需加到 spec 里。

def test_sop_change_rebuilds_agent(capture_create, monkeypatch):
    """SOP 提示词变更 → 指纹变化 → Agent 重建(无需重启后端)。"""
    a1 = agent_factory.build_harness_agent()
    monkeypatch.setattr(agent_factory, "SYSTEM_PROMPT", "新的提示词:" + "x" * 80)
    a2 = agent_factory.build_harness_agent()
    assert a2 != a1
    assert capture_create.calls == 2


def test_no_spec_change_keeps_singleton(capture_create):
    """spec 未变时不得重建(否则单例缓存失去意义,每请求都重装配)。"""
    a1 = agent_factory.build_harness_agent()
    a2 = agent_factory.build_harness_agent()
    a3 = agent_factory.build_harness_agent()
    assert a1 is a2 is a3
    assert capture_create.calls == 1


def test_temperature_change_rebuilds_agent(capture_create, monkeypatch):
    """温度也是行为影响参数:改了必须重建(不能只哈希提示词字符串)。"""
    agent_factory.build_harness_agent()
    # 温度解析在 app.deepagent.harness 内(legacy DeepAgent 路径的实现),
    # spec 每次调用时从那里取,故 patch 源模块
    monkeypatch.setattr("app.deepagent.harness._resolve_temperature", lambda p=None: 0.9)
    agent_factory.build_harness_agent()
    assert capture_create.calls == 2


def test_spec_covers_prompt_provider_and_temperature(capture_create, monkeypatch):
    """spec 必须同时含提示词、provider、温度三要素(防下一个人漏加参数)。"""
    spec = agent_factory._agent_spec()
    assert "system_prompt" in spec
    assert "provider" in spec
    assert "temperature" in spec
    assert spec["tools"], "工具清单也属行为影响参数"
    assert spec["middleware"], "中间件清单也属行为影响参数"


def test_system_prompt_requires_dimension_breakdown_and_citation():
    """SOP 必须要求:结论先行 + 逐维度展开 + 标注数据来源查询。

    标注来源让接地检测从模糊匹配变成对账(模型自报数字→查询的映射)。
    """
    from app.harness.agent_factory import SYSTEM_PROMPT

    for kw in ("维度", "数据来源"):
        assert kw in SYSTEM_PROMPT, f"SOP 缺少结构要求: {kw}"