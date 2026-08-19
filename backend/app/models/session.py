"""
会话存储模型 —— chat_sessions + chat_nodes + session_events 表 ORM 映射

MySQL 存储会话元数据 + 节点标题 + 事件溯源日志，Redis 保留 LangGraph checkpoints 用于工作流状态恢复。
"""
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, func, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base


class ChatSession(Base):
    """会话元数据表"""
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True,
        comment="会话ID: {user_name}:{uuid}"
    )
    user_name: Mapped[str] = mapped_column(
        String(30), nullable=False, comment="归属用户"
    )
    title: Mapped[str] = mapped_column(
        String(200), nullable=False, default="",
        comment="LLM生成的会话标题"
    )
    goal: Mapped[str] = mapped_column(
        Text, nullable=True, comment="会话长期目标（阶段4 B6，注入 system prompt）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
        comment="更新时间"
    )


class ChatNode(Base):
    """节点标题表 —— 每轮问答一条记录"""
    __tablename__ = "chat_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="所属会话 thread_id"
    )
    node_index: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="第几轮问答（从0开始）"
    )
    title: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="LLM生成的节点标题"
    )
    question: Mapped[str] = mapped_column(
        Text, nullable=True, comment="用户提问原文（前200字）"
    )
    run_id: Mapped[str] = mapped_column(
        String(128), nullable=True, comment="LangGraph 运行 ID（用于 Redis checkpoint 恢复）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间"
    )


class SessionEvent(Base):
    """会话事件日志表 —— append-only 事件溯源（Phase 1）

    借鉴 DeepSeek Harness 的 Session 事件溯源设计：会话的唯一事实来源
    是类型化事件的追加日志，用户可见消息由事件「投影（surface）」派生，
    而非单独存储。

    与 dsh 的对应关系：
      - seq = 自增 id 的全局单调性（会话内按 id 排序即事件顺序）
      - surface 投影 = derive_messages()（仅投影最终态业务事件）
      - user/message、assistant/message、tool/result ≈ user_message/sql/result 等事件类型
    """
    __tablename__ = "session_events"
    __table_args__ = (
        Index("idx_session_events_thread_id", "thread_id"),
        Index("idx_session_events_run_id", "run_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="所属会话 thread_id"
    )
    run_id: Mapped[str] = mapped_column(
        String(128), nullable=True, comment="本轮运行 run_id（对应 chat_nodes.run_id）"
    )
    node_index: Mapped[int] = mapped_column(
        Integer, nullable=True, comment="第几轮问答（从0开始，与 chat_nodes.node_index 对齐）"
    )
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="事件类型：user_message/sql/result/analysis/chart/error/plan/clarification/tool_chain"
    )
    role: Mapped[str] = mapped_column(
        String(20), nullable=True, comment="角色：user/assistant/system"
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=True, comment="文本内容（SQL/分析文本/错误信息/用户提问等）"
    )
    payload: Mapped[str] = mapped_column(
        Text, nullable=True, comment="结构化数据（JSON 字符串，如查询结果/图表配置/计划步骤）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间"
    )
