"""
Milvus 向量检索
从知识库中检索与查询最相关的文档片段
"""
import logging

from app.core.config import settings
from app.rag.embeddings import embed_texts, _ensure_milvus_connection

logger = logging.getLogger(__name__)

# ── Milvus 优雅降级 ─────────────────────────────────────────────────────
try:
    from pymilvus import (  # type: ignore[import-untyped]
        Collection,
        utility,
        MilvusException,
    )
    _MILVUS_AVAILABLE = True
except ImportError:
    _MILVUS_AVAILABLE = False


# ── 向量检索 ────────────────────────────────────────────────────────────


async def search_similar(
    query: str,
    collection_name: str = "knowledge_base",
    top_k: int = 5,
) -> list[dict]:
    """
    在 Milvus 知识库中搜索与查询文本最相似的文档片段。

    流程：
    1. 将查询文本通过 embeddings API 向量化
    2. 在指定 Milvus collection 中执行 ANN（近似最近邻）搜索
    3. 返回余弦相似度最高的 top_k 个结果

    参数:
        query: 用户查询文本
        collection_name: 目标 Milvus collection 名称，默认使用配置值
        top_k: 返回的最相似结果数量，默认 5

    返回:
        搜索结果列表，每个元素为 dict:
            - content (str):  匹配到的文档片段原文
            - score (float):  余弦相似度得分，越接近 1 越相似
            - metadata (dict): 附加元数据（预留字段）
        如果 Milvus 不可用、collection 不存在或搜索失败，返回空列表（优雅降级）。
    """
    if not query or not query.strip():
        return []

    used_collection = collection_name or settings.MILVUS_COLLECTION_NAME

    # 1. 向量化查询文本
    query_embeddings = await embed_texts([query])
    if not query_embeddings:
        logger.warning("查询向量化失败，无法执行检索")
        return []

    query_vector = query_embeddings[0]

    # 2. 连接 Milvus 并获取 collection
    if not _MILVUS_AVAILABLE or not _ensure_milvus_connection():
        return []

    try:
        if not utility.has_collection(used_collection):
            logger.warning("Milvus collection '%s' 不存在", used_collection)
            return []

        collection = Collection(used_collection)
        collection.load()

        # 3. 执行 ANN 搜索
        search_params = {
            "metric_type": "COSINE",
            "params": {"nprobe": 16},
        }
        results = collection.search(
            data=[query_vector],
            anns_field="vector",
            param=search_params,
            limit=top_k,
            output_fields=["content", "metadata"],
        )

        # 4. 格式化返回结果
        formatted: list[dict] = []
        for hits in results:
            for hit in hits:
                formatted.append({
                    "content": hit.entity.get("content", ""),
                    "score": float(hit.distance),
                    "metadata": hit.entity.get("metadata", {}),
                })

        logger.info("检索完成: 查询='%s...', 命中 %d 条", query[:50], len(formatted))
        return formatted

    except MilvusException as e:
        logger.warning(f"Milvus 搜索失败: {e}")
        return []


# ── Collection 信息查询 ─────────────────────────────────────────────────


async def get_collection_info(collection_name: str = "knowledge_base") -> dict:
    """
    获取指定 Milvus collection 的统计信息。

    不会抛出异常，所有错误信息通过返回 dict 中的字段体现。

    参数:
        collection_name: collection 名称，默认使用配置值

    返回:
        dict 包含:
            - available (bool):     Milvus 服务是否可用
            - name (str):          collection 名称
            - num_entities (int):  collection 中的文档片段数量
            - error (str):         错误信息（仅在异常时存在此字段）
    """
    used_collection = collection_name or settings.MILVUS_COLLECTION_NAME

    # 检查 pymilvus 是否安装
    if not _MILVUS_AVAILABLE:
        return {
            "available": False,
            "name": used_collection,
            "num_entities": 0,
            "error": "pymilvus 未安装",
        }

    # 检查 Milvus 连接
    if not _ensure_milvus_connection():
        return {
            "available": False,
            "name": used_collection,
            "num_entities": 0,
            "error": "无法连接到 Milvus 服务",
        }

    try:
        if not utility.has_collection(used_collection):
            return {
                "available": True,
                "name": used_collection,
                "num_entities": 0,
            }

        collection = Collection(used_collection)
        collection.load()
        num = collection.num_entities

        return {
            "available": True,
            "name": used_collection,
            "num_entities": num,
        }

    except MilvusException as e:
        return {
            "available": False,
            "name": used_collection,
            "num_entities": 0,
            "error": str(e),
        }
