# Harness Phase 1 主循环接入实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 装配 Harness 主循环(deepagents create_agent + Phase 0 工具与安全闸),把智能体事件桥接进现有 18 类 SSE 协议,前端步骤链改 todo 驱动;以影子双跑比对验证产出,全程默认行为不变。

**Architecture:** 新增 `app/harness/agent_factory.py`(装配)、`sse_bridge.py`(事件翻译,纯函数化可单测)、`stream_harness.py`(SSE 生成器,镜像 legacy 的 HITL 等待-恢复模式)、`shadow.py`(双跑比对);chat.py 只加分发开关 `HARNESS_MODE`(off 默认/shadow/on),不改现有两个生成器。前端 reducer 的 `plan` 事件在带 `todos` 字段时同步 steps Map(todo 驱动),缺省走原逻辑。

**Tech Stack:** deepagents(`create_deep_agent`,已装)/ langchain(`AgentMiddleware`)/ langgraph(`Command`/checkpointer)/ 现有 `app.harness.*`(Phase 0)/ `app.core.hitl`(审批等待)/ FastAPI SSE。

**范围声明(YAGNI):**
- 默认 `HARNESS_MODE=off`,data 模式行为与本阶段开始前完全一致;shadow 模式仅追加后台比对,不影响返回。
- 不动 `_stream_chat` / `_stream_chat_deepagent` 两个既有生成器(Phase 3 收敛时统一);不接 Skills/MCP/子 Agent(Phase 3)。
- `HARNESS_MODE=on` 的线上切换属 Phase 2,本计划只把开关接线留好并保证 on 路径可用。

**设计依据:** `docs/plans/2026-10-14-harness-agent-architecture-design.md` §4(流式映射)、§6(Phase 1 门禁)。

---

### Task 1: Harness Agent 装配工厂

**Files:**
- Create: `backend/app/harness/agent_factory.py`
- Test: `backend/tests/test_harness_agent_factory.py`

**Step 1: 写失败测试**

`backend/tests/test_harness_agent_factory.py`:

```python
"""Harness Agent 装配工厂测试(monkeypatch 掉真实模型创建,只验装配参数)。"""
import pytest

from app.harness import agent_factory


def _fake_create(**kwargs):
    """记录 create_deep_agent 收到的参数原样返回。"""
    _fake_create.captured = kwargs
    return object()


@pytest.fixture
def capture_create(monkeypatch):
    monkeypatch.setattr(agent_factory, "_create", _fake_create)
    agent_factory.reset_agent()
    yield _fake_create
    agent_factory.reset_agent()


def test_build_passes_data_tools(capture_create):
    agent_factory.build_harness_agent()
    names = [getattr(t, "__name__", "") for t in capture_create.captured["tools"]]
    assert names == ["get_table_schema", "run_sql", "search_knowledge", "make_chart"]


def test_build_includes_sql_gate_middleware(capture_create):
    from app.harness.sql_gate_middleware import SqlGateMiddleware

    agent_factory.build_harness_agent()
    mws = capture_create.captured["middleware"]
    assert any(isinstance(m, SqlGateMiddleware) for m in mws)


def test_build_has_system_prompt(capture_create):
    agent_factory.build_harness_agent()
    prompt = capture_create.captured.get("system_prompt") or ""
    assert "run_sql" in prompt
    assert "get_table_schema" in prompt


def test_build_no_subagents_in_phase1(capture_create):
    """Phase 1 不挂子 Agent(report/doc 智能化在 Phase 3)。"""
    agent_factory.build_harness_agent()
    assert capture_create.captured.get("subagents") in (None, [])


def test_singleton(capture_create):
    a = agent_factory.build_harness_agent()
    b = agent_factory.build_harness_agent()
    assert a is b
    assert len(capture_create.calls) == 1 if hasattr(capture_create, "calls") else True
```

注意:`_fake_create` 需记录调用次数,把辅助函数改为:

```python
def _fake_create(**kwargs):
    _fake_create.captured = kwargs
    _fake_create.calls = getattr(_fake_create, "calls", 0) + 1
    return f"agent-{_fake_create.calls}"
```

`test_singleton` 相应简化为:

```python
def test_singleton(capture_create):
    a = agent_factory.build_harness_agent()
    b = agent_factory.build_harness_agent()
    assert a is b
    assert capture_create.calls == 1
```

**Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_harness_agent_factory.py -v`
Expected: FAIL(`ModuleNotFoundError: No module named 'app.harness.agent_factory'`)

**Step 3: 实现**

`backend/app/harness/agent_factory.py`:

```python
"""Harness 主循环装配工厂(Phase 1)。

用 deepagents.create_deep_agent 装配顶层 Agent:
- 工具:Phase 0 数据能力工具(过 R9 流水线)
- 中间件:SqlGateMiddleware(安全闸)+ deepagents 默认中间件
  (TodoList/Filesystem/Summarization/SubAgent 框架,create_deep_agent 内置)
- system_prompt:只读优先 + 工具使用 SOP(分析流程沉淀为提示词规则,替代
  legacy 的 quality_gate 节点;Phase 3 再迁 Skills)

DeepAgent 为全局单例:构建期变量(模型/工具集)在首次调用时确定;
每请求变量(user_name/today/mode)由 chat.py 以 system 消息注入(既有模式)。
"""
from __future__ import annotations

from typing import Any

from app.harness.sql_gate_middleware import SqlGateMiddleware
from app.harness.tools import get_data_tools
from app.core.tool_pipeline import apply_tool_pipeline
from app.utils.log_utils import log

SYSTEM_PROMPT = """你是 DataAgent Pro 的数据智能体,基于只读业务数据库回答用户的数据问题。

## 能力边界(硬约束)
- 你只能通过工具访问数据库,禁止凭记忆猜测表名/字段名;写 SQL 前必须先调用
  get_table_schema 了解结构。
- 只读优先:默认只生成 SELECT 类查询。写入/结构变更(INSERT/UPDATE/DELETE/
  DROP/ALTER 等)会被安全闸拦截并要求人工审批,除非用户明确要求且审批通过。
- 禁止多语句(分号分隔的多条 SQL),每条 SQL 只做一件事。

## 标准流程(SOP)
1. 理解问题:需要库内数据时,先 get_table_schema(keywords=问题关键词) 取相关表结构;
2. 生成并执行 SQL:写出单条 SELECT,调用 run_sql(sql, purpose) 执行;
   - 失败时阅读返回的 error,修正 SQL 后重试(最多换 2 种写法);
   - 连续失败就明确告知用户"查不到",不要反复试同一写法;
3. 分析结果:基于返回的 rows/columns 做统计与洞察(计数/汇总/对比/异常);
4. 可视化:数据适合图表时调用 make_chart 生成图表配置(用户指定了图表类型时,
   通过 chart_type 参数传入);
5. 输出回答:先给结论,再给关键数字,最后给数据口径(SQL 与行数)。

## 其它
- 涉及指标口径/系统使用说明的问题,优先 search_knowledge 检索知识库;
- 回答使用简体中文;数字保留原始精度,单位写清楚;
- 用户问题超出数据库范围(闲聊/常识)时直接回答,不要强行查库。
"""

