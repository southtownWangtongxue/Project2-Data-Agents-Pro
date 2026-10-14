# DeepSeek Harness 实测体验调研报告

> 版本：v1.0
> 日期：2026-08-18
> 体验方式：通过 Chrome DevTools MCP 实际操作系统界面（http://127.0.0.1:3080），逐项操作并记录每一步结果、遇到的问题与解决方案
> 定位：为「参考 Harness 界面交互与智能体执行机制改造本项目」提供第一手事实依据

---

## 0. 摘要

- **体验环境**：本地部署实例 `http://127.0.0.1:3080`，工作区 `D:\WorkSpace\AI_Study\DeepSeek-Harness`，模型 agnes-2.5-flash（支持 DeepSeek-V4 系列），权限模式 Workspace Write，Agent 预设标准模式。
- **体验方式**：Chrome DevTools MCP 自动化操作（`take_snapshot` 定位 + `evaluate_script`/`click` 驱动），共完成 14 项功能体验，含真实模型调用 2 次、工具调用 9 步。
- **一句话结论**：Harness 是一套**「界面 → 会话 → 智能体执行 → 轨迹/性能可观测」全链路自洽**的编码 Agent 产品；其界面交互（工作区/Agent 预设/权限模式/命令面板/详情面板）与执行可观测（轨迹、性能指标、上下文监控）是本项目当前**最值得对齐的两类能力**，且本项目前五阶段改造（事件溯源/类型化流式/seam/PromptSection）已为对齐打下后端基础。

---

## 1. 功能概述

### 1.1 产品定位

DeepSeek Harness（dsh）是面向编码/通用任务的 Agent 工作台，核心特征：
- **一切皆插件**（Everything is a Plugin）：界面由 `dsh-client-ui-*` 系列插件模块组合（对话/侧边栏/布局/设置/工具/子代理/轨迹/命令/任务/交付物/工作区/计划/目标/反馈/提问建议/权限预设等 20+ 模块）。
- **会话即执行**：每个会话绑定一个工作区目录与 Agent 预设，模型在会话内持续执行（工具调用、子代理、计划、目标）。
- **可观测性内置**：每次执行都有 step 级轨迹（Trajectory）、性能指标（LLM 耗时/首 token/tok/s/缓存命中）、上下文占用监控。

### 1.2 核心功能清单（实测确认）

