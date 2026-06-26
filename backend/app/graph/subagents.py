"""
SubAgent 构建工厂

将当前 LangGraph 工作流中的节点包装为 CompiledSubAgent，
供 DeepAgent 通过 task 工具动态委派调用。

构建两个核心子 Agent:
- data-query:   完整 SQL 查询链路 (schema → sql → security → execute → analyst → reporter)
- knowledge-retrieval: RAG 知识库检索链路
"""
from __future__ import annotations

from typing import Any

from langgraph.graph import StateGraph, END

from app.agents import schema_agent as _schema
from app.agents import sql_coder as _sql
from app.agents import security as _sec
from app.agents import analyst as _analyst
from app.agents import reporter as _reporter
from app.agents import rag_agent as _rag
from app.graph.state import AgentState
from app.utils.log_utils import log


async def build_sql_pipeline_subagent() -> Any:
    """
    构建 SQL 查询管道的编译子 Agent。

    链路: schema_agent → sql_coder → security → execute_sql → analyst → reporter → finish

    不包含 orchestrator 节点，因为调度由 DeepAgent 统一管理。
    输入 state 需包含 user_question，输出包含 analysis_text / chart_config / query_result。

    返回:
        CompiledSubAgent 实例
    """
    from deepagents import CompiledSubAgent

    # ── 构建子图 ────────────────────────────────────
    builder = StateGraph(AgentState)

    # 复用现有节点函数（不改变内部逻辑）
    from app.graph.workflow import (
        schema_node,
        sql_coder_node,
        security_node,
        execute_node,
        analyst_node,
        reporter_node,
        finish_node,
        route_schema,
        route_sql_coder,
        route_security,
    )

    builder.add_node("schema_agent", schema_node)
    builder.add_node("sql_coder", sql_coder_node)
    builder.add_node("security", security_node)
    builder.add_node("execute_sql", execute_node)
    builder.add_node("analyst", analyst_node)
    builder.add_node("reporter", reporter_node)
    builder.add_node("finish", finish_node)

    # 入口: schema_agent（接收 user_question 并加载表结构）
    builder.set_entry_point("schema_agent")

    # 条件边（复用现有路由逻辑）
    builder.add_conditional_edges(
        "schema_agent", route_schema,
        {"sql_coder": "sql_coder", "finish": "finish"},
    )
    builder.add_conditional_edges(
        "sql_coder", route_sql_coder,
        {"security": "security", "finish": "finish"},
    )
    builder.add_conditional_edges(
        "security", route_security,
        {"execute_sql": "execute_sql", "finish": "finish"},
    )
    builder.add_edge("execute_sql", "analyst")
    builder.add_edge("analyst", "reporter")
    builder.add_edge("reporter", "finish")
    builder.add_edge("finish", END)

    compiled = builder.compile()
    log.info("[SubAgent] SQL 查询管道已编译")

    return CompiledSubAgent(
        name="data-query",
        description=(
            "处理数据查询、SQL生成与执行、安全审核、数据分析、图表生成。"
            "用于用户的数据查询、统计、报表、图表需求。"
            "输入 state 需包含 user_question 字段。"
        ),
        runnable=compiled,
    )


async def build_rag_subagent() -> Any:
    """
    构建 RAG 知识检索的编译子 Agent。

    链路: rag_agent → finish

    返回:
        CompiledSubAgent 实例
    """
    from deepagents import CompiledSubAgent
    from app.graph.workflow import rag_node, finish_node

    builder = StateGraph(AgentState)

    builder.add_node("rag_agent", rag_node)
    builder.add_node("finish", finish_node)

    builder.set_entry_point("rag_agent")
    builder.add_edge("rag_agent", "finish")
    builder.add_edge("finish", END)

    compiled = builder.compile()
    log.info("[SubAgent] RAG 知识检索管道已编译")

    return CompiledSubAgent(
        name="knowledge-retrieval",
        description=(
            "从 Milvus 向量数据库检索操作规范、指标定义、系统文档等知识，"
            "由 LLM 基于检索结果生成自然语言回答。"
            "用于帮助咨询、文档查询、概念解释类问题。"
        ),
        runnable=compiled,
    )
