# AntDesignX Vue 前端改造开发计划

> 版本：v1.0 · 日期：2026-08-05
> 依据：`docs/AntDesignXVue集成方案.md` · 官方文档：https://antd-design-x-vue.netlify.app/
> 硬性约束：**后端零改动**；AntDesignX Vue 组件与 API 一律以官方文档为准，禁止猜测。
> 接入路线：渐进式新增 `/chat-x` 页面，复用现有 Pinia store 数据层，仅替换视图层。

---

## 1. 目标与接入路线

### 1.1 目标

在现有 DataAgent Pro 前端中，新增一个基于 **Ant Design X Vue** 的 AI 对话页 `ChatXVue.vue`（路由 `/chat-x`），实现：

- 会话列表（`Conversations`）对接 `store.sessions`
- 消息流（`Bubble.List`）对接 `store.messages`，结构化消息（SQL/结果/图表/错误/追问/计划）经 `messageRender` 自定义渲染
- 输入区（`Sender`）对接 `store.sendMessage` / `store.stopGeneration`
- 欢迎页与建议列表（`Welcome` + `Prompts`）对接 `store.suggestions`
- 思维链（`ThoughtChain`）渲染 `thinking` / `tool_chain` 类消息

### 1.2 接入路线（渐进式，不回归）

```
现有 /chat（Chat.vue 自绘组件）     ←  保持不变
        │
        └── 新增 /chat-x（ChatXVue.vue，AntDesignX Vue 组件）
              │
              ├── 复用 stores/chat.ts（sendMessage/loadSessions/loadSession/…）
              ├── 复用 composables/useSSE.ts（SSE 事件 → store 内部更新）
              └── 仅替换视图层（Conversations / Bubble.List / Sender / Prompts / ThoughtChain）
```

> 数据层（store + SSE）零改动，所有后端接口契约不变。

### 1.3 数据契约（复用现有 store 状态与方法）

| store 状态/方法 | 类型 | 对接组件 |
|---|---|---|
| `store.messages` | `ChatMessage[]` | `Bubble.List` 的 `items`（经 `messageRender` 分发） |
| `store.sessions` | `SessionInfo[]` | `Conversations` 的 `items` |
| `store.currentThreadId` | `string` | `Conversations` 的 `activeKey` |
| `store.suggestions` | `string[]` | `Prompts` 的 `items` |
| `store.isLoading` | `boolean` | `Bubble` 的 `loading` / `Sender` 的 `loading` |
| `store.sendMessage(text, mode, webSearch, model?)` | fn | `Sender` 的 `onSubmit` |
| `store.stopGeneration()` | fn | `Sender` 的 `onCancel` |
| `store.loadSession(threadId)` | fn | `Conversations` 的 `onActiveChange` |
| `store.deleteSession(threadId)` | fn | `Conversations` menu「删除」 |
| `store.editSessionTitle(threadId, title)` | fn | `Conversations` menu「重命名」 |
| `store.newSession()` | fn | 「新建会话」按钮 |
| `store.loadSuggestions(force?)` | fn | 建议列表刷新 |

---

## 2. 官方 API 核对清单（2026-08-05 逐一核对官方文档）

> 本节为**唯一权威依据**。实施时以本节签名为准，任何与直觉不符之处以此为准。

### 2.1 `Bubble` / `Bubble.List`

| 项 | 官方签名 |
|---|---|
| `Bubble.props` | `avatar: VNode` / `classNames` / `content: ContentType`（VNode\|object\|string\|number）/ `footer` / `header` / `loading: boolean` / `placement: 'start'\|'end'` / `shape: 'round'\|'corner'` / `styles` / `typing: boolean\|{step?,interval?}` / `variant: 'filled'\|'borderless'\|'outlined'\|'shadow'` / `loadingRender: () => VNode` / `messageRender: (content) => VNode` |
| `Bubble.events` | `onTypingComplete`（打字结束回调） |
| `Bubble.slots` | `avatar` / `header` / `footer` / `loading` / `message`（作用域 `{content}`） |
| `Bubble.List.props` | `autoScroll: boolean`（默认 true，用户手动滚动后暂停）/ `items: (BubbleProps & {key?, role?})[]` / `roles: Record<string, BubbleProps> \| (bubble, index) => BubbleProps` / `onScroll: (e) => void` |
| `Bubble.List.slots` | `avatar` / `header` / `footer` / `loading` / `message`（作用域 `{item}`） |
| `Bubble.List.methods` | `scrollTo({key, block})` 定位消息 |

