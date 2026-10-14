"""SQL 安全闸中间件(Harness 安全第 2 层,替代 legacy 的 security 节点)。

拦截 run_sql 工具调用:classify_sql 分类 → decide_sql_gate 档位决策 →
    allow  放行(直接执行)
    ask    interrupt() 挂起,审批决策经 Command(resume) 返回:
               approve          放行原 SQL
               edit(edited_sql) 放行修改后的 SQL
               reject           返回 ToolMessage 说明原因,由模型自主降级
    deny   返回 ToolMessage 拒绝原因(分类异常/无法判定,deny-by-default)

中断载荷复用现有 SSE approval_required 事件字段(type/message/sql/reason),
Phase 1 的 SSE 桥接可直接映射到对话内审批卡。

与 deepagents 自带 _PermissionMiddleware 同一协议(awrap_tool_call),
可与其叠加使用。
"""
from __future__ import annotations

import dataclasses

from langchain.agents.middleware import AgentMiddleware
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import interrupt

from app.agents.security import classify_sql
from app.core.approval_policy import get_tier
from app.harness.sql_gate import decide_sql_gate
from app.utils.log_utils import log

GATE_TOOL = "run_sql"


def apply_approval(args: dict, approval: dict) -> tuple[str, dict, str]:
    """
    审批恢复决策(纯函数)。

    参数:
        args:     原工具调用参数(含 sql/purpose)
        approval: Command(resume=...) 传入的审批决策:
                  {"approved": bool, "edited_sql": str?, "comment": str?};
                  非 dict 的畸形值归一为空 dict(按拒绝处理)

    返回:
        (action, new_args, deny_reason):
            action="execute" → 放行(new_args 为最终参数,edit 时 sql 已替换)
            action="deny"    → 拒绝(deny_reason 将返回给模型)
    """
    approval = approval if isinstance(approval, dict) else {}
    if approval.get("approved"):
        return "execute", args, ""

    edited = str(approval.get("edited_sql") or "").strip()
    if edited:
        return "execute", {**args, "sql": edited}, ""

    return "deny", args, f"审批被驳回:{approval.get('comment') or '无备注'}"


class SqlGateMiddleware(AgentMiddleware):
    """对 run_sql 实施「分类 → 档位 → allow/ask/deny」安全闸。"""

    async def awrap_tool_call(self, request: ToolCallRequest, handler) -> ToolMessage:
        tool_name = request.tool_call["name"]
        if tool_name != GATE_TOOL:
            return await handler(request)

        args = dict(request.tool_call.get("args") or {})
        sql = args.get("sql", "")

        try:
            classification = await classify_sql(sql)
        except Exception as exc:
            # 异常详情只进服务端日志;回给模型的只保留类型名,避免敏感信息外溢
            log.exception("[SqlGate] SQL 分类异常,deny-by-default 拒绝")
            return self._deny(request, f"SQL 安全分类失败({type(exc).__name__})")

        decision = decide_sql_gate(classification, get_tier())
        cls = classification if isinstance(classification, dict) else {}
        log.warning(
            "[SqlGate] run_sql 决策=%s category=%s risk=%s",
            decision,
            cls.get("category"),
            cls.get("risk_level"),
        )

        if decision == "allow":
            return await handler(request)
        if decision == "deny":
            return self._deny(request, cls.get("reason") or "SQL 分类失败")

        # ask:挂起等待人工审批(中断载荷对齐 SSE approval_required 事件字段)
        approval = interrupt({
            "type": "approval_required",
            "message": "检测到高危 SQL 操作(非只读),需要审批",
            "sql": sql,
            "purpose": args.get("purpose", ""),
            "reason": cls.get("reason", ""),
        })

        # 畸形 resume 值(非 dict)优雅降级为拒绝,不在安全核心抛异常
        approval = approval if isinstance(approval, dict) else {}
        action, new_args, deny_reason = apply_approval(args, approval)
        if action == "deny":
            return self._deny(request, deny_reason)

        if new_args.get("sql") != sql:
            log.warning("[SqlGate] 审批人修改 SQL 后放行")
            edited_call = dict(request.tool_call)
            edited_call["args"] = new_args
            request = dataclasses.replace(request, tool_call=edited_call)
        return await handler(request)

    @staticmethod
    def _deny(request: ToolCallRequest, reason: str) -> ToolMessage:
        call = request.tool_call
        return ToolMessage(
            content=(
                f"安全策略拒绝执行该 SQL:{reason}。"
                "请改用只读查询,或向用户说明当前权限限制。"
            ),
            tool_call_id=call["id"],
            name=call["name"],
        )
