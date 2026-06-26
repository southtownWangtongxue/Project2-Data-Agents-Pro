"""
Plain Redis Checkpoint Saver（不依赖 RediSearch 模块）

基于 InMemorySaver + Redis 持久化：写入时同步到 Redis，启动时加载历史数据。

Redis 数据模型（纯 String/ZSET，无需任何模块）：
    ckpt:{thread_id}:{ns}:{checkpoint_id}  → JSON (序列化后的检查点)
    ckpt_z:{thread_id}:{ns}                 → ZSET (checkpoint_id → timestamp, 排序用)
"""
import asyncio
import json
import logging
import time
from collections import defaultdict

import redis.asyncio as aioredis
from langgraph.checkpoint.memory import InMemorySaver

logger = logging.getLogger(__name__)

CKPT_PREFIX = "ckpt"
CKPT_ZSET_PREFIX = "ckpt_z"
CKPT_TTL = 86400 * 7  # 7 天


def _to_serializable(obj):
    """递归转换对象为 JSON 可序列化格式。"""
    if isinstance(obj, dict):
        return {k: _to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_serializable(v) for v in obj]
    if isinstance(obj, bytes):
        return {"__bytes__": obj.hex()}
    if hasattr(obj, "to_json"):
        return obj.to_json()
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "__class__") and hasattr(obj, "content"):
        # LangChain Message 对象
        try:
            return {
                "__type__": obj.__class__.__name__,
                "content": str(getattr(obj, "content", "")),
                "type": getattr(obj, "type", "message"),
            }
        except Exception:
            pass
    return str(obj) if obj is not None else None


