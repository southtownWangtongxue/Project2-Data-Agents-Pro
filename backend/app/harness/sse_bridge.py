"""Harness SSE 事件桥接器(Phase 1)。

把 deepagents astream 的 (mode, data) 事件流翻译为现有 SSE 事件 dict:
- messages 模式 → token(正文)/reasoning(思考)
- updates 模式 → plan(todos 变更)/tool_call(agent 节点完整 calls,唯一来源)/
  sql+result(run_sql 富事件)/chart(make_chart 富事件)/
  tool_result(紧凑摘要)/approval_required(中断)

tool_call 只从 updates 的完整 tool_calls 发:messages 流式首 chunk 只带
name/id、args 为空(实测),在 messages 侧发会导致卡片参数残缺。

step_id 语义(todo 驱动):todos 中 status=in_progress 的条目即当前步骤,
工具事件挂当前步骤;无 in_progress 时挂 0(平铺)。

协议只增不改:全部输出事件均属既有 SSEEventType;plan 事件新增可选字段
todos([{id,title,status}]),前端按有无该字段切换 todo 驱动/legacy 两种分组。
"""
from __future__ import annotations

import json
from typing import Any

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
        # 已发过 tool_call 的调用 id(updates 路径内去重:同一调用只发一次卡)
        self._emitted_call_ids: set[str] = set()

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

        # 注意:messages 模式不發 tool_call——实测流式首 chunk 只带 name/id、
        # args 为空,完整参数只存在于 updates.agent 的完整 tool_calls(见
        # _on_updates);在此發会导致前端卡片参数残缺或同 id 双卡。
        return out

    def _emit_tool_call(self, tc: dict) -> dict | None:
        """把一个工具调用转成 SSE 事件;已发过(同 id)或无名则跳过。"""
        call_id = str(tc.get("id") or "")
        name = tc.get("name")
        if call_id and call_id in self._emitted_call_ids:
            return None
        if not name:
            return None
        if call_id:
            self._emitted_call_ids.add(call_id)
        return {
            "type": "tool_call",
            "name": name,
            "args": _stringify_args(tc.get("args") or "")[:500],
            "step_id": self.current_step_id,
        }

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

            # agent/model 节点收尾消息里的完整 tool_calls(与 messages 增量去重)
            if node_name in ("agent", "model"):
                for msg in state_update.get("messages", []) or []:
                    for tc in getattr(msg, "tool_calls", None) or []:
                        emitted = self._emit_tool_call(tc)
                        if emitted:
                            out.append(emitted)

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
            out.extend(self._rich_events(name, content))
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
