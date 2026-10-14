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