_agent: Any = None


def _create(**kwargs: Any) -> Any:
    """间接层:便于测试替换(不建真实模型)。"""
    from app.deepagent.harness import create_deep_agent

    return create_deep_agent(**kwargs)


def build_harness_agent() -> Any:
    """构建(首次)/返回(全局单例)Harness 主循环 Agent。"""
    global _agent
    if _agent is not None:
        return _agent

    tools = apply_tool_pipeline(get_data_tools())
    _agent = _create(
        model=_build_model(),
        tools=tools,
        middleware=[SqlGateMiddleware()],
        system_prompt=SYSTEM_PROMPT,
    )
    log.info(
        "[Harness] 主循环装配完成: tools=%d middleware=SqlGate",
        len(tools),
    )
    return _agent


def _build_model():
    """复用 DeepAgent 的模型构建逻辑(显式注入 provider key/base)。"""
    from app.deepagent.harness import _build_model as build

    return build()


def reset_agent() -> None:
    """清空单例(测试用)。"""
    global _agent
    _agent = None
```

**Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/test_harness_agent_factory.py -v`
Expected: PASS(5 passed)

**Step 5: 提交**

```bash
git add backend/app/harness/agent_factory.py backend/tests/test_harness_agent_factory.py
git commit -m "feat(harness): 主循环装配工厂——数据工具 + 安全闸中间件 + SOP 系统提示词"
```

---

### Task 2: SSE 事件桥接器(纯函数化)

**Files:**
- Create: `backend/app/harness/sse_bridge.py`
- Test: `backend/tests/test_harness_sse_bridge.py`

**Step 1: 写失败测试**

`backend/tests/test_harness_sse_bridge.py`:

```python
"""Harness SSE 桥接器测试:合成 agent 事件序列 → 期望的 SSE 事件。

桥接器是纯翻译层:输入 astream 的 (mode, data) 事件,输出 SSE dict 列表。
不建真实 Agent,全部用合成事件。
"""
from app.harness.sse_bridge import HarnessEventBridge


def _msg(content="", tool_calls=None, name="", reasoning=""):
    """最小 AIMessage/ToolMessage 替身(桥接器只用属性读取)。"""
    m = type("M", (), {})()
    m.content = content
    m.tool_calls = tool_calls
    m.name = name
    m.reasoning_content = reasoning
    m.additional_kwargs = {}
    return m


def _updates(**nodes):
    return ("updates", nodes)


def _messages(chunk, node="agent"):
    return ("messages", (chunk, {"langgraph_node": node}))


def test_todo_update_emits_plan_with_todos():
    bridge = HarnessEventBridge()
    events = list(bridge.feed(_updates(agent={"todos": [
        {"id": "1", "title": "查各表数据量", "status": "in_progress"},
        {"id": "2", "title": "生成图表", "status": "pending"},
    ]})))
    plans = [e for e in events if e["type"] == "plan"]
    assert len(plans) == 1
    assert plans[0]["steps"] == ["查各表数据量", "生成图表"]
    assert plans[0]["todos"][0]["status"] == "in_progress"
    # in_progress 的 todo 成为当前步骤,后续工具事件挂它
    assert bridge.current_step_id == 1


def test_tool_call_attaches_to_current_step():
    bridge = HarnessEventBridge()
    list(bridge.feed(_updates(agent={"todos": [{"id": "1", "title": "t", "status": "in_progress"}]})))
    chunk = _msg(tool_calls=[{"name": "run_sql", "args": {"sql": "SELECT 1"}, "id": "c1"}])
    events = list(bridge.feed(_messages(chunk)))
    calls = [e for e in events if e["type"] == "tool_call"]
    assert calls[0]["name"] == "run_sql"
    assert calls[0]["step_id"] == 1
    assert "SELECT 1" in calls[0]["args"]


def test_run_sql_result_emits_rich_events():
    """run_sql 的 JSON 载荷 → sql + result 富事件 + 紧凑 tool_result。"""
    bridge = HarnessEventBridge()
    payload = (
        '{"success": true, "sql": "SELECT 1", "row_count": 2, "returned_rows": 2,'
        ' "columns": ["a"], "rows": [{"a": 1}, {"a": 2}], "duration_ms": 12, "error": null}'
    )
    tm = _msg(content=payload, name="run_sql")
    events = list(bridge.feed(_updates(tools={"messages": [tm]})))
    types = [e["type"] for e in events]
    assert "sql" in types
    assert "result" in types
    sql_ev = next(e for e in events if e["type"] == "sql")
    assert sql_ev["sql"] == "SELECT 1"
    result_ev = next(e for e in events if e["type"] == "result")
    assert result_ev["columns"] == ["a"]
    assert result_ev["data"] == [{"a": 1}, {"a": 2}]
    tool_ev = next(e for e in events if e["type"] == "tool_result")
    assert tool_ev["name"] == "run_sql"
    assert tool_ev["status"] == "done"
    assert "2 行" in tool_ev["content"]


def test_make_chart_result_emits_chart_event():
    bridge = HarnessEventBridge()
    payload = '{"chart_type": "bar", "chart_title": "T", "echarts_config": {"xAxis": {}}}'
    tm = _msg(content=payload, name="make_chart")
    events = list(bridge.feed(_updates(tools={"messages": [tm]})))
    charts = [e for e in events if e["type"] == "chart"]
    assert len(charts) == 1
    assert charts[0]["config"] == {"xAxis": {}}


def test_run_sql_failure_result_has_no_rich_events():
    bridge = HarnessEventBridge()
    payload = '{"success": false, "error": "Unknown column"}'
    tm = _msg(content=payload, name="run_sql")
    events = list(bridge.feed(_updates(tools={"messages": [tm]})))
    assert [e["type"] for e in events] == ["tool_result"]
    assert "Unknown column" in events[0]["content"]


def test_plain_text_token_and_reasoning():
    bridge = HarnessEventBridge()
    chunk = _msg(content="结论", reasoning="想一想")
    events = list(bridge.feed(_messages(chunk)))
    assert any(e["type"] == "token" and e["content"] == "结论" for e in events)
    assert any(e["type"] == "reasoning" and e["content"] == "想一想" for e in events)


def test_plain_tool_result_truncated():
    bridge = HarnessEventBridge()
    tm = _msg(content="x" * 2000, name="get_table_schema")
    events = list(bridge.feed(_updates(tools={"messages": [tm]})))
    tool_ev = events[-1]
    assert tool_ev["type"] == "tool_result"
    assert len(tool_ev["content"]) <= 800


def test_interrupt_event_yields_approval_signal():
    """updates 里的 __interrupt__ → 审批信号(chat.py 负责等待-恢复)。"""
    bridge = HarnessEventBridge()
    interrupt_obj = type("I", (), {})()
    interrupt_obj.value = {"type": "approval_required", "sql": "DROP TABLE t", "reason": "高危"}
    events = list(bridge.feed(_updates(__interrupt__=[interrupt_obj])))
    assert len(events) == 1
    assert events[0]["type"] == "approval_required"
    assert events[0]["sql"] == "DROP TABLE t"
    assert bridge.pending_approval is True


def test_other_node_events_ignored():
    bridge = HarnessEventBridge()
    events = list(bridge.feed(_updates(__start__={"messages": []})))
    assert events == []
```

**Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_harness_sse_bridge.py -v`
Expected: FAIL(`ModuleNotFoundError: No module named 'app.harness.sse_bridge'`)

**Step 3: 实现**

`backend/app/harness/sse_bridge.py`:

```python
"""Harness SSE 事件桥接器(Phase 1)。

把 deepagents astream 的 (mode, data) 事件流翻译为现有 SSE 事件 dict:
- messages 模式 → token(正文)/reasoning(思考)/tool_call(工具调用增量)
- updates 模式 → plan(todos 变更)/sql+result(run_sql 富事件)/
  chart(make_chart 富事件)/tool_result(紧凑摘要)/approval_required(中断)

step_id 语义(todo 驱动):todos 中 status=in_progress 的条目即当前步骤,
工具事件挂当前步骤;无 in_progress 时挂 0(平铺)。

协议只增不改:全部输出事件均属既有 SSEEventType;plan 事件新增可选字段
todos([{id,title,status}]),前端按有无该字段切换 todo 驱动/legacy 两种分组。
"""
from __future__ import annotations

import json
from typing import Any, Iterator

_RESULT_CONTENT_MAX = 800


def _todo_step_id(todos: list[dict]) -> int:
    """当前步骤号:in_progress 条目的序号(1 起);无则 0。"""
    for idx, t in enumerate(todos, start=1):
        if t.get("status") == "in_progress":
            return idx
    return 0


class HarnessEventBridge:
    """有状态桥接器:跟踪当前 todo 列表与步骤号,逐事件翻译。"""

    def __init__(self) -> None:
        self.todos: list[dict] = []
        self.current_step_id: int = 0
        self.pending_approval: bool = False

    # ── 对外入口 ────────────────────────────────────────────

    def feed(self, event: tuple[str, Any]) -> list[dict]:
        """消费一个 astream 事件,返回 0..N 个 SSE 事件 dict。"""
        mode, data = event
        if mode == "messages":
            return self._on_messages(data)
        if mode == "updates":
            return self._on_updates(data)
        return []

    # ── messages 模式 ───────────────────────────────────────

    def _on_messages(self, data: tuple) -> list[dict]:
        chunk, metadata = data
        node = metadata.get("langgraph_node", "") if isinstance(metadata, dict) else ""
        if node not in ("agent", "model"):
            return []

        out: list[dict] = []
        content = getattr(chunk, "content", "")
        if isinstance(content, str) and content.strip():
            out.append({"type": "token", "content": content, "step_id": self.current_step_id})

        reasoning = ""
        add_kwargs = getattr(chunk, "additional_kwargs", None) or {}
        if add_kwargs:
            reasoning = add_kwargs.get("reasoning_content", "") or ""
        if not reasoning:
            reasoning = getattr(chunk, "reasoning_content", "") or ""
        if reasoning:
            out.append({"type": "reasoning", "content": reasoning, "step_id": self.current_step_id})

        for tc in getattr(chunk, "tool_call_chunks", None) or []:
            name = tc.get("name")
            if name:
                out.append({
                    "type": "tool_call",
                    "name": name,
                    "args": _stringify_args(tc.get("args") or "")[:500],
                    "step_id": self.current_step_id,
                })
        return out

    # ── updates 模式 ────────────────────────────────────────

    def _on_updates(self, data: dict) -> list[dict]:
        out: list[dict] = []
        for node_name, state_update in (data or {}).items():
            if node_name == "__interrupt__":
                out.append(self._on_interrupt(state_update))
                continue
            if not isinstance(state_update, dict):
                continue

            todos = state_update.get("todos")
            if todos is not None:
                out.extend(self._on_todos(todos))

            if node_name == "tools":
                out.extend(self._on_tool_messages(state_update.get("messages", [])))
        return out

    def _on_todos(self, todos: list[dict]) -> list[dict]:
        self.todos = list(todos)
        self.current_step_id = _todo_step_id(self.todos)
        return [{
            "type": "plan",
            "steps": [str(t.get("title", "")) for t in self.todos],
            "todos": [
                {"id": str(t.get("id", "")), "title": str(t.get("title", "")),
                 "status": str(t.get("status", "pending"))}
                for t in self.todos
            ],
            "step_id": self.current_step_id,
        }]

    def _on_tool_messages(self, messages: list) -> list[dict]:
        out: list[dict] = []
        for msg in messages:
            name = getattr(msg, "name", "") or "tool"
            content = str(getattr(msg, "content", "") or "")
            rich = self._rich_events(name, content)
            out.extend(rich)
            out.append({
                "type": "tool_result",
                "name": name,
                "status": "done",
                "content": _compact_summary(name, content),
                "step_id": self.current_step_id,
            })
        return out

    def _rich_events(self, name: str, content: str) -> list[dict]:
        """已知工具的 JSON 载荷 → sql/result/chart 富事件(前端富渲染)。"""
        if name not in ("run_sql", "make_chart"):
            return []
        try:
            payload = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return []
        if not isinstance(payload, dict):
            return []

        sid = self.current_step_id
        if name == "run_sql":
            if not payload.get("success"):
                return []
            return [
                {"type": "sql", "sql": str(payload.get("sql", "")), "step_id": sid},
                {"type": "result",
                 "data": payload.get("rows") or [],
                 "columns": payload.get("columns") or [],
                 "step_id": sid},
            ]
        # make_chart
        if payload.get("chart_type") == "none" or not payload.get("echarts_config"):
            return []
        return [{
            "type": "chart",
            "config": payload.get("echarts_config") or {},
            "text": str(payload.get("chart_title", "")),
            "step_id": sid,
        }]

    def _on_interrupt(self, state_update: Any) -> dict:
        self.pending_approval = True
        raw = state_update
        if isinstance(raw, (list, tuple)):
            raw = raw[0] if raw else None
        payload = getattr(raw, "value", raw)
        if not isinstance(payload, dict):
            payload = {}
        return {
            "type": "approval_required",
            "sql": str(payload.get("sql", "")),
            "reason": str(payload.get("reason", "")),
            "purpose": str(payload.get("purpose", "")),
            "step_id": self.current_step_id,
        }


