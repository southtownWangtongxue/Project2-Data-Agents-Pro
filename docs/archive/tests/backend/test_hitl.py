"""
HITL 审批等待-恢复单元测试
覆盖:决策送达 / 超时自动拒 / 无等待者回退 / 取消清理
"""
import asyncio

import pytest

from app.core import hitl


@pytest.mark.asyncio
async def test_wait_and_resolve():
    """审批接口送达决策 → 流内等待立即返回"""
    async def approver():
        await asyncio.sleep(0.05)
        assert hitl.resolve("t1", {"approved": True, "comment": "ok"}) is True

    task = asyncio.create_task(approver())
    decision = await hitl.wait_for("t1", timeout=2)
    await task
    assert decision == {"approved": True, "comment": "ok"}


@pytest.mark.asyncio
async def test_wait_timeout_auto_reject():
    """超时返回 None(approve 语义:自动拒绝)"""
    decision = await hitl.wait_for("t_timeout", timeout=0.05)
    assert decision is None


@pytest.mark.asyncio
async def test_resolve_without_waiter_returns_false():
    """无活跃流等待时回退 False(approve.py 走直连恢复兜底)"""
    assert hitl.resolve("no-active-stream", {"approved": True}) is False


@pytest.mark.asyncio
async def test_cancel_cleans_waiter():
    """用户停止生成 → 等待被取消,不泄漏"""
    wait_task = asyncio.create_task(hitl.wait_for("t_cancel", timeout=10))
    await asyncio.sleep(0.01)
    hitl.cancel("t_cancel")
    with pytest.raises(asyncio.CancelledError):
        await wait_task
    # 注册表已清理
    assert "t_cancel" not in hitl._waiters


@pytest.mark.asyncio
async def test_double_resolve_second_returns_false():
    """重复送达:第一次成功,第二次无等待者返回 False"""
    async def approver():
        await asyncio.sleep(0.02)
        first = hitl.resolve("t_double", {"approved": True})
        second = hitl.resolve("t_double", {"approved": False})
        assert first is True and second is False

    task = asyncio.create_task(approver())
    decision = await hitl.wait_for("t_double", timeout=2)
    await task
    assert decision["approved"] is True
