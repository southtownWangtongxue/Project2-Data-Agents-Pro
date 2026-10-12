"""
HITL 审批等待-恢复(流内阻塞模式)

对话内 human-in-the-loop 的核心机制:SSE 流在审批中断点挂起等待,
审批接口 POST /approve 将决策送达此处,流恢复后以 Command(resume) 续流。

实现说明:
- 当前部署为单进程 uvicorn,SSE 生成器与审批接口同处一个事件循环,
  用 asyncio.Future 传递决策最简洁可靠;
- 多 worker 部署时 resolve() 找不到等待者会返回 False,approve.py
  据此回退到「直连恢复」旧路径,天然兜底,不会断裂。
"""
import asyncio
import logging

logger = logging.getLogger(__name__)

# thread_id → 等待中的 Future(值为审批决策 dict)
_waiters: dict[str, asyncio.Future] = {}


def register_waiter(thread_id: str) -> asyncio.Future:
    """注册等待者并返回 Future。"""
    fut: asyncio.Future = asyncio.get_event_loop().create_future()
    _waiters[thread_id] = fut
    return fut


def resolve(thread_id: str, decision: dict) -> bool:
    """送达审批决策。

    返回 True 表示已有活跃的流内等待者(由其自行恢复图执行);
    返回 False 表示当前无等待者(approve.py 应回退直连恢复路径)。
    """
    fut = _waiters.pop(thread_id, None)
    if fut is not None and not fut.done():
        fut.set_result(decision)
        logger.info("[HITL] 决策已送达等待中的流: thread=%s approved=%s",
                    thread_id, decision.get("approved"))
        return True
    return False


def cancel(thread_id: str) -> None:
    """取消等待(用户停止生成/连接断开时清理,防泄漏)。"""
    fut = _waiters.pop(thread_id, None)
    if fut is not None and not fut.done():
        fut.cancel()


async def wait_for(thread_id: str, timeout: float = 300) -> dict | None:
    """流内等待审批决策。

    超时返回 None(调用方按「自动拒绝」处理)。
    """
    fut = register_waiter(thread_id)
    try:
        return await asyncio.wait_for(fut, timeout=timeout)
    except asyncio.TimeoutError:
        _waiters.pop(thread_id, None)
        logger.warning("[HITL] 审批等待超时(%.0fs),自动拒绝: thread=%s", timeout, thread_id)
        return None
