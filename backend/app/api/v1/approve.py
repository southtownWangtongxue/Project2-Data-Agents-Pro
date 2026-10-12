"""
人工审批接口

管理员通过此接口审批/驳回高危 SQL 操作请求，
与 LangGraph 工作流中的 Human-in-the-loop 机制对接。

R10 审批审计：每次审批动作（通过/驳回/越权拒绝）持久化到 MySQL
approval_records 表，不再仅依赖 Redis checkpoint（TTL 1h 后丢失）。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from app.graph.workflow import get_graph
from langgraph.types import Command
from app.api.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/approve", tags=["approve"])


async def _audit_approval(
    task_id: str,
    owner_user: str,
    action: str,
    comment: str,
    approver_user: str,
) -> None:
    """写入审批审计记录（失败仅告警，不阻断审批主流程）。"""
    try:
        from app.models.approval import ApprovalRecord
        from app.db.session import _get_session_factory

        factory = _get_session_factory()
        async with factory() as session:
            session.add(ApprovalRecord(
                task_id=task_id,
                owner_user=owner_user or "",
                action=action,
                comment=comment or "",
                approver_user=approver_user,
            ))
            await session.commit()
        logger.info("[Approve][Audit] 审计已落库: task=%s action=%s approver=%s",
                    task_id, action, approver_user)
    except Exception as exc:
        logger.warning("[Approve][Audit] 审计落库失败（不影响审批）: %s", exc)


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
        需登录（Bearer token）；仅 admin（user_type=00）可审批。
        发起人与审批人职责分离：即使是非 admin 会话的发起者，也不能自行审批
        自己触发的高危 SQL（deny-by-default 的审批关卡）。
    """
    # 职责分离：高危操作审批仅允许管理员执行（DEF-007）
    is_admin = user.get("user_type") == "00" or user.get("user_name") == "admin"
    thread_id = body.task_id
    owner = thread_id.split(":", 1)[0] if ":" in thread_id else ""
    if not is_admin:
        logger.warning(
            "[Approve] 非管理员审批被拒绝（职责分离）: user=%s task_id=%s",
            user.get("user_name"), body.task_id,
        )
        # R10 审计：越权尝试也落库
        await _audit_approval(
            task_id=thread_id, owner_user=owner, action=body.action,
            comment="[拒绝] 非管理员审批被拒（职责分离）",
            approver_user=str(user.get("user_name") or ""),
        )
        raise HTTPException(status_code=403, detail="高危操作审批仅允许管理员执行")

    # ── HITL 流内等待优先 ──
    # 存在活跃的 SSE 审批等待时,仅送达决策(由该流自行 Command(resume) 恢复并续流,
    # 续流事件直接进入原对话);无活跃流(旧调用方/页面已关闭)时回退直连恢复兜底。
    from app.core import hitl
    decision = {"approved": body.action == "approve", "comment": body.comment or ""}
    if hitl.resolve(body.task_id, decision):
        logger.info("[Approve] 已通知活跃 SSE 流恢复: task=%s action=%s approver=%s",
                    body.task_id, body.action, user.get("user_name"))
        await _audit_approval(
            task_id=thread_id, owner_user=owner, action=body.action,
            comment=body.comment, approver_user=str(user.get("user_name") or ""),
        )
        return {"status": "notified", "task_id": body.task_id}

    graph = get_graph()
    config = {"configurable": {"thread_id": body.task_id}}

    if body.action == "approve":
        # 恢复图执行，传递审批通过信号
        result = await graph.ainvoke(
            Command(resume={"approved": True, "comment": body.comment}),
            config,
        )
        logger.info(f"[Approve] task_id={body.task_id} 审批通过")
        # R10 审计
        await _audit_approval(
            task_id=thread_id, owner_user=owner, action="approve",
            comment=body.comment, approver_user=str(user.get("user_name") or ""),
        )
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
        # R10 审计
        await _audit_approval(
            task_id=thread_id, owner_user=owner, action="reject",
            comment=body.comment, approver_user=str(user.get("user_name") or ""),
        )
        return {
            "status": "rejected",
            "task_id": body.task_id,
            "result": result,
        }


@router.get("/policy", summary="查询审批档位（R11）")
async def get_approval_policy(user: dict = Depends(get_current_user)):
    """查询当前审批预设档位：read_only / workspace_write / full_access。"""
    from app.core.approval_policy import get_tier, TIER_LABELS
    tier = get_tier()
    return {"tier": tier, "label": TIER_LABELS.get(tier, tier)}


class PolicyRequest(BaseModel):
    """档位设置请求体"""
    tier: str = Field(
        ...,
        description="目标档位: read_only / workspace_write / full_access",
    )
    confirm: bool = Field(
        default=False,
        description="二次确认标志；切换到 full_access 时必须为 true",
    )


@router.put("/policy", summary="设置审批档位（R11，admin，full_access 需二次确认）")
async def set_approval_policy(
    body: PolicyRequest,
    user: dict = Depends(get_current_user),
):
    """
    设置审批预设档位。

    - read_only：所有写操作人工审批（默认，最严）
    - workspace_write：DML 自动放行，DDL/权限操作仍需审批
    - full_access：全部自动放行——**必须二次确认**（confirm=true），否则 400
    """
    is_admin = user.get("user_type") == "00" or user.get("user_name") == "admin"
    if not is_admin:
        raise HTTPException(status_code=403, detail="审批档位仅管理员可修改")

    from app.core.approval_policy import set_tier, TIER_LABELS
    ok, error = set_tier(body.tier, confirm=body.confirm)
    if not ok:
        raise HTTPException(status_code=400, detail=error)

    logger.info("[Approve][Policy] 审批档位已变更: tier=%s operator=%s",
                body.tier, user.get("user_name"))
    return {"ok": True, "tier": body.tier, "label": TIER_LABELS.get(body.tier, body.tier)}


@router.get("/records", summary="审批审计记录查询（管理员）")
async def list_approval_records(
    limit: int = 50,
    user: dict = Depends(get_current_user),
):
    """
    查询审批审计记录（R10 审批关卡链），按时间倒序返回最新记录。

    权限：仅 admin（user_type=00）。
    """
    is_admin = user.get("user_type") == "00" or user.get("user_name") == "admin"
    if not is_admin:
        raise HTTPException(status_code=403, detail="审计记录仅管理员可查")

    limit = max(1, min(limit, 200))
    from sqlalchemy import select
    from app.models.approval import ApprovalRecord
    from app.db.session import _get_session_factory

    factory = _get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(ApprovalRecord)
            .order_by(ApprovalRecord.id.desc())
            .limit(limit)
        )
        rows = result.scalars().all()

    return {
        "total": len(rows),
        "records": [
            {
                "id": r.id,
                "task_id": r.task_id,
                "owner_user": r.owner_user,
                "action": r.action,
                "comment": r.comment,
                "approver_user": r.approver_user,
                "created_at": str(r.created_at),
            }
            for r in rows
        ],
    }
