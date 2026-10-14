# DeepSeek Harness 源码研读笔记

> 面向后续开发/集成 DeepSeek Harness（CLI 名 `dsh`）的参考笔记。
> 基于开源仓库 `deepseek-ai/deepseek-harness`（master 分支）与官方文档 `deepseek-harness.github.io` 源码级研读整理，聚焦**不会在插件层面直接体现的关键内容**。

---

## 0. 一句话定位

DeepSeek Harness 是 DeepSeek AI 开源的 **Agent Harness / 智能体运行框架**，核心理念是 **"Everything is a Plugin"（一切皆插件）**，底层由 **Cordis** 插件框架驱动。它不是一个"模型"，而是一个可插拔的、用于编排 Agent（模型 + 工具 + 沙箱 + 持久化 + 审批）的宿主程序。

**关键状态**：当前处于 **Developer Preview（技术预览）**，快速迭代中，明确声明会有 **COMPATIBILITY-BREAKING CHANGES（不兼容重大变更）**。生产集成需锁定版本并持续关注 changelog。

---

## 1. 核心工作机制（源码级）

### 1.1 意图识别：无传统 NLP 模块，数据驱动的流程控制

deepseek-harness **没有传统意义上的"意图识别"模块**（不通过关键词/分类器判断用户要做什么）。其"该做什么、何时停止"的决策，完全由**事件溯源 + inbox 队列 + waterfall 事件链**这套数据驱动机制实现。

**双 inbox 队列**：每个 Agent 持有两条输入队列，是流程控制的核心：

| 队列 | 消费策略 | 用途 |
|---|---|---|
| `next-turn` | 每轮消费一条 | 普通轮次（用户消息、followup） |
| `next-step` | 每步消费全部 | 步骤级上下文注入（子代理结果、维护产物） |

**AgentHandle 关键方法**（对 Agent 外部/内部均可调用的控制面）：

| 方法 | 语义 |
|---|---|
| `send()` | 路由输入并唤醒 driver，启动新一轮 |
| `followup()` | 普通后续轮次 |
| `steer()` | **中途引导**：提交最近步骤的引导（在工具执行间插入控制信号） |
| `inject()` | 排队下一步模型可见的上下文，**不唤醒**（静默注入） |
| `cancel()` | 取消当前运行 |
| `whenIdle()` | 等待空闲（await 空闲状态） |
| `runMaintenance()` | 运行维护性任务 |

**waterfall 事件链**（核心决策机制）：`agent/*` 事件采用 waterfall 语义——监听者可以返回 `reject`/`enter` 来影响流程，而非仅被动观察：

- `agent/pre-step`：每一步开始前触发，监听者可返回 `reject`（拒绝该步）或 `enter`（介入），从而决定"下一步该做什么"。
- `agent/turn-stopping`：轮次即将结束时触发，可被监听者延迟/取消。
- `agent/request-error`：请求出错时触发，监听者返回 `{ kind: 'retry' }` 可接管错误恢复策略。

**结论**：轮次结束由 **inbox 排空**决定，而非显式意图分类。这使行为扩展完全通过"挂接事件监听器"实现，而非修改核心决策逻辑。

### 1.2 harness 间调用协同：事件溯源 + 因果归因边界

**Agent 生命周期管理**：

- `ctx.agents.create()`：构建新 Agent（分配上下文、初始化事件日志）。
- `ctx.agents.resume()`：从持久化会话恢复 Agent。
- `withInitiator()` / `withoutInitiator()`：建立**进程内因果归因边界**——区分"谁触发了这段执行"（用户 vs 内部子代理），用于审批/权限/审计的源头追溯。

**子代理委派**：通过 `subagent` 包族实现，支持多种 provider 作为"委派目标"：

| 子代理包 | 委派后端 |
|---|---|
| `dsh-subagent-fork-in-process` | 进程内 fork |
| `dsh-subagent-dsh-sdk` | 通过 Python SDK 调起 |
| `dsh-subagent-acp` | ACP 协议 |
| `dsh-subagent-claude-code` / `codex` | 外部 CLI 工具 |

**事件词汇分离（关键设计）**：

- **`session/event` 词汇**：append-only 持久化日志，用于**回放/持久化**（历史真源）。
- **`agent/*` 词汇**：实时协调事件，用于**运行时协同**（不持久化）。

两套词汇分离，使"历史可重放"与"实时可协调"互不干扰。

### 1.3 系统提示词构建：PromptSection 分层组装

系统提示词不是单一字符串，而是由多个 **`PromptSection`** 按规则组装而成。

**PromptSection 结构**：`{ name, order, text, complete }`。

**order 约定（分层语义）**：

| order 区间 | 语义 |
|---|---|
| `-100` | Harness 身份声明（框架自述） |
| `0` | persona（人设/角色） |
| `100–199` | 工具使用指引 |

**组装机制**：

