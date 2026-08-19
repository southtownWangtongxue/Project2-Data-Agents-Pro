"""
Question Suggester Agent — 基于数据库表结构生成自然语言问题模板

系统启动后自动加载目标数据库的全部表结构，调用 LLM 分析表名、字段名、
字段注释，生成 3-5 条符合实际数据场景的自然语言分析问题。
这些问题用于替换前端硬编码的「查询本月销售额Top10产品」等模板。
"""

import json
import logging
from app.core.llm import get_llm
from app.core.config import settings
from app.core.llm import get_model_name

logger = logging.getLogger(__name__)

# 模块级缓存：避免每次请求都调用 LLM
_cached_suggestions: list[str] | None = None
_cached_schema_hash: str | None = None


SUGGESTER_SYSTEM_PROMPT = """你是一个数据分析助手。下面提供的是用户数据库中所有表的完整表结构，
包括表名、字段名、字段类型、字段注释（如有）。

请根据这些表结构，生成 3 到 5 条自然语言数据分析问题。
这些问题是给用户作为"问题模板"展示的，用户点击即可直接提问。

要求：
1. 每条问题必须基于真实存在的表和字段，不能编造不存在的表或字段
2. 问题尽量多样化，涵盖不同表和分析角度（如排名、趋势、占比、对比、汇总等）
3. 使用中文提问，语气自然，像人类分析师会问的问题
4. 问题应该具体且可执行，让后续 SQL 生成能直接处理
5. 每条问题长度适中（10-30 个字）

请严格按照以下 JSON 格式输出，不要包含其他文字：
{
  "questions": ["问题1", "问题2", "问题3", "问题4", "问题5"]
}"""


async def generate_question_suggestions(
    schema_text: str,
    force_refresh: bool = False,
    provider: dict | None = None,
) -> list[str]:
    """
    基于表结构文本生成推荐问题列表。

    参数:
        schema_text: 格式化的表结构文本
        force_refresh: 是否强制刷新（忽略缓存）
        provider: 显式 LLM provider（前端模型列表）；不传则使用上下文 provider，
                  绝不回退到 .env 的 settings

    返回:
        推荐问题字符串列表，如 ["查询本月销售额Top10产品", ...]
    """
    global _cached_suggestions, _cached_schema_hash

    schema_hash = str(hash(schema_text))

    # 如果表结构未变且不强制刷新，直接返回缓存
    if not force_refresh and _cached_suggestions is not None and _cached_schema_hash == schema_hash:
        logger.info("[QuestionSuggester] 使用缓存的问题建议")
        return _cached_suggestions

    # 如果表结构为空，返回通用兜底问题
    if not schema_text or schema_text.strip() == "":
        return [
            "帮我分析一下数据库中有哪些数据",
            "查看数据库表结构概览",
            "统计数据库中的记录数量",
        ]

    logger.info("[QuestionSuggester] 正在调用 LLM 生成问题建议...")

    client = get_llm(provider)

    try:
        response = await client.chat.completions.create(
            model=get_model_name(provider),
            messages=[
                {"role": "system", "content": SUGGESTER_SYSTEM_PROMPT},
                {"role": "user", "content": f"以下是数据库的表结构信息：\n\n{schema_text}"},
            ],
            temperature=0.7,  # 稍高温度以获得多样化的问题
        )

        content = response.choices[0].message.content.strip()

        # 尝试解析 JSON 响应
        # LLM 可能在 JSON 外包裹 markdown 代码块标记
        if content.startswith("```"):
            lines = content.split("\n")
            # 去掉首尾的 ``` 标记行
            content = "\n".join(
                line for line in lines if not line.strip().startswith("```")
            ).strip()

        try:
            data = json.loads(content)
            questions: list[str] = data.get("questions", [])
        except json.JSONDecodeError:
            # JSON 解析失败，尝试按行提取问题
            logger.warning("[QuestionSuggester] JSON 解析失败，尝试按行提取")
            questions = [
                line.strip().lstrip("0123456789.、- ").strip('"')
                for line in content.split("\n")
                if line.strip() and len(line.strip()) > 5
            ]

        # 确保至少有 3 个问题
        result = questions[:5] if len(questions) >= 5 else questions[:]

        if len(result) < 3:
            logger.warning(f"[QuestionSuggester] 生成的问题不足 3 个：{result}")
            result = ["请帮我查询数据库中的关键数据"] + result

        # 写入缓存
        _cached_suggestions = result
        _cached_schema_hash = schema_hash

        logger.info(f"[QuestionSuggester] 成功生成 {len(result)} 条问题建议")
        return result

    except Exception as e:
        logger.error(f"[QuestionSuggester] LLM 调用失败: {e}")
        # 降级返回通用问题
        return [
            "帮我分析一下数据库中有哪些数据",
            "查看数据库表结构概览",
            "统计数据库中的记录数量",
        ]


def get_cached_suggestions() -> list[str] | None:
    """获取当前缓存的问题建议（不触发 LLM 调用）"""
    return _cached_suggestions


def clear_cache() -> None:
    """清空问题建议缓存"""
    global _cached_suggestions, _cached_schema_hash
    _cached_suggestions = None
    _cached_schema_hash = None
