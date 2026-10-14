"""Harness SSE 桥接器测试:合成 agent 事件序列 → 期望的 SSE 事件。

桥接器是纯翻译层:输入 astream 的 (mode, data) 事件,输出 SSE dict 列表。
不建真实 Agent,全部用合成事件。
"""
from app.harness.sse_bridge import HarnessEventBridge


def _msg(content="", tool_calls=None, name="", reasoning=""):
    """最小 AIMessage/ToolMessage 替身(桥接器只用属性读取)。"""
    m = type("M", (), {})()
    m.content = content
    m.tool_calls = tool_calls
    m.name = name
    m.reasoning_content = reasoning
    m.additional_kwargs = {}
    return m


def _updates(**nodes):
    return ("updates", nodes)


def _messages(chunk, node="agent"):
    return ("messages", (chunk, {"langgraph_node": node}))


def test_todo_update_emits_plan_with_todos():
    bridge = HarnessEventBridge()
    events = list(bridge.feed(_updates(agent={"todos": [
        {"id": "1", "title": "查各表数据量", "status": "in_progress"},
        {"id": "2", "title": "生成图表", "status": "pending"},
    ]})))
    plans = [e for e in events if e["type"] == "plan"]
    assert len(plans) == 1
    assert plans[0]["steps"] == ["查各表数据量", "生成图表"]
    assert plans[0]["todos"][0]["status"] == "in_progress"
    # in_progress 的 todo 成为当前步骤,后续工具事件挂它
    assert bridge.current_step_id == 1


def test_tool_call_attaches_to_current_step():
    """工具调用来自 updates.agent 的完整 tool_calls,挂当前 in_progress 步骤。"""
    bridge = HarnessEventBridge()
    list(bridge.feed(_updates(agent={"todos": [{"id": "1", "title": "t", "status": "in_progress"}]})))
    ai_msg = _msg(tool_calls=[{"name": "run_sql", "args": {"sql": "SELECT 1"}, "id": "c1"}])
    events = list(bridge.feed(_updates(agent={"messages": [ai_msg]})))
    calls = [e for e in events if e["type"] == "tool_call"]
    assert len(calls) == 1
    assert calls[0]["name"] == "run_sql"
    assert calls[0]["step_id"] == 1
    assert "SELECT 1" in calls[0]["args"]


def test_tool_call_emitted_once_across_modes():
    """同一调用 id 在 messages(增量)/updates(完整)两条路径只发一次卡。"""
    bridge = HarnessEventBridge()
    list(bridge.feed(_updates(agent={"todos": [{"id": "1", "title": "t", "status": "in_progress"}]})))
    # messages 模式的流式 chunk(首 chunk args 为空)——不应产生 tool_call 事件
    chunk = _msg(tool_calls=None)
    chunk.tool_call_chunks = [{"name": "run_sql", "args": "", "id": "c1"}]
    events = list(bridge.feed(_messages(chunk)))
    assert [e for e in events if e["type"] == "tool_call"] == []
    # updates.agent 的完整 calls——发一次
    ai_msg = _msg(tool_calls=[{"name": "run_sql", "args": {"sql": "SELECT 1"}, "id": "c1"}])
    events = list(bridge.feed(_updates(agent={"messages": [ai_msg]})))
    assert len([e for e in events if e["type"] == "tool_call"]) == 1


def test_run_sql_result_emits_rich_events():
    """run_sql 的 JSON 载荷 → sql + result 富事件 + 紧凑 tool_result。"""
    bridge = HarnessEventBridge()
    payload = (
        '{"success": true, "sql": "SELECT 1", "row_count": 2, "returned_rows": 2,'
        ' "columns": ["a"], "rows": [{"a": 1}, {"a": 2}], "duration_ms": 12, "error": null}'
    )
    tm = _msg(content=payload, name="run_sql")
    events = list(bridge.feed(_updates(tools={"messages": [tm]})))
    types = [e["type"] for e in events]
    assert "sql" in types
    assert "result" in types
    sql_ev = next(e for e in events if e["type"] == "sql")
    assert sql_ev["sql"] == "SELECT 1"
    result_ev = next(e for e in events if e["type"] == "result")
    assert result_ev["columns"] == ["a"]
    assert result_ev["data"] == [{"a": 1}, {"a": 2}]
    tool_ev = next(e for e in events if e["type"] == "tool_result")
    assert tool_ev["name"] == "run_sql"
    assert tool_ev["status"] == "done"
    assert "2 行" in tool_ev["content"]


def test_make_chart_result_emits_chart_event():
    bridge = HarnessEventBridge()
    payload = '{"chart_type": "bar", "chart_title": "T", "echarts_config": {"xAxis": {}}}'
    tm = _msg(content=payload, name="make_chart")
    events = list(bridge.feed(_updates(tools={"messages": [tm]})))
    charts = [e for e in events if e["type"] == "chart"]
    assert len(charts) == 1
    assert charts[0]["config"] == {"xAxis": {}}


def test_run_sql_failure_result_has_no_rich_events():
    bridge = HarnessEventBridge()
    payload = '{"success": false, "error": "Unknown column"}'
    tm = _msg(content=payload, name="run_sql")
    events = list(bridge.feed(_updates(tools={"messages": [tm]})))
    assert [e["type"] for e in events] == ["tool_result"]
    assert "Unknown column" in events[0]["content"]


def test_plain_text_token_and_reasoning():
    bridge = HarnessEventBridge()
    chunk = _msg(content="结论", reasoning="想一想")
    events = list(bridge.feed(_messages(chunk)))
    assert any(e["type"] == "token" and e["content"] == "结论" for e in events)
    assert any(e["type"] == "reasoning" and e["content"] == "想一想" for e in events)


def test_plain_tool_result_truncated():
    bridge = HarnessEventBridge()
    tm = _msg(content="x" * 2000, name="get_table_schema")
    events = list(bridge.feed(_updates(tools={"messages": [tm]})))
    tool_ev = events[-1]
    assert tool_ev["type"] == "tool_result"
    assert len(tool_ev["content"]) <= 800


def test_interrupt_event_yields_approval_signal():
    """updates 里的 __interrupt__ → 审批信号(chat.py 负责等待-恢复)。"""
    bridge = HarnessEventBridge()
    interrupt_obj = type("I", (), {})()
    interrupt_obj.value = {"type": "approval_required", "sql": "DROP TABLE t", "reason": "高危"}
    events = list(bridge.feed(_updates(__interrupt__=[interrupt_obj])))
    assert len(events) == 1
    assert events[0]["type"] == "approval_required"
    assert events[0]["sql"] == "DROP TABLE t"
    assert bridge.pending_approval is True


def test_other_node_events_ignored():
    bridge = HarnessEventBridge()
    events = list(bridge.feed(_updates(__start__={"messages": []})))
    assert events == []
