"""
RAG Agent —— 知识库检索与增强回答

提供基于 Milvus 向量数据库的语义检索能力：
- retrieve_knowledge: 纯检索，返回相关文档片段
- answer_with_rag: 检索 + LLM 生成回答
- enhance_schema_with_rag: 用知识库补充表结构上下文
"""
import logging

from app.rag.retriever import search_similar
from app.core.llm import get_llm
from app.core.config import settings
from app.core.stream import get_stream_context

logger = logging.getLogger(__name__)


async def retrieve_knowledge(query: str, top_k: int = 5) -> str:
    """
    从 Milvus 知识库中检索与查询最相关的文档片段，拼接为上下文字符串。

    优雅降级策略：
    - 空查询或仅空白字符 → 返回空字符串
    - Milvus 不可用或检索失败 → 返回空字符串（不抛异常）

    参数:
        query: 用户查询文本
        top_k:  返回的最相关文档片段数

    返回:
        拼接后的检索结果字符串；无结果或失败时返回 ""
    """
    if not query or not query.strip():
        logger.debug("[RAGAgent] 空查询，跳过检索")
        return ""

    try:
        results = await search_similar(query, top_k=top_k)

        if not results:
            logger.info(f"[RAGAgent] 未检索到相关文档: {query[:60]}")
            return ""

        # 将检索结果拼接为 LLM 可用的上下文
        parts = []
        for i, item in enumerate(results, 1):
            score = item.get("score", 0)
            content = item.get("content", "")
            if content.strip():
                parts.append(f"[参考片段 {i} (相似度: {score:.2f})]\n{content}")

        context = "\n\n".join(parts)
        logger.info("[RAGAgent] 检索完成: 查询='%s...', 命中 %d 条", query[:50], len(results))
        return context

    except Exception as exc:
        # 任何异常都不应中断主流程
        logger.warning(f"[RAGAgent] 检索异常（已降级）: {exc}")
        return ""


async def answer_with_rag(question: str) -> str:
    """
    基于 RAG 检索结果调用 LLM 生成自然语言回答。

    流程：
    1. 调用 retrieve_knowledge() 检索相关文档
    2. 若检索到文档，构造 RAG prompt 让 LLM 基于上下文回答
    3. 若未检索到文档，使用通用回答 prompt
    4. LLM 调用失败时返回友好的降级消息

    参数:
        question: 用户问题

    返回:
        LLM 生成的回答文本
    """
    if not question or not question.strip():
        return "请提供您的问题。"

    # 1. 检索相关知识
    context = await retrieve_knowledge(question)

    # 2. 构造 prompt
    if context:
        system_prompt = (
            "你是一个智能业务数据助手。请基于以下知识库参考内容回答用户的问题。"
            "如果参考内容不足以回答问题，请如实说明。请以专业、友好的语气回答。\n\n"
            f"=== 知识库参考内容 ===\n{context}"
        )
    else:
        system_prompt = (
            "你是一个智能业务数据助手。当前知识库中暂无与该问题相关的资料，"
            "请基于你的通用知识以专业、友好的语气回答用户问题。"
            "如果涉及系统操作，建议用户查阅帮助文档或联系管理员。"
        )

    # 3. 调用 LLM（流式输出，实时推送 token）
    try:
        client = get_llm()
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            temperature=0.3,
            stream=True,
        )
        ctx = get_stream_context()
        content_chunks = []
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                content_chunks.append(token)
                if ctx.queue:
                    await ctx.push_token(token)
        answer = "".join(content_chunks).strip()
        logger.info(f"[RAGAgent] LLM 回答生成完成: {answer[:80]}")
        return answer

    except Exception as exc:
        logger.warning(f"[RAGAgent] LLM 调用失败: {exc}")
        return "抱歉，当前服务暂时不可用，请稍后再试。"


async def enhance_schema_with_rag(schema_info: str, question: str) -> str:
    """
    从知识库中检索与当前问题相关的补充信息，增强表结构上下文。

    用于在 Schema Agent 加载表结构后，额外补充业务指标定义、
    字段含义说明、常见查询模式等知识，提升 LLM 生成 SQL 的准确性。

    参数:
        schema_info: Schema Agent 加载的原始表结构描述
        question:    用户查询问题

    返回:
        增强后的表结构描述文本（原始 schema_info + RAG 检索结果）
    """
    if not question or not question.strip():
        return schema_info

    try:
        # 检索与问题相关的业务知识
        knowledge = await retrieve_knowledge(question, top_k=3)

        if not knowledge:
            logger.debug("[RAGAgent] 无额外知识可补充 schema")
            return schema_info

        # 将知识库内容追加到 schema 描述末尾
        enhanced = (
            f"{schema_info}\n\n"
            f"=== 以下为知识库中相关的业务知识（可辅助 SQL 生成） ===\n"
            f"{knowledge}"
        )
        logger.info(f"[RAGAgent] Schema 增强完成，追加 {len(knowledge.split("[参考片段"))} 条知识")
        return enhanced

    except Exception as exc:
        logger.warning(f"[RAGAgent] Schema 增强失败（已降级）: {exc}")
        return schema_info
