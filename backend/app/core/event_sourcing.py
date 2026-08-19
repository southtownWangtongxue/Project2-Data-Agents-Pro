"""
Event Sourcing —— 会话事件溯源 + surface 投影（Phase 1）

借鉴 DeepSeek Harness 的 Session 事件溯源设计，在现有 FastAPI + LangGraph
架构上落地 append-only 事件日志与投影机制：

- SessionEvent 是会话的唯一事实来源（append-only，不可变）
- 用户可见消息由 derive_messages()「投影（surface）」派生，而非单独存储
- 事件类型化，为后续审计 / 重放 / Fork 提供统一底座

与 dsh 的对应关系（见 docs/reference/deepseek-harness-integration-analysis.md）：
  - append-only SessionEvent ≈ session_events 表
  - surface 投影（user/message、assistant/message、tool/result）≈ SURFACE_EVENT_TYPES
  - deriveMessages() ≈ derive_messages()
  - Fork API ≈ fork()
"""
import json
import logging

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import _get_session_factory
from app.models.session import SessionEvent
from app.utils.json_encoder import CustomEncoder

logger = logging.getLogger(__name__)

# 历史会话投影时查询结果最多保留的行数（与现有 get_session_messages 保持一致）
MAX_RESULT_ROWS = 50


class EventType:
    """会话事件类型（类型化事件，借鉴 dsh 的 SessionEvent）。

    分为两类：
    - 最终态业务事件（可投影为可见消息）：user_message/sql/result/analysis/chart/error
    - 过程态事件（默认不投影，供审计/重放；tool_chain 现已投影为工具卡片）：
      plan/clarification/tool_chain
    """

    USER_MESSAGE = "user_message"
    SQL = "sql"
    RESULT = "result"
    ANALYSIS = "analysis"
    CHART = "chart"
    ERROR = "error"
    PLAN = "plan"
    CLARIFICATION = "clarification"
    TOOL_CHAIN = "tool_chain"


# 可投影为可见消息的事件类型（对应 dsh 的 surface 投影——仅最终态三类可见，
# 其余 agent/*、turn/*、chunk 等过程事件不投影）
SURFACE_EVENT_TYPES = {
    EventType.USER_MESSAGE,
    EventType.SQL,
    EventType.RESULT,
    EventType.ANALYSIS,
    EventType.CHART,
    EventType.ERROR,
}


def event_sourcing_enabled() -> bool:
    """读取 feature flag：是否启用事件溯源（默认关闭，保持旧行为）。"""
    return get_settings().EVENT_SOURCING_ENABLED