def _stringify_args(args: Any) -> str:
    if isinstance(args, str):
        return args
    if isinstance(args, (dict, list)):
        return json.dumps(args, ensure_ascii=False)
    return str(args)


def _compact_summary(name: str, content: str) -> str:
    """工具结果的紧凑摘要(富事件已承载详情,卡片只留一行读数)。"""
    if name == "run_sql":
        try:
            payload = json.loads(content)
            if isinstance(payload, dict) and payload.get("success"):
                return (
                    f"查询成功 · {payload.get('row_count', 0)} 行"
                    f"(返回 {payload.get('returned_rows', 0)}) · {payload.get('duration_ms', 0)}ms"
                )
        except (json.JSONDecodeError, TypeError):
            pass
    return content[:_RESULT_CONTENT_MAX]
```

**Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/test_harness_sse_bridge.py -v`
Expected: PASS(9 passed)

**Step 5: 提交**

```bash
git add backend/app/harness/sse_bridge.py backend/tests/test_harness_sse_bridge.py
git commit -m "feat(harness): SSE 事件桥接器——agent 事件翻译为现有协议(todo→plan/工具富事件/中断信号)"
```

---

### Task 3: Harness SSE 流式生成器(含 HITL 等待-恢复)

**Files:**
- Create: `backend/app/harness/stream_harness.py`
- Modify: `backend/app/api/v1/chat.py`(分发开关 + 新分支,约 +40 行,不改既有生成器)
- Test: `backend/tests/test_harness_stream.py`

**Step 1: 写失败测试**

`backend/tests/test_harness_stream.py`(用假 Agent + 假 hitl,验证完整 SSE 序列与恢复续流):

```python
"""Harness SSE 生成器测试:假 Agent + 假 hitl,验证审批挂起-恢复续流。"""
import json

import pytest

from app.harness import stream_harness


class _FakeAgent:
    """按脚本产出 astream 事件的假 Agent。"""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    async def astream(self, input_data, config, stream_mode=None):
        self.calls += 1
        # 第一次调用产出到中断为止;第二次(Command(resume))产出后续
        phase = "first" if self.calls == 1 else "resume"
        for ev in self.script.get(phase, []):
            yield ev


def _interrupt_evt(sql="DELETE FROM t"):
    obj = type("I", (), {})()
    obj.value = {"type": "approval_required", "sql": sql, "reason": "高危", "purpose": "清理"}
    return ("updates", {"__interrupt__": [obj]})


def _text_msg(text):
    m = type("M", (), {})()
    m.content = text
    m.tool_calls = None
    m.tool_call_chunks = None
    m.additional_kwargs = {}
    m.reasoning_content = ""
    return m


@pytest.fixture
def patched(monkeypatch):
    """替换 Agent 构建 / hitl 等待 / 标题生成 / 会话落库,隔离外部依赖。"""
    monkeypatch.setattr(stream_harness, "build_harness_agent", lambda: _FAKE_AGENT[0])
    monkeypatch.setattr(stream_harness.hitl, "wait_for", _fake_wait_for)
    monkeypatch.setattr(stream_harness, "_save_chat_node", _noop_async)
    monkeypatch.setattr(stream_harness, "_upsert_chat_session", _noop_async)
    monkeypatch.setattr(stream_harness, "generate_node_title", _fake_title)
    yield


_FAKE_AGENT: list = []
_DECISION: list = []


async def _fake_wait_for(thread_id, timeout=300):
    return _DECISION[0] if _DECISION else None


async def _noop_async(*a, **kw):
    return None


async def _fake_title(question, text, provider=None):
    return "测试标题"


async def _collect(gen) -> list[dict]:
    out = []
    async for chunk in gen:
        out.append(json.loads(chunk.removeprefix("data: ").strip()))
    return out


@pytest.mark.asyncio
async def test_full_flow_with_approval(patched):
    """文本流 → 审批挂起(approval_required)→ 决策到达 → 恢复续流 → done/title。"""
    _FAKE_AGENT[:] = [_FakeAgent({
        "first": [
            ("messages", (_text_msg("我先分析"), {"langgraph_node": "agent"})),
            _interrupt_evt(),
        ],
        "resume": [
            ("messages", (_text_msg("已完成"), {"langgraph_node": "agent"})),
            ("updates", {"__end__": {}}),
        ],
    })]
    _DECISION[:] = [{"approved": True, "comment": "ok"}]

    events = await _collect(stream_harness.stream_chat_harness(
        question="清理数据", user_name="admin", existing_thread_id="t1",
    ))
    types = [e["type"] for e in events]
    assert "thread_id" in types
    assert "approval_required" in types
    assert "done" in types
    assert "title" in types
    # done 必须先于 title(已修复语义)
    assert types.index("done") < types.index("title")
    # 恢复后的正文也到达前端
    tokens = "".join(e.get("content", "") for e in events if e["type"] == "token")
    assert "我先分析" in tokens and "已完成" in tokens


@pytest.mark.asyncio
async def test_approval_timeout_auto_reject(patched):
    """审批超时(wait_for 返回 None)→ 自动拒绝 → 状态提示 + 正常收尾。"""
    _FAKE_AGENT[:] = [_FakeAgent({
        "first": [_interrupt_evt()],
        "resume": [("updates", {"__end__": {}})],
    })]
    _DECISION[:] = []  # wait_for 返回 None

    events = await _collect(stream_harness.stream_chat_harness(
        question="x", user_name="admin", existing_thread_id="t1",
    ))
    statuses = [e.get("content", "") for e in events if e["type"] == "status"]
    assert any("自动拒绝" in s for s in statuses)
    assert any(e["type"] == "done" for e in events)


@pytest.mark.asyncio
async def test_simple_flow_no_approval(patched):
    """无审批的简单流:token → done → title。"""
    _FAKE_AGENT[:] = [_FakeAgent({
        "first": [
            ("messages", (_text_msg("你好"), {"langgraph_node": "agent"})),
            ("updates", {"__end__": {}}),
        ],
        "resume": [],
    })]
    events = await _collect(stream_harness.stream_chat_harness(
        question="你好", user_name="admin", existing_thread_id="t1",
    ))
    types = [e["type"] for e in events]
    assert "approval_required" not in types
    assert types[-2] == "done" and types[-1] == "title"
```

**Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_harness_stream.py -v`
Expected: FAIL(`ModuleNotFoundError: No module named 'app.harness.stream_harness'`)

**Step 3: 实现**

`backend/app/harness/stream_harness.py`(结构镜像 `_stream_chat_deepagent`,复用 chat.py 既有助手函数;HITL 用 legacy 同款「等待-恢复」):

```python
"""Harness 主循环 SSE 流式生成器(Phase 1)。

与 _stream_chat_deepagent 的差异:
- Agent 来自 agent_factory.build_harness_agent(数据工具 + 安全闸中间件)
- 事件翻译走 HarnessEventBridge(todo→plan / 工具富事件 / 中断信号)
- HITL 采用 legacy 同款流内等待-恢复:approval_required 下发后
  hitl.wait_for 等待决策,Command(resume) 恢复并续流(拒绝则收尾)

复用 chat.py 的既有助手(_sse_event/_save_chat_node/_upsert_chat_session/
generate_node_title/事件溯源),不重复实现;Phase 3 收敛时与另外两个
生成器合并。
"""
from __future__ import annotations

import os as _os
import time as _time
import uuid

from langgraph.types import Command

from app.core import hitl
from app.harness.agent_factory import build_harness_agent
from app.harness.sse_bridge import HarnessEventBridge
from app.utils.log_utils import log

# ── 复用 chat.py 既有助手(延迟导入避免循环依赖)────────────────
def _helpers():
    from app.api.v1.chat import (
        _sse_event, _save_chat_node, _upsert_chat_session,
        generate_node_title, _count_nodes, event_sourcing_enabled,
        SessionEventStore, EventType, turn_event_enabled,
    )
    return (_sse_event, _save_chat_node, _upsert_chat_session,
            generate_node_title, _count_nodes, event_sourcing_enabled,
            SessionEventStore, EventType, turn_event_enabled)


def _sse(data: dict) -> str:
    from app.api.v1.chat import _sse_event
    return _sse_event(data)


async def stream_chat_harness(
    question: str,
    user_name: str,
    history: list[dict] | None = None,
    existing_thread_id: str | None = None,
    model: str | None = None,
    mode: str = "data",
    web_search: bool = False,
    runtime_context: str = "",
):
    """Harness 主循环 SSE 生成器(接口与 _stream_chat/_stream_chat_deepagent 一致)。"""
    (_sse_event, _save_chat_node, _upsert_chat_session,
     generate_node_title, _count_nodes, event_sourcing_enabled,
     SessionEventStore, EventType, turn_event_enabled) = _helpers()

    agent = build_harness_agent()
    session_thread_id = existing_thread_id or f"{user_name}:{uuid.uuid4()}"
    run_id = f"{user_name}:{uuid.uuid4()}"
    config = {
        "configurable": {"thread_id": run_id},
        "recursion_limit": int(_os.getenv("HARNESS_RECURSION_LIMIT", "40")),
    }

    yield _sse_event({"type": "thread_id", "thread_id": session_thread_id})
    await _upsert_chat_session(session_thread_id, user_name)
    node_index = await _count_nodes(session_thread_id) if existing_thread_id else 0

    es_enabled = event_sourcing_enabled()
    full_text = ""
    bridge = HarnessEventBridge()
    _done_emitted = False

    async def _track(etype, role=None, content="", payload=None):
        if es_enabled:
            await SessionEventStore.append(
                session_thread_id, etype, run_id=run_id,
                node_index=node_index, role=role, content=content, payload=payload,
            )

    if es_enabled:
        await _track(EventType.USER_MESSAGE, role="user", content=question)

    input_data = {"messages": [*(history or []), {"role": "user", "content": question}]}
    if existing_thread_id:
        from app.api.v1.chat import _get_session_goal
        goal = await _get_session_goal(existing_thread_id)
        if goal:
            input_data["messages"] = [
                {"role": "system", "content": f"[会话长期目标] {goal}\n请始终围绕该目标执行任务并回答用户问题。"},
                *input_data["messages"],
            ]
    if runtime_context:
        input_data["messages"] = [
            {"role": "system", "content": runtime_context}, *input_data["messages"],
        ]
    if web_search:
        input_data["messages"][-1]["content"] += (
            "\n\n[提示] 可以使用 web_search_tool 搜索互联网获取实时信息。"
        )

    yield _sse_event({"type": "status", "content": "正在分析您的请求..."})

    started = _time.monotonic()
    max_seconds = float(_os.getenv("HARNESS_MAX_SECONDS", "300"))
    interrupted = False

    def _remaining() -> float:
        return max_seconds - (_time.monotonic() - started)

    try:
        while True:
            remain = _remaining()
            if remain <= 0:
                yield _sse_event({"type": "status",
                                  "content": f"任务执行超过 {int(max_seconds)}s 仍未完成，已主动结束。"})
                break
            aiter = agent.astream(input_data, config,
                                  stream_mode=["updates", "messages"]).__aiter__()
            while True:
                remain = _remaining()
                if remain <= 0:
                    yield _sse_event({"type": "status",
                                      "content": f"任务执行超过 {int(max_seconds)}s 仍未完成，已主动结束。"})
                    break
                try:
                    import asyncio as _asyncio
                    event = await _asyncio.wait_for(aiter.__anext__(), timeout=remain)
                except StopAsyncIteration:
                    break
                except TimeoutError:
                    yield _sse_event({"type": "status",
                                      "content": f"任务执行超过 {int(max_seconds)}s 仍未完成，已主动结束。"})
                    break

                for sse in bridge.feed(event):
                    if sse["type"] == "token":
                        full_text += sse.get("content", "")
                    if sse["type"] == "approval_required":
                        # ── HITL 流内等待-恢复(legacy 同款)──
                        yield _sse_event({
                            "type": "approval_required",
                            "thread_id": session_thread_id,
                            "question": question,
                            "sql": sse.get("sql", ""),
                            "reason": sse.get("reason", ""),
                        })
                        decision = await hitl.wait_for(session_thread_id, timeout=300)
                        if decision is None:
                            decision = {"approved": False, "comment": "审批超时（5 分钟），自动拒绝"}
                            yield _sse_event({"type": "status", "content":
                                              "审批超时（5 分钟），已自动拒绝。",
                                              "approval_state": "rejected"})
                        input_data = Command(resume=decision)
                        interrupted = True
                        break
                    yield _sse_event(sse)
                if interrupted:
                    interrupted = False
                    break
            else:
                continue
            break
    except Exception as exc:  # noqa: BLE001 —— 收尾后重新抛出由调用方记录
        log.exception("[Harness SSE] 流式异常")
        yield _sse_event({"type": "error", "content": f"执行异常: {exc}", "recoverable": True})

    # ── 收尾:done 先行,标题后置(已修复语义)──────────────
    if not _done_emitted:
        _done_emitted = True
        if es_enabled and full_text:
            await _track(EventType.ANALYSIS, role="assistant", content=full_text)
        yield _sse_event({"type": "done"})
        try:
            title = await generate_node_title(question, full_text[:200])
            await _save_chat_node(session_thread_id, node_index, title, question, run_id)
            if node_index == 0:
                await _upsert_chat_session(session_thread_id, user_name, title)
            yield _sse_event({"type": "title", "content": title,
                              "thread_id": session_thread_id, "node_index": node_index})
        except Exception as title_exc:
            log.warning("[Harness SSE] 标题生成失败(不影响 done): %s", title_exc)
