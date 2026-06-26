# 对话接口

核心对话接口 `POST /api/v1/chat/completions`，基于 SSE 流式推送实时进度和结果。

> **最后更新**: 2026-06-26 — 更新 SSE 事件类型、新增 node_started、任务清单机制。

---

## 流式对话

### `POST /api/v1/chat/completions`

接收用户消息，通过 SSE 流式返回执行进度和结果。需要 Bearer Token 认证。

#### 请求体

```json
{
  "messages": [
    {"role": "user", "content": "查询上个月的销售额TOP10"}
  ],
  "stream": true,
  "thread_id": "admin:uuid"  // 可选，多轮对话复用
}
```

#### 响应格式

`Content-Type: text/event-stream`。每个事件一行：

```
data: {"type": "node_started", "agent": "clarify_plan", "label": "意图分析"}
```

#### SSE 事件类型

| 类型 | 触发时机 | 关键字段 |
|------|---------|---------|
| `thread_id` | 流开始时 | `thread_id` |
| `node_started` | **每个节点开始时** | `agent`, `label` |
| `thinking` | 节点完成时 | `agent`, `phase`, `content` |
| `clarification` | 意图不明确时 | `text`, `options` |
| `plan` | 执行计划生成后 | `intent`, `intent_label`, `steps`, `chart_suitable` |
| `tool_call` | 工具调用开始 | `tool_name`, `sql`/`rows`/`cols` |
| `tool_result` | 工具调用结束 | `tool_name`, `row_count` |
| `sql` | SQL 生成完成 | `content` |
| `result` | 查询结果 | `data`, `columns` |
| `token` | 流式文本（逐字） | `content` |
| `chart` | 图表配置 | `config` |
| `title` | 标题生成 | `content`, `thread_id`, `node_index` |
| `approval_required` | 高危 SQL 需审批 | `thread_id`, `sql`, `reason` |
| `error` | 异常 | `error`, `code`, `recoverable` |
| `done` | 流结束 | — |

#### 典型交互时序

```
用户: "查询a_sheet1表project_no为1到5的cur_month_actual"

SSE 事件流:
  → thread_id: "admin:uuid"
  → node_started: "意图分析" (running)
  → plan: {intent:"query_data", steps:[...]}
  → node_started: "加载表结构" (running)
  → node_started: "生成SQL" (running)
  → sql: "SELECT cur_month_actual FROM a_sheet1 WHERE project_no BETWEEN 1 AND 5;"
  → node_started: "安全审核" → "执行查询"
  → tool_call: "execute_sql"
  → result: {data:[{cur_month_actual:16516},...], columns:["cur_month_actual"]}
  → tool_result: "execute_sql"
  → node_started: "质量评估" → "数据分析"
  → token: "共查询到" → token: " 5 条记录..." → ... (Markdown 流式)
  → node_started: "生成图表"/"生成回答"
  → node_started: "完成"
  → title: "查询a_sheet1表实际值"
  → done
```

#### 去重说明

- **SQL 仅出现一次**：由 `sql` 事件展示，不再有 token 流或 tool_call 重复
- **分析文本流式输出**：由 `token` 事件逐字追加，无 tool_call/text 重复
- **工具卡片清洁**：`tool_call`/`tool_result` 仅含必要字段，无 `undefined`

---

## 会话管理

### `GET /api/v1/chat/sessions`

获取当前用户的会话列表。

### `DELETE /api/v1/chat/sessions/{thread_id}`

删除指定会话（MySQL + Redis 双删）。

### `GET /api/v1/chat/sessions/{thread_id}`

恢复历史会话的完整消息。遍历所有节点从 Redis 恢复每轮数据。

返回格式：
```json
{
  "thread_id": "admin:uuid",
  "title": "查询项目编号与名称",
  "nodes": [
    {"index": 0, "title": "第1轮标题", "question": "用户问题", "run_id": "admin:run-uuid"}
  ],
  "messages": [
    {"role": "user", "type": "text", "content": "用户问题"},
    {"role": "assistant", "type": "sql", "sql": "SELECT ..."},
    {"role": "assistant", "type": "result", "data": [...], "columns": [...]},
    {"role": "assistant", "type": "text", "content": "Markdown分析..."}
  ]
}
```

---

## 审批回调

### `POST /api/v1/chat/approve`

```json
{
  "thread_id": "admin:uuid",
  "approved": true,
  "comment": "确认安全，允许执行"
}
```
