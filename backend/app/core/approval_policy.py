"""
审批预设档位（R11，对齐 Harness 审批预设）

三档策略决定 dangerous SQL 是否必须人工审批：

    read_only        最严：所有非只读操作一律人工审批（默认，等同旧行为）
    workspace_write  中：放行 DML（INSERT/UPDATE/DELETE/REPLACE/MERGE），
                     DDL / 权限系统类（DROP/ALTER/TRUNCATE/GRANT/EXEC…）仍需人工审批
    full_access      最宽：全部自动放行；切换到该档必须二次确认（confirm=true）

档位持久化到 configs/approval_policy.json（经 ConfigManager，热更新生效）；
决策逻辑为纯函数（decide_approval），可独立单元测试。
"""
from __future__ import annotations

from app.core.config_manager import get_config_manager
from app.utils.log_utils import log

POLICY_FILE = "approval_policy.json"

VALID_TIERS = ("read_only", "workspace_write", "full_access")

TIER_LABELS = {
    "read_only": "只读模式（所有写操作需人工审批）",
    "workspace_write": "数据写入模式（DML 自动放行，DDL/权限操作仍需审批）",
    "full_access": "完全放行模式（所有 SQL 自动执行，谨慎使用）",
}

# 各档位允许自动放行的风险等级（dangerous 语句细分：dml / ddl / admin）
AUTO_APPROVE_RISK = {
    "read_only": set(),                       # 无自动放行
    "workspace_write": {"dml"},               # 仅数据写入
    "full_access": {"dml", "ddl", "admin"},   # 全部
}


def get_tier() -> str:
    """读取当前审批档位；配置缺失/非法时回退 read_only（最严默认）。"""
    data = get_config_manager().get(POLICY_FILE)
    tier = data.get("tier", "read_only")
    if tier not in VALID_TIERS:
        return "read_only"
    return tier


def set_tier(tier: str, confirm: bool = False) -> tuple[bool, str]:
    """
    设置审批档位。

    full_access 为高危档位，必须显式二次确认（confirm=True），否则拒绝。

    返回:
        (ok, error)：ok=False 时 error 为给前端的提示信息
    """
    if tier not in VALID_TIERS:
        return False, f"无效档位 '{tier}'，可选值: {', '.join(VALID_TIERS)}"
    if tier == "full_access" and not confirm:
        return False, (
            "切换到 full_access（完全放行）属于高危操作，需要二次确认："
            "请在请求中携带 confirm=true 重试"
        )

    data = get_config_manager().get(POLICY_FILE)
    old_tier = data.get("tier", "read_only")
    data["tier"] = tier
    err = get_config_manager().save(POLICY_FILE, data)
    if err:
        return False, f"保存失败: {err}"
    log.warning(f"[ApprovalPolicy] 档位变更: {old_tier} → {tier} (confirm={confirm})")
    return True, ""


def decide_approval(category: str, risk_level: str = "admin") -> str:
    """
    纯函数：根据当前档位与 SQL 风险等级决定放行方式。

    参数:
        category: classify_sql 结果的 category（"safe" / "dangerous"）
        risk_level: dangerous 语句的风险细分（"dml" / "ddl" / "admin"）

    返回:
        "auto_approve"（跳过人工审批，直接执行）或 "interrupt"（挂起等待人工审批）
    """
    if category != "dangerous":
        return "auto_approve"

    tier = get_tier()
    if risk_level in AUTO_APPROVE_RISK.get(tier, set()):
        return "auto_approve"
    return "interrupt"
