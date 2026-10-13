# 前端二次开发指南

本文档面向前端开发者，说明 `frontend-react/` 的架构、关键组件、SSE 事件管线与消息渲染约定。

> **最后更新**: 2026-10-13 — 前端切换为 React 19 + Ant Design X 2.9，Vue 版本冻结归档于 `frontend/`（tag `vue-legacy`）。

---

## 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| React | ^18.3（对齐 antdx 2.9 基线） | 视图层 |
| TypeScript | ~5.6 | 类型安全 |
| Vite | ^5 | 构建 / 开发服务器 |
| Ant Design | ^6 | 基础组件与暗色令牌（ConfigProvider） |
| @ant-design/x | ^2.9 | Bubble.List / Sender / Conversations / Welcome / Prompts / ThoughtChain / Actions |
| @ant-design/x-sdk | ^2.9 | XStream（SSE 解析） |
| @ant-design/x-markdown | ^2.9 | 流式 Markdown 渲染 |
| zustand | ^5 | 领域状态（chat / auth / config） |
| react-router-dom | ^7 | 路由 |
| TailwindCSS | ^3.4 | 工具类样式与设计令牌 |
| echarts-for-react | ^3 | 图表渲染 |
| vitest | ^2 | 单元测试 |

## 目录结构

```
frontend-react/src/
├── api/client.ts             # fetch 封装 + JWT 读写 + 下载
├── sdk/
│   ├── protocol.ts           # 18 类 SSE 事件类型与领域 Msg/Step 类型
│   ├── DataAgentProvider.ts  # XStream 消费 SSE，逐事件回调
│   ├── reducer.ts            # 纯函数：SSE 事件 → chat 状态（含审批状态机）
│   ├── blocks.ts             # 纯函数：消息 → 渲染块（步骤全局聚合）
│   └── *.test.ts             # vitest：协议 / reducer / blocks / 审批
├── stores/
│   ├── chat.ts               # 会话、消息、流编排、排队、取消、导出
│   ├── auth.ts               # 登录态
│   └── config.ts             # LLM provider 与思考模式
├── pages/
│   ├── Chat.tsx              # 对话工作台（三段式布局）
│   ├── Login.tsx
│   ├── AdminLayout.tsx
│   └── admin/                # 模型 / 技能 / MCP / 审批策略配置
├── components/
│   ├── chat/                 # MessageList / MessageItem / StepChain / SenderInput /
│   │                         # ChatSidebar / WelcomePanel / StatBar / TrajectoryDrawer
│   │                         # SQLCard / ResultTable / ChartView / ToolCard / ReasoningCard /
│   │                         # PlanCard / ClarifyCard / ApprovalCard / ErrorCard / SubagentNode
│   └── bits/                 # TypeText / Aurora / ClickSpark（克制动效点缀）
├── theme/tokens.ts           # antd 暗色令牌（碳黑 + 品牌紫）
└── index.css                 # Tailwind 指令 + CSS 变量 + 动画
```

## 核心架构

### SSE 流式接收（`sdk/DataAgentProvider.ts`）

使用 `XStream`（官方 SSE 解析器）消费 `POST /api/v1/chat/completions` 的响应流，替代手写 buffer 行解析：

```typescript
const stream = XStream({
  transformStream: sseStream,
  onSuccess: res => { ... },
})

const response = await fetch(url, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}` },
  body: JSON.stringify(payload),
  signal,
})