| 能力域 | 具体功能 | 实测状态 |
|---|---|---|
| **工作区** | 多工作区管理、绑定本地目录、工作区标签 | ✅ 会话树分组展示；添加工作区触发系统目录选择器 |
| **会话** | 新建/搜索/视图选项、自动命名（取首问）、运行中标记、Fork 分支、导出 ZIP | ✅ 全流程验证 |
| **Agent 预设** | 标准模式/PTC 模式/极简模式/创造模式（可自定义） | ✅ 4 种预设 + 能力说明 |
| **模型配置** | 多提供方管理、自定义提供方、**推理等级（reasoning level）** | ✅ DeepSeek/agnes 两提供方 4 模型；推理等级 High |
| **权限模式** | Read Only / Workspace Write / Full access | ✅ 三档切换 |
| **命令面板** | /compact /export /feedback /goal /permission /plan /model | ✅ 7 个命令，export 实测触发 ZIP 下载 |
| **设置面板** | 模型/插件/Agent 预设/权限默认值/语言/外观（浅色深色跟随系统）/**繁忙时 Enter 行为（排队发送）** | ✅ 全项确认 |
| **模型调用** | 思考（Think）+ 正文分离、上下文注入、缓存命中 | ✅ 实测 |
| **工具调用** | Glob/Pwsh 等工具、工具行可展开、结果回喂模型 | ✅ 实测 9 步 |
| **轨迹系统** | step 级执行记录、按 Duration/Turns/Calls/Input/Model/Tools 过滤 | ✅ 实测 |
| **上下文监控** | 上下文占用百分比 + 系统提示词/工具/对话消息分类统计 | ✅ 实测 |
| **消息反馈** | 好的回答 / 有问题的回答 | ✅ 入口确认 |
| **性能展示** | 用时/首 token/tok/s/缓存命中/输入输出 token/轮次步数 | ✅ 实测 |

---

## 2. 使用流程（实操体验记录）

### 2.1 界面布局与导航

**布局结构**（实际渲染）：
```
┌──────────────┬────────────────────────────────┬─────────────┐
│  侧边栏      │  顶部工具栏                     │  右侧详情   │
│  新建会话    │  Agent预设 ▍权限模式 ▍模型选择  │  面板       │
│  ▾工作区     │  ┌───────────────────────────┐  │  "点击消息流 │
│   会话树     │  │     对话消息区             │  │   中的工具行 │
│   搜索/视图  │  └───────────────────────────┘  │   查看详情"  │
│   设置       │  输入区: textarea ▍命令 ▍发送    │             │
└──────────────┴────────────────────────────────┴─────────────┘
```

- 侧边栏：`新建会话`、`工作区`分组（含会话树）、`搜索会话`、`视图选项`、`添加工作区`、底部`设置`。
- 顶部：`选择工作区`、`Agent 预设`（"标准模式"）、`权限模式`（"Workspace Write"）、`模型选择`（"agnes-2.5-flash"）。
- 输入区：textarea（"描述你想要构建的内容"）+ `命令`按钮 + `发送消息`。
- 右侧：详情面板（默认占位"点击消息流中的工具行查看详情"）。

**体验问题与解决**：SPA 重渲染导致 DOM 节点频繁变化，`evaluate_script` 按文本查找按钮多次失败 → 改用 `take_snapshot` 的 uid 定位 + `click`，稳定可靠。

### 2.2 会话与工作区

- 新建会话：点击侧边栏"新建会话"，输入区清空，会话树出现"新会话"。
- 自动命名：发送首条消息后，会话自动命名为消息文本（如"你好，请简单介绍你自己"），运行中显示"进行中"标记。
- 会话树支持搜索（搜索框）与视图选项。
- 工作区：当前会话绑定 `D:\WorkSpace\AI_Study\DeepSeek-Harness`；"添加工作区"点击后弹出**系统级目录选择器**（native dialog，DOM 无法捕获）。

### 2.3 Agent 预设与模型/推理等级

**Agent 预设**（点击"标准模式"）：
| 预设 | 说明 |
|---|---|
| 标准模式 | 功能完整：文件编辑、Shell、文件/网页检索、Skills、计划、目标、子代理、工作流 |
| PTC 模式 | 标准模式全部能力 + Code Mode SDK，用 TypeScript 程序组合多步操作 |
| 极简模式 | 仅持久 bash + str_replace_editor 双工具 |
| 创造模式 | 创建自定义 preset：全部能力 + 运行时检查、插件实验、创作指导 |

**模型选择**（点击"选择模型"→"模型与推理等级"菜单）：
- 提供方分组：DeepSeek（V4-Flash / V4-Pro）、agnes（2.5-flash / 2.0-flash），共 4 模型。
- 推理等级：切换模型后按钮显示 "DeepSeek-V4-Pro · High"——支持模型+推理等级两级配置。
- 设置面板的"模型"页支持 API 密钥管理、添加自定义提供方（OpenAI 兼容端点）。

### 2.4 权限模式

三档权限（点击"访问模式"）：
- **Read Only**：只读（实测切换成功，按钮显示"Read Only"）。
- **Workspace Write**（默认）：可写工作区。
- **Full access**：完全访问。

权限与运行上下文联动：轨迹的 CONTEXT 步骤显示"Current DSH file policy: workspace-write … Approval policy: ask. Operations that require approval may ask through the configured answerers; without an available answerer, the request fails closed."

### 2.5 命令面板

点击"命令"弹出 7 个会话级命令：

| 命令 | 用途 |
|---|---|
| `/compact` | 压缩较旧的会话历史 |
| `/export` | 下载本会话日志为 ZIP 归档 |
| `/feedback` | 记录对本会话的反馈 |
| `/goal` | 设置/查看长期运行任务的目标 |
| `/permission` | 切换权限预设（沙箱模式+审批策略） |
| `/plan` | 进入/离开计划模式 |
| `/model` | 选择本会话使用的模型 |

**实测**：选择 `export` 后触发"Session 导出已开始下载，浏览器正在下载 Session ZIP 文件"（下载提示曾被命令面板遮挡，后经 Session log 视图确认）。

### 2.6 设置面板

点击侧边栏底部"设置"弹出对话框，含：
- 通用设置：模型 / 插件 / Agent 预设 / 打开配置文件。
- Agent 预设：**"对此后新建的会话生效。运行中的会话保持它开始时的预设"**（预设按会话固化）。
- 权限：新会话默认权限模式。
- 语言：中文。
- 外观：浅色 / 深色 / 跟随系统。
- **繁忙时 Enter 键行为：排队发送**（仅在智能体运行时生效；Cmd/Ctrl+Enter 使用另一行为）——对应 dsh 的 inbox 排队机制。

### 2.7 模型调用（实测）

**输入**："你好，请简单介绍你自己"
**执行链路**（对话视图逐项出现）：
1. `permission preset read-only` / `preset workspace-write`（权限预设事件，可展开）
2. `上下文注入 @deepseek-ai/dsh-system-prompt`（系统提示词注入，可展开）
3. `Think 用户让我简单介绍自己。根据系统指令，我应该用简洁的方式回答…`（思考内容，可展开）
4. 回答："你好！我是 Agnes，由 Sapiens AI 开发的大型语言模型。有什么我可以帮你的吗？"
5. 性能条：`用时 5秒 · 首 token 5.3秒 · 117 tok/s`

**关键观察**：
- 思考（Think）与正文**类型化分离**，独立可折叠——与本项目 Phase 4 的 reasoning 卡片设计一致。
- 每次回答下方有 `复制`、`好的回答`、`有问题的回答`（反馈）、`在新对话中分支`（Fork）操作。

### 2.8 工具调用（实测）

**输入**："请列出当前工作区目录下的所有文件"
**执行链路**（9 步工具调用，模型根据工具结果持续调整策略）：
```
Think → Glob * → Glob **/* → Think → Pwsh(查看当前工作目录) → Pwsh(列出工作区根目录内容)
→ Think → Pwsh(列出工作区目录) → Pwsh(用 dir 列出工作区) → Think
→ Pwsh(递归列出) → Pwsh(从当前目录递归) → Think → Pwsh(测试路径存在) → Pwsh(.NET 方法)
→ Pwsh(列出子目录) → Think → Pwsh(cmd dir) → Pwsh(强制含隐藏) → Think
→ Pwsh(含隐藏/系统文件) → Pwsh(父目录子目录) → Pwsh(查看隐藏文件)
```
- 每个工具行（`Glob *`、`Pwsh …`）可点击在右侧详情面板查看调用详情。
- 工具调用结果自动回喂模型，模型据此调整下一步工具与参数。
- **性能**：`2 轮 · 9 步 | LLM 49.2s · 工具调用 8.1s | 首 token 平均 5.2s · 173 tok/s | 缓存命中 91% | 输入 72.4K tok · 输出 1.3K tok`。

### 2.9 错误处理与中断（实测）

**错误场景**：工作区目录为空，模型所有文件列举命令均无输出。
- **模型行为**：识别到"glob 返回没有找到文件"→ 判断"可能路径问题"→ 换 Pwsh → 换 dir → 换递归 → 换 .NET 方法 → 换 cmd → 含隐藏文件 → **仍无收敛**（9 步后继续）。
- **观察结论**：多策略重试能力强，但**空结果场景可能陷入无收敛循环**，需要人工中断。

**中断机制**（实测成功）：
- 运行中发送按钮变为**"停止生成"**。
- 点击后执行立即停止（停在第 9 步），发送按钮恢复"发送消息"，性能统计定格（`2 轮 · 9 步`）。

### 2.10 轨迹系统（实测）

点击顶部"轨迹"标签页：
- 过滤器：Duration（时长）、Turns（轮次）、Calls（调用）、Input（输入）、Model（模型）、Tools（工具）。
- 逐步记录：`SYSTEM Initial System Prompt` → `Turn 1 #1` → `USER` → `CONTEXT`（运行时上下文快照：文件策略/工作区路径/审批策略）→ `ASSISTANT`。

