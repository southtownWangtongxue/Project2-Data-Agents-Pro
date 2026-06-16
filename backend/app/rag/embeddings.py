"""
文档切片与向量化
将知识库文档转换为向量存入 Milvus
"""
import re
import logging
from typing import Optional
from langchain_huggingface.embeddings import HuggingFaceEmbeddings
from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Milvus 相关导入（优雅降级：pymilvus 未安装时功能不可用但不阻塞主流程）──
try:
    from pymilvus import (  # type: ignore[import-untyped]
        connections as milvus_connections,
        Collection,
        FieldSchema,
        CollectionSchema,
        DataType,
        utility,
        MilvusException,
    )

    _MILVUS_AVAILABLE = True
except ImportError:
    _MILVUS_AVAILABLE = False
    logger.warning("pymilvus 未安装，向量存储功能不可用")


# ── 文本切分 ────────────────────────────────────────────────────────────


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """
    将长文本按句子边界切分成 chunk，每个 chunk 不超过 chunk_size 字符。

    切分策略：
    1. 先按段落（双换行 \\n\\n）切分，保留文档的自然段落结构
    2. 对超过 chunk_size 的段落，按句子边界（。！？.!? 换行等）进一步切分
    3. 相邻 chunk 之间保留 overlap 字符的重叠，确保上下文语义连贯
    4. 尽可能不在句子中间切断；单句超长时退化为按固定长度切分

    参数:
        text: 待切分的原始文本
        chunk_size: 每个 chunk 的最大字符数，默认 500
        overlap: 相邻 chunk 之间的重叠字符数，默认 50

    返回:
        切分后的文本片段列表。输入为空时返回空列表。
    """
    if not text or not text.strip():
        return []

    # 第 1 步：按段落切分
    paragraphs = text.split("\n\n")
    chunks: list[str] = []

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # 短段落直接作为 chunk
        if len(para) <= chunk_size:
            chunks.append(para)
            continue

        # 第 2 步：段落过长，按句子边界切分
        # 匹配中文和英文句子的结束标记
        sentences = re.split(r"(?<=[。！？.!?\n])\s*", para)
        current_chunk = ""

        for sentence in sentences:
            sentence_clean = sentence.strip()
            if not sentence_clean:
                continue

            # 特殊情况：单个句子仍然超过 chunk_size，强制按字符切
            if len(sentence_clean) > chunk_size:
                # 先保存当前积累的 chunk
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                    # 新 chunk 以 overlap 开头
                    overlap_text = (
                        current_chunk[-overlap:]
                        if len(current_chunk) > overlap
                        else current_chunk
                    )
                else:
                    overlap_text = ""

                # 按固定步长切分超长句子
                step = chunk_size - overlap
                for i in range(0, len(sentence_clean), step):
                    sub = sentence_clean[i: i + chunk_size]
                    if sub.strip():
                        chunks.append(sub.strip())
                current_chunk = ""
                continue

            # 判断加入当前句子后是否超出 chunk_size
            if len(current_chunk) + len(sentence) <= chunk_size:
                current_chunk += sentence
            else:
                # 当前 chunk 已满，保存并开启新 chunk（含 overlap）
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                overlap_text = (
                    current_chunk[-overlap:]
                    if len(current_chunk) > overlap
                    else current_chunk
                )
                current_chunk = overlap_text + sentence

        # 收尾：保存最后一个 chunk
        if current_chunk.strip():
            chunks.append(current_chunk.strip())

    # 过滤掉空白 chunk
    return [c for c in chunks if c.strip()]


