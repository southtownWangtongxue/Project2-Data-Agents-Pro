"""SQL 权限闸决策(纯函数,Harness 安全第 2 层的核心)。

把 security.classify_sql 的分类结果与 approval_policy 的审批档位,映射为三态:

    allow  直接放行(只读语句,或档位已授权该风险等级)
    ask    挂起等待人工审批(HITL interrupt)
    deny   拒绝执行并告知模型原因(分类失败/无法判定,deny-by-default)

决策为纯函数,不依赖 DB/LLM/Graph 上下文,可独立单测。
"""
from __future__ import annotations

from typing import Literal

from app.core.approval_policy import AUTO_APPROVE_RISK, VALID_TIERS

GateDecision = Literal["allow", "ask", "deny"]


def decide_sql_gate(classification: dict | None, tier: str) -> GateDecision:
    """
    参数:
        classification: classify_sql 的返回。合法形态:
            {"category": "safe"|"dangerous", "risk_level": "dml"|"ddl"|"admin", ...}
            注:classify_sql 的 safe 分支不带 risk_level、llm-confirm 高危分支
            也不带;本函数的 "admin" 兜底将这些路径一律按最严处理。
        tier: 审批档位(read_only / workspace_write / full_access);非法值按 read_only 处理

    返回:
        "allow" | "ask" | "deny"
    """
    if tier not in VALID_TIERS:
        tier = "read_only"

    if not isinstance(classification, dict) or classification.get("category") not in ("safe", "dangerous"):
        return "deny"

    if classification["category"] == "safe":
        return "allow"

    risk = classification.get("risk_level", "admin")
    if risk in AUTO_APPROVE_RISK.get(tier, set()):
        return "allow"
    return "ask"