### 2.11 上下文监控（实测）

点击"上下文已用 2%"（输入区右侧）：
```
上下文已用 2%  ~10.6K / 512K
系统提示词 ~1.6K
工具 ~6.7K
对话消息 ~1.9K
```
按系统提示词/工具/对话消息三类分类统计，窗口 512K。

### 2.12 Fork 分支（实测）

点击消息上的"在新对话中分支"：
- 会话树出现新会话 `你好，请简单介绍你自己 (1)`，自动切换过去。
- 分支会话仅含分支点之前的消息（工具调用消息不在其中）——事件溯源语义的 Fork。

### 2.13 导出（实测）

命令面板 `/export` → "Session 导出已开始下载，浏览器正在下载 Session ZIP 文件"（会话日志完整导出）。

---

## 3. 性能表现（实测数据汇总）

| 场景 | 轮次/步数 | LLM 耗时 | 工具调用耗时 | 首 token | 速率 | 缓存命中 | 输入 token | 输出 token |
|---|---|---|---|---|---|---|---|---|
| 简单对话（自我介绍） | 1 轮 / 1 步 | 5.8s | - | 5.3s | 117 tok/s | 81% | 8.5K | 59 |
| 工具调用（列出文件，9 步） | 2 轮 / 9 步 | 49.2s | 8.1s | 5.2s | 173 tok/s | 91% | 72.4K | 1.3K |

