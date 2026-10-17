"""SQL 权限闸决策纯函数测试(Harness 安全第 2 层核心)。"""
from app.core.approval_policy import VALID_TIERS
from app.harness.sql_gate import decide_sql_gate

SAFE = {"category": "safe", "method": "whitelist", "reason": "只读语句"}
DML = {"category": "dangerous", "risk_level": "dml", "method": "whitelist", "reason": "写入"}
DDL = {"category": "dangerous", "risk_level": "ddl", "method": "whitelist", "reason": "结构变更"}
ADMIN = {"category": "dangerous", "risk_level": "admin", "method": "whitelist", "reason": "高危"}


def test_safe_sql_always_allow():
    """只读语句在任何档位都直接放行。"""
    for tier in VALID_TIERS:
        assert decide_sql_gate(SAFE, tier) == "allow"


def test_read_only_tier_asks_all_dangerous():
    """read_only 档:一切高危都转人工审批。"""
    assert decide_sql_gate(DML, "read_only") == "ask"
    assert decide_sql_gate(DDL, "read_only") == "ask"
    assert decide_sql_gate(ADMIN, "read_only") == "ask"


def test_workspace_write_allows_dml_only():
    """workspace_write 档:仅 DML 自动放行,DDL/权限类仍审批。"""
    assert decide_sql_gate(DML, "workspace_write") == "allow"
    assert decide_sql_gate(DDL, "workspace_write") == "ask"
    assert decide_sql_gate(ADMIN, "workspace_write") == "ask"


def test_full_access_allows_all_dangerous():
    """full_access 档:全部自动放行。"""
    assert decide_sql_gate(DML, "full_access") == "allow"
    assert decide_sql_gate(DDL, "full_access") == "allow"
    assert decide_sql_gate(ADMIN, "full_access") == "allow"


def test_unclassifiable_denies():
    """deny-by-default:分类缺失/异常/非法 category 一律拒绝执行。"""
    assert decide_sql_gate(None, "read_only") == "deny"
    assert decide_sql_gate({}, "read_only") == "deny"
    assert decide_sql_gate({"category": "unknown"}, "read_only") == "deny"


def test_invalid_tier_falls_back_to_read_only():
    """非法档位按最严(read_only)处理。"""
    assert decide_sql_gate(DML, "bogus") == "ask"
