"""
会话存储模型 —— chat_sessions + chat_nodes 表 ORM 映射

MySQL 存储会话元数据 + 节点标题，Redis 保留 LangGraph checkpoints 用于工作流状态恢复。
"""
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, func
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
