# Harness Phase 0 工具层实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把现有 agents 能力封装为 Harness 外围工具(4 个数据工具 + SQL 安全闸纯函数 + 安全闸中间件),全部 TDD,不动主线、不改变任何现有行为。

**Architecture:** 三层分离——`sql_gate.py`(分类+档位 → allow/ask/deny 纯函数)、`tools/data_tools.py`(纯能力,无安全逻辑)、`sql_gate_middleware.py`(中间件层闸口,ask 时 `interrupt()` 挂起,恢复支持 approve/edit/reject)。工具返回 JSON 字符串适配 R9 流水线与 LangChain 工具协议。

**Tech Stack:** Python 3.12 / uv / pytest + pytest-asyncio / langgraph(`interrupt`/`Command`)/ langchain(`AgentMiddleware`/`ToolCallRequest`)/ 现有 `app.agents.*` / `app.core.approval_policy` / `app.core.tool_pipeline`。

**范围声明(YAGNI):**
- Phase 0 **不把工具挂载到任何 Agent**(主线不动,工具在此阶段是"惰性"的);挂载与 SSE 桥接属 Phase 1。
- `export_report` / `send_notification` 工具**不在本计划**——Phase 1 需要时再加(现有 skill executor 已可用)。
- 不改 `app/graph/workflow.py`、`app/api/v1/chat.py`、前端任何文件。

**设计依据:** `docs/plans/2026-10-14-harness-agent-architecture-design.md`(§2.2 工具清单、§3 安全模型)。

**与设计文档的一处偏差(已确认更优):** 设计 §2.2 曾写 `run_sql` 内含自纠错。厚主线下 SQL 由模型亲自写出,纠错责任应交还模型(工具只返回结构化错误),工具内不再调用 LLM 重新生成——否则等于在模型背后换问法。故 `run_sql` 只做执行+结构化返回。

---

### Task 1: SQL 权限闸决策纯函数

**Files:**
- Modify: `backend/app/core/approval_policy.py`(第 30 行区域,常量公开化)
- Create: `backend/app/harness/__init__.py`
- Create: `backend/app/harness/sql_gate.py`
- Test: `backend/tests/test_sql_gate.py`

**Step 1: 写失败测试**

`backend/tests/test_sql_gate.py`:

```python
"""SQL 权限闸决策纯函数测试(Harness 安全第 2 层核心)。"""
from app.core.approval_policy import VALID_TIERS
from app.harness.sql_gate import decide_sql_gate

SAFE = {"category": "safe", "method": "whitelist", "reason": "只读语句"}
DML = {"category": "dangerous", "risk_level": "dml", "method": "whitelist", "reason": "写入"}
DDL = {"category": "dangerous", "risk_level": "ddl", "method": "whitelist", "reason": "结构变更"}
ADMIN = {"category": "dangerous", "risk_level": "admin", "method": "whitelist", "reason": "高危"}


def test_safe_sql_always_allow():
    """只读语句在任何档位都直接放行。"""
    for tier in VALID_TIERS:
        assert decide_sql_gate(SAFE, tier) == "allow"


def test_read_only_tier_asks_all_dangerous():
    """read_only 档:一切高危都转人工审批。"""
    assert decide_sql_gate(DML, "read_only") == "ask"
    assert decide_sql_gate(DDL, "read_only") == "ask"
    assert decide_sql_gate(ADMIN, "read_only") == "ask"


def test_workspace_write_allows_dml_only():
    """workspace_write 档:仅 DML 自动放行,DDL/权限类仍审批。"""
    assert decide_sql_gate(DML, "workspace_write") == "allow"
    assert decide_sql_gate(DDL, "workspace_write") == "ask"
    assert decide_sql_gate(ADMIN, "workspace_write") == "ask"


def test_full_access_allows_all_dangerous():
    """full_access 档:全部自动放行。"""
    assert decide_sql_gate(DML, "full_access") == "allow"
    assert decide_sql_gate(DDL, "full_access") == "allow"
    assert decide_sql_gate(ADMIN, "full_access") == "allow"


def test_unclassifiable_denies():
    """deny-by-default:分类缺失/异常/非法 category 一律拒绝执行。"""
    assert decide_sql_gate(None, "read_only") == "deny"
    assert decide_sql_gate({}, "read_only") == "deny"
    assert decide_sql_gate({"category": "unknown"}, "read_only") == "deny"


def test_invalid_tier_falls_back_to_read_only():
    """非法档位按最严(read_only)处理。"""
    assert decide_sql_gate(DML, "bogus") == "ask"
```

**Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_sql_gate.py -v`
Expected: FAIL(`ModuleNotFoundError: No module named 'app.harness'`)

**Step 3: 实现**

`backend/app/harness/__init.py` 内容为空文件即可(包标记)。

`backend/app/harness/sql_gate.py`:

```python
"""SQL 权限闸决策(纯函数,Harness 安全第 2 层的核心)。

把 security.classify_sql 的分类结果与 approval_policy 的审批档位,映射为三态:

    allow  直接放行(只读语句,或档位已授权该风险等级)
    ask    挂起等待人工审批(HITL interrupt)
    deny   拒绝执行并告知模型原因(分类失败/无法判定,deny-by-default)

决策为纯函数,不依赖 DB/LLM/Graph 上下文,可独立单测。
"""
from __future__ import annotations

from typing import Literal

from app.core.approval_policy import AUTO_APPROVE_RISK, VALID_TIERS

GateDecision = Literal["allow", "ask", "deny"]


def decide_sql_gate(classification: dict | None, tier: str) -> GateDecision:
    """
    参数:
        classification: classify_sql 的返回。合法形态:
            {"category": "safe"|"dangerous", "risk_level": "dml"|"ddl"|"admin", ...}
        tier: 审批档位(read_only / workspace_write / full_access);非法值按 read_only 处理

    返回:
        "allow" | "ask" | "deny"
    """
    if tier not in VALID_TIERS:
        tier = "read_only"

    if not classification or classification.get("category") not in ("safe", "dangerous"):
        return "deny"

    if classification["category"] == "safe":
        return "allow"

    risk = classification.get("risk_level", "admin")
    if risk in AUTO_APPROVE_RISK.get(tier, set()):
        return "allow"
    return "ask"
```

`backend/app/core/approval_policy.py` 修改(第 30 行区域):

```python
# 各档位允许自动放行的风险等级(dangerous 语句细分:dml / ddl / admin)
AUTO_APPROVE_RISK = {
    "read_only": set(),                       # 无自动放行
    "workspace_write": {"dml"},               # 仅数据写入
    "full_access": {"dml", "ddl", "admin"},   # 全部
}
```

同时把同文件第 88 行 `_AUTO_APPROVE_RISK.get(tier, set())` 改为 `AUTO_APPROVE_RISK.get(tier, set())`(重命名后仅此一处引用,`git grep _AUTO_APPROVE_RISK` 确认无其他引用)。

**Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/test_sql_gate.py -v`
Expected: PASS(7 passed)

**Step 5: 提交**

```bash
git add backend/app/harness/ backend/app/core/approval_policy.py backend/tests/test_sql_gate.py
git commit -m "feat(harness): SQL 权限闸决策纯函数——分类+档位映射 allow/ask/deny 三态"
```

---

### Task 2: 数据能力工具(4 个)

**Files:**
- Create: `backend/app/harness/tools/__init__.py`
- Create: `backend/app/harness/tools/data_tools.py`
- Test: `backend/tests/test_data_tools.py`

**Step 1: 写失败测试**

`backend/tests/test_data_tools.py`:

```python
"""Harness 数据工具测试(Phase 0)—— monkeypatch 隔离 DB/LLM,不触真实资源。"""
import json

import pytest

from app.harness.tools import data_tools


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
    assert len(payload["rows"]) == data_tools.MAX_ROWS
    assert payload["columns"] == ["a"]
    assert payload["error"] is None
    assert payload["duration_ms"] >= 0


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
```

**Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_data_tools.py -v`
Expected: FAIL(`ModuleNotFoundError: No module named 'app.harness.tools'`)

**Step 3: 实现**

`backend/app/harness/tools/__init__.py`:

```python
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
```

`backend/app/harness/tools/data_tools.py`:

```python
"""Harness 数据工具层(Phase 0)。

把现有 agents 能力封装为 LangChain 工具契约(纯 async 函数 + docstring + 类型标注),
供 Phase 1 的 Harness 主循环挂载。

职责边界(重要):
- 本模块只含"能力",不含任何安全闸逻辑。run_sql 的执行安全闸在
  app/harness/sql_gate_middleware.py 的中间件层,直接裸调 run_sql 是危险的,
  Phase 1 起所有挂载路径必须包含 SqlGateMiddleware。
- 所有工具返回字符串(JSON 或文本):适配 R9 流水线的截断与 LangChain 工具协议。
- run_sql 行数上限 MAX_ROWS:超出只返回前 N 行(truncated=true),并告知
  row_count,防止大结果集撑爆上下文。
- 失败语义(Task 2 审查后修正为真实契约,原计划此处描述比实现更美好):
  业务失败(execute_sql 返回 success=false)以 JSON success=false 返回;
  基础设施异常(DB 连接/LLM 调用)向上传播,由 R9 流水线兜底为错误字符串——
  因此挂载本模块时必须启用 R9(TOOL_PIPELINE_ENABLED,默认开启)。
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
        purpose: 本次执行的目的(一句话,写入审计日志)。

    Returns:
        JSON 字符串,字段:success / sql / row_count / returned_rows / columns /
        rows / duration_ms / error。失败时 success=false 且 error 说明原因,
        请根据 error 修正 SQL 后重试,或换一种问法。
    """
    t0 = time.monotonic()
    engine = get_engine()
    result = await execute_sql(engine, sql)
    duration_ms = int((time.monotonic() - t0) * 1000)

    if not result["success"]:
        log.warning("[run_sql] 执行失败: %s", result.get("error"))
        return _dumps({
            "success": False,
            "sql": sql,
            "row_count": 0,
            "returned_rows": 0,
            "columns": [],
            "rows": [],
            "duration_ms": duration_ms,
            "error": result.get("error") or "未知错误",
        })

    rows = result["data"]
    columns = list(rows[0].keys()) if rows else []
    returned = rows[:MAX_ROWS]
    return _dumps({
        "success": True,
        "sql": sql,
        "row_count": len(rows),
        "returned_rows": len(returned),
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
        rows: run_sql 返回的数据行(list[dict])。
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
```

**Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/test_data_tools.py -v`
Expected: PASS(10 passed)

**Step 5: 提交**

```bash
git add backend/app/harness/tools/ backend/tests/test_data_tools.py
git commit -m "feat(harness): 数据能力工具——get_table_schema/run_sql/search_knowledge/make_chart"
```

---

### Task 3: SQL 安全闸中间件(allow/ask/deny + approve/edit/reject)

**Files:**
- Create: `backend/app/harness/sql_gate_middleware.py`
- Test: `backend/tests/test_sql_gate_middleware.py`

**Step 1: 写失败测试**

`backend/tests/test_sql_gate_middleware.py`(用最小 LangGraph 图验证 interrupt 挂起/恢复全链路,不 mock interrupt 本身):

```python
"""SQL 安全闸中间件测试(Harness 安全第 2 层)。

用最小 LangGraph 图(节点内调用中间件)验证真实 interrupt 语义:
ask → ainvoke 返回 __interrupt__ → Command(resume) 恢复。
"""
import pytest
import pytest_asyncio
from langchain.tools.tool_node import ToolCallRequest
from langchain.checkpoint.memory import InMemorySaver
from langchain_core.messages import ToolMessage
from langchain.graph import END, StateGraph
from langchain.types import Command

from app.harness.sql_gate_middleware import SqlGateMiddleware, apply_approval


def _request(sql: str, tool: str = "run_sql") -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": tool, "args": {"sql": sql, "purpose": "测试"}, "id": "call_1"},
        tool=None,
        state={},
        runtime=None,
    )


async def _ok_handler(request):
    """模拟工具执行:回显最终 SQL(用于验证 edit 决策是否替换了参数)。"""
    return ToolMessage(
        content=f"executed:{request.tool_call['args']['sql']}",
        tool_call_id=request.tool_call["id"],
        name=request.tool_call["name"],
    )


def _build_graph(monkeypatch, classify_result=None, classify_exc=None, tier="read_only"):
    """构造 节点→中间件→handler 的最小图;分类与档位均可注入。"""
    mw = SqlGateMiddleware()
    if classify_exc is not None:
        async def fake_classify(sql):
            raise classify_exc
    else:
        async def fake_classify(sql):
            return classify_result
    monkeypatch.setattr("app.harness.sql_gate_middleware.classify_sql", fake_classify)
    monkeypatch.setattr("app.harness.sql_gate_middleware.get_tier", lambda: tier)

    async def gate_node(state):
        result = await mw.awrap_tool_call(_request(state["sql"]), _ok_handler)
        return {"result": result.content}

    builder = StateGraph(dict)
    builder.add_node("gate", gate_node)
    builder.set_entry_point("gate")
    builder.add_edge("gate", END)
    return builder.compile(checkpointer=InMemorySaver())


# ── allow 路径 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_safe_sql_passes_through(monkeypatch):
    graph = _build_graph(monkeypatch, classify_result={"category": "safe"}, tier="read_only")
    out = await graph.ainvoke({"sql": "SELECT 1"}, {"configurable": {"thread_id": "t_allow"}})
    assert out["result"] == "executed:SELECT 1"
    assert "__interrupt__" not in out


@pytest.mark.asyncio
async def test_dangerous_dml_auto_allow_under_workspace_write(monkeypatch):
    graph = _build_graph(
        monkeypatch,
        classify_result={"category": "dangerous", "risk_level": "dml"},
        tier="workspace_write",
    )
    out = await graph.ainvoke({"sql": "DELETE FROM t"}, {"configurable": {"thread_id": "t_ws"}})
    assert out["result"] == "executed:DELETE FROM t"
    assert "__interrupt__" not in out


# ── ask 路径:挂起 → approve / edit / reject ──────────────────

@pytest.mark.asyncio
async def test_dangerous_asks_then_approve(monkeypatch):
    graph = _build_graph(
        monkeypatch,
        classify_result={"category": "dangerous", "risk_level": "ddl"},
        tier="read_only",
    )
    config = {"configurable": {"thread_id": "t_ask"}}
    out = await graph.ainvoke({"sql": "DROP TABLE t"}, config)
    assert "__interrupt__" in out
    payload = out["__interrupt__"][0].value
    assert payload["type"] == "approval_required"
    assert payload["sql"] == "DROP TABLE t"

    resumed = await graph.ainvoke(Command(resume={"approved": True}), config)
    assert resumed["result"] == "executed:DROP TABLE t"


@pytest.mark.asyncio
async def test_dangerous_asks_then_edit_sql(monkeypatch):
    """edit 决策:审批人修改 SQL 后放行,handler 收到的是修改后的 SQL。"""
    graph = _build_graph(
        monkeypatch,
        classify_result={"category": "dangerous", "risk_level": "dml"},
        tier="read_only",
    )
    config = {"configurable": {"thread_id": "t_edit"}}
    out = await graph.ainvoke({"sql": "DELETE FROM t"}, config)
    assert "__interrupt__" in out

    resumed = await graph.ainvoke(
        Command(resume={"approved": False, "edited_sql": "DELETE FROM t WHERE id = 1"}), config
    )
    assert resumed["result"] == "executed:DELETE FROM t WHERE id = 1"


@pytest.mark.asyncio
async def test_dangerous_asks_then_reject(monkeypatch):
    """reject 决策:返回拒绝 ToolMessage,handler 未执行。"""
    graph = _build_graph(
        monkeypatch,
        classify_result={"category": "dangerous", "risk_level": "admin"},
        tier="read_only",
    )
    config = {"configurable": {"thread_id": "t_reject"}}
    out = await graph.ainvoke({"sql": "GRANT ALL ON t"}, config)
    assert "__interrupt__" in out

    resumed = await graph.ainvoke(
        Command(resume={"approved": False, "comment": "权限不足"}), config
    )
    assert "executed:" not in resumed["result"]
    assert "审批被驳回" in resumed["result"]
    assert "权限不足" in resumed["result"]


# ── deny 路径 ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_classify_exception_denies(monkeypatch):
    """分类异常 → deny-by-default,handler 不执行。"""
    graph = _build_graph(monkeypatch, classify_exc=RuntimeError("boom"), tier="read_only")
    out = await graph.ainvoke({"sql": "SELECT 1"}, {"configurable": {"thread_id": "t_deny"}})
    assert "executed:" not in out["result"]
    assert "拒绝" in out["result"]


@pytest.mark.asyncio
async def test_unclassifiable_result_denies(monkeypatch):
    """分类返回非法形态(None)→ deny。"""
    graph = _build_graph(monkeypatch, classify_result=None, tier="read_only")
    out = await graph.ainvoke({"sql": "SELECT 1"}, {"configurable": {"thread_id": "t_deny2"}})
    assert "executed:" not in out["result"]
    assert "拒绝" in out["result"]


# ── 非 run_sql 工具直通(不触发分类)──────────────────────────

@pytest.mark.asyncio
async def test_other_tool_not_gated(monkeypatch):
    called = {"classify": False}

    async def fake_classify(sql):
        called["classify"] = True
        return {"category": "safe"}

    monkeypatch.setattr("app.harness.sql_gate_middleware.classify_sql", fake_classify)

    mw = SqlGateMiddleware()
    req = ToolCallRequest(
        tool_call={"name": "get_table_schema", "args": {"keywords": "x"}, "id": "c2"},
        tool=None, state={}, runtime=None,
    )
    result = await mw.awrap_tool_call(req, _ok_handler)
    assert result.content == "executed:x"  # 注:args 无 sql,回显 keywords 由 handler 逻辑决定
    assert called["classify"] is False


# ── apply_approval 纯函数 ──────────────────────────────────

def test_apply_approval_approve():
    action, args, reason = apply_approval({"sql": "DROP TABLE t"}, {"approved": True})
    assert action == "execute"
    assert args["sql"] == "DROP TABLE t"
    assert reason == ""


def test_apply_approval_edit_replaces_sql():
    action, args, reason = apply_approval(
        {"sql": "DELETE FROM t"}, {"approved": False, "edited_sql": "DELETE FROM t WHERE id=1"}
    )
    assert action == "execute"
    assert args["sql"] == "DELETE FROM t WHERE id=1"


def test_apply_approval_reject_with_comment():
    action, _, reason = apply_approval(
        {"sql": "DROP TABLE t"}, {"approved": False, "comment": "太危险"}
    )
    assert action == "deny"
    assert "太危险" in reason


def test_apply_approval_reject_without_comment():
    action, _, reason = apply_approval({"sql": "x"}, {"approved": False})
    assert action == "deny"
    assert "无备注" in reason
```

注意:`test_other_tool_not_gated` 中 handler 回显 `request.tool_call['args']['sql']`,而该请求 args 无 `sql` 键会 KeyError——把断言改为 `"executed:" in result.content` 并在测试内用带 `sql` 键的 args,或直接断言 handler 被调用且 classify 未被调用。修正后的该测试:

```python
@pytest.mark.asyncio
async def test_other_tool_not_gated(monkeypatch):
    called = {"classify": False}

    async def fake_classify(sql):
        called["classify"] = True
        return {"category": "safe"}

    monkeypatch.setattr("app.harness.sql_gate_middleware.classify_sql", fake_classify)

    mw = SqlGateMiddleware()
    req = ToolCallRequest(
        tool_call={"name": "get_table_schema", "args": {"keywords": "x"}, "id": "c2"},
        tool=None, state={}, runtime=None,
    )

    async def handler(request):
        return ToolMessage(content="schema-ok", tool_call_id="c2", name="get_table_schema")

    result = await mw.awrap_tool_call(req, handler)
    assert result.content == "schema-ok"
    assert called["classify"] is False
```

**Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_sql_gate_middleware.py -v`
Expected: FAIL(`ModuleNotFoundError: No module named 'app.harness.sql_gate_middleware'`)

**Step 3: 实现**

`backend/app/harness/sql_gate_middleware.py`:

```python
"""SQL 安全闸中间件(Harness 安全第 2 层,替代 legacy 的 security 节点)。

拦截 run_sql 工具调用:classify_sql 分类 → decide_sql_gate 档位决策 →
    allow  放行(直接执行)
    ask    interrupt() 挂起,审批决策经 Command(resume) 返回:
               approve         放行原 SQL
               edit(edited_sql) 放行修改后的 SQL
               reject          返回 ToolMessage 说明原因,由模型自主降级
    deny   返回 ToolMessage 拒绝原因(分类异常/无法判定,deny-by-default)

中断载荷复用现有 SSE approval_required 事件字段(type/message/sql/reason),
Phase 1 的 SSE 桥接可直接映射到对话内审批卡。
"""
from __future__ import annotations

import dataclasses
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import interrupt

from app.agents.security import classify_sql
from app.core.approval_policy import get_tier
from app.harness.sql_gate import decide_sql_gate
from app.utils.log_utils import log

GATE_TOOL = "run_sql"


def apply_approval(args: dict, approval: dict) -> tuple[str, dict, str]:
    """
    审批恢复决策(纯函数)。

    参数:
        args:     原工具调用参数(含 sql/purpose)
        approval: Command(resume=...) 传入的审批决策:
                  {"approved": bool, "edited_sql": str?, "comment": str?}

    返回:
        (action, new_args, deny_reason):
            action="execute" → 放行(new_args 为最终参数,edit 时 sql 已替换)
            action="deny"    → 拒绝(deny_reason 将返回给模型)
    """
    if approval.get("approved"):
        return "execute", args, ""

    edited = str(approval.get("edited_sql") or "").strip()
    if edited:
        return "execute", {**args, "sql": edited}, ""

    return "deny", args, f"审批被驳回:{approval.get('comment') or '无备注'}"


class SqlGateMiddleware(AgentMiddleware):
    """对 run_sql 实施「分类 → 档位 → allow/ask/deny」安全闸。"""

    async def awrap_tool_call(self, request: ToolCallRequest, handler) -> ToolMessage:
        tool_name = request.tool_call["name"]
        if tool_name != GATE_TOOL:
            return await handler(request)

        args = dict(request.tool_call.get("args") or {})
        sql = args.get("sql", "")

        try:
            classification = await classify_sql(sql)
        except Exception as exc:
            log.exception("[SqlGate] SQL 分类异常,deny-by-default 拒绝")
            return self._deny(request, f"SQL 安全分类失败({exc})")

        decision = decide_sql_gate(classification, get_tier())
        log.warning(
            "[SqlGate] run_sql 决策=%s category=%s risk=%s",
            decision,
            classification.get("category"),
            classification.get("risk_level"),
        )

        if decision == "allow":
            return await handler(request)
        if decision == "deny":
            return self._deny(request, classification.get("reason") or "SQL 分类失败")

        # ask:挂起等待人工审批(中断载荷对齐 SSE approval_required 事件字段)
        approval = interrupt({
            "type": "approval_required",
            "message": "检测到高危 SQL 操作(非只读),需要审批",
            "sql": sql,
            "purpose": args.get("purpose", ""),
            "reason": classification.get("reason", ""),
        })

        action, new_args, deny_reason = apply_approval(args, approval or {})
        if action == "deny":
            return self._deny(request, deny_reason)

        if new_args.get("sql") != sql:
            log.warning("[SqlGate] 审批人修改 SQL 后放行")
            edited_call = dict(request.tool_call)
            edited_call["args"] = new_args
            request = dataclasses.replace(request, tool_call=edited_call)
        return await handler(request)

    @staticmethod
    def _deny(request: ToolCallRequest, reason: str) -> ToolMessage:
        call = request.tool_call
        return ToolMessage(
            content=(
                f"安全策略拒绝执行该 SQL:{reason}。"
                "请改用只读查询,或向用户说明当前权限限制。"
            ),
            tool_call_id=call["id"],
            name=call["name"],
        )
```

**Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/test_sql_gate_middleware.py -v`
Expected: PASS(11 passed)

**Step 5: 提交**

```bash
git add backend/app/harness/sql_gate_middleware.py backend/tests/test_sql_gate_middleware.py
git commit -m "feat(harness): SQL 安全闸中间件——run_sql 拦截 + HITL 审批(approve/edit/reject)"
```

---

### Task 4: R9 流水线集成验证

**Files:**
- Test: `backend/tests/test_harness_tools_pipeline.py`

**Step 1: 写失败测试**

`backend/tests/test_harness_tools_pipeline.py`:

```python
"""Harness 工具 × R9 流水线集成测试(Phase 0 门禁的一部分)。"""
import asyncio

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
```

**Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_harness_tools_pipeline.py -v`
Expected: FAIL(`ModuleNotFoundError: No module named 'app.harness.tools'`)

**Step 3: 实现**

无需新实现——Task 2 已完成 `get_data_tools` 与工具函数;本任务验证 R9 流水线对它们的包装行为。若测试暴露包装问题(如 functools.wraps 未保留 docstring),修 `app/core/tool_pipeline.py` 的 `_wrap`(它已用 `functools.wraps`,预期直接通过)。

**Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/test_harness_tools_pipeline.py -v`
Expected: PASS(3 passed)

**Step 5: 提交**

```bash
git add backend/tests/test_harness_tools_pipeline.py
git commit -m "test(harness): 工具 × R9 流水线集成——名称/docstring 保留 + 异常兜底"
```

---

### Task 5: Phase 0 门禁(全量回归 + 前端构建)

**Files:** 无新增。仅验证与记录。

**Step 1: 后端全量测试**

Run: `cd backend && uv run pytest -q`
Expected: 全部通过,且总数 = 原 52 + 新增 31(7 + 10 + 11 + 3)= 83 passed

**Step 2: 确认主线零改动**

Run: `git diff --stat HEAD -- backend/app/graph backend/app/api backend/app/agents backend/app/core/approval_policy.py`
Expected: 仅 `approval_policy.py` 一行常量重命名(`_AUTO_APPROVE_RISK` → `AUTO_APPROVE_RISK`);graph/api/agents 无 diff

**Step 3: 前端构建不受影响**

Run: `cd frontend-react && npm run build`
Expected: built 成功(本阶段不触前端,仅防共享类型/接口被误改)

**Step 4: 更新设计文档状态**

在 `docs/plans/2026-10-14-harness-agent-architecture-design.md` 的 §2.2 工具清单后追加一行:

```markdown
> Phase 0 已完成:上述工具与安全闸已落地并通过 83 项后端测试(见
> docs/plans/2026-10-14-harness-phase0-tools.md),尚未挂载到任何 Agent。
```

**Step 5: 提交**

```bash
git add docs/plans/2026-10-14-harness-agent-architecture-design.md
git commit -m "docs(plan): Phase 0 工具层完成——设计文档状态更新"
```

---

## Phase 0 完成定义(DoD)

1. `backend/app/harness/` 下四个模块存在且被 31 个新测试覆盖;
2. 安全闸三态(allow/ask/deny)与审批三决策(approve/edit/reject)有真实 interrupt 链路测试;
3. `uv run pytest -q` 全绿(83 passed);`npm run build` 成功;
4. 除 `approval_policy.py` 常量重命名外,主线代码零 diff;
5. 工具尚未挂载——Phase 1(主循环接入 + 影子双跑)开始前,线上行为与本阶段开始前完全一致。
