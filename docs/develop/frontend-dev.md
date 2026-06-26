# 前端二次开发指南

本文档面向前端开发者，说明前端架构、关键组件、SSE 流式处理和任务清单机制。

> **最后更新**: 2026-06-26 — 重构为任务清单 UI、新增 node_started 事件处理。

---

## 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| Vue 3 | ^3.4 | SFC 框架 |
| TypeScript | ^5.x | 类型安全 |
| Pinia | ^2.x | 状态管理 |
| Vite | ^5.x | 构建工具 |
| Element Plus | ^2.x | UI 组件（el-table） |
| ECharts | ^5.x | 图表渲染 |
| marked | ^9.x | Markdown → HTML |
| sql-formatter | ^15.x | SQL 格式化 |

## 目录结构

```
frontend/src/
├── api/
│   └── client.ts          # axios 实例 + 下载工具
├── components/
│   ├── ChatInput.vue       # 底部输入区（含停止按钮）
│   ├── ChatSidebar.vue     # 左侧会话列表
│   ├── ClarifierCard.vue   # 追问卡片
│   ├── ExecutionCard.vue   # 执行计划卡片
│   └── NodeSeparator.vue   # 多轮对话分隔线
├── composables/
│   └── useSSE.ts           # SSE fetch + ReadableStream 消费
├── router/
│   └── index.ts            # 路由表
├── stores/
│   ├── chat.ts             # 核心状态管理（消息/任务/会话）
│   └── approval.ts         # 审批任务管理
└── views/
    ├── Chat.vue            # 聊天主页面
    ├── Home.vue            # 首页
    ├── Login.vue           # 登录
    └── Approval.vue        # 审批管理
```

## 核心架构

### SSE 流式接收 (`useSSE.ts`)

使用 `fetch + ReadableStream` 而非 EventSource（需要 POST 请求体）：

```typescript
const response = await fetch(url, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ...' },
  body: JSON.stringify(body),
  signal: abortController.signal,
})

const reader = response.body!.getReader()
const decoder = new TextDecoder()
let buffer = ''

while (true) {
  const { done, value } = await reader.read()
  if (done) break
  buffer += decoder.decode(value, { stream: true })
  const lines = buffer.split('\n')
  buffer = lines.pop() || ''
  for (const line of lines) {
    if (line.startsWith('data: ')) {
      const event = JSON.parse(line.slice(6))
      dispatchEvent(event, callbacks)
    }
  }
}
```

### 事件分发

```typescript
function dispatchEvent(event, callbacks) {
  switch (event.type) {
    case 'node_started':  callbacks.onNodeStarted(event.agent, event.label); break
    case 'thinking':      callbacks.onThinking(event.agent, event.phase, event.content); break
    case 'token':         callbacks.onToken(event.content); break
    case 'tool_call':     callbacks.onToolCall(event.tool_name, meta); break
    case 'tool_result':   callbacks.onToolResult(event.tool_name, meta); break
    case 'sql':           callbacks.onSQL(event.content); break
    case 'result':        callbacks.onResult(event.data, event.columns); break
    case 'chart':         callbacks.onChart(event.config); break
    case 'plan':          callbacks.onPlan(event.intent, event.intent_label, event.steps, ...); break
    case 'clarification': callbacks.onClarification(event.text, event.options, ...); break
    case 'title':         callbacks.onTitle(event.thread_id, event.content, ...); break
    case 'error':         callbacks.onError(event.error, event.code, event.recoverable); break
    case 'done':          callbacks.onDone(); break
  }
}
```

## 任务清单（替代旧水平管道）

### 数据模型 (`chat.ts`)

```typescript
interface TaskItem {
  key: string           // Agent 名称，如 "sql_coder"
  label: string         // 显示名称，如 "生成SQL"
  status: 'pending' | 'running' | 'completed'
  startedAt?: number
}

const tasks = ref<TaskItem[]>([])
const tasksCollapsed = ref(false)
```

### 更新时机

```
onNodeStarted  → 将任务标记为 running（旋转 spinner）
onThinking     → 将任务标记为 completed（绿色对勾）
onDone         → completeAllTasks() → 2s 后自动折叠
```

### 组件模板 (`Chat.vue`)

```html
<div class="task-list" :class="{ 'is-collapsed': store.tasksCollapsed }">
  <div class="task-list-header" @click="store.tasksCollapsed = !store.tasksCollapsed">
    <span class="task-list-title">
      <svg>📋</svg> 任务清单
    </span>
    <span class="task-list-count">
      {{ completedCount }}/{{ tasks.length }}
      <svg class="chevron">▼</svg>
    </span>
  </div>
  <div v-if="!store.tasksCollapsed" class="task-list-body">
    <div v-for="task in tasks" class="task-item" :class="statusClass(task)">
      <div class="task-item-icon">
        <!-- running → spinner SVG -->
        <!-- completed → checkmark SVG -->
      </div>
      <span class="task-item-label">{{ task.label }}</span>
    </div>
  </div>
</div>
```

完成后自动折叠为一行绿色提示：`✅ 任务清单 (8/8) ▼`

### 去重逻辑

```typescript
// onToken: sql_coder/rag_agent 活跃时跳过 token 文本输出
setCurrentAgent(agent) { this.currentAgent = agent }
onToken(content) {
  if (this.currentAgent === 'sql_coder' || this.currentAgent === 'rag_agent') return
  // ... 正常流式追加
}

// onToolCall/onToolResult: 过滤空值 + sql/sql_preview 字段
const cleanMeta = {}
for (const [k, v] of Object.entries(meta)) {
  if (v !== undefined && v !== null && v !== '' && k !== 'sql' && k !== 'sql_preview')
    cleanMeta[k] = v
}
```

## 消息渲染

### 消息类型映射

| msg.type | 渲染组件 |
|----------|---------|
| `text` (user) | `message-bubble--user` |
| `text` (assistant) | `message-bubble--assistant` + `marked` Markdown |
| `sql` | `message-sql` (SQL 格式化 + 复制按钮) |
| `result` | `message-result` (el-table + CSV/Excel 导出) |
| `chart` | `message-chart` (VChart + ECharts) |
| `thinking` | `thinking-card` (可折叠) |
| `tool_call` / `tool_result` | `tool-card` (紧凑型，可展开查看详情) |
| `clarification` | `ClarifierCard` (追问按钮) |
| `plan` | `ExecutionCard` (执行计划卡片) |
| `error` | `message-error-row` (错误信息 + 重试按钮) |

## Store 核心方法

| 方法 | 功能 |
|------|------|
| `sendMessage(text)` | 发送消息→SSE 连接→事件处理 |
| `loadSession(threadId)` | 从 API 加载历史会话 |
| `loadSessions()` | 加载会话列表 |
| `loadSuggestions(force)` | 加载建议问题（8s 超时→默认模板兜底） |
| `stopGeneration()` | 中止 SSE 连接 |
| `newSession()` | 新建会话（清空消息） |
| `retryLastMessage()` | 重试最后的失败消息 |
| `exportData(data, cols, format)` | 导出 CSV/Excel |