- 各片段按 `order` 升序拼接成最终系统提示词。
- **作用域遮蔽**：作用域（scope）内的片段会遮蔽同名的全局片段（按 agent 粒度定制提示词）。
- `system-prompt/assemble` 是**专家级 waterfall 事件**，允许监听者介入/改写组装结果。
- 工具 schema 通过 `ctx.systemPrompt.tools(provider)` 注入（工具定义自动进提示词）。
- **`TOOL_ORDER_REST` 保留名**：在 toolOrder 中用于表示"其余工具"的插入位置，必须恰好出现一次。
- **变量插值**：`{{var}}` 由 `renderPrompt` 运行时插值。
- **`complete: true`**：标记该片段可替换整个提示词（完全接管）。

**传递链路**：`PromptSection` 注册 → `assemble` waterfall 组装 → 注入模型请求上下文 → 随每轮 LLM 调用传递。

---

## 2. 界面交互设计

### 2.1 工具调用过程展示：纯函数渲染卡片

工具调用在 UI 的展示由 **`presentCall` / `presentResult` 纯函数**负责（无副作用，因此可同时服务"实时流式"与"历史回放"两个场景）。

**六类工具卡片**：

| 卡片类型 | 展示内容 |
|---|---|
| `generic` | 通用工具调用（默认） |
| `terminal` | 终端命令及输出 |
| `diff` | 文件增删改（diff 视图） |
| `search` | 搜索结果列表 |
| `read` | 文件读取内容 |
| `web` | 网页浏览/抓取 |

**展示状态流转**：工具执行中显示"待执行视图"（调用参数），执行完成后**用"已完成视图"替换**（结果/输出），形成"输入 → 结果"的视觉闭环。

### 2.2 思考内容展示：reasoning 块与正文隔离

- 模型输出通过 **`ContentBlockMap`** 结构化，其中 `reasoning`（思考）块与 `text`（正文）块**类型隔离**。
- 流式传输用 **`StreamChunk`** 的 `reasoning-delta` 分片独立传输思考内容。
- UI 将思考内容**折叠独立呈现**（与正文分离，用户可展开/收起），避免思考过程干扰最终回答的可读性。

### 2.3 长链接会话：事件溯源执行逻辑与状态管理

**事件溯源架构（核心）**：

- **append-only `SessionEvent` 日志是唯一真源（single source of truth）**，LLM 消息历史从日志**派生**（而非独立存储）。
- 每个事件 `seq = log.length`，严格连续递增，保证回放确定性。

**surface（投影）机制**：UI 展示的消息并非直接读取日志，而是对日志做**投影派生**，仅三种事件投影为用户可见消息：

| 事件类型 | 投影结果 |
|---|---|
| `user/message` | 用户消息 |
| `assistant/message` | 助手回复 |
| `tool/result` | 工具结果 |

其余事件（如 `agent/*`、中间步骤）不投影到消息列表，仅用于内部状态。

**状态管理与持久化**：

- `connection` 包（client/host 双端）+ `runtime`/`modules` 管理连接状态。
- 持久化支持 **JSONL**（默认 `zstd` 压缩）与 **SQLite** 两种存储。
- 提供 **Fork API**：可从任意事件点分叉会话（重放/分支实验）。

---

## 3. 前端布局与动效设计，及与前后端分离架构对比

### 3.1 deepseek-harness 前端技术栈

| 维度 | 说明 |
|---|---|
| 框架 | **React 18.2** |
| 构建 | **Vite 6** + TypeScript 6 |
| 状态管理 | **无第三方库**（使用 workspace 内部包） |
| 动画 | **无第三方动画库** |
| UI 组件 | `packages/client` 下 30+ 子包 |

**UI 组件包（部分）**：`ui-layout`（布局）、`ui-sidebar`（侧边栏）、`ui-conversation`（会话流）、`ui-message-feedback`（消息反馈）、`ui-input-trigger`、`ui-model-selection`、`ui-plan`、`ui-jobs`、`ui-workflow-run`、`ui-trajectory`（轨迹）、`ui-tool`、`ui-subagent`、`ui-settings-*` 等。

**架构特点**：

- 前后端**同仓（monorepo）**，`apps/web` + `packages/client` 组成 UI，与后端插件运行时共享类型定义。
- 长链接通过 `connection` 包实现**双端**（host 运行在服务器插件，client 运行在浏览器）。
- Web 服务默认 `host=127.0.0.1`（仅本机），`port=0` 时 OS 自动分配端口。
- **动效设计**：无独立动画库，依赖 React 组件状态切换 + CSS 过渡实现轻量动效（工具卡片状态替换、思考内容折叠等），保持依赖极简。

### 3.2 与 DataAgent Pro 前后端分离架构对比