# ── 向量化 ──────────────────────────────────────────────────────────────


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    调用 OpenAI 兼容 API 的 embeddings 接口将文本转为向量。

    使用 settings.EMBEDDING_MODEL 指定的模型名称，通过
    settings.LLM_BASE_URL 和 settings.LLM_API_KEY 进行认证。
    若 LLM API 不支持 embeddings 端点，捕获异常并返回空列表。

    参数:
        texts: 待向量化的文本列表

    返回:
        向量列表，每个向量为 float 列表；如果 API 不支持或调用失败则返回空列表。
    """
    if not texts:
        return []

    client = HuggingFaceEmbeddings(
        model_name='BAAI/bge-large-zh-v1.5',
        model_kwargs={
            'device': 'cuda',
            # 'device': 'cpu',
        },
        encode_kwargs={'normalize_embeddings': True}  # set True to compute cosine similarity
    )

    try:
        # ── 注意：HuggingFaceEmbeddings.embed_documents() 直接返回 List[List[float]] ──
        # 不是 OpenAI 风格的 response 对象，不需要 .data / .embedding 属性访问
        embeddings = client.embed_documents(texts)
        dim = len(embeddings[0]) if embeddings else 0
        logger.info("成功向量化 %d 条文本，维度=%d", len(embeddings), dim)
        return embeddings

    except Exception as e:
        logger.warning("调用 embeddings 失败（模型=%s）: %s", settings.EMBEDDING_MODEL, e)
        return []


# ── Milvus 连接与 Collection 管理（模块内部使用） ─────────────────────


def _ensure_milvus_connection() -> bool:
    """确保已建立 Milvus 连接，返回连接是否成功。"""
    if not _MILVUS_AVAILABLE:
        return False
    try:
        if not milvus_connections.has_connection("default"):
            milvus_connections.connect(
                "default",
                host=settings.MILVUS_HOST,
                port=settings.MILVUS_PORT,
            )
            logger.info("已连接到 Milvus: %s:%d", settings.MILVUS_HOST, settings.MILVUS_PORT)
        return True
    except MilvusException as e:
        logger.warning("连接 Milvus 失败: %s", e)
        return False


def _get_or_create_collection(collection_name: str, dim: int) -> Optional[Collection]:
    """
    获取或创建 Milvus collection，确保向量索引已建立。

    参数:
        collection_name: Milvus collection 名称
        dim: 向量维度（由 embedding 模型决定）

    返回:
        Collection 对象；连接或创建失败时返回 None。
    """
    if not _ensure_milvus_connection():
        return None

    try:
        if utility.has_collection(collection_name):
            collection = Collection(collection_name)
        else:
            # 定义 collection 字段结构
            fields = [
                FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
                FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=dim),
                FieldSchema(name="metadata", dtype=DataType.JSON),
            ]
            schema = CollectionSchema(fields, description="知识库文档向量存储")
            collection = Collection(collection_name, schema)
            logger.info("创建 Milvus collection '%s'，向量维度=%d", collection_name, dim)

            # 创建 IVF_FLAT 向量索引，使用余弦相似度
            index_params = {
                "metric_type": "COSINE",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128},
            }
            collection.create_index("vector", index_params)
            logger.info("为 collection '%s' 创建向量索引", collection_name)

        # 加载 collection 到内存
        collection.load()
        return collection

    except MilvusException as e:
        logger.warning("操作 Milvus collection 失败: %s", e)
        return None


# ── 切分 → 向量化 → 入库 一体化流程 ───────────────────────────────────


async def embed_and_store(
        texts: list[str],
        collection_name: str = "knowledge_base",
) -> int:
    """
    文本切片 + 向量化 + Milvus 入库的完整流水线。

    流程：
    1. 对每条文本调用 chunk_text 切分为小片段
    2. 调用 embed_texts 将所有片段向量化
    3. 将向量及原文存入 Milvus collection

    参数:
        texts: 待入库的文本列表，每条通常为一个文档的完整内容
        collection_name: 目标 Milvus collection 名称，默认使用 settings.MILVUS_COLLECTION_NAME

    返回:
        成功存入的向量/片段数量。任何环节失败均返回 0。
    """
    if not texts:
        return 0

    used_collection = collection_name or settings.MILVUS_COLLECTION_NAME

    # 1. 切分文本
    all_chunks: list[str] = []
    for text in texts:
        chunks = chunk_text(text)
        all_chunks.extend(chunks)

    if not all_chunks:
        logger.warning("文本切分后无有效内容")
        return 0

    logger.info("文本切分完成: %d 个片段", len(all_chunks))

    # 2. 向量化
    embeddings = await embed_texts(all_chunks)
    if not embeddings:
        logger.warning("向量化失败，无法存入 Milvus")
        return 0

    if len(embeddings) != len(all_chunks):
        logger.warning("向量数量(%d)与文本片段数量(%d)不一致", len(embeddings), len(all_chunks))
        return 0

    # 3. 存入 Milvus
    dim = len(embeddings[0])
    collection = _get_or_create_collection(used_collection, dim)
    if collection is None:
        return 0

    try:
        data = [
            all_chunks,  # content 字段
            embeddings,  # vector 字段
            [{}] * len(all_chunks),  # metadata 字段（预留扩展）
        ]
        insert_result = collection.insert(data)
        collection.flush()
        count = len(insert_result.primary_keys)
        logger.info("成功存入 %d 条向量到 collection '%s'", count, used_collection)
        return count

    except MilvusException as e:
        logger.warning("写入 Milvus 失败: %s", e)
        return 0
