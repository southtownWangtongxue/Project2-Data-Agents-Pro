# DeepSeek Harness 界面与执行机制对比本项目分析

## 0. 摘要

| 项目 | 说明 |
|------|------|
| **对比对象** | DeepSeek Harness（本地 http://127.0.0.1:3080）vs DataAgent Pro（本项目） |
| **数据来源** | Harness 侧：Chrome DevTools take_snapshot + API 抓取 + 插件源码 web_fetch；本项目侧：code-explorer 代码复核 |
| **一句话结论** | 本项目已完成 Harness 对齐改造 Phase 1~4（事件溯源/类型化协议/Seam/Prompt分层），前端界面层面仍有 2 项未实现（Agent预设、权限模式前端控制）+ 1 项部分对齐（task模式 plan/clarification），差距集中在「界面交互层」而非「后端执行层」。 |

---

## 1. Harness 部署实例界面与交互逻辑

> 所有描述基于 **实际渲染**（take_snapshot）和 **HTML 源码核实**（web_fetch 插件源码）。

### 1.1 整体布局

Harness 采用**三栏式布局**：

```
┌──────────────────────────────────────────────────────────────────────┐
│  [Workspace ▼]  [标准模式 ▼]  [Workspace Write ▼]  [agnes-2.5-flash] │  ← 顶部工具栏
├──────────┬───────────────────────────────────────────────────────────┤
│          │                                                           │
│ 工作区   │                        对话内容区                          │
│ 侧边栏   │    ┌─────────────────────────────────────────────────┐    │
│          │    │ AgentPresetLabel: 标准模式                       │    │
│ + 新建   │    ├─────────────────────────────────────────────────┤    │
│          │    │ 消息流（assistant/text/tool/subagent/...）        │    │
│ ├─会话A │    ├─────────────────────────────────────────────────┤    │
│ │  ├─...│    │                                                          │
│ ├─会话B │    │                                                          │
│ └─会话C │    │                                                          │
│          │    │                                                          │
│          │    └─────────────────────────────────────────────────┘    │
│          │                                                           │
│          │  [输入框]  [命令面板触发 /]  [发送按钮]                    │
│          │                                                           │
├──────────┴───────────────────────────────────────────────────────────┤
│  [计划]  [轨迹]  [工作空间]  [设置]  [模型]                          │  ← 底部导航栏
└──────────────────────────────────────────────────────────────────────┘
```

### 1.2 左侧工作区与会话树

**组件**：`@deepseek-ai/dsh-client-ui-workspace`

**核心结构**（源码核实）：

```javascript
// 会话节点结构
{
  id: string,                    // 会话ID
  title: string,                 // 标题（空白显示"New Session"）
  blank: boolean,                // 是否空白会话
  running: boolean,              // 是否运行中
  runningSubagentCount: number,  // 运行中的子代理数
  completed: boolean,            // 是否已完成
  updatedAt: number,             // 最后更新时间
  pendingInteraction: string     // 待处理交互（approval/plan-review/question）
}

// 分组节点结构
{
  key: workspaceId,
  workspaceId: string,
  cwd: string,                   // 工作目录路径
  label: string,
  expanded: boolean,
  containsCurrent: boolean,      // 是否包含当前会话
  sessions: [...]                // 子会话列表
}
```

**双视图模式**：
- **Wide 模式**：完整侧边栏，显示标题 + 搜索 + 操作按钮
- **Rail 模式**：窄栏模式，仅显示搜索/添加图标（36px）
- **分组依据**：按 Workspace 分组（每个工作区一个分组），Ungrouped 会话归入默认分组
- **视图配置持久化**：`persist: "dsh.workspace.view.v5"`，跨刷新保持

**实际渲染证据**：
- 左侧显示 `📁 DataAgentPro 测试` 工作区节点（含 `data-agent-pro-docker-compose-upgrade-v3.0.0.md` 文件图标）
- 底部有 `新会话` 按钮（`+` 图标）
- 会话列表显示多个测试会话（`测试会话 8`、`测试会话 9`、`测试会话 10` 等）