```

注意:上面 `while/for/else` 的双层循环是「恢复后重新 astream」的直白写法;若实现时读起来太重,可抽 `_drain(aiter)` 内部生成器,行为不变。

**Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/test_harness_stream.py -v`
Expected: PASS(3 passed)

**Step 5: chat.py 分发开关(仅新增,不改既有生成器)**

在 `chat.py` 的 `chat_completions` 分流处(约 1362 行 `USE_DEEP_AGENT 全局开启或 mode=task → deepagent,其余 → legacy-graph` 附近)加入:

```python
# ── HARNESS_MODE:off(默认)/ shadow / on ─────────────────────
# on:    data 模式走 Harness 主循环(Phase 2 切换默认)
# shadow:data 模式走 legacy,完成后后台跑 Harness 双跑比对(Phase 1 验证)
# off:   完全 legacy 行为
_HARNESS_MODE = _os.getenv("HARNESS_MODE", "off").lower()
```

分流逻辑改为(在既有 USE_DEEP_AGENT 判断之前):

```python
if _HARNESS_MODE == "on" and mode == "data":
    return _stream_chat_harness(...)          # 同名参数原样传递
if _HARNESS_MODE == "shadow" and mode == "data":
    # legacy 响应照常;收尾后挂后台比对(见 Task 5)
    ...
```

并在文件头 import 区加:

```python
from app.harness.stream_harness import stream_chat_harness as _stream_chat_harness
```

**Step 6: 提交**

```bash
git add backend/app/harness/stream_harness.py backend/tests/test_harness_stream.py backend/app/api/v1/chat.py
git commit -m "feat(harness): Harness SSE 流式生成器 + HITL 等待-恢复 + HARNESS_MODE 分发开关"
```

---

### Task 4: 前端 todo 驱动步骤分组

**Files:**
- Modify: `frontend-react/src/sdk/protocol.ts`(SSEEvent 增 `todos` 可选字段)
- Modify: `frontend-react/src/sdk/reducer.ts`(E.PLAN 的 todo 分支 + Step.status 增 `pending`)
- Modify: `frontend-react/src/components/chat/StepChain.tsx`(pending 态渲染)
- Test: `frontend-react/src/sdk/reducer.test.ts`(追加用例)

**Step 1: 写失败测试**

在 `frontend-react/src/sdk/reducer.test.ts` 追加(先 import `applyEvent, initialChatState` 若未导入):

```typescript
describe('todo 驱动的步骤分组(Harness Phase 1)', () => {
  it('plan 事件带 todos 时同步 steps(含 pending/running/completed)', () => {
    let s = initialChatState()
    s = applyEvent(s, {
      type: 'plan',
      steps: ['查各表数据量', '生成图表'],
      todos: [
        { id: '1', title: '查各表数据量', status: 'in_progress' },
        { id: '2', title: '生成图表', status: 'pending' },
      ],
    })
    expect(s.steps.get(1)).toMatchObject({ id: 1, label: '查各表数据量', status: 'running' })
    expect(s.steps.get(2)).toMatchObject({ id: 2, label: '生成图表', status: 'pending' })
    expect(s.currentStepId).toBe(1)
  })

  it('todos 状态推进时更新既有步骤(不新建)', () => {
    let s = initialChatState()
    const first = {
      type: 'plan', steps: ['A', 'B'],
      todos: [
        { id: '1', title: 'A', status: 'in_progress' },
        { id: '2', title: 'B', status: 'pending' },
      ],
    }
    s = applyEvent(s, first)
    s = applyEvent(s, {
      type: 'plan', steps: ['A', 'B'],
      todos: [
        { id: '1', title: 'A', status: 'completed' },
        { id: '2', title: 'B', status: 'in_progress' },
      ],
    })
    expect(s.steps.size).toBe(2)
    expect(s.steps.get(1)?.status).toBe('completed')
    expect(s.steps.get(2)?.status).toBe('running')
    expect(s.currentStepId).toBe(2)
  })

  it('plan 事件不带 todos 时走 legacy 行为(仅 plan 消息,不建 steps)', () => {
    let s = initialChatState()
    s = applyEvent(s, { type: 'plan', steps: ['load_schema', 'generate_sql'], intent: 'query_data' })
    expect(s.steps.size).toBe(0)
    expect(s.messages.some(m => m.kind === 'plan')).toBe(true)
  })

  it('工具事件挂当前 in_progress 步骤', () => {
    let s = initialChatState()
    s = applyEvent(s, {
      type: 'plan', steps: ['A'],
      todos: [{ id: '1', title: 'A', status: 'in_progress' }],
    })
    s = applyEvent(s, { type: 'tool_call', name: 'run_sql', args: 'SELECT 1', step_id: 1 })
    const tool = s.messages.find(m => m.kind === 'tool')
    expect(tool?.stepId).toBe(1)
  })
})
```

**Step 2: 运行确认失败**

Run: `cd frontend-react && npx vitest run src/sdk/reducer.test.ts`
Expected: FAIL(`s.steps.get(1)` 为 undefined / `status: 'pending'` 不存在)

**Step 3: 实现**

`frontend-react/src/sdk/protocol.ts` —— SSEEvent 增字段(只增):

```typescript
  /* plan 事件可选:Harness todo 驱动步骤链(缺省走 legacy steps 语义) */
  todos?: { id: string; title: string; status: 'pending' | 'in_progress' | 'completed' }[]
```

Step.status 扩展:

```typescript
export interface Step {
  id: number
  agent: string
  label: string
  status: 'pending' | 'running' | 'completed'
}
```

`frontend-react/src/sdk/reducer.ts` —— E.PLAN 分支改造:

