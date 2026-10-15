"""Harness SSE 生成器测试:假 Agent + 假 hitl,验证审批挂起-恢复续流。"""
import json

import pytest

from app.harness import stream_harness


class _FakeAgent:
    """按脚本产出 astream 事件的假 Agent(第一次到中断,第二次恢复后续)。"""

    def __init__(self, script):
        self.script = dict(script)
        self.calls = 0

    async def astream(self, input_data, config, stream_mode=None):
        self.calls += 1
        phase = "first" if self.calls == 1 else "resume"
        for ev in self.script.get(phase, []):
            yield ev


def _interrupt_evt(sql="DELETE FROM t"):
    obj = type("I", (), {})()
    obj.value = {"type": "approval_required", "sql": sql, "reason": "高危", "purpose": "清理"}
    return ("updates", {"__interrupt__": [obj]})


def _text_msg(text):
    m = type("M", (), {})()
    m.content = text
    m.tool_calls = None
    m.tool_call_chunks = None
    m.additional_kwargs = {}
    m.reasoning_content = ""
    return m


_FAKE_AGENT: list = []
_DECISION: list = []


async def _fake_wait_for(thread_id, timeout=300):
    return _DECISION[0] if _DECISION else None


async def _noop_async(*a, **kw):
    return None


async def _fake_title(question, text, provider=None):
    return "测试标题"


class _FakeHitl:
    wait_for = staticmethod(_fake_wait_for)

    @staticmethod
    def cancel(thread_id):
        return None


@pytest.fixture
def patched(monkeypatch):
    """替换 Agent 构建 / hitl / 标题生成 / 会话落库,隔离外部依赖。"""
    monkeypatch.setattr(stream_harness, "build_harness_agent", lambda: _FAKE_AGENT[0])
    monkeypatch.setattr(stream_harness, "hitl", _FakeHitl)
    monkeypatch.setattr(stream_harness, "_save_chat_node", _noop_async)
    monkeypatch.setattr(stream_harness, "_upsert_chat_session", _noop_async)
    monkeypatch.setattr(stream_harness, "_count_nodes", _noop_async)
    monkeypatch.setattr(stream_harness, "_get_session_goal", _noop_async)
    monkeypatch.setattr(stream_harness, "generate_node_title", _fake_title)
    yield


async def _collect(gen) -> list[dict]:
    out = []
    async for chunk in gen:
        out.append(json.loads(chunk.removeprefix("data: ").strip()))
    return out


@pytest.mark.asyncio
async def test_full_flow_with_approval(patched):
    """文本流 → 审批挂起(approval_required)→ 决策到达 → 恢复续流 → done/title。"""
    _FAKE_AGENT[:] = [_FakeAgent({
        "first": [
            ("messages", (_text_msg("我先分析"), {"langgraph_node": "agent"})),
            _interrupt_evt(),
        ],
        "resume": [
            ("messages", (_text_msg("已完成"), {"langgraph_node": "agent"})),
            ("updates", {"__end__": {}}),
        ],
    })]
    _DECISION[:] = [{"approved": True, "comment": "ok"}]

    events = await _collect(stream_harness.stream_chat_harness(
        question="清理数据", user_name="admin", existing_thread_id="t1",
    ))
    types = [e["type"] for e in events]
    assert "thread_id" in types
    assert "approval_required" in types
    assert "done" in types
    assert "title" in types
    # done 必须先于 title(已修复语义)
    assert types.index("done") < types.index("title")
    # 恢复后的正文也到达前端
    tokens = "".join(e.get("content", "") for e in events if e["type"] == "token")
    assert "我先分析" in tokens and "已完成" in tokens


@pytest.mark.asyncio
async def test_approval_timeout_auto_reject(patched):
    """审批超时(wait_for 返回 None)→ 自动拒绝 → 状态提示 + 正常收尾。"""
    _FAKE_AGENT[:] = [_FakeAgent({
        "first": [_interrupt_evt()],
        "resume": [("updates", {"__end__": {}})],
    })]
    _DECISION[:] = []  # wait_for 返回 None

    events = await _collect(stream_harness.stream_chat_harness(
        question="x", user_name="admin", existing_thread_id="t1",
    ))
    statuses = [e.get("content", "") for e in events if e["type"] == "status"]
    assert any("自动拒绝" in s for s in statuses)
    assert any(e["type"] == "done" for e in events)


