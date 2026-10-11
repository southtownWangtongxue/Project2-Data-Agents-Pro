"""
审批审计模型 —— approval_records 表 ORM 映射（R10 审批关卡链）

高危 SQL 审批记录持久化到 MySQL（此前仅存 Redis checkpoint，TTL 1h 即丢失），
满足"谁、何时、对哪个任务、做了什么决定、备注是什么"的审计要求。
"""
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, func, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base


class ApprovalRecord(Base):
    """高危操作审批审计表 —— 每次审批动作（通过/驳回/越权拒绝）一条记录"""
    __tablename__ = "approval_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        String(128), nullable=False,
        comment="审批任务 ID（即发起会话的 thread_id）"
    )
    owner_user: Mapped[str] = mapped_column(
        String(30), nullable=False, default="",
        comment="发起人（从 task_id 前缀解析，跨会话/无前缀时为空）"
    )
    action: Mapped[str] = mapped_column(
        String(16), nullable=False,
        comment="审批动作: approve / reject"
    )
    comment: Mapped[str] = mapped_column(
        Text, nullable=True,
        comment="审批备注；越权拒绝时记录拒绝原因"
    )
    approver_user: Mapped[str] = mapped_column(
        String(30), nullable=False,
        comment="实际执行审批操作的用户"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="审批时间"
    )

    __table_args__ = (
        Index("idx_approval_task", "task_id"),
        Index("idx_approval_created", "created_at"),
    )