stream.process({
  stream: response.body,
  onEvent: event => onEvent(event as SSEEvent),
  onError: err => onError(err.message),
})
```

取消通过 `AbortController` 触发，同时调用 `POST /api/v1/chat/cancel` 通知后端中断图执行。

### 事件分发（`sdk/reducer.ts`）

事件 → 状态的转换全部收敛在纯函数 `applyEvent(chat, event)`，便于单测；`stores/chat.ts` 只负责网络编排与性能统计。

| 事件 | 状态变化 |
|------|----------|
| `thread_id` | 记录多轮会话 ID |
| `node_started` | 新建 `Step`（running） |
| `token` | 按 `step_id` + `channel` 追加到对应正文消息（并行节点隔离槽位） |
| `reasoning` / `thinking` | 思考内容消息（`thinking_mode` 关闭时仅隐藏不丢弃） |
| `tool_call` / `tool_result` | 工具卡（结果即正文的 `misc_agent` 降级为状态点） |
| `sql` / `result` / `chart` | SQL 卡片 / 数据表格 / ECharts 图表 |
| `plan` / `clarification` | 执行计划卡 / 追问卡（空步骤不渲染） |
| `approval_required` | 审批卡（`state: pending`，流在断点挂起） |
| `title` | 会话标题（`done` 之后异步推送，不阻塞结束） |
| `done` / `error` | 结束 / 错误消息 |

### 渲染块编排（`sdk/blocks.ts`）

- 用户消息、无 `stepId` 的消息 → 平铺块；
- 同一 `stepId` 的消息**全局聚合**为一个步骤块（并行 analyst / reporter 交错到达也不会拆成多个步骤头）；
- 步骤块插入在「该步骤首条消息」出现的位置。

## 步骤链（受控折叠）

组件：`components/chat/StepChain.tsx`，视觉对齐官方 `ThoughtChain`。

语义（已确认，不可回退）：

1. 步骤 `running` → 强制展开；
2. 步骤 `completed` → 2 秒后自动折叠；
3. 用户手动点击 → 用户意图优先于自动行为；
4. 组内固定类型序：思考（reasoning/thinking）→ 工具（tool）→ 正文 / SQL / 结果 / 图表。

## 消息渲染

`MessageItem.tsx` 按 `Msg.kind` 分发到 14 类渲染器：

| kind | 组件 | 说明 |
|------|------|------|
| `text`(user) | 气泡（placement=end） | 品牌紫渐变底 |
| `text`(ai) | `XMarkdown` | `streaming.hasNextChunk` 跟随流式状态 |
| `sql` | `SQLCard` | `channel=sql` 的逐 token 流式写入 |
| `result` | `ResultTable` | antd Table + CSV/Excel 导出 |
| `chart` | `ChartView` | echarts-for-react 懒渲染 |
| `tool` | `ToolCard` | 紧凑型，可展开详情 |
| `reasoning` / `thinking` | `ReasoningCard` / 内联 | 跟随 `thinkingModeEnabled` |
| `plan` | `PlanCard` | 空 `steps` 不渲染 |
| `clarification` | `ClarifyCard` | 追问选项一键发送 |
| `approval` | `ApprovalCard` | 通过 / 拒绝 / 意见，调 `/chat/approve` |
| `error` | `ErrorCard` | 错误码 + 重试 |
| `status` | 内联状态胶囊 | 紫点脉冲 |

## 对话内审批（HITL）

后端在 `GraphInterrupt` 分支发出 `approval_required` 后**保持 SSE 流挂起**，等待审批决策（Redis 通知，超时 5 分钟自动拒绝）；收到决策后以 `Command(resume=...)` 恢复同一条图并继续输出。前端只需渲染审批卡并提交决策，后续事件自然汇入同一条流。

安全约束：审批沿用后端 tier 三档权限，非管理员不可自审；提交失败必须显式提示，不得静默。

## Store 核心方法（`stores/chat.ts`）

| 方法 | 功能 |
|------|------|
| `sendMessage(text, mode?, webSearch?, model?)` | 发送消息 → SSE 流；运行中再发送则入 `pendingQueue` 排队 |
| `cancelGeneration()` | 中止 SSE + 通知后端取消 |
| `retryLastMessage()` | 移除最后一轮并重发 |
| `loadSessions()` / `loadSession(threadId)` | 会话列表 / 历史回放 |
| `deleteSession()` / `editSessionTitle()` | 会话删除 / 重命名 |
| `loadSuggestions(force?)` | 建议问题（8s 超时 → 模板兜底） |
| `resolveApprovalMsg(msgId, state, comment)` | 提交审批决策 |
| `exportData(data, columns, format)` | 导出 CSV / Excel |

## 本地验证

```bash
cd frontend-react
npm run dev            # 开发服务器 :5173，/api 代理到 :8000
npx tsc -b             # 类型检查
npm run build          # 生产构建
npx vitest run         # 数据流单测（Provider / reducer / blocks / 审批）
```

> 后端服务重启由人工执行；前端改动通过 Vite HMR 自动生效。