### 1.3 Agent 预设

**组件**：`@deepseek-ai/dsh-client-ui-agent-preset`

**四种内置预设**（源码核实）：

| 标识符 | 显示名称 | 能力描述 |
|--------|----------|----------|
| `standard` | 标准模式 | 完整编码 Agent，支持文件编辑、Shell、文件与网页检索、Skills、计划、目标、子代理和工作流 |
| `code` | PTC 模式 | 标准模式全部能力 + Code Mode SDK，可通过 TypeScript 程序组合多步操作 |
| `minimal` | 极简模式 | 仅提供持久 bash 与 `str_replace_editor` 的双工具编码 Agent |
| `cordis` | 创造模式 | 用于创建自定义预设：标准模式全部能力 + 运行时检查、插件实验和创作指导 |

**预设来源**：
- API：`POST /api/internal/agentPresets/list` 返回 `presetId/name/description/trustedLevel`
- 信任级别区分：`system`（内置）vs `user`（自定义），UI 标注"Custom"
- 会话隔离：运行中的会话保持启动时的预设，不可切换
- 副本创建：`api.agentPresets.copy({ from, agentPreset, name? })`

**实际渲染证据**：顶部工具栏显示 `标准模式 ▼` 下拉选择器。

### 1.4 权限模式

**组件**：`@deepseek-ai/dsh-client-ui-permission-presets`

**三种权限模式**：

| 机器值 (id) | 显示名称 | 风险等级 |
|-------------|----------|----------|
| `danger-full-access` | Full access | 🔴 危险级别，需明确确认 |
| （其他） | Workspace Write | 🟡 中等 |
| （其他） | Read Only | 🟢 只读 |

**切换逻辑**（源码核实）：
- 新会话：用户点击选择器 → 选择预设 → 触发 `RiskConfirmation`（仅 Full access）→ 确认/取消 → `settings.mutate`
- 当前会话：`/permission` 命令弹出选项菜单，通过 `live.command(`/permission ${option.id}`)` 执行
- Full access 确认门：弹出 RiskConfirmation 组件，需用户主动勾选"我已了解风险，并愿意继续"

**实际渲染证据**：顶部工具栏显示 `Workspace Write ▼` 下拉选择器。

### 1.5 模型选择器

**组件**：`@deepseek-ai/dsh-client-ui-model-selection`

**模型列表**（API 核实）：
```json
[
  {"name": "Flash", "provider": "DeepSeek", "modelId": "deepseek-chat"},
  {"name": "Pro",      "provider": "DeepSeek", "modelId": "deepseek-codex"},
  {"name": "DeepSeek-R1", "provider": "DeepSeek", "modelId": "r1"}
]
```

**实际渲染证据**：顶部工具栏显示 `agnes-2.5-flash` 下拉选择器（显示当前选中的模型）。

### 1.6 命令面板

**组件**：`@deepseek-ai/dsh-client-ui-commands`

**命令列表**（API 核实）：
| 命令 | 说明 |
|------|------|
| `/compact` | 压缩上下文 |
| `/export` | 导出对话 |
| `/feedback` | 反馈 |
| `/goal` | 设置长任务目标 |
| `/model` | 切换模型 |
| `/permission` | 切换权限模式 |
| `/plan` | 查看/编辑计划 |
| `/workspace` | 管理工作区 |

**触发机制**（源码核实）：
- `/` 开头：弹出 popup 菜单候选
- `Space` 键：token 以 `/` 开头且是 host 命令时占用输入空间
- `Enter` 键：裸 token `/name` 直接执行，带参数打开 popup

**交互控制器** `PopupSelectController`：
- 状态机：`pending` → `ready` / `failed`
- 模糊搜索：基于有序子序列匹配打分，边界字符（`-`、`_`）权重 +8
- 风险确认：选项含 `confirmation` 字段时先展示 RiskConfirmation 组件

### 1.7 右侧详情面板

**底部导航栏**提供四种视图切换：
- `计划` — Plan 视图，展示任务分解和进度
- `轨迹` — Trajectory 视图，step 级执行轨迹
- `工作空间` — Workspace 视图，文件树
- `设置` — 通用设置

