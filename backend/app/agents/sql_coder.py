"""
SQL Coder Agent - 编码专家
接收精简后的 Schema 和用户问题，生成目标方言 SQL
具备 SQL 自校正能力（最多重试 2 次）
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import settings
from app.core.llm import get_model_name
from app.core.llm import get_llm
from app.core.stream import get_stream_context


async def generate_sql(
    user_question: str,
    schema_info: str,
    dialect: str = "mysql",
) -> str:
    """
    调用 LLM 根据用户问题和表结构信息生成 SQL。

    参数:
        user_question: 用户自然语言问题
        schema_info: 数据库表结构字符串（由 Schema Agent 提供）
        dialect: 目标 SQL 方言，默认 mysql

    返回:
        纯 SQL 语句字符串（已去除 markdown 代码块标记）
    """
    client = get_llm()

    system_prompt = (
        "你是一个专业的 SQL 编码专家。"
        "根据提供的数据库表结构信息和用户问题，生成正确的 SQL 查询语句。\n\n"
        "严格要求：\n"
        "1. 只返回纯 SQL 语句，不要使用 markdown 代码块\n"
        "2. 不要添加任何解释、注释或描述性文字\n"
        "3. 只返回一条可执行的 SQL 语句\n"
        f"4. 使用 {dialect} 方言语法\n"
        "5. 如果用户问题无法用 SQL 回答，返回：SELECT '无法回答此问题' AS message;"
    )

    user_message = (
        f"## 数据库表结构\n\n{schema_info}\n\n"
        f"## 用户问题\n\n{user_question}\n\n"
        f"请生成 {dialect} SQL 语句："
    )

    response = await client.chat.completions.create(
        model=get_model_name(),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.1,
        stream=True,
    )

    ctx = get_stream_context()
    content_chunks = []
    async for chunk in response:
        if chunk.choices and chunk.choices[0].delta.content:
            token = chunk.choices[0].delta.content
            content_chunks.append(token)
            # 不推送 token：SQL 内容短，由格式化 SQL 卡片展示，避免前端重复显示
    sql = "".join(content_chunks).strip()
    sql = _clean_sql(sql)
    return sql


async def execute_sql(engine: AsyncEngine, sql: str) -> dict:
    """
    执行 SQL 语句并返回结果。

    参数:
        engine: SQLAlchemy 异步引擎
        sql: 要执行的 SQL 语句

    返回:
        {"success": bool, "data": list[dict], "error": str | None}
        其中 data 为查询结果行列表，每行为一个字典；
        非查询语句时 data 包含 affected_rows 信息。
    """
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text(sql))

            # 尝试获取返回行（适用于 SELECT 语句）
            try:
                rows = result.fetchall()
                if rows:
                    columns = list(result.keys())
                    data = [dict(zip(columns, row)) for row in rows]
                else:
                    data = [{"affected_rows": result.rowcount}]
            except Exception:
                # 非查询语句（INSERT/UPDATE/DELETE），结果集中无行
                data = [{"affected_rows": result.rowcount}]

            await conn.commit()

            return {"success": True, "data": data, "error": None}
    except Exception as e:
        return {"success": False, "data": [], "error": str(e)}


async def generate_and_execute_sql(
    user_question: str,
    engine: AsyncEngine,
    schema_info: str,
    dialect: str = "mysql",
    max_retries: int = 2,
    initial_sql: str = "",
) -> dict:
    """
    生成 SQL 并执行，执行失败时自动将错误反馈给 LLM 进行重试修正。

    组合 generate_sql + execute_sql，执行失败时将错误信息附加到
    prompt 中重新调用 LLM 生成修正后的 SQL，最多重试 max_retries 次。

    参数:
        user_question: 用户自然语言问题
        engine: SQLAlchemy 异步引擎
        schema_info: 数据库表结构字符串（由 Schema Agent 提供）
        dialect: 目标 SQL 方言，默认 mysql
        max_retries: 最大重试次数，默认 2
        initial_sql: 已生成的初始 SQL（如从工作流状态传入），非空时跳过重新生成

    返回:
        {
            "success": bool,
            "sql": str（最终生成的 SQL）,
            "data": list[dict],
            "error": str | None,
            "retries": int
        }
    """
    # 优先使用工作流传入的已有 SQL，否则重新生成
    if initial_sql:
        sql = initial_sql
    else:
        sql = await generate_sql(user_question, schema_info, dialect)

    # 尝试执行
    result = await execute_sql(engine, sql)
    retries = 0

    # 自校正循环：执行失败时将错误信息反馈给 LLM 重新生成
    while not result["success"] and retries < max_retries:
        retries += 1
        sql = await _generate_sql_with_error(
            user_question=user_question,
            schema_info=schema_info,
            dialect=dialect,
            previous_sql=sql,
            error_message=result["error"],
        )
        result = await execute_sql(engine, sql)

    return {
        "success": result["success"],
        "sql": sql,
        "data": result["data"],
        "error": result["error"],
        "retries": retries,
    }


async def _generate_sql_with_error(
    user_question: str,
    schema_info: str,
    dialect: str,
    previous_sql: str,
    error_message: str,
) -> str:
    """
    将 SQL 执行错误信息反馈给 LLM，要求其生成修正后的 SQL。

    参数:
        user_question: 用户原始问题
        schema_info: 表结构信息
        dialect: SQL 方言
        previous_sql: 之前执行失败的 SQL
        error_message: 数据库返回的错误信息

    返回:
        修正后的纯 SQL 字符串
    """
    client = get_llm()

    system_prompt = (
        "你是一个专业的 SQL 编码专家。"
        "之前生成的 SQL 执行失败，请根据错误信息分析原因并修正 SQL。\n\n"
        "严格要求：\n"
        "1. 只返回修正后的纯 SQL 语句，不要使用 markdown 代码块\n"
        "2. 不要添加任何解释、注释或描述性文字\n"
        f"3. 使用 {dialect} 方言语法"
    )

    user_message = (
        f"## 数据库表结构\n\n{schema_info}\n\n"
        f"## 用户问题\n\n{user_question}\n\n"
        f"## 之前生成的 SQL（执行失败）\n\n```sql\n{previous_sql}\n```\n\n"
        f"## 数据库返回的错误信息\n\n{error_message}\n\n"
        "请分析错误原因并修正 SQL："
    )

    response = await client.chat.completions.create(
        model=get_model_name(),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.1,
    )

    sql = response.choices[0].message.content.strip()
    sql = _clean_sql(sql)
    return sql


def _clean_sql(sql: str) -> str:
    """
    清理 LLM 返回的 SQL 字符串：去除可能的 markdown 代码块标记。

    参数:
        sql: 原始 SQL 字符串

    返回:
        清理后的纯 SQL 字符串
    """
    if sql.startswith("```"):
        lines = sql.split("\n")
        # 去掉首行标记（``` 或 ```sql）
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        # 去掉尾行标记（```）
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        sql = "\n".join(lines)

    return sql.strip()
