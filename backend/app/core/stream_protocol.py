"""
Stream Protocol —— 类型化 SSE 流式事件协议（Phase 4）

借鉴 DeepSeek Harness 的 StreamChunk 类型化流式设计：
- reasoning（思考）与 text（正文）在协议层类型隔离
- 思考内容用独立的 reasoning 事件推送，前端可折叠展示，正文永远干净

本项目 SSE 事件类型集中定义于此，避免散落字符串。
新增类型只增不删，保证向后兼容（旧前端忽略未知类型）。
"""
from __future__ import annotations


class SSEEventType:
    """SSE 事件类型常量。

    对齐 frontend/src/composables/useSSE.ts 的 dispatchEvent case 分支。
    reasoning 为 Phase 4 新增：模型思考内容增量，与正文 token 类型化隔离。
    """

    THREAD_ID = "thread_id"
    STATUS = "status"
    SCHEMA = "schema"
    THINKING = "thinking"
    REASONING = "reasoning"
    TOKEN = "token"
    TEXT = "text"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    SQL = "sql"
    RESULT = "result"
    CHART = "chart"
    ANALYSIS = "analysis"
    PLAN = "plan"
    CLARIFICATION = "clarification"
    ERROR = "error"
    TITLE = "title"
    DONE = "done"
    APPROVAL_REQUIRED = "approval_required"
    QUALITY_FEEDBACK = "quality_feedback"
    NODE_STARTED = "node_started"


def make_event(event_type: str, **fields) -> dict:
    """构造一个 SSE 事件 dict。"""
    return {"type": event_type, **fields}
