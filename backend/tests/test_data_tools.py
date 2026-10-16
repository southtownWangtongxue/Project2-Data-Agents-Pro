"""Harness 数据工具测试(Phase 0)—— monkeypatch 隔离 DB/LLM,不触真实资源。"""
import json

import pytest

from app.harness.tools import data_tools
from tests.fakes import FakeCursorResult, FakeEngine


# ── get_table_schema ────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_table_schema_filters_by_keywords(monkeypatch):
    calls = {}

    async def fake_filter(engine, intent):
        calls["intent"] = intent
        return ["orders"]

    async def fake_schemas(engine, table_names):
        calls["tables"] = table_names
        return "CREATE TABLE orders (id BIGINT);"

    monkeypatch.setattr(data_tools, "filter_relevant_tables", fake_filter)
    monkeypatch.setattr(data_tools, "get_table_schemas", fake_schemas)

    text = await data_tools.get_table_schema("订单")
    assert calls == {"intent": "订单", "tables": ["orders"]}
    assert "orders" in text


@pytest.mark.asyncio
async def test_get_table_schema_empty_keywords_skips_filter(monkeypatch):
    """空关键词不过滤,直接取全库结构(过滤器的空 intent 会退化为 LLM 盲选)。"""
    calls = {"filter": False}

    async def fake_filter(engine, intent):
        calls["filter"] = True
        return []

    async def fake_schemas(engine, table_names):
        calls["tables"] = table_names
        return "CREATE TABLE all_t (id BIGINT);"

    monkeypatch.setattr(data_tools, "filter_relevant_tables", fake_filter)
    monkeypatch.setattr(data_tools, "get_table_schemas", fake_schemas)

    text = await data_tools.get_table_schema("")
    assert calls == {"filter": False, "tables": None}
    assert "all_t" in text


@pytest.mark.asyncio
async def test_get_table_schema_empty_returns_hint(monkeypatch):
    async def fake_filter(engine, intent):
        return []

    async def fake_schemas(engine, table_names):
        return ""

    monkeypatch.setattr(data_tools, "filter_relevant_tables", fake_filter)
    monkeypatch.setattr(data_tools, "get_table_schemas", fake_schemas)

    assert "未获取到" in await data_tools.get_table_schema("")


