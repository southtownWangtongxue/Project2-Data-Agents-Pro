"""审批 edit 决策端到端落地测试(端点层 + 决策构造纯函数)。

设计 §3:edit = 审批人修改 SQL 后再放行;中间件 apply_approval 的
edit 分支已实现有测试(test_sql_gate_middleware),本文件补 approve
端点缺口:action=edit 的请求校验(保 §5.3 双保险)、决策 dict 构造
(approved=False + edited_sql,匹配 apply_approval 契约)、活跃流送达。
"""
import asyncio

import pytest
from httpx import AsyncClient, ASGITransport

from app.api.v1.approve import ApproveRequest
from app.core import hitl
from app.main import app
from tests.test_api import _auth_headers


# ═══ 决策构造纯函数(apply_approval 契约)═══


def test_build_decision_approve():
    from app.api.v1.approve import _build_decision
    body = ApproveRequest(task_id="admin:t1", action="approve", comment="同意")
    assert _build_decision(body) == {"approved": True, "comment": "同意"}


def test_build_decision_reject():
    from app.api.v1.approve import _build_decision
    body = ApproveRequest(task_id="admin:t1", action="reject", comment="风险高")
    assert _build_decision(body) == {"approved": False, "comment": "风险高"}


def test_build_decision_edit():
    """edit 决策:approved 恒 False + edited_sql——apply_approval 先查
    approved(真→原 SQL),再看 edited_sql(非空→改后 SQL),edit 必须
    走「approved 假 + edited_sql」分支才能命中替换逻辑。"""
    from app.api.v1.approve import _build_decision
    body = ApproveRequest(task_id="admin:t1", action="edit",
                          comment="加了 WHERE", edited_sql="DELETE FROM t WHERE id=1")
    assert _build_decision(body) == {
        "approved": False, "comment": "加了 WHERE", "edited_sql": "DELETE FROM t WHERE id=1",
    }


# ═══ 请求校验(§5.3 双保险的 schema 层)═══


@pytest.mark.asyncio
async def test_edit_requires_edited_sql():
    """action=edit 缺 edited_sql → 422,且错误信息指向 edited_sql(而非 action 不合法)"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/approve", headers=_auth_headers(),
                                 json={"task_id": "admin:t1", "action": "edit", "comment": "x"})
    assert resp.status_code == 422
    assert "edited_sql" in resp.text


@pytest.mark.asyncio
async def test_approve_channel_cannot_carry_edited_sql():
    """approve/reject 通道携带 edited_sql → 422。

    §5.3 篡改注入验证的安全前提「approve 端点不传 sql 字段」必须在
    schema 层保持:edited_sql 仅在 action=edit 时允许携带。
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/approve", headers=_auth_headers(),
                                 json={"task_id": "admin:t1", "action": "approve",
                                       "comment": "x", "edited_sql": "DROP TABLE users"})
        assert resp.status_code == 422
        resp = await client.post("/api/v1/approve", headers=_auth_headers(),
                                 json={"task_id": "admin:t1", "action": "reject",
                                       "comment": "x", "edited_sql": "DROP TABLE users"})
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_edit_non_admin_forbidden():
    """非 admin 发起 edit → 403(职责分离对 edit 同样生效)"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/approve", headers=_auth_headers("user1", "01"),
                                 json={"task_id": "user1:t1", "action": "edit",
                                       "comment": "x", "edited_sql": "UPDATE t SET a=1"})
    assert resp.status_code == 403


# ═══ 活跃流送达(生产拓扑:流内等待 + 审批并发)═══


@pytest.mark.asyncio
async def test_edit_decision_delivered_to_active_stream():
    """活跃 SSE 流等待时,edit 决策原样送达(含 edited_sql),响应 notified。

    决策经 hitl.resolve → stream_harness 的 Command(resume=decision)
    → apply_approval(已有测试覆盖 edit 分支替换执行)。
    """
    waiter = asyncio.create_task(hitl.wait_for("admin:t-edit", timeout=5))
    await asyncio.sleep(0.01)  # 让 waiter 先注册(否则 resolve 走兜底路径)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/approve", headers=_auth_headers(),
                                 json={"task_id": "admin:t-edit", "action": "edit",
                                       "comment": "限定范围后放行",
                                       "edited_sql": "DELETE FROM orders WHERE id = 1"})
    decision = await waiter

    assert resp.status_code == 200
    assert resp.json()["status"] == "notified"
    assert decision == {
        "approved": False,
        "comment": "限定范围后放行",
        "edited_sql": "DELETE FROM orders WHERE id = 1",
    }
