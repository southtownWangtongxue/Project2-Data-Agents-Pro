"""
Misc Agent - 杂项助理
处理无法意图归类的问题
"""

from app.core.config import settings
from app.core.llm import get_model_name
from app.core.llm import get_llm
from app.core.reasoning import extract_reasoning
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
        '你是 DataAgent Pro 的智能助手，负责处理与业务数据相关的对话。\n\n'
        '你的任务:\n'
        '- 用户可能是打招呼、询问你是谁、询问系统能做什么，或提出其他问题\n'
        '- **先自然、友好地回应用户**：打招呼就直接问候；问你是谁就自我介绍；'
        '问能做什么就具体介绍下面的能力；提问就认真回答\n'
        '- 只有当用户的问题确实与本系统的数据能力无关时，才简要说明并引导到下面的能力范围\n'
        '- 不可生成 SQL 语句，不可调用知识库，也不可执行任何数据操作\n\n'
        '当前系统的能力范围:\n'
        '- 数据查询与分析：统计、筛选、排序、聚合、分组等\n'
        '- 数据库探索：查看表结构、字段说明、数据量统计\n'
        '- 数据可视化：生成柱状图、折线图、饼图等图表\n'
        '- 数据导出：导出为 CSV 或 Excel 格式\n'
        '- 使用帮助：查询系统使用方法\n\n'
        '回复风格:\n'
        '- 语气友好、清晰、不冗余（2~4 句）\n'
        '- **不要以「超出能力范围」之类的措辞开头**——先回应，再引导\n'
        '- 可举例说明系统能支持的问题类型\n\n'
        '输出要求:\n'
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
            # 思考增量优先推送(兼容 OpenRouter reasoning / Qwen reasoning_content)
            reasoning = extract_reasoning(chunk)
            if reasoning and ctx.queue:
                await ctx.push({"type": "reasoning", "content": reasoning, "agent": "misc_agent"})
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
        # 错误透明化：不再把异常文本伪装成回答内容返回（会被前端当正常回答渲染，
        # 用户看到"无法归类为查询数据: Error code: 404..."这类错误串）。
        # 向上抛出 → misc_node 不捕获 → 图执行异常 → chat.py 统一转 error 事件
        # （前端渲染错误卡片 + 重试按钮，UX 正确）。
        raise RuntimeError(f"回答生成失败（LLM 调用异常）: {e}") from e