class PlainRedisSaver(InMemorySaver):
    """支持 Redis 持久化的 InMemorySaver（无需 RediSearch 模块）。

    继承 InMemorySaver 获得完整的 LangGraph 检查点逻辑，
    重写写入方法以将数据同步到 Redis，并在初始化时加载历史数据。

    用法:
        saver = PlainRedisSaver(redis_url="redis://localhost:6379/0")
        await saver.asetup()   # 异步初始化 Redis 连接 + 加载历史
        graph = builder.compile(checkpointer=saver)
    """

    def __init__(self, redis_url: str):
        super().__init__()
        self._redis_url = redis_url
        self._redis: aioredis.Redis | None = None
        self._initialized = False

    # ── 生命周期 ──────────────────────────────────────────

    async def asetup(self) -> None:
        """初始化 Redis 连接并加载历史检查点。"""
        if self._initialized:
            return
        try:
            self._redis = aioredis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            await self._redis.ping()
            logger.info("[PlainRedisSaver] Redis 连接成功: %s", self._redis_url)
            await self._load_from_redis()
            self._initialized = True
        except Exception as exc:
            logger.warning("[PlainRedisSaver] Redis 初始化失败 (%s)，仅使用内存存储", exc)
            self._redis = None
            self._initialized = True

    async def aclose(self) -> None:
        """关闭 Redis 连接。"""
        if self._redis is not None:
            try:
                await self._redis.close()
                logger.info("[PlainRedisSaver] Redis 连接已关闭")
            except Exception:
                pass
            self._redis = None

    async def __aenter__(self):
        await self.asetup()
        return self

    async def __aexit__(self, *args):
        await self.aclose()

    # ── Redis 加载 ────────────────────────────────────────

    @staticmethod
    def _parse_ckpt_key(key: str) -> tuple[str, str, str] | None:
        """
        解析检查点 Redis Key，正确处理 thread_id 中的冒号。

        Key 格式: ckpt:{thread_id}:{ns}:{ckpt_id}
        thread_id 格式: {username}:{uuid}（含一个冒号）

        兼容两种格式:
        - 新格式 (4段): ckpt:admin:uuid:ns:ckpt_id → thread_id=admin:uuid
        - 旧格式 (3段): ckpt:simple_id:ns:ckpt_id → thread_id=simple_id
        """
        content = key.removeprefix(CKPT_PREFIX + ":")
        parts = content.split(":", 3)
        if len(parts) == 4:
            # 新格式: username + uuid 各一段，thread_id 需要拼接
            thread_id = parts[0] + ":" + parts[1]
            ns = parts[2]
            ckpt_id = parts[3]
        elif len(parts) == 3:
            # 旧格式: thread_id 不含冒号
            thread_id, ns, ckpt_id = parts[0], parts[1], parts[2]
        else:
            return None
        return thread_id, ns, ckpt_id

    async def _load_from_redis(self) -> None:
        """从 Redis 加载所有历史检查点到 InMemorySaver（带超时保护）。"""
        if self._redis is None:
            return

        cursor = 0
        loaded = 0
        try:
            cursor, keys = await asyncio.wait_for(
                self._redis.scan(cursor, match=f"{CKPT_PREFIX}:*", count=100),
                timeout=5.0,
            )
        except asyncio.TimeoutError:
            logger.warning("[PlainRedisSaver] SCAN 超时，跳过历史加载")
            return
        except Exception as exc:
            logger.warning("[PlainRedisSaver] SCAN 失败: %s，跳过历史加载", exc)
            return

        while True:
            for key in keys:
                try:
                    parsed = self._parse_ckpt_key(key)
                    if parsed is None:
                        continue
                    thread_id, ns, ckpt_id = parsed

                    data_str = await self._redis.get(key)
                    if data_str is None:
                        continue
                    saved = json.loads(data_str)

                    # 还原 storage
                    ckpt_blob = (
                        saved.get("ckpt_type", "json"),
                        bytes.fromhex(saved["ckpt_data"]) if isinstance(saved.get("ckpt_data"), str) else saved.get("ckpt_data", b""),
                    )
                    meta_blob = (
                        saved.get("meta_type", "json"),
                        bytes.fromhex(saved["meta_data"]) if isinstance(saved.get("meta_data"), str) else saved.get("meta_data", b""),
                    )
                    self.storage[thread_id][ns][ckpt_id] = (
                        ckpt_blob,
                        meta_blob,
                        saved.get("parent_checkpoint_id"),
                    )

                    # 还原 blobs（channel_values → self.blobs）
                    channel_values = saved.get("channel_values", {})
                    channel_versions = saved.get("channel_versions", {})
                    for ch_name, ch_version in channel_versions.items():
                        val = channel_values.get(ch_name)
                        if val is not None and ch_name not in {"__start__", "__end__"}:
                            blob_key = (thread_id, ns, ch_name, ch_version)
                            self.blobs[blob_key] = self.serde.dumps_typed(val)

                    loaded += 1
                except Exception as exc:
                    logger.warning("[PlainRedisSaver] 加载检查点失败 key=%s: %s", key, exc)

            if cursor == 0:
                break
            try:
                cursor, keys = await asyncio.wait_for(
                    self._redis.scan(cursor, match=f"{CKPT_PREFIX}:*", count=100),
                    timeout=3.0,
                )
            except (asyncio.TimeoutError, Exception):
                break

        if loaded > 0:
            logger.info("[PlainRedisSaver] 从 Redis 加载了 %d 个检查点", loaded)

    # ── 写入重写（同步到 Redis）──────────────────────────

    async def aput(self, config, checkpoint, metadata, new_versions):
        """保存检查点（先写内存，持久化到 Redis）。"""
        result = await super().aput(config, checkpoint, metadata, new_versions)
        if self._redis is not None:
            try:
                thread_id = config["configurable"]["thread_id"]
                ns = config["configurable"].get("checkpoint_ns", "")
                ckpt_id = checkpoint["id"]

                ckpt_type, ckpt_bytes = self.serde.dumps_typed(checkpoint)
                meta_type, meta_bytes = self.serde.dumps_typed(metadata)

                key = f"{CKPT_PREFIX}:{thread_id}:{ns}:{ckpt_id}"
                payload = {
                    "ckpt_type": ckpt_type,
                    "ckpt_data": ckpt_bytes.hex(),
                    "meta_type": meta_type,
                    "meta_data": meta_bytes.hex(),
                    "channel_values": checkpoint.get("channel_values", {}),
                    "channel_versions": checkpoint.get("channel_versions", {}),
                    "parent_checkpoint_id": (
                        result.get("configurable", {}).get("checkpoint_id")
                        if isinstance(result, dict)
                        else None
                    ),
                    "ts": time.time(),
                }
                pipe = self._redis.pipeline()
                pipe.set(key, json.dumps(payload, default=str), ex=CKPT_TTL)
                pipe.zadd(f"{CKPT_ZSET_PREFIX}:{thread_id}:{ns}", {ckpt_id: time.time()})
                await pipe.execute()
            except Exception as exc:
                logger.warning("[PlainRedisSaver] Redis 写入失败: %s", exc)
        return result

    async def adelete_thread(self, thread_id: str) -> None:
        """删除线程所有检查点（内存 + Redis）。"""
        await super().adelete_thread(thread_id)
        if self._redis is not None:
            try:
                pattern = f"{CKPT_PREFIX}:{thread_id}:*"
                cursor = 0
                while True:
                    cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
                    if keys:
                        await self._redis.delete(*keys)
                    if cursor == 0:
                        break
                zset_pattern = f"{CKPT_ZSET_PREFIX}:{thread_id}:*"
                cursor = 0
                while True:
                    cursor, keys = await self._redis.scan(cursor, match=zset_pattern, count=100)
                    if keys:
                        await self._redis.delete(*keys)
                    if cursor == 0:
                        break
                logger.info("[PlainRedisSaver] 线程 %s 已删除", thread_id)
            except Exception as exc:
                logger.warning("[PlainRedisSaver] 删除失败: %s", exc)
