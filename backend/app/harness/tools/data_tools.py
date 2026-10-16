"""Harness 数据工具层(Phase 0)。

把现有 agents 能力封装为 LangChain 工具契约(纯 async 函数 + docstring + 类型标注),
供 Phase 1 的 Harness 主循环挂载。

职责边界(重要):
- 本模块只含"能力",不含任何安全闸逻辑。run_sql 的执行安全闸在
  app/harness/sql_gate_middleware.py 的中间件层,直接裸调 run_sql 是危险的,
  Phase 1 起所有挂载路径必须包含 SqlGateMiddleware。
- 所有工具返回字符串(JSON 或文本):适配 R9 流水线的截断与 LangChain 工具协议。
- 失败语义分两层:业务失败(execute_sql 返回 success=false)以 JSON 返回、
  不抛异常,由模型观察后自行修正;基础设施异常(DB 连接失败/LLM 调用异常)
  会向上传播,由 R9 流水线兜底为错误字符串——因此挂载本模块时必须启用
  R9 流水线(TOOL_PIPELINE_ENABLED=true,默认开启)。
- run_sql 行数上限 MAX_ROWS:超出只返回前 N 行,并告知 row_count,
  防止大结果集撑爆上下文。
"""
from __future__ import annotations

import json
import time

from app.agents.rag_agent import answer_with_rag
from app.agents.reporter import generate_chart_config
from app.agents.schema_agent import filter_relevant_tables, get_table_schemas
from app.agents.sql_coder import execute_sql
from app.db.session import get_engine
from app.utils.log_utils import log

MAX_ROWS = 200


def _dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


async def get_table_schema(keywords: str = "") -> str:
    """获取业务数据库表结构(只读)。

    生成 SQL 前必须先调用本工具了解表与字段,禁止凭记忆猜测表名。

    Args:
        keywords: 可选,与问题相关的关键词(表名/字段名/业务词)。为空时返回
            全库结构;提供关键词则由 LLM 筛选相关表(约 10 张以内,可显著
            降低 Token 消耗)。

    Returns:
        表结构文本(建表语句/字段注释);未获取到时返回提示文本。
    """
    engine = get_engine()
    # 空关键词不过滤,直接取全库结构(过滤器的空 intent 会退化为 LLM 盲选约 10 张)
    relevant = await filter_relevant_tables(engine, keywords) if keywords.strip() else None
    schema_text = await get_table_schemas(engine, relevant)
    if not schema_text:
        return "未获取到任何表结构,请检查数据库连接或更换关键词。"
    return schema_text


async def run_sql(sql: str, purpose: str) -> str:
    """在业务数据库上执行一条 SQL(必须经 SqlGateMiddleware 安全闸后方可到达)。

    Args:
        sql: 待执行的 SQL 语句(单条,MySQL 方言)。
        purpose: 本次执行的目的(一句话,经 R9 流水线 pre-execute 写入审计日志)。

    Returns:
        JSON 字符串,字段:success / sql / row_count / returned_rows / truncated /
        columns / rows / duration_ms / error。失败时 success=false 且 error
        说明原因,请根据 error 修正 SQL 后重试,或换一种问法。
        注意:row_count 为结果集行数——查询无匹配行时 rows=[] 且 row_count=0,
        如实告知用户「查无数据」,不要虚构数字;非 SELECT 语句恒为 1,实际影响
        行数见 rows[0].affected_rows;truncated=true 表示结果超过 MAX_ROWS 已被
        截断,请用 WHERE/LIMIT 缩小范围后重查。
    """
    t0 = time.monotonic()
    engine = get_engine()
    result = await execute_sql(engine, sql)
    duration_ms = int((time.monotonic() - t0) * 1000)

    if not result.get("success"):
        log.warning("[run_sql] 失败 purpose=%s sql=%s err=%s", purpose, sql[:200], result.get("error"))
        return _dumps({
            "success": False,
            "sql": sql,
            "row_count": 0,
            "returned_rows": 0,
            "truncated": False,
            "columns": [],
            "rows": [],
            "duration_ms": duration_ms,
            "error": result.get("error") or "未知错误",
        })

    rows = result.get("data") or []
    # execute_sql 以 dict(zip(columns, values)) 构造行,行结构同构,取首行取列名
    columns = list(rows[0].keys()) if rows else []
    returned = rows[:MAX_ROWS]
    return _dumps({
        "success": True,
        "sql": sql,
        "row_count": len(rows),
        "returned_rows": len(returned),
        "truncated": len(returned) < len(rows),
        "columns": columns,
        "rows": returned,
        "duration_ms": duration_ms,
        "error": None,
    })


async def search_knowledge(query: str) -> str:
    """检索企业知识库(操作规范/指标定义/系统文档)并生成回答(只读)。

    涉及指标口径、系统使用方法、"什么是XX"类问题,优先使用本工具而非猜测。

    Args:
        query: 检索问题(自然语言)。

    Returns:
        基于检索结果的回答文本;未找到时返回提示文本。
    """
    answer = await answer_with_rag(query)
    return answer or "知识库中未找到相关内容。"


async def make_chart(
    question: str,
    rows: list[dict],
    columns: list[str],
    chart_type: str = "",
) -> str:
    """把查询结果渲染为 ECharts 图表配置。

    Args:
        question: 用户问题(用于图表标题与类型选择)。
        rows: run_sql 返回 JSON 中 rows 字段的数组(需先从 JSON 解析取出)。
        columns: 列名列表。
        chart_type: 可选,指定图表类型(bar/pie/line/scatter);为空由模型判定。

    Returns:
        JSON 字符串:{chart_type, chart_title, echarts_config};
        数据不适合图表时为 {chart_type: "none", reason}。
    """
    hint = f"请使用 {chart_type} 图表展示:" if chart_type else ""
    result = await generate_chart_config(question=hint + question, data=rows, columns=columns)
    if not result or result.get("chart_type") == "none":
        return _dumps({
            "chart_type": "none",
            "reason": (result or {}).get("reason") or "当前数据不适合图表展示",
        })
    return _dumps({
        "chart_type": result.get("chart_type"),
        "chart_title": result.get("chart_title", ""),
        "echarts_config": result.get("echarts_config", {}),
    })
