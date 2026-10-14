"""SQL 安全闸中间件测试(Harness 安全第 2 层)。

用最小 LangGraph 图(节点内调用中间件)验证真实 interrupt 语义:
ask → ainvoke 返回 __interrupt__ → Command(resume) 恢复。
不 mock interrupt 本身,确保挂起/恢复链路是真实的。
"""
import pytest
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command

from app.harness.sql_gate_middleware import SqlGateMiddleware, apply_approval


def _request(sql: str, tool: str = "run_sql") -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": tool, "args": {"sql": sql, "purpose": "测试"}, "id": "call_1"},
        tool=None,
        state={},
        runtime=None,
    )


async def _ok_handler(request):
    """模拟工具执行:回显最终 SQL(用于验证 edit 决策是否替换了参数)。"""
    return ToolMessage(
        content=f"executed:{request.tool_call['args']['sql']}",
        tool_call_id=request.tool_call["id"],
        name=request.tool_call["name"],
    )


def _build_graph(monkeypatch, classify_result=None, classify_exc=None, tier="read_only"):
    """构造 节点→中间件→handler 的最小图;分类与档位均可注入。"""
    mw = SqlGateMiddleware()
    if classify_exc is not None:

        async def fake_classify(sql):
            raise classify_exc
    else:

        async def fake_classify(sql):
            return classify_result

    monkeypatch.setattr("app.harness.sql_gate_middleware.classify_sql", fake_classify)
    monkeypatch.setattr("app.harness.sql_gate_middleware.get_tier", lambda: tier)

    async def gate_node(state):
        result = await mw.awrap_tool_call(_request(state["sql"]), _ok_handler)
        return {"result": result.content}

    builder = StateGraph(dict)
    builder.add_node("gate", gate_node)
    builder.set_entry_point("gate")
    builder.add_edge("gate", END)
    return builder.compile(checkpointer=InMemorySaver())


# ── allow 路径 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_safe_sql_passes_through(monkeypatch):
    graph = _build_graph(monkeypatch, classify_result={"category": "safe"}, tier="read_only")
    out = await graph.ainvoke({"sql": "SELECT 1"}, {"configurable": {"thread_id": "t_allow"}})
    assert out["result"] == "executed:SELECT 1"
    assert "__interrupt__" not in out


@pytest.mark.asyncio
async def test_dangerous_dml_auto_allow_under_workspace_write(monkeypatch):
    graph = _build_graph(
        monkeypatch,
        classify_result={"category": "dangerous", "risk_level": "dml"},
        tier="workspace_write",
    )
    out = await graph.ainvoke({"sql": "DELETE FROM t"}, {"configurable": {"thread_id": "t_ws"}})
    assert out["result"] == "executed:DELETE FROM t"
    assert "__interrupt__" not in out


# ── ask 路径:挂起 → approve / edit / reject ──────────────────

@pytest.mark.asyncio
async def test_dangerous_asks_then_approve(monkeypatch):
    graph = _build_graph(
        monkeypatch,
        classify_result={"category": "dangerous", "risk_level": "ddl"},
        tier="read_only",
    )
    config = {"configurable": {"thread_id": "t_ask"}}
    out = await graph.ainvoke({"sql": "DROP TABLE t"}, config)
    assert "__interrupt__" in out
    payload = out["__interrupt__"][0].value
    assert payload["type"] == "approval_required"
    assert payload["sql"] == "DROP TABLE t"
    assert payload["purpose"] == "测试"
    assert "reason" in payload

    resumed = await graph.ainvoke(Command(resume={"approved": True}), config)
    assert resumed["result"] == "executed:DROP TABLE t"


@pytest.mark.asyncio
async def test_dangerous_asks_then_malformed_resume_denies(monkeypatch):
    """畸形 resume 值(非 dict,如 Command(resume=True))→ 优雅拒绝,不抛异常。"""
    graph = _build_graph(
        monkeypatch,
        classify_result={"category": "dangerous", "risk_level": "dml"},
        tier="read_only",
    )
    config = {"configurable": {"thread_id": "t_malformed"}}
    out = await graph.ainvoke({"sql": "DELETE FROM t"}, config)
    assert "__interrupt__" in out

    resumed = await graph.ainvoke(Command(resume=True), config)
    assert "executed:" not in resumed["result"]
    assert "审批被驳回" in resumed["result"]