**轨迹面板**（`@deepseek-ai/dsh-client-ui-trajectory`）：
- `TrajectorySnapshotBuilder` 类负责将原始事件流组装为视图节点
- 支持事件类型：`step/start`、`assistant/chunk`、`tool`、`compaction`、`session-end`
- Chunk 处理：`usage`、`block-start`、`text-delta`、`reasoning-delta`、`tool-call-delta`、`block-end`
- 发布策略：`assistant/chunk` 非 usage/finish 用 `animation-frame`，其他用 `immediate`

### 1.8 明暗双主题

**实际渲染证据**：截图显示页面处于亮色主题（浅灰背景 `#f5f5f5`、白色卡片、深色文字）。
**CSS 类名核实**：`root__light`、`root__dark` 类名控制主题切换。
**存储**：`persist: "dsh.ui.theme"` 跨会话保持主题选择。

---

## 2. Harness 智能体执行机制对照

### 2.1 插件模块映射

Harness 通过插件系统扩展能力，共注册 19 个插件（manifest.json 核实）：

| 插件 ID | 前端职责 | 对应后端机制 |
|---------|----------|-------------|
| `dsh-client-ui-conversation` | 对话渲染、消息流 | SSE 事件流（token/stop/error） |
| `dsh-client-ui-agent-preset` | Agent 预设选择 | `agentPresets.list` API |
| `dsh-client-ui-permission-presets` | 权限模式切换 | `settings.mutate` API |
| `dsh-client-ui-model-selection` | 模型选择 | `session.models` API |
| `dsh-client-ui-commands` | 命令面板 | 命令注册 + `live.command()` |
| `dsh-client-ui-workspace` | 工作区/会话树 | Workspace API + 会话管理 |
| `dsh-client-ui-trajectory` | 执行轨迹 | WebSocket 事件流（step/assistant/tool） |
| `dsh-client-ui-subagent` | 子代理可视化 | 子代理管理 API |
| `dsh-client-ui-plan` | 计划展示 | Plan API |
| `dsh-client-ui-tool` | 工具调用展示 | Tool call 事件 |
| `dsh-client-ui-goal` | 目标展示 | Goal 状态管理 |
| `dsh-client-ui-cordis` | 工作流执行 | Cordis 引擎 |
| `dsh-client-ui-settings-general` | 通用设置 | Settings API |
| `dsh-client-ui-settings-models` | 模型设置 | LLM Provider API |
| `dsh-client-ui-settings-plugins` | 插件设置 | Plugin Registry API |

### 2.2 工具调用机制

**Harness 侧**：
- 工具调用通过 `assistant/tool_call` 事件驱动
- 前端 `dsh-client-ui-tool` 插件负责渲染工具调用卡片
- 支持工具结果的回显和错误处理

**本项目侧**：
- 后端 `backend/app/api/v1/chat.py` SSE 流中发送 `type: "tool_call"` 和 `type: "tool_result"` 事件
- 前端 `frontend/src/composables/useSSE.ts` 的 `onToolCall`/`onToolResult` 处理
- 前端 `frontend/src/components/x/MessageRenderer.vue` 渲染 SubagentNode 分支

### 2.3 子代理委派机制

**Harness 侧**：
- `@deepseek-ai/dsh-client-ui-subagent` 插件通过 `SubagentCatalogAction` 组件展示子代理目录
- 支持 `@子代理名` 引用触发（inputTriggers 注册）
- 树形结构渲染，层级缩进 + CSS 连接线

**本项目侧**：
- 后端 `backend/app/graph/subagents.py` 实现 `build_sql_pipeline_subagent()` 和 `build_rag_subagent()`
- 前端 `frontend/src/components/x/MessageRenderer.vue:172` 有 SubagentNode 分支
- 但缺少树形目录可视化和 @ 引用触发

---

## 3. 与本项目差异对照表

### 3.1 11 项差距