**roles 用法要点**：`items[].role` 自动匹配 `roles` 中对应键；角色默认属性可含 `placement/avatar/typing/style/messageRender` 等 `BubbleProps`。

### 2.2 `Conversations`

| 项 | 官方签名 |
|---|---|
| `props` | `activeKey: string` / `defaultActiveKey: string` / `items: Conversation[]` / `onActiveChange: (value: string) => void` / `menu: MenuProps \| ((conv: Conversation) => MenuProps)` / `groupable: boolean \| GroupableProps` / `styles` / `classNames` |
| `Conversation` | `key: string` / `label: VNode\|string` / `timestamp?: number` / `group?: string` / `icon?: VNode\|string` / `disabled?: boolean` |
| `GroupableProps` | `sort?: (a,b)=>number` / `title?: (group, {components:{GroupTitle}}) => VNode` |
| 事件 | **仅 `onActiveChange`**（无 `onSelect`、无内建 `onDelete`/`onRename`） |

> 删除/重命名通过 `menu` 的 `onClick` 实现，选中变更统一走 `@active-change`。

### 2.3 `Sender`

| 项 | 官方签名 |
|---|---|
| `props` | `value`（v-model）/ `loading: boolean` / `placeholder`（透传）/ `prefix: VNode\|()=>VNode` / `actions: VNode \| (oriNode, {components}) => VNode \| false` / `allowSpeech` / `submitType: 'enter'\|'shiftEnter'` / `autoSize: boolean\|{minRows?,maxRows?}`（默认 `{maxRows:8}`）/ `disabled` / `readOnly` / `header` / `footer` / `classNames` / `styles` |
| 事件 | `onSubmit: (message: string) => void` / `onChange: (value, event?) => void` / `onCancel: () => void` / `onPasteFile: (firstFile, files) => void` |
| `#actions` 插槽 | 作用域 `{ori, info:{components:{SendButton, ClearButton, LoadingButton, SpeechButton}}}` |
| `ref` | `focus()` / `blur()` / `nativeElement` |

> **不存在** `disableSend`、`clear` 事件。停止生成用 `loading=true` 时 Sender 自动切换为停止按钮（`onCancel`）。
> `SendButton` / `LoadingButton` 等通过 `#actions` 插槽的 `info.components` 获取。

### 2.4 `Welcome` + `Prompts`

| 组件 | 官方签名 |
|---|---|
| `Welcome.props` | `title: VNode\|string` / `description` / `icon: VNode` / `extra: VNode\|string` / `variant: 'filled'\|'borderless'` / `classNames` / `styles` / `rootClassName` |
| `Welcome` | **无事件、无 suggestions prop**。建议列表一律用 `Prompts` 组件 |
| `Prompts.props` | `items: PromptProps[]` / `title` / `vertical: boolean` / `wrap: boolean` / `onItemClick: ({data: PromptProps}) => void` / `classNames` / `styles` |
| `PromptProps` | `key` / `label: VNode\|string`（**提示主要内容是 `label`，不是 `title`**）/ `description` / `icon: VNode` / `children: PromptProps[]` / `disabled` |

### 2.5 `ThoughtChain`

| 项 | 官方签名 |
|---|---|
| `props` | `items: ThoughtChainItem[]` / `size: 'large'\|'middle'\|'small'`（默认 middle）/ `collapsible: boolean\|CollapsibleOptions` / `prefixCls` / `classNames` / `styles` |
| `ThoughtChainItem` | `title: VNode\|string` / `description` / `content: VNode\|string` / `extra` / `footer` / `icon: VNode` / `key: string` / `status: 'pending'\|'success'\|'error'` / `tooltip` |
| `CollapsibleOptions` | `expandedKeys: string[]` / `onExpand: (keys)=>void` |

> **不存在 `children` 字段**。嵌套链条通过把子 `<ThoughtChain>` 放进某节点的 `content` 实现。

### 2.6 `useXAgent` / `useXChat` / `XStream`