| 对比维度 | DeepSeek Harness | DataAgent Pro（本项目） |
|---|---|---|
| 前后端关系 | **同仓 monorepo**，插件即后端 | **前后端分离**，独立 `backend/` + `frontend/` |
| 前端框架 | React 18 + Vite 6 | Vue 3 + Vite + Element Plus + Pinia |
| 状态管理 | 无第三方库（内部 workspace 包） | Pinia |
| 后端形态 | Cordis 插件运行时（TS/Node） | FastAPI（Python，async + SSE） |
| 通信方式 | `connection` 包（client/host 双端长链接） | HTTP + SSE 流式 |
| 类型共享 | 前后端共享 TS 类型定义 | 前后端各自定义（JSON 契约） |
| 部署 | 单进程插件树（可 patch 叠加） | 单体镜像（nginx 反代 + supervisor） |
| 扩展方式 | 一切皆插件 + Seam 可替换 | skill 落盘 + ConfigManager 热加载 |

**优缺点分析**：

- **DeepSeek Harness 优势**：前后端同仓带来**类型统一、契约天然一致**；插件化 + 事件溯源使**扩展与回放能力极强**；单进程部署运维简单。
- **DeepSeek Harness 劣势**：React/TS 单一技术栈，团队若熟悉 Vue/Python 有迁移成本；Developer Preview 不稳定；不支持 Windows agent 运行；密钥明文存储。
- **DataAgent Pro 优势**：前后端分离**职责清晰、可独立演进**，团队技术栈（Vue + Python）熟悉度高；FastAPI SSE 流式成熟稳定；Python 生态利于数据/LLM 处理。
- **DataAgent Pro 劣势**：前后端契约需手工同步（易漂移）；扩展机制（skill 单例需重启）不如 dsh 插件热插拔灵活。

---

## 4. 关键默认值、行为与限制（易踩坑点）

### 4.1 安全默认（偏保守）

- 沙箱默认 `mode: 'read-only'`，可写工作区需显式选择。
- 子进程环境默认经**凭据清理**，敏感凭据不自动传入子进程。
- Python SDK 的 minimal 组合使用 **`danger-full-access`** 权限，官方提示**只能在可丢弃 checkout 或容器内运行**。
- `permission presets`：默认含 `workspace-write` 和 `danger-full-access`，`custom` 是保留名。

### 4.2 会话/上下文

- 上下文压缩 `dsh-compaction-basic` 默认：`thresholdRatio=0.8`、`retainRatio=0.16`、`maxTokens=8192`、`auto=true`。
- 工具结果裁剪默认：`thresholdChars=8192` / `headChars=4096` / `tailChars=1024`。
- `dsh-session-reference` 的 `maxReferences` 仅 1–3。

### 4.3 流式协议（StreamChunk）

原始流分片顺序：`block-start` → `text-delta` / `reasoning-delta` / `tool-call-delta` → `block-end` → `usage` → `finish`。**`usage` 在 `finish` 前，`finish` 后无分片**；空闲超时默认 5 分钟。

### 4.4 持久化/查询默认

- JSONL 默认 `compression='zstd'`（约省 60%）；SQLite `journalMode='wal'`。
- 会话查询 SQLite：`defaultLimit=20`、`maxLimit=100`、`snippetChars=240`。
- 存储的 `root`/`path` **无默认值是有意为之**——避免 `process.cwd()` 变化导致文件散落。

### 4.5 平台限制与兼容性风险

- **agent 运行时不支持 Windows**（需 POSIX 终端环境）；Python SDK 限定 Linux x64/arm64、macOS 14+ arm64。
- **Developer Preview**：明确声明有兼容性破坏变更，不建议未锁版本深度集成。
- **密钥明文存储**：`.credentials.yaml` 明文存密钥（仅 UI 层脱敏回显），需注意文件权限与泄露风险。
- 自定义 OpenAI 兼容服务若不提供 `GET /models`（401/不存在），无法自动发现模型，**必须手动输入模型 id**。
- 视觉/图片输入需在 `settings.yaml` 显式声明 `input: [text, image]`，否则发图被拒。
- DeepSeek 官方 chat-completions 路由为纯文本，不支持图片且无法配置改变。
- 配置错误 **"fail loud"**：加载时直接失败，不静默回退。
- Python SDK 复用相同 `session_id` 会保留 Bash 状态（cwd/env/函数），独立任务需换新 id。

---

## 附：对 DataAgent Pro 的集成借鉴

- **架构思想**：本项目的 `ConfigManager` 热更新 + skill 落盘，与 dsh 的"一切皆插件 + Seam 可替换 + 可逆副作用"理念一致；可参考其 **session 事件日志（append-only JSONL）+ 投影查询** 强化会话持久化与可重放能力。
- **热更新边界对照**：本项目 DeepAgent 单例缓存需重启才加载新 skill，与 dsh 的 profile/bundle 叠加 + `--patch` 覆盖机制可对照——dsh 通过插件树叠加实现部分热插拔，值得参考。
- **轻量接入路径**：可考虑仅用其 **Python SDK**（`DeepSeekHarness`）作为通用任务模式的可插拔执行引擎，与本项目现有 `deepagent/` 并存。
- **注意**：dsh 处于 preview、不支持 Windows agent、明文存密钥，生产集成需隔离运行（容器）+ 自管密钥。

---

*笔记生成时间：2026-08-17；数据来源：GitHub 仓库与官方文档（deepseek-harness.github.io）。*