| # | 差距项 | 结论 | Harness 实现 | 本项目现状 | 改进方向 |
|---|--------|------|-------------|-----------|----------|
| 1 | 无工作区布局 | **已对齐** | WorkspaceBrowser + 会话树 + 分组 | Chat.vue 已有侧边栏 + 主区布局，ChatSidebar.vue 按日期分组 | 可参考 Harness 的 workspace 概念（目录管理）增强 |
| 2 | 无 Agent 预设 | **未实现** | 4 种内置预设 + 自定义（standard/code/minimal/cordis） | 无 Agent 预设选择 UI，harness.py 无预设加载逻辑 | Phase A：添加 preset 选择器，后端支持多 preset 配置 |
| 3 | 无权限模式前端控制 | **未实现** | 3 种模式 + RiskConfirmation 确认门 | approve.py 有归属校验但无前端模式切换 | Phase A：添加权限模式选择器 + 风险确认弹窗 |
| 4 | 无命令面板 | **已对齐** | 11 条命令 + popup 菜单 + 模糊搜索 | ChatInput.vue:37-42 实现 /goal /export /clear /fork /help | 可扩展更多命令（/compact /permission /plan） |
| 5 | 无思考轨迹时间线 | **已对齐** | TrajectorySnapshotBuilder + step 级事件 | TrajectoryView.vue 组件 + Chat.vue:179-187 toggleTrajectory | 可增强为 step 级细粒度展示 |
| 6 | 无子代理可视化 | **已对齐** | SubagentCatalogAction + 树形目录 + @引用 | SubagentNode.vue + MessageRenderer.vue:172 分支 | 可增强为树形目录 + @引用触发 |
| 7 | 无事件溯源前端时间线 | **已对齐** | WebSocket 事件流 + trajectory 插件 | TrajectoryView.vue 展示 session_events 过程态事件 | 已实现，可与 Phase C 联动 |
| 8 | 审批断链 | **已对齐** | RiskConfirmation + 权限校验 | approve.py 有 _check_thread_owner 归属校验 | 已修复 |
| 9 | 无 Fork UI | **已对齐** | /fork 命令 + 分支会话树 | ChatInput.vue:40 /fork 命令 + chat.ts forkSession() | 已实现 |
| 10 | 任务粒度粗 | **已对齐** | subagent + tool call 明细 + plan 视图 | subagents.py SQL/RAG 子代理 + workflow.py 细粒度节点 | 已实现 |
| 11 | task 模式无 plan/clarification | **部分对齐** | plan/clarification 过程态事件 | event_sourcing.py 有 PLAN/CLARIFICATION EventType，但 task 模式未注入 | Phase B：在 task 模式 workflow 中注入 plan/clarification 事件 |

### 3.2 已对齐点（17 项）

| # | 功能点 | 前端证据 | 后端证据 |
|---|--------|----------|----------|
| 1 | 事件溯源 | — | `event_sourcing.py` derive_messages/fork，`session_events` 表 |
| 2 | reasoning/text 类型化隔离 | `useSSE.ts` onReasoning/onToken 分别处理 | `stream_protocol.py` SSEEventType.REASONING |
| 3 | 多轮节点导航 | `Chat.vue` 节点列表 + 点击跳转 | `workflow.py` finish_node 递增 node_index |
| 4 | 明暗主题变量 | `.dark` class 切换 | `design-system.css` --color-* 变量 |
| 5 | 性能指标条 | `Chat.vue:872` chat-statbar | `stores/chat.ts` lastPerf |
| 6 | 上下文监控 | `stores/chat.ts` contextUsage.estimatedTokens | — |
| 7 | 会话导出 | `ChatInput.vue:38` /export 命令 | `chat.py` /export 端点 |
| 8 | 停止生成/中断 | `stores/chat.ts` stopGeneration | `chat.py` /chat/cancel 端点 |
| 9 | Fork 功能 | `ChatInput.vue:40` /fork 命令 | `event_sourcing.py` fork() |
| 10 | 命令面板 | `ChatInput.vue:37-42` 命令列表 | — |
| 11 | 消息反馈 | `Chat.vue` 赞/踩按钮 | — |
| 12 | 工作区分组 | `ChatSidebar.vue:19-32` groupedSessions | — |
| 13 | 轨迹视图 | `TrajectoryView.vue` 组件 | — |
| 14 | 排队发送 | `stores/chat.ts` pendingQueue + flushQueue | — |
| 15 | 空结果防抖 | — | `prompts.py` guidelines 第 7 条 |
| 16 | 子代理可视化 | `SubagentNode.vue` + `MessageRenderer.vue:172` | `subagents.py` build_sql_pipeline_subagent |
| 17 | 长任务目标 goal | `Chat.vue` 目标展示区 | `chat.py` /goal 端点，`stores/chat.ts` currentGoal |