| 项 | 官方签名 |
|---|---|
| `useXAgent` | 返回 `[agent]`；`agent.request(info, callbacks)`；`agent.isRequesting()`；自定义模式 `request: (info, {onUpdate, onSuccess, onError, onStream}) => void` |
| 预设模式 | `baseURL` / `key` / `model` / `dangerouslyApiKey`（有安全风险，本项目不采用） |
| `useXChat` | 配置 `agent` / `parser` / `requestPlaceholder` / `requestFallback` / `transformMessage` / `resolveAbortController`；返回 `messages` / `parsedMessages` / `onRequest` / `setMessages` |
| `XStream` | `XStream({readableStream, transformStream?})` → `ReadableStream`；默认 `sseTransformStream` 解析 SSE（chunk 为 `{event, data}`） |

> **本项目决策**：数据层**继续复用现有 `useSSE.ts` + `stores/chat.ts`**，不采用 `useXAgent`/`useXChat`（避免重复实现 SSE 解析，降低回归风险）。`XStream` 仅作为参考，不引入。

### 2.7 与集成方案文档的差异修正（2026-08-05）

| 原文档写法（有误） | 官方文档正确写法 |
|---|---|
| `Welcome :suggestions @click` | `Welcome` 仅展示标题/描述/图标，建议列表改用 `<Prompts :items @item-click>` |
| `Sender :disable-send` / `@clear` | 不存在；`loading` 时自动变停止按钮触发 `@cancel`；`#actions` 插槽自定义按钮 |
| `ThoughtChain :items` 的 `children` | `ThoughtChainItem` 无 `children`；嵌套链条用 `content` 内嵌子 `<ThoughtChain>` |

---

## 3. 阶段计划总览（P0–P5）

| 阶段 | 目标 | 涉及文件 | 验收标准 |
|---|---|---|---|
| **P0** | 依赖安装 + 按需引入 + `/chat-x` 路由与占位页 | `frontend/package.json`、`frontend/src/views/ChatXVue.vue`（新建）、`frontend/src/router/index.ts` | 页面可访问，显示 XProvider 包裹的欢迎文案，无控制台报错 |
| **P1** | `XConversations` 会话列表 | `frontend/src/components/x/XConversations.vue`（新建） | 会话列表渲染、分组、选中加载历史、menu 删除/重命名 |
| **P2** | `XBubbleList` 消息流 + `MessageRenderer` | `frontend/src/components/x/XBubbleList.vue`（新建）、`frontend/src/components/x/MessageRenderer.vue`（新建） | 用户/AI 气泡、Markdown、SQL/结果/图表/错误/追问/计划卡片全部可渲染，流式打字 |
| **P3** | `XSender` 输入区 | `frontend/src/components/x/XSender.vue`（新建） | 发送消息、loading 停止按钮、模式/联网搜索开关（prefix） |
| **P4** | `XWelcome` 欢迎页 + `Prompts` 建议 | `frontend/src/components/x/XWelcome.vue`（新建） | 空会话时展示欢迎语 + 建议列表，点击建议直接发送 |
| **P5** | `XThoughtChain` 思维链 + `ChatXVue.vue` 组装 + 端到端验证 | `frontend/src/components/x/XThoughtChain.vue`（新建）、`frontend/src/views/ChatXVue.vue`（改写） | 完整对话流程可用；浏览器验证通过 |

---

## 4. 每阶段提示词

> 使用方法：将某一阶段的提示词整段复制给 AI 编码助手，由其按该阶段要求实施。提示词内已包含阶段边界、官方 API 依据与验收标准，避免越界改动。

### 4.0 全局提示词（各阶段通用前置）

```text
你是 DataAgent Pro 项目的前端工程师。项目位于 d:/WorkSpace/AI_Study/Project2-Data-Agent-Pro，
前端在 frontend/ 目录（Vue3 + Vite + TS + ElementPlus + Pinia，端口 5173，后端 8000）。

本项目正在用 Ant Design X Vue（npm 包名 ant-design-x-vue，官方文档 https://antd-design-x-vue.netlify.app/）
渐进式改造 AI 对话界面。铁律：
1. 所有 AntDesignX Vue 组件/API 必须严格按官方文档使用，禁止凭记忆猜测；
   权威签名见 docs/plans/2026-08-05-ant-design-x-vue-integration.md 第 2 章。
2. 后端零改动；数据层复用 frontend/src/stores/chat.ts 与 composables/useSSE.ts。
3. 只读不改现有 Chat.vue / ChatInput.vue / ChatSidebar.vue（旧界面保持可用）。
4. 新增组件统一放在 frontend/src/components/x/ 目录。
5. 代码完成后：确认前后端已启动；若已启动，用 Chrome DevTools MCP 做端到端浏览器验证；
   若未启动，先启动（后端: cd backend && uv run uvicorn app.main:app --reload --port 8000；
   前端: cd frontend && npm run dev）再验证。
```

