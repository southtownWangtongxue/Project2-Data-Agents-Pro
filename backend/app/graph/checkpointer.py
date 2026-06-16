"""
Redis 状态快照持久化

用于 LangGraph Human-in-the-loop 中断时保存和恢复 Graph 状态。
将 AgentState 序列化为 JSON 存入 Redis，以 thread_id 为键。
"""
import json
import logging

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Redis 异步客户端 ──────────────────────────────────
# 延迟初始化，避免模块导入时立即连接 Redis（若 Redis 不可用则优雅降级）
_redis_client: aioredis.Redis | None = None


async def _get_redis() -> aioredis.Redis | None:
    """延迟获取 Redis 客户端，连接失败时返回 None 而非抛异常。"""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
        # 测试连接可用性
        await _redis_client.ping()
        logger.info("[Checkpointer] Redis 连接成功: %s", settings.REDIS_URL)
        return _redis_client
    except Exception as exc:
        logger.warning("[Checkpointer] Redis 连接失败 (%s)，checkpoint 功能不可用", exc)
        _redis_client = None
        return None

# checkpoint 在 Redis 中的 key 前缀
CHECKPOINT_KEY_PREFIX = "graph:checkpoint"
# checkpoint 默认过期时间（秒）
CHECKPOINT_TTL = 3600  # 1 小时


async def save_checkpoint(thread_id: str, state: dict) -> None:
    """保存 Graph 状态快照到 Redis

    将 AgentState 字典序列化为 JSON 后存入 Redis，
    并设置过期时间防止内存泄漏。

    参数:
        thread_id: 对话线程 ID，作为 Redis key 的一部分
        state: AgentState 字典，将序列化为 JSON 存储
    """
    client = await _get_redis()
    if client is None:
        return
    key = f"{CHECKPOINT_KEY_PREFIX}:{thread_id}"
    payload = json.dumps(state, ensure_ascii=False, default=str)
    await client.set(key, payload)
    await client.expire(key, CHECKPOINT_TTL)


async def load_checkpoint(thread_id: str) -> dict | None:
    """从 Redis 加载 Graph 状态快照

    根据 thread_id 查找并反序列化之前保存的状态。

    参数:
        thread_id: 对话线程 ID

    返回:
        反序列化的状态字典；若 key 不存在或已过期则返回 None
    """
    client = await _get_redis()
    if client is None:
        return None
    key = f"{CHECKPOINT_KEY_PREFIX}:{thread_id}"
    data = await client.get(key)
    if data is None:
        return None
    return json.loads(data)


async def delete_checkpoint(thread_id: str) -> None:
    """删除 Graph 状态快照

    用于清理已完成或已取消的对话状态。

    参数:
        thread_id: 对话线程 ID
    """
    client = await _get_redis()
    if client is None:
        return
    key = f"{CHECKPOINT_KEY_PREFIX}:{thread_id}"
    await client.delete(key)


async def checkpoint_exists(thread_id: str) -> bool:
    """检查指定 thread_id 的 checkpoint 是否存在

    参数:
        thread_id: 对话线程 ID

    返回:
        True 表示存在有效 checkpoint，False 表示不存在或已过期
    """
    client = await _get_redis()
    if client is None:
        return False
    key = f"{CHECKPOINT_KEY_PREFIX}:{thread_id}"
    return await client.exists(key) > 0
