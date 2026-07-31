"""
Misc Agent - 杂项助理
处理无法意图归类的问题
"""

from app.core.config import settings
from app.core.llm import get_model_name
from app.core.llm import get_llm
from app.core.stream import get_stream_context
from app.utils.log_utils import log


async def misc_agent(user_question: str) -> dict:
    """
    调用 LLM 流式生成回复，实时推送 token 到前端。

    参数:
        user_question: 用户输入的自然语言问题

    返回:
        {"content": "..."}

        若 LLM 返回解析失败，返回错误兜底。
    """
    client = get_llm()

    system_prompt = (
        '你是系统的友好助手，专门处理\u201c不在业务范围内\u201d的用户问题。\n\n'
        '你的任务：\n'
        '- 用户当前的问题无法归类为查询数据（query_data）、询问帮助（ask_help）或修改数据（write_data）\n'
        '- 你不可生成 SQL 语句，不可调用知识库，也不可执行任何数据操作\n'
        '- 你需要礼貌地告知用户：该问题超出了本系统的能力范围，并引导用户提出与系统功能相关的问题\n\n'
        '当前系统的能力范围：\n'
        '- 数据查询与分析：统计、筛选、排序、聚合、分组等\n'
        '- 数据库探索：查看表结构、字段说明、数据量统计\n'
        '- 数据可视化：生成柱状图、折线图、饼图等图表\n'
        '- 数据导出：导出为 CSV 或 Excel 格式\n'
        '- 使用帮助：查询系统使用方法\n\n'
        '回复风格：\n'
        '- 语气友好、清晰、不冗余\n'
        '- 当用户问题超出范围时，明确告知并引导到上述能力范围内\n'
        '- 可举例说明系统能支持的问题类型\n\n'
        '输出要求：\n'
        '- 只输出回复文本，不要包含 JSON、代码块或额外说明'
    )

    try:
        response = await client.chat.completions.create(
            model=get_model_name(),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_question},
            ],
            temperature=1.0,
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
        content = "".join(content_chunks).strip()
        log.info(f"misc_agent->content:{content[:80]}...")
        return {"content": content}

    except Exception as e:
        log.exception(f"misc_agent->Exception:{e}")
        return {"content": f"无法归类为查询数据: {str(e)}"}
