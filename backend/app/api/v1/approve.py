"""
人工审批接口

管理员通过此接口审批/驳回高危 SQL 操作请求，
与 LangGraph 工作流中的 Human-in-the-loop 机制对接。

R10 审批审计：每次审批动作（通过/驳回/越权拒绝）持久化到 MySQL
approval_records 表，不再仅依赖 Redis checkpoint（TTL 1h 后丢失）。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
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
        description="审批操作: approve（原样执行）/ reject（拒绝执行）/ edit（按修改后的 SQL 执行）",
        pattern="^(approve|reject|edit)$",
    )
    comment: str = Field(
        default="",
        description="审批备注，说明通过或拒绝的原因",
    )
    edited_sql: str = Field(
        default="",
        description="edit 决策专用：审批人修改后的 SQL；仅 action=edit 时允许携带",
    )

    @model_validator(mode="after")
    def _edited_sql_iff_edit(self) -> "ApproveRequest":
        # §5.3 双保险的 schema 层：approve/reject 通道禁止携带 SQL（篡改注入
        # 验证的前提「approve 端点不传 sql 字段」在此保持）；edit 必须携带
        # 非空 SQL，否则决策无法命中 apply_approval 的替换分支。
        if self.action == "edit" and not self.edited_sql.strip():
            raise ValueError("action=edit 必须携带非空 edited_sql")
        if self.action != "edit" and self.edited_sql.strip():
            raise ValueError("edited_sql 仅在 action=edit 时允许携带（approve/reject 通道禁止夹带 SQL）")
        return self


def _build_decision(body: ApproveRequest) -> dict:
    """构造 Command(resume) 审批决策（与 sql_gate_middleware.apply_approval 契约对齐）。

    edit 决策恒为 approved=False + edited_sql：apply_approval 先查 approved
    （真→原样执行），再看 edited_sql（非空→执行修改后的 SQL），因此 edit
    只有走「approved 假 + edited_sql」分支才能命中替换逻辑；approve/reject
    的决策里永远没有 edited_sql 字段（双保险的运行时层）。

    信任边界说明：edited_sql 不再做安全重分类——admin 对「模型发来的任意
    SQL」本就有 approve 全权（信任锚），edit 不扩大该边界；分类器无权
    否决审批人的显式修改。
    """
    decision: dict = {"approved": body.action == "approve", "comment": body.comment or ""}
    if body.action == "edit":
        decision["edited_sql"] = body.edited_sql
    return decision


@router.post("", summary="审批高危 SQL 操作")
async def approve_task(
    body: ApproveRequest,
    user: dict = Depends(get_current_user),
):
    """
    管理员审批/驳回/修改高危 SQL。

    - ``action="approve"``：原样执行，LangGraph 从中断点恢复继续
    - ``action="reject"``：拒绝执行，流程终止并返回拒绝信息
    - ``action="edit"``：按审批人修改后的 SQL 执行（``edited_sql`` 必填；
      仅 admin 可发起，与 approve 同一职责分离校验）

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

    # edit 决策的审计必须留下「实际执行的 SQL」：审批卡上的原 SQL 与最终
    # 执行的 SQL 不同，审计表无独立列，附在 comment 里保证可追溯
    audit_comment = body.comment
    if body.action == "edit":
        audit_comment = f"{body.comment} | 修改后SQL: {body.edited_sql}".lstrip(" |")

    # ── HITL 流内等待优先 ──
    # 存在活跃的 SSE 审批等待时,仅送达决策(由该流自行 Command(resume) 恢复并续流,
    # 续流事件直接进入原对话);无活跃流(旧调用方/页面已关闭)时回退直连恢复兜底。
    from app.core import hitl
    decision = _build_decision(body)
    if hitl.resolve(body.task_id, decision):
        logger.info("[Approve] 已通知活跃 SSE 流恢复: task=%s action=%s approver=%s",
                    body.task_id, body.action, user.get("user_name"))
        await _audit_approval(
            task_id=thread_id, owner_user=owner, action=body.action,
            comment=audit_comment, approver_user=str(user.get("user_name") or ""),
        )
        return {"status": "notified", "task_id": body.task_id}

    # 直连兜底：无活跃流时直接恢复图执行。注意 legacy 图的 security 节点只认
    # approved 布尔（忽略 edited_sql，edit 请求在 legacy 线程上等效拒绝）；
    # Harness 线程的中断由上方活跃流路径处理，正常不会走到这里。
    graph = get_graph()
    config = {"configurable": {"thread_id": body.task_id}}
    result = await graph.ainvoke(Command(resume=decision), config)
    logger.info("[Approve] task_id=%s 直连恢复完成: action=%s comment=%s",
                body.task_id, body.action, body.comment)
    await _audit_approval(
        task_id=thread_id, owner_user=owner, action=body.action,
        comment=audit_comment, approver_user=str(user.get("user_name") or ""),
    )
    status = {"approve": "approved", "reject": "rejected", "edit": "edited"}[body.action]
    return {"status": status, "task_id": body.task_id, "result": result}


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