### 4.1 P0 提示词：依赖安装 + 按需引入 + 路由占位

```text
阶段 P0：AntDesignX Vue 接入基础。

任务：
1. 在 frontend/ 目录执行：npm install ant-design-x-vue ant-design-vue @ant-design/icons-vue
   （ant-design-vue 与 @ant-design/icons-vue 是其 peer 依赖，须显式安装）。
2. 新建 frontend/src/views/ChatXVue.vue（占位版）：
   - 顶部用 <XProvider> 包裹整页（默认主题即可）；
   - ⚠️ 样式说明（2026-08-05 实测包 `ant-design-x-vue@1.6.0`）：包内**无 CSS 文件**
     （`dist/` 无 `.css`，官方 README 示例也未引入任何样式），组件样式由 cssinjs 在
     `XProvider` 内运行时注入，**无需、也无法引入 `ant-design-x-vue/dist/index.css`**；
   - 展示一个简单的欢迎占位（如「Ant Design X 对话页（建设中）」），引用 store 验证可用。
3. 在 frontend/src/router/index.ts 增加路由：
   { path: '/chat-x', name: 'ChatX', component: () => import('@/views/ChatXVue.vue'),
     meta: { title: 'AI 对话 (X)', requiresAuth: true } }
4. 暂不改 vite.config.ts（不引入 unplugin），采用组件内手动按需 import。
   即每个 .vue 组件 <script setup> 中：import { Bubble, Sender } from 'ant-design-x-vue'。

验收：
- npm run dev 无编译错误；
- 浏览器访问 /chat-x 能显示占位内容且控制台无报错；
- 现有 /chat 页面不受影响。
完成后按全局提示词第 5 条做浏览器验证。
```

### 4.2 P1 提示词：XConversations 会话列表

```text
阶段 P1：基于 Conversations 组件实现会话列表。

新建 frontend/src/components/x/XConversations.vue，只读消费 useChatStore：
- 数据映射（严格对照文档 2.2 节）：
  store.sessions[] -> Conversation[]：
    { key: s.thread_id, label: s.title || s.question?.slice(0,30) || '无标题',
      timestamp: new Date(s.created_at).getTime(),
      group: groupOf(s.created_at) }  // 今天/昨天/更早
- activeKey 绑定 store.currentThreadId；@active-change 调用 store.loadSession(threadId)。
- groupable 开启分组（groupable 传 true 即可，或配置 sort）。
- menu 配置（文档 2.2 节：menu 为 MenuProps 或函数）：
  重命名：menu.onClick 中触发内联编辑（用 <Input> 渲染 label 编辑态）-> store.editSessionTitle(key, val)；
  删除：store.deleteSession(key)，注意 domEvent.stopPropagation() 防止触发选中。
- 顶部提供「新建会话」按钮（store.newSession()）。
- 空列表展示占位文案。

官方 API 依据（勿用 onSelect/onDelete/onRename）：
<Conversations :items="convItems" :active-key="store.currentThreadId"
  @active-change="onActiveChange" :menu="menuFn" groupable />

验收：左侧会话列表渲染正确、可分组、点击加载历史、右键菜单删除/重命名生效。
完成后按全局提示词第 5 条做浏览器验证。
```

### 4.3 P2 提示词：XBubbleList 消息流 + MessageRenderer