# ── run_sql ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_sql_success_caps_rows(monkeypatch):
    async def fake_execute(engine, sql):
        return {"success": True, "data": [{"a": i} for i in range(500)], "error": None}

    monkeypatch.setattr(data_tools, "execute_sql", fake_execute)

    payload = json.loads(await data_tools.run_sql("SELECT a FROM t", "测试"))
    assert payload["success"] is True
    assert payload["sql"] == "SELECT a FROM t"
    assert payload["row_count"] == 500
    assert payload["returned_rows"] == data_tools.MAX_ROWS
    assert payload["truncated"] is True
    assert len(payload["rows"]) == data_tools.MAX_ROWS
    assert payload["columns"] == ["a"]
    assert payload["error"] is None
    assert payload["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_run_sql_small_result_not_truncated(monkeypatch):
    async def fake_execute(engine, sql):
        return {"success": True, "data": [{"a": 1}, {"a": 2}], "error": None}

    monkeypatch.setattr(data_tools, "execute_sql", fake_execute)

    payload = json.loads(await data_tools.run_sql("SELECT a FROM t", "测试"))
    assert payload["truncated"] is False
    assert payload["row_count"] == payload["returned_rows"] == 2


@pytest.mark.asyncio
async def test_run_sql_failure_returns_structured_error(monkeypatch):
    async def fake_execute(engine, sql):
        return {"success": False, "data": [], "error": "Unknown column 'x'"}

    monkeypatch.setattr(data_tools, "execute_sql", fake_execute)

    payload = json.loads(await data_tools.run_sql("SELECT x", "测试"))
    assert payload["success"] is False
    assert "Unknown column" in payload["error"]
    assert payload["rows"] == []
    assert payload["row_count"] == 0
    assert payload["truncated"] is False
    assert payload["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_run_sql_zero_row_select_reports_zero_rows(monkeypatch):
    """零行 SELECT 端到端症状:run_sql 必须报 row_count=0/rows=[]。

    在引擎层替换(真实 execute_sql 逻辑全程参与),复现交接文档 §4.3 遗留:
    零行 SELECT 被伪装成 affected_rows 单行,模型看到 row_count=1
    会误以为查到了数据。修复后应明确呈现「无数据」。
    """
    engine = FakeEngine(FakeCursorResult(returns_rows=True, rows=[], columns=["v"]))
    monkeypatch.setattr(data_tools, "get_engine", lambda: engine)

    payload = json.loads(await data_tools.run_sql("SELECT v FROM t WHERE 1=0", "测试"))
    assert payload["success"] is True
    assert payload["row_count"] == 0
    assert payload["returned_rows"] == 0
    assert payload["rows"] == []
    assert payload["columns"] == []
    assert payload["truncated"] is False


# ── 委托异常传播契约(模块 docstring 声明的真实失败语义)──────

@pytest.mark.asyncio
async def test_get_table_schema_propagates_infrastructure_error(monkeypatch):
    async def fake_filter(engine, intent):
        return ["orders"]

    async def boom(engine, table_names):
        raise RuntimeError("db down")

    monkeypatch.setattr(data_tools, "filter_relevant_tables", fake_filter)
    monkeypatch.setattr(data_tools, "get_table_schemas", boom)
    with pytest.raises(RuntimeError, match="db down"):
        await data_tools.get_table_schema("订单")


@pytest.mark.asyncio
async def test_run_sql_propagates_infrastructure_error(monkeypatch):
    async def boom(engine, sql):
        raise RuntimeError("connection lost")

    monkeypatch.setattr(data_tools, "execute_sql", boom)
    with pytest.raises(RuntimeError, match="connection lost"):
        await data_tools.run_sql("SELECT 1", "测试")


@pytest.mark.asyncio
async def test_search_knowledge_propagates_error(monkeypatch):
    async def boom(question):
        raise RuntimeError("llm down")

    monkeypatch.setattr(data_tools, "answer_with_rag", boom)
    with pytest.raises(RuntimeError, match="llm down"):
        await data_tools.search_knowledge("q")


@pytest.mark.asyncio
async def test_make_chart_propagates_error(monkeypatch):
    async def boom(question, data, columns):
        raise RuntimeError("llm down")

    monkeypatch.setattr(data_tools, "generate_chart_config", boom)
    with pytest.raises(RuntimeError, match="llm down"):
        await data_tools.make_chart("q", [{"a": 1}], ["a"])


# ── search_knowledge ───────────────────────────────────────

@pytest.mark.asyncio
async def test_search_knowledge_delegates_to_rag(monkeypatch):
    async def fake_rag(question):
        return "GMV 的定义是…"

    monkeypatch.setattr(data_tools, "answer_with_rag", fake_rag)
    assert "GMV" in await data_tools.search_knowledge("什么是GMV")


@pytest.mark.asyncio
async def test_search_knowledge_empty_answer_fallback(monkeypatch):
    async def fake_rag(question):
        return ""

    monkeypatch.setattr(data_tools, "answer_with_rag", fake_rag)
    assert "未找到" in await data_tools.search_knowledge("不存在的问题")


# ── make_chart ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_make_chart_none_returns_reason(monkeypatch):
    async def fake_chart(question, data, columns):
        return {"chart_type": "none", "reason": "数据点太少"}

    monkeypatch.setattr(data_tools, "generate_chart_config", fake_chart)

    payload = json.loads(await data_tools.make_chart("问题", [{"a": 1}], ["a"]))
    assert payload["chart_type"] == "none"
    assert "太少" in payload["reason"]


@pytest.mark.asyncio
async def test_make_chart_success_returns_config(monkeypatch):
    async def fake_chart(question, data, columns):
        return {"chart_type": "bar", "chart_title": "标题", "echarts_config": {"xAxis": {}}}

    monkeypatch.setattr(data_tools, "generate_chart_config", fake_chart)

    payload = json.loads(await data_tools.make_chart("问题", [{"a": 1}], ["a"]))
    assert payload["chart_type"] == "bar"
    assert payload["chart_title"] == "标题"
    assert payload["echarts_config"] == {"xAxis": {}}


@pytest.mark.asyncio
async def test_make_chart_type_hint_prepends_to_question(monkeypatch):
    seen = {}

    async def fake_chart(question, data, columns):
        seen["question"] = question
        return {"chart_type": "pie"}

    monkeypatch.setattr(data_tools, "generate_chart_config", fake_chart)

    await data_tools.make_chart("各地销量", [{"a": 1}], ["a"], chart_type="pie")
    assert seen["question"].startswith("请使用 pie")
    assert "各地销量" in seen["question"]