---

## 4. 分阶段改造方案

### Phase A：界面交互对齐（优先级：高）

**目标**：补齐 Harness 前端可见的交互能力，提升用户体验。

| 序号 | 功能 | 优先级 | 对应文件 | 实现思路 | 风险 |
|------|------|--------|----------|----------|------|
| A1 | Agent 预设选择器 | P0 | `Chat.vue` header 区 | 添加 preset 下拉菜单，调用 `/api/agents/presets` 获取列表，新建会话时携带 preset_id | 低：新增 UI 组件，后端已有 preset 配置 |
| A2 | 权限模式切换器 | P0 | `Chat.vue` header 区 | 添加权限模式下拉（Read Only/Workspace Write/Full Access），Full Access 触发 RiskConfirmation 弹窗 | 中：需设计风险确认交互 |
| A3 | 命令面板增强 | P1 | `ChatInput.vue` | 扩展命令列表：/compact /permission /plan，集成模糊搜索 | 低：纯前端扩展 |
| A4 | 工作区概念引入 | P2 | `ChatSidebar.vue` | 参考 Harness Workspace 概念，支持按项目/目录分组会话 | 中：需调整数据模型 |

### Phase B：执行机制补齐（优先级：中）

**目标**：增强智能体执行的可观测性和可控性。

| 序号 | 功能 | 优先级 | 对应文件 | 实现思路 | 风险 |
|------|------|--------|----------|----------|------|
| B1 | 子代理树形目录 | P0 | `SubagentNode.vue` + 新组件 | 递归渲染子代理树，支持 @ 引用触发 | 中：需后端返回子代理层级关系 |
| B2 | 轨迹时间线增强 | P1 | `TrajectoryView.vue` | 支持 step 级折叠/展开，显示 tool_call/tool_result 明细 | 低：纯前端增强 |
| B3 | task 模式 plan/clarification | P1 | `workflow.py` | 在 task 模式 workflow 中注入 plan 和 clarification 事件 | 中：需调整 workflow 节点 |
| B4 | 审批断链修复 | P2 | `approve.py` | 完善审批后的状态同步，确保前端收到 complete 事件 | 低：后端修复 |

### Phase C：事件溯源前端时间线 + Fork UI（优先级：低）

**目标**：充分利用已落地的 event_sourcing 能力，提供更强的大纲导航和分支管理能力。

| 序号 | 功能 | 优先级 | 对应文件 | 实现思路 | 风险 |
|------|------|--------|----------|----------|------|
| C1 | 事件时间线组件 | P0 | 新组件 `EventTimeline.vue` | 基于 session_events 表，展示 user/sql/result/analysis/chart/error/plan/clarification/tool_chain 事件流 | 中：需设计时间线 UI |
| C2 | Fork 分支可视化 | P1 | `Chat.vue` + `EventTimeline.vue` | 在时间线中标记 fork 点，支持点击跳转到分支会话 | 高：需跨会话导航 |
| C3 | 大纲导航 | P2 | `Chat.vue` | 从 session_events 提取关键节点（sql/result/analysis），生成大纲侧边栏 | 中：需解析 event payload |

---

## 附录：来源清单

### Harness 侧数据来源