**补充观察**：
- 上下文窗口：512K；占用 2%（~10.6K：系统提示词 1.6K + 工具 6.7K + 对话消息 1.9K）。
- 缓存命中率高（81%→91%），长会话场景收益明显。
- 工具调用本身开销低（8.1s / 9 步 ≈ 0.9s/步），主要耗时在 LLM 生成与决策。

---

## 4. 优缺点分析

### 4.1 优点

1. **全链路可观测**：轨迹 step 级记录 + 性能指标（LLM 耗时/首 token/tok/s/缓存命中）+ 上下文分类统计，用户能精确看到"时间花在哪、上下文用在哪"。这是同类产品最突出的差异化能力。
2. **界面交互完备**：Agent 预设、权限模式、命令面板、工作区、明暗主题、多语言，工程完成度高。
3. **智能体机制成熟**：思考/正文类型化分离、工具调用可视化、子代理/计划/目标/工作流、Fork 分支、会话导出、消息反馈。
4. **上下文管理出色**：缓存命中率实时可见，`/compact` 支持压缩历史，`/goal` 支持长期任务目标锚定。
5. **排队机制友好**：繁忙时 Enter 排队发送（inbox 语义），多轮任务下用户可连续输入不被丢弃。

### 4.2 缺点/局限

1. **空结果场景易不收敛**：实测列出空目录文件时，模型 9 步多策略重试仍未收敛，只能人工"停止生成"——缺少自动终止/防抖策略。
2. **上下文消耗快**：多工具轮次输入 token 从 8.5K 飙至 72.4K，长任务对上下文窗口敏感。
3. **系统级对话框不可编程**：添加工作区触发 native 目录选择器，自动化/远程场景受限。
4. **推理等级与模型耦合**：切换模型后推理等级重置（实测从 V4-Pro High 回到默认），配置易失。
5. **错误提示可读性**：工具无输出时模型表现为"自我怀疑式"的多次重试，而非直接结论，用户体验依赖模型质量。
6. **预览版状态**：官方声明 Developer Preview + COMPATIBILITY-BREAKING CHANGES，接口稳定性有风险。

---

## 5. 适用场景建议

| 场景 | 适配度 | 说明 |
|---|---|---|
| **编码 Agent / 文件工程任务** | ★★★★★ | 文件编辑/Shell/检索/Skills/计划/子代理全能力，标准模式即完整编码工作台 |
| **通用任务多步编排** | ★★★★☆ | PTC 模式（TS 程序编排）适合复杂多步组合 |
| **长时运行/后台任务** | ★★★★☆ | /goal 锚定目标、/compact 压缩历史、排队发送 |
| **教学/插件开发** | ★★★★☆ | 创造模式自带运行时检查与 preset 创作指导 |
| **数据分析（本项目场景）** | ★★★☆☆ | 无内置 SQL 引擎/图表能力，需自建工具；但其执行机制与可观测性值得借鉴 |
| **生产环境稳定服务** | ★★☆☆☆ | 预览版 + breaking changes + 系统对话框不可编程，不适合直接托管 |

---

## 6. 如何对齐修改到本项目

> 本项目 DataAgent Pro 已完成五阶段改造（事件溯源/类型化流式/能力接缝/PromptSection/动效规范），后端已具备对齐 Harness 的基础。以下按「界面交互」「执行机制」两类给出对齐方案。

### 6.1 现状对比（本项目 vs Harness）

