"""事件溯源投影单测（纯函数，无 DB 依赖）。

覆盖 2026-10 前端优化新增的 THINKING/REASONING 投影，以及既有
TOOL_CHAIN/最终态投影的回归断言——历史会话恢复依赖这些投影类型。
"""
import json

from app.core.event_sourcing import EventType, _project
from app.models.session import SessionEvent


def _evt(etype: str, content: str = "", payload: dict | None = None) -> SessionEvent:
    evt = SessionEvent(
        thread_id="u1:t1",
        run_id="u1:r1",
        node_index=0,
        event_type=etype,
        role="system",
        content=content,
    )
    evt.payload = json.dumps(payload, ensure_ascii=False) if payload else None
    return evt


def test_thinking_projection():
    msg = _project(_evt(
        EventType.THINKING,
        content="正在生成SQL查询...",
        payload={"agent": "sql_coder", "phase": "generating"},
    ))
    assert msg == {
        "role": "system",
        "type": "thinking",
        "agent": "sql_coder",
        "phase": "generating",
        "content": "正在生成SQL查询...",
    }


def test_thinking_projection_without_payload():
    """无 payload 时 agent/phase 为空串，不抛错（旧数据兼容）。"""
    msg = _project(_evt(EventType.THINKING, content="分析用户意图..."))
    assert msg["type"] == "thinking"
    assert msg["agent"] == ""
    assert msg["phase"] == ""
    assert msg["content"] == "分析用户意图..."


def test_reasoning_projection():
    msg = _project(_evt(
        EventType.REASONING,
        content="先统计各表行数，再对比上周数据……",
    ))
    assert msg == {
        "role": "assistant",
        "type": "reasoning",
        "content": "先统计各表行数，再对比上周数据……",
        "collapsed": True,
    }


def test_tool_chain_projection_keeps_result_summary():
    msg = _project(_evt(
        EventType.TOOL_CHAIN,
        content="查询成功 · 12 行",
        payload={"name": "run_sql", "status": "done"},
    ))
    assert msg["type"] == "tool_chain"
    assert msg["toolName"] == "run_sql"
    assert msg["toolMeta"]["result"] == "查询成功 · 12 行"
    assert msg["collapsed"] is True


def test_final_state_projections_unchanged():
    """回归：既有最终态投影格式不能被思考事件改动破坏。"""
    assert _project(_evt(EventType.USER_MESSAGE, content="统计各表数据量")) == {
        "role": "user", "type": "text", "content": "统计各表数据量",
    }
    assert _project(_evt(EventType.SQL, content="SELECT 1")) == {
        "role": "assistant", "type": "sql", "sql": "SELECT 1",
    }
    assert _project(_evt(EventType.ANALYSIS, content="共 12 张表")) == {
        "role": "assistant", "type": "text", "content": "共 12 张表",
    }
    chart = _project(_evt(EventType.CHART, payload={"config": {"series": []}}))
    assert chart["type"] == "chart"
    assert chart["chartConfig"] == {"series": []}


def test_process_events_not_projected():
    """回归：plan/clarification/turn_* 等过程态事件仍不投影。"""
    assert _project(_evt(EventType.PLAN, payload={"steps": ["a"]})) is None
    assert _project(_evt(EventType.CLARIFICATION, content="请澄清")) is None
    assert _project(_evt(EventType.TURN_START)) is None
    assert _project(_evt(EventType.TURN_END)) is None
