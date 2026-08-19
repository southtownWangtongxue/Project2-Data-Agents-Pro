"""
人工审批接口

管理员通过此接口审批/驳回高危 SQL 操作请求，
与 LangGraph 工作流中的 Human-in-the-loop 机制对接。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from app.graph.workflow import get_graph
from langgraph.types import Command
from app.api.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/approve", tags=["approve"])


class ApproveRequest(BaseModel):
    """审批请求体"""
    task_id: str = Field(
        ...,
        description="审批任务 ID，即 chat 接口返回的 thread_id",
    )
    action: str = Field(
        ...,
        description="审批操作: approve（允许执行）或 reject（拒绝执行）",
        pattern="^(approve|reject)$",
    )
    comment: str = Field(
        default="",
        description="审批备注，说明通过或拒绝的原因",
    )


@router.post("", summary="审批高危 SQL 操作")
async def approve_task(
    body: ApproveRequest,
    user: dict = Depends(get_current_user),
):
    """
    管理员审批/驳回高危 SQL 操作。

    - ``action="approve"``：允许执行，LangGraph 从 Security 节点继续到 Execute 节点
    - ``action="reject"``：拒绝执行，LangGraph 终止流程并返回拒绝信息

    调用时机：
        当 chat SSE 接口返回 ``approval_required`` 事件后，
        管理员使用该 thread_id 调用本接口进行审批。

    权限：
        需登录（Bearer token）；非 admin 用户仅能审批自己会话（thread_id 前缀
        ``{user_name}:``）的审批任务。
    """
    # 会话归属校验：仅允许审批自己的会话（admin 除外）
    thread_id = body.task_id
    owner = thread_id.split(":", 1)[0] if ":" in thread_id else ""
    is_admin = user.get("user_type") == "00" or user.get("user_name") == "admin"
    if not is_admin and owner != user.get("user_name"):
        logger.warning("[Approve] 越权审批被拒绝: user=%s task_id=%s", user.get("user_name"), thread_id)
        raise HTTPException(status_code=403, detail="无权审批该会话的操作请求")

    graph = get_graph()
    config = {"configurable": {"thread_id": body.task_id}}

    if body.action == "approve":
        # 恢复图执行，传递审批通过信号
        result = await graph.ainvoke(
            Command(resume={"approved": True, "comment": body.comment}),
            config,
        )
        logger.info(f"[Approve] task_id={body.task_id} 审批通过")
        return {
            "status": "approved",
            "task_id": body.task_id,
            "result": result,
        }
    else:
        # 传递拒绝信号，图将终止并设置 error_message
        result = await graph.ainvoke(
            Command(resume={"approved": False, "comment": body.comment}),
            config,
        )
        logger.info(f"[Approve] task_id={body.task_id} 审批驳回: {body.comment}")
        return {
            "status": "rejected",
            "task_id": body.task_id,
            "result": result,
        }