def _safe_json_dumps(obj) -> str | None:
    """序列化 payload，容忍 datetime/Decimal/未知类型（回退为字符串）。"""
    if obj is None:
        return None
    try:
        return json.dumps(obj, ensure_ascii=False, cls=CustomEncoder)
    except (TypeError, ValueError):
        try:
            return json.dumps(obj, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return None


def _safe_json_loads(payload_json: str | None):
    """反序列化 payload，失败返回 None。"""
    if not payload_json:
        return None
    try:
        return json.loads(payload_json)
    except (json.JSONDecodeError, TypeError):
        return None


class SessionEventStore:
    """会话事件日志存储 + 投影。

    提供 append（追加事件）、list_events（按序查询）、
    derive_messages（投影为前端消息格式）、fork（从事件点分支）。
    """

    @staticmethod
    async def append(
        thread_id: str,
        event_type: str,
        run_id: str = "",
        node_index: int | None = None,
        role: str | None = None,
        content: str = "",
        payload: dict | None = None,
    ) -> int | None:
        """追加一条事件。返回事件 id，失败返回 None（不阻断主流程）。"""
        if not thread_id or not event_type:
            return None
        factory = _get_session_factory()
        payload_json = _safe_json_dumps(payload)
        try:
            async with factory() as session:
                evt = SessionEvent(
                    thread_id=thread_id,
                    run_id=run_id or "",
                    node_index=node_index,
                    event_type=event_type,
                    role=role,
                    content=content or "",
                    payload=payload_json,
                )
                session.add(evt)
                await session.commit()
                await session.refresh(evt)
                return evt.id
        except Exception as exc:
            logger.warning(
                "[event-sourcing] 追加事件失败: %s (thread=%s, type=%s)",
                exc, thread_id, event_type,
            )
            return None

    @staticmethod
    async def list_events(thread_id: str) -> list[SessionEvent]:
        """按 id 升序返回会话的全部事件（id 单调递增即事件顺序）。"""
        factory = _get_session_factory()
        try:
            async with factory() as session:
                result = await session.execute(
                    select(SessionEvent)
                    .where(SessionEvent.thread_id == thread_id)
                    .order_by(SessionEvent.id)
                )
                return list(result.scalars().all())
        except Exception as exc:
            logger.warning("[event-sourcing] 查询事件失败: %s", exc)
            return []

    @staticmethod
    async def derive_messages(thread_id: str) -> list[dict]:
        """surface 投影：从事件日志派生用户可见消息列表。

        返回格式与现有 get_session_messages 的 messages 一致，
        使前端 loadSession 无感复用。
        """
        events = await SessionEventStore.list_events(thread_id)
        messages: list[dict] = []
        for evt in events:
            msg = _project(evt)
            if msg is not None:
                messages.append(msg)
        return messages

    @staticmethod
    async def fork(
        source_thread_id: str,
        new_thread_id: str,
        before_event_id: int,
    ) -> int:
        """Fork：将源会话在 before_event_id 之前的事件复制到新会话。

        这是事件溯源的直接红利——关系表模型难以等价实现。
        """
        factory = _get_session_factory()
        try:
            async with factory() as session:
                result = await session.execute(
                    select(SessionEvent)
                    .where(
                        SessionEvent.thread_id == source_thread_id,
                        SessionEvent.id < before_event_id,
                    )
                    .order_by(SessionEvent.id)
                )
                src_events = result.scalars().all()
                for evt in src_events:
                    session.add(
                        SessionEvent(
                            thread_id=new_thread_id,
                            run_id=evt.run_id,
                            node_index=evt.node_index,
                            event_type=evt.event_type,
                            role=evt.role,
                            content=evt.content,
                            payload=evt.payload,
                        )
                    )
                await session.commit()
                return len(src_events)
        except Exception as exc:
            logger.warning("[event-sourcing] fork 失败: %s", exc)
            return 0


def _project(evt: SessionEvent) -> dict | None:
    """将单条事件投影为前端消息格式。非投影类型返回 None。"""
    payload = _safe_json_loads(evt.payload)
    etype = evt.event_type

    if etype == EventType.USER_MESSAGE:
        return {"role": "user", "type": "text", "content": evt.content or ""}

    if etype == EventType.SQL:
        return {"role": "assistant", "type": "sql", "sql": evt.content or ""}

    if etype == EventType.RESULT:
        data = payload.get("data", []) if payload else []
        columns = payload.get("columns", []) if payload else []
        total_rows = len(data)
        return {
            "role": "assistant",
            "type": "result",
            "data": data,
            "columns": columns,
            "content": f"{total_rows} 条记录",
        }

    if etype == EventType.ANALYSIS:
        return {"role": "assistant", "type": "text", "content": evt.content or ""}

    if etype == EventType.CHART:
        config = payload.get("config", {}) if payload else {}
        return {"role": "assistant", "type": "chart", "chartConfig": config}

    if etype == EventType.ERROR:
        return {"role": "assistant", "type": "error", "content": evt.content or ""}

    if etype == EventType.TOOL_CHAIN:
        # 工具调用链过程态事件投影为工具卡片，保证切换会话后工具输出可见
        name = ""
        result = evt.content or ""
        if payload:
            name = payload.get("name", "") or payload.get("tool_name", "") or ""
            # 优先取 payload 中的结构化结果（status/content/result）
            result = payload.get("result") or payload.get("content") or result
        tool_meta: dict = {}
        if result:
            tool_meta["result"] = str(result)[:500]
        return {
            "role": "system",
            "type": "tool_chain",
            "toolName": name or "tool",
            "toolMeta": tool_meta if tool_meta else None,
            "collapsed": True,
        }

    # 其余过程态事件（plan/clarification）不投影为可见消息
    return None
