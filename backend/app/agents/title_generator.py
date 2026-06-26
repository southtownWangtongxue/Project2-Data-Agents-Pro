"""
TitleGenerator Agent —— 异步生成节点标题和会话标题

在 SSE 流完成后异步调用，不阻塞用户对话体验。
使用 LLM 根据用户问题和 AI 回答摘要生成 15 字以内的标题。
"""
import logging
from app.core.config import settings
from app.core.llm import get_llm

logger = logging.getLogger(__name__)


async def generate_node_title(question: str, answer_summary: str = "") -> str:
    """
    根据用户问题（含可选回答摘要）生成节点标题。

    参数:
        question: 用户提问原文
        answer_summary: AI 回答的前 200 字摘要（可选）

    返回:
        15 字以内的中文标题。LLM 调用失败时返回降级标题。
    """
    client = get_llm()

    # 构建 prompt 上下文
    context = f"用户提问: {question[:200]}"
    if answer_summary:
        context += f"\nAI回答摘要: {answer_summary[:200]}"

    system_prompt = (
        "你是一个对话标题生成器。根据用户的问题（和可选的AI回答摘要），"
        "生成一个简短的标题（15字以内，中文）。\n\n"
        "规则:\n"
        "- 标题必须简洁，能概括本轮对话的核心主题\n"
        "- 只返回标题文本，不要添加引号、序号或其他符号\n"
        "- 如果问题涉及数据查询，用「查询」开头\n"
        "- 如果问题涉及数据分析，用「分析」开头\n"
        "- 如果问题涉及统计汇总，用「统计」开头\n"
        "- 如果是帮助类问题，用「帮助」开头\n\n"
        "示例:\n"
        "输入: 用户提问: 查询a_sheet1表上个月销售额Top10\n"
        "输出: 上月销售Top10查询\n"
        "输入: 用户提问: 帮我分析用户增长趋势和留存率\n"
        "输出: 用户增长与留存分析\n"
        "输入: 用户提问: 你能做什么\n"
        "输出: 功能介绍\n"
    )

    try:
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context},
            ],
            temperature=0.3,
            max_tokens=50,
        )
        title = response.choices[0].message.content.strip()
        # 去除可能的引号包裹
        title = title.strip('"' '"' "'" "'" '「' '」' '《' '》')
        # 限制长度 15 字（中文按字符计）
        if len(title) > 15:
            title = title[:15]
        if title:
            logger.info("[TitleGen] 节点标题生成: '%s'", title)
            return title
    except Exception as exc:
        logger.warning("[TitleGen] 标题生成失败，使用降级标题: %s", exc)

    # 降级：截取问题前 15 字
    fallback = question.strip()[:15]
    logger.info("[TitleGen] 降级标题: '%s'", fallback)
    return fallback


async def generate_session_title(question: str, answer_summary: str = "") -> str:
    """
    为会话生成标题（通常使用第一轮节点的标题）。

    参数:
        question: 用户首次提问
        answer_summary: 首次 AI 回答摘要

    返回:
        15 字以内的会话标题
    """
    # 会话标题与节点标题生成方式一致，复用 generate_node_title
    return await generate_node_title(question, answer_summary)