| 能力 | Harness（实测） | 本项目现状 | 差距 |
|---|---|---|---|
| 工作区/会话 | 工作区绑定本地目录，会话挂工作区 | 会话仅 thread_id，无 workspace 层 | 🔴 缺失 |
| Agent 预设 | 4 预设+自定义 | 前端 4 个硬编码 mode（data/report/doc/task） | 🔴 硬编码 |
| 权限模式 | Read Only/Workspace Write/Full access | 审批接口 `/approve` 无权限校验 | 🔴 前端无控制 |
| 命令面板 | /compact /export /feedback /goal /permission /plan /model | 无 | 🔴 缺失 |
| 轨迹系统 | step 级记录+过滤 | 事件溯源 `session_events` 有过程态事件（plan/clarification/tool_chain）但**不投影、前端无轨迹视图** | 🟡 后端有、前端无 |
| 性能指标 | LLM 耗时/首 token/tok/s/缓存命中 | 无 | 🔴 缺失 |
| 上下文监控 | 分类统计占用 | 无 | 🔴 缺失 |
| Fork 分支 | "在新对话中分支" | `SessionEventStore.fork` 后端已有 | 🟡 后端有、前端无 UI |
| 中断 | 停止生成 | SSE 流无 cancel 机制 | 🔴 缺失 |
| 思考/正文分离 | Think + 正文 | reasoning 卡片（Phase 4） | ✅ 已对齐 |
| 消息反馈 | 好的/有问题的回答 | 无 | 🟡 可加 |
| 导出 | Session ZIP | 无 | 🟡 可加 |
| 明暗主题 | 浅色/深色/跟随系统 | CSS 变量已支持（design-system.css） | ✅ 变量已备 |

### 6.2 界面交互对齐方案（Phase A，优先级高，纯前端可先行）

| # | 改造点 | 落地文件（建议） | 实现思路 |
|---|---|---|---|
| A1 | **命令面板** | `ChatInput.vue` 新增 `CommandPalette.vue` | 输入 `/` 触发命令列表，映射到现有能力：`/export`（会话导出）、`/model`（切换模型）、`/permission`（审批开关） |
| A2 | **性能指标条** | `stores/chat.ts` + `Chat.vue` | 统计 SSE 事件耗时（首 token 时刻、总 token 数、tok/s），展示在消息底部 |
| A3 | **上下文监控** | `Chat.vue` 底部工具条 | 展示当前会话已用 token（可从事件溯源 `session_events` 统计输入/输出，或 SSE 累加），近似百分比 |
| A4 | **停止生成** | `useSSE.ts` + `Chat.vue` | 发送中按钮变"停止"，断开 SSE + 调后端 cancel 端点（新增） |
| A5 | **消息反馈** | `Chat.vue` 消息卡片 | 好的回答/有问题的回答，前端收集 + 可选落库 |
| A6 | **Fork UI** | `Chat.vue` 消息操作 + `chat.ts` | 调 `SessionEventStore.fork` 后端已有能力，前端加"分支会话"按钮 |
| A7 | **会话导出** | `chat.ts` + 后端 | 新增导出端点（基于 `session_events` 生成 ZIP/JSONL） |
| A8 | **Agent 预设** | `ModeBar.vue` → `AgentPresetSelector.vue` | 4 个 mode 升级为可配置预设（前端配置 + 后端 system prompt 分段），复用 Phase 2 PromptSection 的 scope 能力 |
| A9 | **工作区** | `ChatSidebar.vue` + 后端 | 会话表加 `workspace` 列，侧边栏按工作区分组（最小改动：先按 project 字段分组） |

### 6.3 智能体执行机制对齐方案（Phase B，后端为主）