```typescript
    case E.PLAN: {
      // Harness todo 驱动:带 todos 字段时同步 steps Map(id 取 todo 序号)
      if (ev.todos && ev.todos.length > 0) {
        ev.todos.forEach((t, idx) => {
          const id = idx + 1
          const status = t.status === 'completed' ? 'completed'
            : t.status === 'in_progress' ? 'running' : 'pending'
          const existing = s.steps.get(id)
          s.steps.set(id, {
            id,
            agent: existing?.agent ?? 'harness',
            label: t.title,
            status,
          })
        })
        const inProgress = ev.todos.findIndex(t => t.status === 'in_progress')
        s.currentStepId = inProgress >= 0 ? inProgress + 1 : 0
      }
      s.messages.push({
        id: msgId(),
        role: 'system',
        kind: 'plan',
        planIntent: ev.intent,
        planIntentLabel: ev.intent_label,
        planSteps: ev.steps,
        planChartSuitable: ev.chart_suitable,
        stepId: ev.step_id,
      })
      return s
    }
```

`frontend-react/src/components/chat/StepChain.tsx` —— ThoughtChain.Item 状态映射补 pending:

```tsx
status: step.status === 'running' ? 'loading'
  : step.status === 'pending' ? 'abort'   // 未开始:官方 abort 态(空心)
  : 'success',
```

(pending 用官方 `abort` 状态位表达"未开始",视觉为空心圈;运行中 loading 紫点脉冲,完成 success 绿点,与已确认语义一致。)

**Step 4: 运行确认通过**

Run: `cd frontend-react && npx vitest run`
Expected: 全部通过(原 24 + 新 4 = 28 passed)

**Step 5: 提交**

```bash
git add frontend-react/src/sdk/protocol.ts frontend-react/src/sdk/reducer.ts frontend-react/src/components/chat/StepChain.tsx frontend-react/src/sdk/reducer.test.ts
git commit -m "feat(frontend): 步骤链 todo 驱动——plan 事件同步 steps(pending/running/completed 三态)"
```

---

### Task 5: 影子双跑比对

**Files:**
- Create: `backend/app/harness/shadow.py`
- Modify: `backend/app/api/v1/chat.py`(shadow 分支收尾处挂后台任务,约 +25 行)
- Test: `backend/tests/test_harness_shadow.py`

**Step 1: 写失败测试**

`backend/tests/test_harness_shadow.py`:

```python
"""影子双跑比对测试:legacy 与 harness 双跑,产出比对记录;影子失败不影响主流程。"""
import json

import pytest

from app.harness import shadow


class _FakeAgent:
    def __init__(self, text="智能体回答", tools=0):
        self.text = text
        self.tools = tools

    async def astream(self, input_data, config, stream_mode=None):
        from app.harness.sse_bridge import HarnessEventBridge

        bridge = HarnessEventBridge()
        events = [("messages", (type("M", (), {"content": self.text, "tool_calls": None,
                                               "tool_call_chunks": None,
                                               "additional_kwargs": {},
                                               "reasoning_content": ""})(),
                                {"langgraph_node": "agent"}))]
        for ev in events:
            for sse in bridge.feed(ev):
                yield sse


@pytest.fixture
def patched(monkeypatch, tmp_path):
    monkeypatch.setattr(shadow, "build_harness_agent", lambda: _FakeAgent())
    monkeypatch.setattr(shadow, "COMPARISON_LOG", tmp_path / "shadow.jsonl")
    yield tmp_path


@pytest.mark.asyncio
async def test_comparison_record_written(patched):
    rec = await shadow.run_shadow_comparison(
        question="统计各表数据量",
        legacy_answer="legacy 回答",
        legacy_metrics={"duration_ms": 1000, "llm_calls": 4, "tools": 5},
    )
    assert rec["question"] == "统计各表数据量"
    assert rec["legacy"]["answer"] == "legacy 回答"
    assert rec["harness"]["answer"] == "智能体回答"
    assert rec["harness"]["llm_calls"] >= 1
    lines = shadow.COMPARISON_LOG.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["question"] == "统计各表数据量"


@pytest.mark.asyncio
async def test_shadow_failure_returns_none_and_logs(patched, monkeypatch):
    def boom():
        raise RuntimeError("agent build failed")

    monkeypatch.setattr(shadow, "build_harness_agent", boom)
    rec = await shadow.run_shadow_comparison(
        question="x", legacy_answer="y", legacy_metrics={"duration_ms": 1},
    )
    assert rec is None
    assert not shadow.COMPARISON_LOG.exists()


def test_report_aggregates(patched):
    import json as _json

    shadow.COMPARISON_LOG.write_text("\n".join(_json.dumps(r) for r in [
        {"question": "q1", "legacy": {"answer": "a"}, "harness": {"answer": "b", "llm_calls": 2}},
        {"question": "q2", "legacy": {"answer": "c"}, "harness": {"answer": "d", "llm_calls": 3}},
    ]), encoding="utf-8")
    report = shadow.shadow_report()
    assert report["total"] == 2
    assert report["avg_llm_calls"] == 2.5
```

**Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_harness_shadow.py -v`
Expected: FAIL(`ModuleNotFoundError: No module named 'app.harness.shadow'`)

**Step 3: 实现**

`backend/app/harness/shadow.py`:

```python
"""影子双跑比对(Phase 1 验证基建)。

HARNESS_MODE=shadow 时,data 模式的 legacy 响应照常返回;收尾后由
chat.py 以后台任务调用本模块:用同一问题跑 Harness 主循环,收集
回答文本/模型往返次数/工具调用数,与 legacy 的对应指标一起写入
JSONL 比对日志(configs/shadow_comparison.jsonl)。

设计约束:
- 影子失败(构建/执行任何异常)一律吞掉返回 None,绝不影响主流程;
- 只记录不比对(相似度判定留给人读报告;自动化阈值属 Phase 2);
- 日志按天轮转上限 SHADOW_LOG_MAX_LINES,防无限增长。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from app.harness.sse_bridge import HarnessEventBridge
from app.utils.log_utils import log

COMPARISON_LOG = Path("configs/shadow_comparison.jsonl")
SHADOW_LOG_MAX_LINES = 5000


async def run_shadow_comparison(
    question: str,
    legacy_answer: str,
    legacy_metrics: dict,
    user_name: str = "shadow",
) -> dict | None:
    """跑一次 Harness 影子执行并写比对记录;任何失败返回 None(不抛)。"""
    try:
        from app.harness.agent_factory import build_harness_agent

        agent = build_harness_agent()
        bridge = HarnessEventBridge()
        text_parts: list[str] = []
        tool_calls = 0
        llm_rounds = 0
        t0 = time.monotonic()

        config = {"configurable": {"thread_id": f"shadow:{user_name}:{time.time_ns()}"}}
        aiter = agent.astream(
            {"messages": [{"role": "user", "content": question}]},
            config, stream_mode=["updates", "messages"],
        ).__aiter__()
        while True:
            try:
                event = await aiter.__anext__()
            except StopAsyncIteration:
                break
            for sse in bridge.feed(event):
                if sse["type"] == "token":
                    text_parts.append(sse.get("content", ""))
                elif sse["type"] == "tool_call":
                    tool_calls += 1
            # 粗略的模型往返计数:每个 updates.agent/model 事件记一轮
            mode, data = event
            if mode == "updates" and isinstance(data, dict):
                llm_rounds += sum(1 for k in data if k in ("agent", "model"))

        record = {
            "ts": time.time(),
            "question": question[:200],
            "legacy": {
                "answer": (legacy_answer or "")[:2000],
                **legacy_metrics,
            },
            "harness": {
                "answer": "".join(text_parts)[:2000],
                "llm_rounds": llm_rounds,
                "tool_calls": tool_calls,
                "duration_ms": int((time.monotonic() - t0) * 1000),
            },
        }
        _append(record)
        return record
    except Exception as exc:  # noqa: BLE001 —— 影子失败绝不波及主流程
        log.warning("[Shadow] 比对执行失败(已忽略): %s", exc)
        return None


def _append(record: dict) -> None:
    COMPARISON_LOG.parent.mkdir(parents=True, exist_ok=True)
    with COMPARISON_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    _rotate()


def _rotate() -> None:
    try:
        lines = COMPARISON_LOG.read_text(encoding="utf-8").splitlines()
        if len(lines) > SHADOW_LOG_MAX_LINES:
            COMPARISON_LOG.write_text(
                "\n".join(lines[-SHADOW_LOG_MAX_LINES:]) + "\n", encoding="utf-8",
            )
    except OSError:
        pass


def shadow_report() -> dict:
    """聚合比对日志:总数 + harness 平均模型往返(供人工审查)。"""
    if not COMPARISON_LOG.exists():
        return {"total": 0, "avg_llm_rounds": 0}
    records = []
    for line in COMPARISON_LOG.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    rounds = [r.get("harness", {}).get("llm_rounds", 0) for r in records]
    return {
        "total": len(records),
        "avg_llm_rounds": round(sum(rounds) / len(rounds), 2) if rounds else 0,
    }
```

`backend/app/api/v1/chat.py` shadow 分支(在 legacy 生成器返回后、路由函数 return 之前):

```python
# ── HARNESS_MODE=shadow:后台双跑比对(失败/超时均不影响主响应)──
if _HARNESS_MODE == "shadow" and mode == "data":
    import asyncio as _a
    from app.harness.shadow import run_shadow_comparison

    _legacy_metrics = {"duration_ms": int((_time.monotonic() - _req_started) * 1000)}

    async def _shadow_task():
        try:
            await _a.wait_for(
                run_shadow_comparison(question, legacy_answer="", legacy_metrics=_legacy_metrics,
                                      user_name=user_name),
                timeout=float(_os.getenv("HARNESS_SHADOW_TIMEOUT", "120")),
            )
        except Exception as _se:  # noqa: BLE001
            log.warning("[Shadow] 后台任务异常(已忽略): %s", _se)

    _a.create_task(_shadow_task())
```

(注:`legacy_answer=""` 为占位——legacy 的完整回答文本收集属既有生成器内部状态,Phase 1 影子比对以「问题 + harness 侧指标 + 耗时」为主,回答文本对比由人工用同一问题集在两个模式间各跑一次完成;如需自动采集 legacy 回答,在 Phase 2 切换默认时一并做。)

**Step 4: 运行确认通过**

Run: `cd backend && uv run pytest tests/test_harness_shadow.py -v`
Expected: PASS(3 passed)

**Step 5: 提交**

```bash
git add backend/app/harness/shadow.py backend/tests/test_harness_shadow.py backend/app/api/v1/chat.py
git commit -m "feat(harness): 影子双跑比对——shadow 模式后台执行 Harness 并写 JSONL 比对日志"
```

---

### Task 6: Phase 1 门禁

**Files:** 无新增。仅验证与文档。

**Step 1: 后端全量测试**

Run: `cd backend && uv run pytest -q`
Expected: 全部通过,总数 = 96(Phase 0 末)+ 5(工厂)+ 9(桥接)+ 3(流式)+ 3(影子)= 116 passed

**Step 2: 前端全量测试 + 构建**

Run: `cd frontend-react && npx vitest run && npm run build`
Expected: 28 passed;built 成功

**Step 3: 默认行为不变验证**

Run:
```
cd d:/WorkSpace/Project2-Data-Agents-Pro && git --no-pager diff 5f68100 HEAD --stat -- backend/app/api/v1/chat.py
```
Expected:chat.py 的改动仅为「HARNESS_MODE 常量 + import + 两处分支」,且 `HARNESS_MODE` 默认 off;`grep -n "_HARNESS_MODE" backend/app/api/v1/chat.py` 确认分流只在 data 模式生效

**Step 4: 影子链路冒烟(不触真实 LLM,用假 Agent 已验证于 Task 5;真实 LLM 冒烟留 Phase 2 切换时)**

Run: `cd backend && uv run python -c "from app.harness.shadow import shadow_report; print(shadow_report())"`
Expected: `{'total': 0, 'avg_llm_rounds': 0}`(空日志不报错)

**Step 5: 更新设计文档状态**

在 `docs/plans/2026-10-14-harness-agent-architecture-design.md` §6 Phase 1 条目后追加:

```markdown
> Phase 1 已完成:Harness 主循环(装配工厂 + SSE 桥接 + 流式生成器)、
> HITL 等待-恢复、前端 todo 驱动步骤链、影子双跑比对均已落地并通过
> 116 项后端 + 28 项前端测试;HARNESS_MODE 默认 off,线上行为不变。
> Phase 2(切换默认)前置:用同一问题集在 on/shadow 两模式各跑一轮,
> 以 shadow_report() 与人工抽检确认"结果可用率"不低于 legacy。
```

**Step 6: 提交**

```bash
git add docs/plans/2026-10-14-harness-agent-architecture-design.md
git commit -m "docs(plan): Phase 1 主循环接入完成——门禁通过与设计文档状态更新"
```

---

## Phase 1 完成定义(DoD)

1. `build_harness_agent()` 可装配出带数据工具 + SqlGateMiddleware 的 Agent(单例,测试验参);
2. SSE 桥接把 todo/工具/中断翻译为现有协议,run_sql/make_chart 载荷产出 sql/result/chart 富事件;
3. Harness 生成器的 HITL 走 legacy 同款「approval_required → wait_for → Command(resume) 续流」,超时自动拒;
4. 前端步骤链 todo 驱动(三态),legacy plan 事件行为不变;
5. 影子双跑可产出比对日志且失败不波及主流程;
6. `HARNESS_MODE=off`(默认)时线上行为与本阶段开始前完全一致:pytest 116 + vitest 28 + build 全绿,chat.py 改动仅开关接线。