```text
阶段 P2：基于 Bubble.List 实现消息流 + 按消息类型自定义渲染。

新建两个组件：
1) frontend/src/components/x/MessageRenderer.vue —— 消息内容渲染器（不做气泡外壳）：
   - 入参 msg: ChatMessage；
   - 按 msg.type 分支渲染（沿用现有 Chat.vue 的渲染逻辑与样式，可抽取样式）：
     text/analysis -> Markdown（marked 渲染，类名 markdown-body）；
     sql -> SQL 卡片（格式化 + 复制按钮，sql-formatter）；
     result -> el-table 结果表格（data/columns + CSV/Excel 导出，store.exportData）；
     chart -> VChart（chartConfig -> ECharts option，注入暗色主题）；
     error -> 错误样式 + 重试按钮（store.retryLastMessage，recoverable）；
     status -> 居中状态行；
     thinking/tool_call/tool_result/tool_chain -> 交给 XThoughtChain（P5）或先复用折叠卡片；
     clarification -> 复用现有 components/ClarifierCard.vue；
     plan -> 复用现有 components/ExecutionCard.vue。
2) frontend/src/components/x/XBubbleList.vue：
   - roles（文档 2.1 节）：
     ai: { placement:'start', typing:{ step:5, interval:20 } }，
     user: { placement:'end' }；
   - items 映射（文档 2.1 节）：store.messages -> 
     { key: msg.id, role: msg.role==='user'?'user':'ai', content: msg, loading: ... }；
   - content 传原始 ChatMessage 对象，用 #message 插槽或 messageRender 渲染：
     <template #message="{ item }"><MessageRenderer :msg="item.content" /></template>；
   - autoScroll 默认开启（保留现有 smartScroll 行为：用户上滚时暂停，可用 onScroll 记录）。

官方 API 依据：
<Bubble.List :items="items" :roles="roles" autoScroll>
  <template #message="{ item }"><MessageRenderer :msg="item.content" /></template>
</Bubble.List>

注意：Bubble 的 content 支持任意对象（ContentType），MessageRenderer 接收的正是 ChatMessage。
验收：发送问题后用户/AI 气泡正确；Markdown/SQL/表格/图表/错误/追问/计划全部渲染；流式打字逐字更新。
完成后按全局提示词第 5 条做浏览器验证。
```

### 4.4 P3 提示词：XSender 输入区

```text
阶段 P3：基于 Sender 组件实现输入区。

新建 frontend/src/components/x/XSender.vue，对接 useChatStore：
- v-model:value 绑定本地 ref(input)；
- :loading="store.isLoading" —— 官方文档 2.3 节：loading 为 true 时发送按钮自动变为停止
  按钮，点击触发 onCancel；
- @submit="onSubmit"：text 非空且未加载时 store.sendMessage(text, mode, webSearch, model)，随后清空 input；
- @cancel="store.stopGeneration()"；
- placeholder 透传；
- prefix 插槽：放置「模式切换（data/report/doc/task）+ 联网搜索开关」，与现有 Chat.vue 一致
  （内部状态用 defineModel 或 props 传入 mode/webSearch/model）；
- actions：默认按钮即可；如需自定义，用 #actions 插槽的 info.components 获取
  SendButton/LoadingButton（文档 2.3 节），例如在发送前显示 LoadingButton。

官方 API 依据（勿用 disableSend/clear）：
<Sender v-model:value="input" :loading="store.isLoading" :placeholder="..." 
  @submit="onSubmit" @cancel="store.stopGeneration()">
  <template #prefix>...</template>
</Sender>

验收：输入/发送/流式中按钮变停止/点击停止、模式与联网搜索开关生效。
完成后按全局提示词第 5 条做浏览器验证。
```

### 4.5 P4 提示词：XWelcome 欢迎页 + Prompts 建议

```text
阶段 P4：空会话欢迎页 + 建议列表。

新建 frontend/src/components/x/XWelcome.vue，仅当 store.messages.length === 0 时展示：
- <Welcome>：title="开始您的数据分析之旅"、description=...、icon 可选（文档 2.4 节）。
  注意：Welcome 无 suggestions、无 click 事件，纯展示。
- <Prompts>：建议列表（文档 2.4 节）：
  items = store.suggestions.map(q => ({ key: q, label: q, description: '点击直接提问' }));
  @item-click="{ data }" -> store.sendMessage(data.label 或 data.key)；
  空/加载态沿用现有 Chat.vue 的骨架与兜底逻辑（store.suggestionsLoading）。
- 提供刷新按钮：store.loadSuggestions(true)。

官方 API 依据：
<Welcome title="..." description="..." />
<Prompts :items="promptItems" @item-click="onItemClick" />

验收：空会话显示欢迎语与建议；点击建议直接发送；刷新建议生效。
完成后按全局提示词第 5 条做浏览器验证。
```

### 4.6 P5 提示词：XThoughtChain 思维链 + 组装 + 端到端验证