@pytest.mark.asyncio
async def test_dangerous_asks_then_edit_sql(monkeypatch):
    """edit 决策:审批人修改 SQL 后放行,handler 收到的是修改后的 SQL。"""
    graph = _build_graph(
        monkeypatch,
        classify_result={"category": "dangerous", "risk_level": "dml"},
        tier="read_only",
    )
    config = {"configurable": {"thread_id": "t_edit"}}
    out = await graph.ainvoke({"sql": "DELETE FROM t"}, config)
    assert "__interrupt__" in out

    resumed = await graph.ainvoke(
        Command(resume={"approved": False, "edited_sql": "DELETE FROM t WHERE id = 1"}), config
    )
    assert resumed["result"] == "executed:DELETE FROM t WHERE id = 1"


@pytest.mark.asyncio
async def test_dangerous_asks_then_reject(monkeypatch):
    """reject 决策:返回拒绝 ToolMessage,handler 未执行。"""
    graph = _build_graph(
        monkeypatch,
        classify_result={"category": "dangerous", "risk_level": "admin"},
        tier="read_only",
    )
    config = {"configurable": {"thread_id": "t_reject"}}
    out = await graph.ainvoke({"sql": "GRANT ALL ON t"}, config)
    assert "__interrupt__" in out

    resumed = await graph.ainvoke(
        Command(resume={"approved": False, "comment": "权限不足"}), config
    )
    assert "executed:" not in resumed["result"]
    assert "审批被驳回" in resumed["result"]
    assert "权限不足" in resumed["result"]


# ── deny 路径 ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_classify_exception_denies(monkeypatch):
    """分类异常 → deny-by-default,handler 不执行。"""
    graph = _build_graph(monkeypatch, classify_exc=RuntimeError("boom"), tier="read_only")
    out = await graph.ainvoke({"sql": "SELECT 1"}, {"configurable": {"thread_id": "t_deny"}})
    assert "executed:" not in out["result"]
    assert "拒绝" in out["result"]


@pytest.mark.asyncio
async def test_unclassifiable_result_denies(monkeypatch):
    """分类返回非法形态(None)→ deny。"""
    graph = _build_graph(monkeypatch, classify_result=None, tier="read_only")
    out = await graph.ainvoke({"sql": "SELECT 1"}, {"configurable": {"thread_id": "t_deny2"}})
    assert "executed:" not in out["result"]
    assert "拒绝" in out["result"]


# ── 非 run_sql 工具直通(不触发分类)──────────────────────────

@pytest.mark.asyncio
async def test_other_tool_not_gated(monkeypatch):
    called = {"classify": False}

    async def fake_classify(sql):
        called["classify"] = True
        return {"category": "safe"}

    monkeypatch.setattr("app.harness.sql_gate_middleware.classify_sql", fake_classify)

    mw = SqlGateMiddleware()
    req = ToolCallRequest(
        tool_call={"name": "get_table_schema", "args": {"keywords": "x"}, "id": "c2"},
        tool=None, state={}, runtime=None,
    )

    async def handler(request):
        return ToolMessage(content="schema-ok", tool_call_id="c2", name="get_table_schema")

    result = await mw.awrap_tool_call(req, handler)
    assert result.content == "schema-ok"
    assert called["classify"] is False


# ── apply_approval 纯函数 ──────────────────────────────────

def test_apply_approval_approve():
    action, args, reason = apply_approval({"sql": "DROP TABLE t"}, {"approved": True})
    assert action == "execute"
    assert args["sql"] == "DROP TABLE t"
    assert reason == ""


def test_apply_approval_edit_replaces_sql():
    action, args, reason = apply_approval(
        {"sql": "DELETE FROM t"}, {"approved": False, "edited_sql": "DELETE FROM t WHERE id=1"}
    )
    assert action == "execute"
    assert args["sql"] == "DELETE FROM t WHERE id=1"


def test_apply_approval_reject_with_comment():
    action, _, reason = apply_approval(
        {"sql": "DROP TABLE t"}, {"approved": False, "comment": "太危险"}
    )
    assert action == "deny"
    assert "太危险" in reason


def test_apply_approval_reject_without_comment():
    action, _, reason = apply_approval({"sql": "x"}, {"approved": False})
    assert action == "deny"
    assert "无备注" in reason
