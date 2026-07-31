"""
三层记忆系统 — 短期(Redis) + 长期(Milvus+MySQL) + 工作记忆(对话上下文)

短期: Redis List, 每会话最多保留 50 条, TTL 24h
长期: Milvus 向量检索 + MySQL chat_sessions 持久化
工作记忆: AgentState.messages 对话上下文, 随会话生命周期
"""
import json
import redis.asyncio as async_redis
from app.core.config import settings
from app.utils.log_utils import log


class MemoryLayer:
    """三层记忆管理器"""

    def __init__(self):
        self._redis: async_redis.Redis | None = None

    async def _get_redis(self):
        if self._redis is None:
            try:
                self._redis = await async_redis.from_url(settings.REDIS_URL, decode_responses=True)
            except Exception:
                log.warning("[Memory] Redis 不可用，短期记忆降级")
                return None
        return self._redis

    # ── 短期记忆 (Redis) ──

    async def short_add(self, user: str, role: str, content: str):
        r = await self._get_redis()
        if r is None:
            return
        key = f"memory:short:{user}"
        entry = json.dumps({"role": role, "content": content[:2000]}, ensure_ascii=False)
        await r.lpush(key, entry)
        await r.ltrim(key, 0, 49)  # 最多 50 条
        await r.expire(key, 86400)  # TTL 24h

    async def short_get(self, user: str, count: int = 10) -> list[dict]:
        r = await self._get_redis()
        if r is None:
            return []
        items = await r.lrange(f"memory:short:{user}", 0, count - 1)
        return [json.loads(i) for i in items]

    # ── 长期记忆 (Milvus 向量检索) ──

    async def long_search(self, user: str, query: str, top_k: int = 5) -> list[str]:
        try:
            from app.rag.retriever import search_similar
            results = await search_similar(query, collection_name=f"kb_{user}", top_k=top_k)
            return [r.get("text", r.get("content", ""))[:500] for r in results]
        except Exception:
            return []

    # ── 工作记忆 ──

    @staticmethod
    def working_context(messages: list, max_turns: int = 6) -> str:
        """从对话消息提取最近 N 轮作为工作记忆上下文"""
        recent = messages[-max_turns:] if len(messages) > max_turns else messages
        parts = []
        for m in recent:
            role = m.get("role", "?") if isinstance(m, dict) else getattr(m, "role", "?")
            content = m.get("content", "") if isinstance(m, dict) else getattr(m, "content", "")
            parts.append(f"[{role}]: {str(content)[:200]}")
        return "\n".join(parts)


# 全局单例
_memory_layer: MemoryLayer | None = None


def get_memory() -> MemoryLayer:
    global _memory_layer
    if _memory_layer is None:
        _memory_layer = MemoryLayer()
    return _memory_layer
