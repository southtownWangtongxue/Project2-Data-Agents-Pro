"""Harness 工具包(Phase 0:数据能力工具)。

挂载到 Agent 前统一过 R9 流水线:

    from app.core.tool_pipeline import apply_tool_pipeline
    tools = apply_tool_pipeline(get_data_tools())
"""
from app.harness.tools.data_tools import (
    get_table_schema,
    make_chart,
    run_sql,
    search_knowledge,
)

__all__ = [
    "get_data_tools",
    "get_table_schema",
    "make_chart",
    "run_sql",
    "search_knowledge",
]


def get_data_tools() -> list:
    """返回数据能力工具列表(未过 R9 流水线;挂载前必须 apply_tool_pipeline)。"""
    return [get_table_schema, run_sql, search_knowledge, make_chart]