@pytest.mark.asyncio
async def test_simple_flow_no_approval(patched):
    """无审批的简单流:token → done → title。"""
    _FAKE_AGENT[:] = [_FakeAgent({
        "first": [
            ("messages", (_text_msg("你好"), {"langgraph_node": "agent"})),
            ("updates", {"__end__": {}}),
        ],
        "resume": [],
    })]
    events = await _collect(stream_harness.stream_chat_harness(
        question="你好", user_name="admin", existing_thread_id="t1",
    ))
    types = [e["type"] for e in events]
    assert "approval_required" not in types
    assert types[-2] == "done" and types[-1] == "title"


@pytest.mark.asyncio
async def test_resolves_request_model_provider(patched, monkeypatch):
    """必须按请求指定的模型锁定 provider(与 legacy 的 set_provider 一致)。

    否则 Harness 会沿用启动时的 provider:管理台切模型后请求仍打到旧模型,
    且指纹缓存也不会失效。
    """
    seen = {}

    def fake_set_provider(cfg):
        seen["cfg"] = cfg

    class _Mgr:
        @staticmethod
        def get_llm_config(model):
            seen["model_arg"] = model
            return {"id": "qwen-flash", "model": "qwen3.7-flash"}

    monkeypatch.setattr(stream_harness, "set_provider", fake_set_provider)
    monkeypatch.setattr(stream_harness, "get_config_manager", lambda: _Mgr())
    _FAKE_AGENT[:] = [_FakeAgent({
        "first": [("messages", (_text_msg("ok"), {"langgraph_node": "agent"})),
                  ("updates", {"__end__": {}})],
        "resume": [],
    })]

    await _collect(stream_harness.stream_chat_harness(
        question="你好", user_name="admin", existing_thread_id="t1", model="qwen-flash",
    ))
    assert seen["model_arg"] == "qwen-flash"
    assert seen["cfg"] == {"id": "qwen-flash", "model": "qwen3.7-flash"}


class _FlakyAgent:
    """前 fail_times 次抛瞬时错误(403 FreeTierOnly),之后正常产出。"""

    def __init__(self, fail_times=1, fail_msg=None):
        self.fail_times = fail_times
        self.calls = 0
        self.fail_msg = fail_msg or (
            "Error code: 403 - {'error': {'code': 'AllocationQuota.FreeTierOnly',"
            " 'message': 'Free quota exhausted... disable the use free tier only mode'}}"
        )

    async def astream(self, input_data, config, stream_mode=None):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise Exception(self.fail_msg)
        m = _text_msg("恢复成功")
        yield ("messages", (m, {"langgraph_node": "agent"}))
        yield ("updates", {"__end__": {}})


@pytest.mark.asyncio
async def test_transient_llm_error_retries_and_recovers(patched, monkeypatch):
    """OpenRouter 免费档间歇性 403 → 自动重试并成功,用户无需重发。"""
    agent = _FlakyAgent(fail_times=1)
    _FAKE_AGENT[:] = [agent]
    monkeypatch.setattr("app.core.llm_retry.next_retry_delay", lambda attempt: 0)

    events = await _collect(stream_harness.stream_chat_harness(
        question="你好", user_name="admin", existing_thread_id="t1",
    ))
    types = [e["type"] for e in events]
    assert "error" not in types, f"不应向用户暴露瞬时错误: {[e for e in events if e['type']=='error']}"
    tokens = "".join(e.get("content", "") for e in events if e["type"] == "token")
    assert "恢复成功" in tokens
    assert agent.calls >= 2


@pytest.mark.asyncio
async def test_permanent_llm_error_not_retried(patched):
    """鉴权类永久错误不重试,直接以 error 事件收尾(不放大真实缺陷)。"""
    agent = _FlakyAgent(fail_times=99, fail_msg="Error code: 401 - invalid api key")
    _FAKE_AGENT[:] = [agent]

    events = await _collect(stream_harness.stream_chat_harness(
        question="你好", user_name="admin", existing_thread_id="t1",
    ))
    assert any(e["type"] == "error" for e in events)
    assert agent.calls == 1, "永久错误不应重试"


@pytest.mark.asyncio
async def test_retry_exhausted_reports_error(patched, monkeypatch):
    """瞬时错误连续超过重试上限 → 明确报错,不无限重试。"""
    agent = _FlakyAgent(fail_times=99)
    _FAKE_AGENT[:] = [agent]
    monkeypatch.setattr("app.core.llm_retry.next_retry_delay", lambda attempt: 0)

    events = await _collect(stream_harness.stream_chat_harness(
        question="你好", user_name="admin", existing_thread_id="t1",
    ))
    assert any(e["type"] == "error" for e in events)
    assert agent.calls <= 5, f"重试次数应受限,实际 {agent.calls}"