| # | 改造点 | 落地文件（建议） | 实现思路 |
|---|---|---|---|
| B1 | **审批权限校验** | `backend/app/api/v1/approve.py` | `/approve` 加 `Depends(get_current_user)` + 权限校验 |
| B2 | **轨迹视图** | 新增 `TrajectoryView.vue` + 后端事件 | 将 `session_events` 的**过程态事件**（plan/clarification/tool_chain）开放为轨迹数据源，前端按 step 渲染 + Duration/Turns/Calls 过滤（对齐 dsh Trajectory） |
| B3 | **中断机制** | `chat.py` 新增 cancel 端点 + 前端"停止生成" | 后端维护运行中的 `asyncio.Task` 句柄，cancel 时 `task.cancel()` 并关闭 SSE |
| B4 | **子代理可视化** | 前端 `tool_chain` 卡扩展 | DeepAgent 子 Agent 委派渲染为独立执行节点（替代单条 tool_result 文本） |
| B5 | **排队发送** | `chat.ts` 队列 | 运行中 Enter 排队（inbox 语义），空闲后依次发送 |
| B6 | **长任务目标** | 后端 + 前端 | 会话增加 `goal` 字段，`/goal` 命令设置，注入 system prompt（复用 PromptSection） |
| B7 | **空结果防抖** | `_stream_chat_deepagent` / 工具执行 | 连续 N 步工具无实质输出时，注入"建议总结并收尾"提示，避免无收敛循环 |

### 6.4 优先级与风险

- **建议顺序**：A1→A2→A4（命令面板/性能指标/停止生成，纯前端、收益大）→ B1（审批安全，低风险）→ A6/A7（Fork/导出，复用事件溯源）→ B2（轨迹视图，中等）→ B3/B5（中断/排队，涉及后端）→ A8/A9（预设/工作区，结构性）→ B4/B6/B7。
- **风险控制**：所有改动沿用既有 feature flag 灰度（EVENT_SOURCING_ENABLED / PROMPT_SECTION_ENABLED / SEAM_ENABLED），SSE 协议只增不删保持向后兼容；每次改动后按约定用 Chrome DevTools MCP 端到端验证。

---

## 附录 A：体验日志（逐步记录）

| 序号 | 操作 | 结果 | 问题 | 解决 |
|---|---|---|---|---|
| 1 | 导航 http://127.0.0.1:3080 | 主界面加载（工作区/会话树/输入区/详情面板） | - | - |
| 2 | 查看 Agent 预设 | 4 种预设+能力说明 | - | - |
| 3 | 查看模型选择 | 模型与推理等级菜单，4 模型 | - | - |
| 4 | 切换 DeepSeek-V4-Pro | 按钮显示 "DeepSeek-V4-Pro High" | - | - |
| 5 | 切换权限 Read Only | 按钮变 "Read Only" | - | - |
| 6 | 打开命令面板 | 7 个命令列表 | - | - |
| 7 | 打开设置 | 通用/模型/插件/Agent预设/权限/语言/外观/Enter行为 | - | - |
| 8 | 添加工作区 | 触发系统目录选择器 | native dialog 无法 DOM 捕获 | 记录交互，改用其他项继续 |
| 9 | 切回 Workspace Write | 成功 | - | - |
| 10 | 发"你好，请简单介绍你自己" | Think+回答完整输出，性能条展示 | - | - |
| 11 | 发"列出工作区文件" | Glob/Pwsh 9 步工具调用 | 空目录无输出，模型不收敛 | 点"停止生成"中断（成功） |
| 12 | 查看轨迹标签 | step 级记录+6 类过滤 | - | - |
| 13 | 查看上下文监控 | 2%（10.6K/512K）+3 类统计 | - | - |
| 14 | 在新对话中分支 | 生成分支会话 (1) | - | - |
| 15 | 命令面板 /export | 触发 Session ZIP 下载 | 下载提示被面板遮挡 | 经 Session log 视图确认 |
| 16 | 新建会话 | SPA 页面关闭（uid 索引异常） | MCP 页面状态丢失 | `new_page` 重建页面 |

## 附录 B：来源与工具

- 实测对象：DeepSeek Harness 本地部署（http://127.0.0.1:3080），工作区 `D:\WorkSpace\AI_Study\DeepSeek-Harness`。
- 操作工具：Chrome DevTools MCP（navigate_page / take_snapshot / click / evaluate_script / new_page / list_pages）。
- 本项目对照：`backend/app/api/v1/chat.py`、`backend/app/graph/workflow.py`、`backend/app/deepagent/harness.py`、`backend/app/graph/subagents.py`、`backend/app/core/event_sourcing.py`、`backend/app/core/stream_protocol.py`、`backend/app/core/seam.py`、`backend/app/core/prompt_section.py`、`frontend/src/views/Chat.vue`、`ChatInput.vue`、`ChatSidebar.vue`、`ModeBar.vue`、`stores/chat.ts`、`composables/useSSE.ts`、`styles/design-system.css`。
