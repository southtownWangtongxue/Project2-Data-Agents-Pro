"""
Schema Agent - 元数据专家
根据用户意图动态从业务库加载相关表结构、字段注释
支持渐进式披露：先匹配表名，再加载详情
"""
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine
from app.core.config import settings
from app.core.llm import get_llm
from app.utils.log_utils import log


async def get_all_table_names(engine: AsyncEngine) -> list[str]:
    """获取数据库中所有表名（轻量，无字段详情）。"""

    def _sync_get(conn):
        return inspect(conn).get_table_names()

    async with engine.connect() as conn:
        return await conn.run_sync(_sync_get)


async def get_table_schemas(
    engine: AsyncEngine, table_names: list[str] | None = None
) -> str:
    """
    动态获取数据库表结构信息，返回格式化字符串供 LLM 作为上下文使用。

    参数:
        engine: SQLAlchemy 异步引擎
        table_names: 要获取的表名列表，为 None 时获取所有表

    返回:
        格式化的表结构字符串，示例格式如下：

        表名: orders
        列:
        - id (INTEGER, NOT NULL, 主键) - 订单ID
        - user_id (INTEGER, NOT NULL) - 用户ID
        - amount (DECIMAL(10,2), NOT NULL) - 订单金额
        - created_at (DATETIME) - 创建时间
    """

    def _sync_get_schemas(conn):
        inspector = inspect(conn)
        if table_names is None:
            tables = inspector.get_table_names()
        else:
            all_tables = inspector.get_table_names()
            tables = [t for t in table_names if t in all_tables]

        parts: list[str] = []
        for table in tables:
            lines = [f"表名: {table}", "列:"]
            pk_constraint = inspector.get_pk_constraint(table)
            pk_cols = set(pk_constraint.get("constrained_columns", []))

            for col in inspector.get_columns(table):
                col_name = col["name"]
                col_type = str(col["type"])
                nullable = "" if col.get("nullable", True) else ", NOT NULL"
                pk_tag = ", 主键" if col_name in pk_cols else ""
                default = col.get("default")
                default_str = f", 默认值={default}" if default is not None else ""
                comment = col.get("comment", "")
                comment_str = f" - {comment}" if comment else ""
                lines.append(
                    f"- {col_name} ({col_type}{nullable}{default_str}{pk_tag}){comment_str}"
                )
            parts.append("\n".join(lines))
        return "\n\n".join(parts) if parts else "（数据库中无用户表）"

    async with engine.connect() as conn:
        return await conn.run_sync(_sync_get_schemas)


async def match_tables_by_llm(
    all_table_names: list[str], user_intent: str
) -> list[str]:
    """
    渐进式披露：将所有表名交给 LLM，由 LLM 根据用户问题匹配相关表。

    参数:
        all_table_names: 数据库中所有表名列表
        user_intent: 用户自然语言问题

    返回:
        LLM 匹配到的相关表名列表（最多 10 个）
    """
    if not all_table_names:
        return []

    # 列出所有表名，每个一行，最多 5000 字符
    table_list = "\n".join(f"- {t}" for t in all_table_names)
    if len(table_list) > 5000:
        table_list = table_list[:5000] + "\n...（表过多，已截断）"

    client = get_llm()
    system_prompt = (
        "你是一个数据库表结构匹配专家。"
        "根据用户问题，从表名列表中找出最可能相关的表（最多 10 个）。\n\n"
        "规则：\n"
        "1. 输出纯 JSON 数组，如 [\"table_a\", \"table_b\"]\n"
        "2. 只输出确实存在于列表中的表名\n"
        "3. 优先匹配用户问题中明确提到的表名（模糊匹配）\n"
        "4. 如果用户问题中没有明确表名，根据语义推断可能的表\n"
        "5. 不要输出不相关的表名\n"
    )

    try:
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"## 可用表名\n{table_list}\n\n## 用户问题\n{user_intent}"},
            ],
            temperature=0.0,
            max_tokens=500,
        )
        content = response.choices[0].message.content.strip()
        # 清理 JSON 包裹
        if content.startswith("```"):
            lines = content.split("\n")
            lines = [l for l in lines if not l.startswith("```")]
            content = "\n".join(lines).strip()
        import json
        matched = json.loads(content)
        # 过滤只保留真实存在的表名
        valid = [t for t in matched if t in all_table_names]
        log.info(f"[SchemaAgent] LLM 匹配表名: 候选=({len(all_table_names)}), 命中={len(valid)}, 用户输入='{user_intent[:60]}'")
        return valid[:10]
    except Exception:
        log.warning("[SchemaAgent] LLM 匹配表名失败，回退到前 20 个表")
        return all_table_names[:20]


async def filter_relevant_tables(
    engine: AsyncEngine, user_intent: str
) -> list[str]:
    """
    渐进式披露：根据用户意图匹配相关表名。

    流程：
        1. 关键词快速匹配（含 LLM 语义匹配）
        2. 无匹配时 → 调用 LLM 从全部表名中筛选
        3. 兜底 → 返回前 20 个表名

    参数:
        engine: SQLAlchemy 异步引擎
        user_intent: 用户自然语言问题

    返回:
        匹配到的相关表名列表
    """
    all_tables = await get_all_table_names(engine)

    if not all_tables:
        return []

    # 第一轮：关键词模糊匹配
    user_lower = user_intent.lower()
    keyword_match = [t for t in all_tables if t.lower() in user_lower]

    if keyword_match:
        log.info(f"[SchemaAgent] 关键词匹配表名: {keyword_match}")
        return keyword_match

    # 第二轮：LLM 语义匹配（渐进式披露）
    return await match_tables_by_llm(all_tables, user_intent)
