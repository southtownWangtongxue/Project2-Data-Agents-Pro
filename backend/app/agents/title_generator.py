"""
TitleGenerator Agent —— 异步生成节点标题和会话标题

在 SSE 流完成后异步调用，不阻塞用户对话体验。
使用 LLM 根据用户问题和 AI 回答摘要生成 15 字以内的标题。
"""
import logging
from app.core.config import settings
from app.core.llm import get_model_name
from app.core.llm import get_llm

logger = logging.getLogger(__name__)


def _is_chinese_title(title: str, min_cjk_ratio: float = 0.4) -> bool:
    """标题是否为有效中文（至少含一定比例汉字，过滤英文/拼音标题）。

    弱模型（如 OpenRouter 免费模型）常输出 "The user is ask" 这类英文标题，
    这里做语言门禁，不合格即降级为问题截断标题。
    """
    if not title:
        return False
    cjk = sum(1 for ch in title if "\u4e00" <= ch <= "\u9fff")
    return cjk >= max(1, int(len(title) * min_cjk_ratio))


async def generate_node_title(question: str, answer_summary: str = "", provider: dict | None = None) -> str:
    """
    根据用户问题（含可选回答摘要）生成节点标题。

    参数:
        question: 用户提问原文
        answer_summary: AI 回答的前 200 字摘要（可选）
        provider: 显式 LLM provider（前端模型列表）；不传则使用上下文 provider，
                  绝不回退到 .env 的 settings。

    返回:
        15 字以内的中文标题。LLM 调用失败时返回降级标题。
    """
    client = get_llm(provider)

    # 构建 prompt 上下文
    context = f"用户提问: {question[:200]}"
    if answer_summary:
        context += f"\nAI回答摘要: {answer_summary[:200]}"

    system_prompt = (
        "你是一个对话标题生成器。根据用户的问题（和可选的AI回答摘要），"
        "生成一个简短的标题。\n\n"
        "硬性规则:\n"
        "- **必须使用简体中文**，禁止英文单词或拼音\n"
        "- 长度 8~15 个汉字，不超过 15 字\n"
        "- 只返回标题文本本身：不要引号、序号、前缀助词、解释、Markdown\n"
        "- 标题是一个名词短语（如「上月销售Top10查询」），不要写成句子\n"
        "- 数据查询类用「查询」开头；数据分析类用「分析」开头；"
        "统计汇总类用「统计」开头；帮助类用「帮助」开头；闲聊类直接概括话题\n\n"
        "示例:\n"
        "输入: 用户提问: 查询a_sheet1表上个月销售额Top10\n"
        "输出: 上月销售额Top10查询\n"
        "输入: 用户提问: 帮我分析用户增长趋势和留存率\n"
        "输出: 用户增长与留存分析\n"
        "输入: 用户提问: 你能做什么\n"
        "输出: 功能介绍\n"
        "输入: 用户提问: 你好，你是谁\n"
        "输出: 助手自我介绍\n"
    )

    try:
        response = await client.chat.completions.create(
            model=get_model_name(provider),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context},
            ],
            temperature=0.2,
            max_tokens=64,
        )
        title = response.choices[0].message.content.strip()
        # 去除可能的引号包裹
        title = title.strip('"' '"' "'" "'" '「' '」' '《' '》')
        # 限制长度 15 字（中文按字符计）
        if len(title) > 15:
            title = title[:15]
        # 语言校验：非中文标题（如 "The user is ask"）一律判为不合格，降级处理
        if title and _is_chinese_title(title):
            logger.info("[TitleGen] 节点标题生成: '%s'", title)
            return title
        if title:
            logger.warning("[TitleGen] 标题非中文('%s'),使用降级标题", title)
    except Exception as exc:
        logger.warning(f"[TitleGen] 标题生成失败，使用降级标题: {exc}")

    # 降级：截取问题前 15 字
    fallback = question.strip()[:15]
    logger.info("[TitleGen] 降级标题: '%s'", fallback)
    return fallback


async def generate_session_title(question: str, answer_summary: str = "", provider: dict | None = None) -> str:
    """
    为会话生成标题（通常使用第一轮节点的标题）。

    参数:
        question: 用户首次提问
        answer_summary: 首次 AI 回答摘要
        provider: 显式 LLM provider（前端模型列表），可选

    返回:
        15 字以内的会话标题
    """
    # 会话标题与节点标题生成方式一致，复用 generate_node_title
    return await generate_node_title(question, answer_summary, provider)