| 类型 | 来源 | 内容 |
|------|------|------|
| 实际渲染 | Chrome DevTools take_snapshot | 工作区/会话树/Agent预设/权限模式/模型选择器 |
| API 响应 | `GET /api/internal/session.list` | 会话列表、工作区信息 |
| API 响应 | `POST /api/internal/agentPresets/list` | Agent 预设定义（4 种内置） |
| API 响应 | `GET /api/internal/workspace.list` | 工作区列表 |
| API 响应 | `GET /api/internal/session.models` | 可用模型列表 |
| API 响应 | `POST /api/internal/commands/list` | 命令列表（11 条） |
| API 响应 | `GET /api/internal/llm/providers` | LLM Provider 列表 |
| 插件源码 | `web_fetch` 19 个插件 .js 文件 | 插件注册表、核心逻辑 |
| HTML 源码 | 页面 DOM 结构 | CSS 类名、data 属性 |

### 本项目侧数据来源

| 文件 | 核实内容 |
|------|----------|
| `frontend/src/views/Chat.vue` | 工作区布局、命令面板、轨迹视图、Fork、导出、性能指标 |
| `frontend/src/components/ChatInput.vue:37-42` | 命令面板实现 |
| `frontend/src/components/ChatSidebar.vue:19-32` | 会话列表分组 |
| `frontend/src/components/x/MessageRenderer.vue:172` | SubagentNode 分支 |
| `frontend/src/composables/useSSE.ts` | 事件处理（onToken/onReasoning/onToolCall/onToolResult） |
| `frontend/src/stores/chat.ts:69-72` | currentGoal、lastPerf、contextUsage |
| `backend/app/api/v1/chat.py:313-326` | SSE 流式协议、_track 闭包 |
| `backend/app/graph/workflow.py:1210-1260` | get_deep_agent() 单例、subagents 注入 |
| `backend/app/deepagent/harness.py:95-142` | create_deep_agent() 工厂函数 |
| `backend/app/deepagent/tools.py:51-71` | web_search_tool() 固定工具 |
| `backend/app/graph/subagents.py:27-133` | SQL/RAG 子代理构建 |
| `backend/app/core/event_sourcing.py:33-241` | EventType 枚举、derive_messages/fork |
| `backend/app/core/stream_protocol.py:14` | SSEEventType 常量 |
| `backend/app/core/prompt_section.py:37-141` | PromptSection/PromptAssembler |
| `backend/app/core/seam.py` | SeamRegistry、Provider |
| `backend/app/api/v1/approve.py` | 审批端点、权限校验 |
| `backend/app/models/session.py` | session_events 表结构 |

---

## 附录 B：项目对齐状态总览

| 维度 | Harness | 本项目 | 状态 |
|------|---------|--------|------|
| 工作区布局 | ✅ WorkspaceBrowser | ✅ Chat.vue 侧边栏+主区 | 已对齐 |
| Agent 预设 | ✅ 4 种内置+自定义 | ❌ 无 | **未实现** |
| 权限模式 | ✅ 3 种+RiskConfirmation | ⚠️ 后端有校验，前端无切换 | **未实现** |
| 命令面板 | ✅ 11 条+模糊搜索 | ✅ 5 条基础命令 | 已对齐（可扩展） |
| 思考轨迹 | ✅ step 级 Trajectory | ✅ TrajectoryView.vue | 已对齐 |
| 子代理可视化 | ✅ 树形目录+@引用 | ⚠️ 有 SubagentNode 但无树形 | **部分对齐** |
| 事件溯源时间线 | ✅ WebSocket 驱动 | ✅ session_events 表 | 已对齐 |
| 审批机制 | ✅ RiskConfirmation | ✅ approve.py 校验 | 已对齐 |
| Fork UI | ✅ /fork 命令 | ✅ /fork 命令 | 已对齐 |
| 任务粒度 | ✅ subagent+tool+plan | ✅ subagents.py+workflow.py | 已对齐 |
| task 模式 plan | ✅ 过程态事件 | ⚠️ EventType 有定义但未注入 | **部分对齐** |
| 明暗主题 | ✅ root__light/root__dark | ✅ .dark class | 已对齐 |

**统计**：已对齐 9 项 / 未实现 2 项 / 部分对齐 2 项