```text
阶段 P5：思维链 + 完整页面组装 + 端到端验证。

1. 新建 frontend/src/components/x/XThoughtChain.vue：
   - 收集 store.messages 中 thinking/tool_call/tool_result/tool_chain 类消息，映射为
     ThoughtChainItem[]（文档 2.5 节，勿用 children）：
       { key: m.id, title: m.type==='thinking' ? `${m.agent} · ${m.phase}` : `工具: ${m.toolName}`,
         status: m.type==='tool_result'||m.type==='tool_chain' ? 'success' : 'pending',
         content: m.content || 格式化后的 toolMeta 摘要 };
   - 每个 AI 回复气泡内（或气泡 footer）内嵌 <ThoughtChain>；
   - collapsible 开启折叠；可结合 expandedKeys/onExpand 受控。
2. 组装 frontend/src/views/ChatXVue.vue 为完整对话页：
   - 左：XConversations；中：XBubbleList + XThoughtChain；底：XSender；空态：XWelcome；
   - onMounted: store.loadSessions() + store.loadSuggestions()；
   - 顶部工具栏：新建会话、模型选择（复用现有 loadModels 逻辑）可选。
3. 样式：为 X 组件补充作用域样式，使其融入现有暗色主题；避免与 ElementPlus 冲突
   （reset.css 引入后注意 body 级影响，必要时限定在 .chatx-root 作用域）。
4. 端到端浏览器验证（全局提示词第 5 条）：
   - 发送问题 -> 流式输出 -> SQL/结果/图表渲染；
   - 多轮对话；会话切换/删除/重命名；建议点击；停止生成；
   - 现有 /chat 页面回归无异常。

验收：/chat-x 全流程可用，浏览器验证证据留存（截图）。
```

---

## 4.7 实施记录（2026-08-05 已完成，浏览器验证通过）

| 阶段 | 状态 | 验证结果 |
|---|---|---|
| P0 | ✅ | `ant-design-x-vue@1.6.0` / `ant-design-vue@4.2.6` / `@ant-design/icons-vue@7.0.1` 安装成功；`/chat-x` 路由 + XProvider 占位页渲染正常 |
| P1 | ✅ | Conversations 会话列表渲染（128 会话分组）、选中加载历史、menu 重命名/删除均通过浏览器验证 |
| P2 | ✅ | Bubble.List 消息流：用户/AI 气泡、SQL 卡片、结果表格、Markdown、执行计划、错误+重试全部渲染正常 |
| P3 | ✅ | Sender 输入区：模式切换、联网搜索、发送消息、loading 停止按钮均正常 |
| P4 | ✅ | Welcome + Prompts：欢迎语 + 3 条建议渲染，点击建议直接发送（自动切换消息流） |
| P5 | ✅ | ThoughtChain 思维链渲染（tool_chain 消息注入验证）；顶部工具栏完成；`vue-tsc` 类型检查通过 |

**实测发现（重要）**：
- 包 `ant-design-x-vue@1.6.0` 无 CSS 文件，样式由 cssinjs 在 `XProvider` 内运行时注入。
- 控制台仅有 antdv 内部 Typography warning（Conversations 内部实现，非本项目代码问题）。
- LLM 对话返回 `403 Free quota exhausted`（外部智谱免费额度耗尽，非代码缺陷）。

---

## 4.8 Ultramodern 样式重构记录（2026-08-05 晚，浏览器验证通过）

**需求**：字体可读性、消息留白、LOGO/用户信息去重、输入框布局比例。
**方案**：参考 `x.ant.design/docs/playground/ultramodern-cn?theme=dark`（紫色品牌色）+ `antd-design-x-vue.netlify.app/playground/independent.html`（三段式布局）。

| 文件 | 变更 |
|---|---|
| `styles/design-system.css` | 主色 `#7056F8` 紫色系；背景 `#0a0a0a/#0f0f11/#1a1a1d`；文字 `rgba(255,255,255,.88/.65/.45)` |
| `styles/element-dark-theme.css` | Element 紫色主色 + 半透明白边框/填充 |
| `views/ChatXVue.vue` | 移除侧栏底部用户信息；Logo→「AI 对话」；紫色新建按钮；侧栏毛玻璃 |
| `components/x/XSender.vue` | 模式+联网搜索移入 `Sender.Header` 面板；prefix 仅模型选择器+设置按钮 |
| `components/x/XWelcome.vue` | 官方暗色渐变提示卡 + 序号徽标 |
| `components/x/XBubbleList.vue` | AI 浅色气泡/用户紫色渐变气泡；36px 头像；消息间距 24px |
| `components/x/MessageRenderer.vue` | Markdown 可读性增强（14px/1.7 行高、代码块、表格） |
| `components/x/XConversations.vue` | 会话项 hover/选中紫色态 |

