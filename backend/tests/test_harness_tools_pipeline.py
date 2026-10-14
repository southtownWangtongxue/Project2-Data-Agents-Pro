"""Harness 工具 × R9 流水线集成测试(Phase 0 门禁的一部分)。"""
import pytest

from app.core.tool_pipeline import apply_tool_pipeline
from app.harness.tools import get_data_tools


def test_pipeline_preserves_tool_names():
    """R9 包装不丢失工具名(LangChain 按名匹配工具调用)。"""
    tools = apply_tool_pipeline(get_data_tools())
    names = [getattr(t, "name", None) or getattr(t, "__name__", None) for t in tools]
    assert names == ["get_table_schema", "run_sql", "search_knowledge", "make_chart"]


def test_pipeline_keeps_docstring_for_tool_schema():
    """docstring 是 LangChain 工具描述来源,包装后必须保留。"""
    tools = apply_tool_pipeline(get_data_tools())
    run_sql = next(t for t in tools if getattr(t, "__name__", "") == "run_sql")
    assert "执行一条 SQL" in (run_sql.__doc__ or "")


@pytest.mark.asyncio
async def test_pipeline_exception_becomes_error_string(monkeypatch):
    """工具抛异常 → R9 兜底为错误字符串,不向上炸(Agent 循环不中断)。"""
    from app.harness.tools import data_tools

    async def boom(engine, sql):
        raise RuntimeError("db down")

    monkeypatch.setattr(data_tools, "execute_sql", boom)
    tools = apply_tool_pipeline([data_tools.run_sql])
    out = await tools[0](sql="SELECT 1", purpose="测试")
    assert "执行失败" in out
    assert "db down" in out