> ⚠️ Sender.Header 坑：`open=false` 时面板 DOM 移除（除非 `forceRender`）；需 `:open` + `@open-change` 双向绑定。

### 4.8.1 字体冲突根因修复（2026-08-05 深夜）

| 问题 | 根因 | 修复 |
|---|---|---|
| 字体/背景冲突、Prompts 白底 | `XProvider` 未传 `theme`，X 组件用 antdv **默认浅色 token**（实测 Prompts 白底白字不可见） | `ChatXVue.vue`：`<XProvider :theme="{ algorithm: theme.darkAlgorithm, token: {...} }">`（`theme` 从 `ant-design-vue` 导入） |
| 未占满右侧 | `XBubbleList`/`XSender` 有 700px 居中限制 | 去居中，改 `padding: 32px`（实测 1640px 全宽） |
| Prompts 渐变未生效 | scoped 穿透选择器类名错误（`ant-x-prompts-item` → 实际 `ant-prompts-item`） | `XWelcome.vue` 改用 `:deep(.ant-prompts-item)` + `!important` |

> ⚠️ **核心教训**：接入 ant-design-x-vue 必须显式配置 `XProvider theme`（含 `darkAlgorithm`），否则组件内部用浅色 token 与深色页面冲突。

### 4.8.2 占满右侧修复（2026-08-05 深夜二次）

**根因**：多处 `max-width` 残留（`XBubbleList` roles `700px`、`XWelcome` `.xw-prompts` `720px`、提示卡 `340px`、`ClarifierCard`/`ExecutionCard` `82%`、`.xr-thought` `82%`）。

**修复**：
| 文件 | 修改 |
|---|---|
| `XBubbleList.vue` | roles 去 `maxWidth`，content `maxWidth:100%` |
| `XWelcome.vue` | 左对齐 `flex-start`；`.xw-prompts` `width:100%`；提示卡 `flex:1 1 240px; max-width:100%` |
| `ClarifierCard.vue` / `ExecutionCard.vue` | `max-width:100%; width:100%` |
| `MessageRenderer.vue` | `.xr-thought` `max-width:100%` |

**验证**：main 1640px 全宽、Bubble content `maxW:100%`、结构化卡片伸展合理宽度、sender 1576px 全宽、`vue-tsc` 通过。

---

## 5. 文件清单汇总

| 操作 | 文件 | 阶段 |
|---|---|---|
| Modify | `frontend/package.json`（新增 3 个依赖） | P0 |
| Create | `frontend/src/views/ChatXVue.vue` | P0 → P5 迭代 |
| Modify | `frontend/src/router/index.ts`（新增 `/chat-x`） | P0 |
| Create | `frontend/src/components/x/XConversations.vue` | P1 |
| Create | `frontend/src/components/x/XBubbleList.vue` | P2 |
| Create | `frontend/src/components/x/MessageRenderer.vue` | P2 |
| Create | `frontend/src/components/x/XSender.vue` | P3 |
| Create | `frontend/src/components/x/XWelcome.vue` | P4 |
| Create | `frontend/src/components/x/XThoughtChain.vue` | P5 |

> 后端文件：**零改动**。

---

## 6. 风险与注意事项

- **包名**：`ant-design-x-vue`（非 `@ant-design-x-vue/ant-design-x-vue`）。
- **样式冲突**：`ant-design-vue` 的 reset.css 与 ElementPlus 全局样式可能互相影响，X 页面样式尽量收敛在 `ChatXVue.vue` 根部作用域。
- **API 演进**：AntDesignX Vue 迭代快，实施前以官方文档 + 本文档第 2 章为准，如遇不一致以官方文档为准并回写本文档。
- **LLM 免费额度**：task 模式 agentic 多轮可能触发外部限流（`403 Free quota exhausted`），前端需正确展示错误并支持「重试」（现有 `recoverable` 逻辑已支持）。
- **数据层复用**：坚持复用 `useSSE.ts` + `stores/chat.ts`，避免用 `useXAgent` 重复实现流式解析。
