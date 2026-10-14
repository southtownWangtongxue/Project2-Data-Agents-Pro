# DeepSeek Harness 源码分析与本项目集成评估

> 版本：v1.0（分析报告）
> 日期：2026-08-17
> 定位：作为「借鉴设计思想、改造现有架构」的决策依据，本报告**仅做分析，不改动业务代码**。代码改造在方案确认后进入第二阶段另行实施。

---

## 0. 摘要

### 0.1 定位

DeepSeek Harness（CLI 名 `dsh`）是 DeepSeek AI 开源的 Agent Harness，核心理念是 **"Everything is a Plugin"（一切皆插件）**，由 vendored 的 Cordis 依赖注入框架驱动，其理论基础来自论文《A Programming Paradigm for Spatiotemporal Composability》。当前处于 **Developer Preview** 阶段，官方明确声明存在 **COMPATIBILITY-BREAKING CHANGES**，协议为 MIT。（来源：GitHub 仓库 README 源码核实）

### 0.2 一句话结论

dsh 的**意图识别、harness 协同、系统提示词、会话持久化、流式协议**五大机制，全部建立在两个统一基石之上——**「事件溯源（event sourcing）」与「能力接缝（capability seams）」**：一切运行时事实都是 append-only 的类型化事件日志，一切可变能力都是可替换的 Provider。本项目当前是「关系表 + 每轮独立 checkpoint + 单一字符串提示词 + 关键词规则路由」的传统形态，二者在**理念层**差异显著、在**工程层**存在清晰的借鉴路径。

### 0.3 事实来源与分级标准

本报告所有结论均来自以下第一手资料，并按可信度分级标注：

| 分级标记 | 含义 | 来源 |
|---|---|---|
| 【官方文档核实】 | 官方文档页面直接陈述 | https://deepseek-harness.github.io/deepseek-harness/ |
| 【源码核实】 | 仓库源码 / AGENTS.md 直接陈述 | https://github.com/deepseek-ai/deepseek-harness |
| 【本项目代码】 | 本项目实际代码 | `backend/app/`、`frontend/src/` |
| ⚠️【待核实】 | 旧笔记中存在但本次未获官方文档/源码直接证实 | 降级标注，建议不作为决策依据 |

> **重要降级说明**：早期研读笔记中的两处内容——「六类工具卡片（generic/terminal/diff/search/read/web）」与「presentCall/presentResult 纯函数」——在本次官方文档与源码核查中**均未被直接证实**（工具执行管线文档聚焦 `pre-execute → guard → execute` 流水线，未提及 UI 卡片分类；UI 渲染归 slot 体系而非纯函数）。本报告一律降级为 ⚠️【待核实】，不纳入集成方案的设计依据。

---

## 1. 核心工作机制

### 1.1 意图识别：无传统 NLP，纯数据驱动决策

**核心结论：dsh 没有传统意义上的「意图识别模块」——没有关键词表、没有分类器、没有独立的 intent 枚举。**「下一步做什么」这个决策完全由三个数据驱动机制协作完成：

1. **Inbox 双队列（InboxTarget）**：每个 Agent 维护一个 inbox，按投递目标分为两类——`next-turn`（普通轮次消息，每轮消费一条）与 `next-step`（steering / 注入内容，每一步消费）。inbox 支持 `append / prepend / replace / remove / clear / splice / claim` 等操作，并记录持久化的 `agent/inbox/spliced` 事件。（来源：官方文档 · reference/subsystems/core）

2. **`agent/pre-step` waterfall 决策点**：在打开每个步骤前，系统广播一个 waterfall 事件，监听者可返回 `PreStepDecision`：
   - `{ kind: 'reject' }`：拒绝打开本步骤（短路，不产生动作）；
   - `{ kind: 'enter', messages: UserMessage[] }`：进入步骤并注入用户消息。
   payload 携带 `messages / turn / step / signal`。（来源：官方文档 · reference/subsystems/core）

3. **事件溯源决定轮次边界**：一轮（turn）的关闭**不由任何状态机显式决定**，而是由「模型已无 live tool calls 且无 fresh steering」这一数据事实决定；`agent/status` 事件镜像 `idle | running` 两个状态。（来源：官方文档 · reference/agent-lifecycle）

**与「旧笔记」的澄清**：旧笔记中「reject/enter」的字面，实际是 `agent/pre-step` 的 `PreStepDecision` 返回值语义（`{kind:'reject'} | {kind:'enter'}`），**不是** Cordis 的事件模式（emit/bail/serial/waterfall）。二者需严格区分。

### 1.2 Harness 间调用协同：AgentHandle 投递 + Subagent seam

**核心结论：dsh 的「多 Agent 协同」由两层机制构成——AgentHandle 的同进程投递方法 + Subagent seam 的跨进程委派。**

#### 1.2.1 AgentHandle 投递方法（同一 Agent 生命周期内的协同）

`AgentHandle` 提供五个投递/控制方法（来源：官方文档 · reference/agent-lifecycle）：

| 方法 | 语义 |
|---|---|
| `send()` | 统一底层路由，暴露 `target` + `wakeup` 参数 |
| `followup()` | 排队一条普通后续轮次消息到 `next-turn` 并唤醒 driver |
| `steer()` | 提交最近步骤的 steering，idle 时启动轮次 / running 时在下一步边界消费 |
| `inject()` | 排队一段模型可见上下文到 `next-step`，**不唤醒** driver |
| `cancel(cause, options)` | 取消当前运行 |

「协同」的本质是**通过 inbox 队列路由消息 + 通过 wakeup 信号唤醒 driver**，而非直接函数调用。这保证了投递是可记录、可回溯的（每条投递都落为事件）。

#### 1.2.2 Subagent seam（跨 Agent 委派）

Subagent 是**可选能力**，不在核心 loop 内。两类委派（来源：官方文档 · reference/subsystems/subagent）：

- **one-shot（一次性）**：`SubagentProvider.start()` 返回 `SubagentRun`，执行完即结束。
- **continuable（可续）**：持久化子代理会话，支持 FIFO 多轮冷恢复。

Provider 采用 Service Provider 模式，实现包括 `spawn-in-process / fork / acp / codex / claude-code / dsh-sdk`。

**因果归因**用 `MessageSource` 类型区分消息来源：`CoordinatorMessageSource`（协调者）、`SubagentReportMessageSource`（子代理报告）、`SubagentSettledMessageSource`（子代理结束）。其中 Settled 与 Report 的 `kind` **刻意不同**，以便下游区分「子代理的中间报告」与「最终结算」。`interrupt()` 是唯一公开的停止操作。

### 1.3 系统提示词：PromptSection 分层组装

**核心结论：dsh 的系统提示词不是单一字符串，而是由 system-prompt 包协调「贡献者（Provider）与组装调用（assemble）」动态拼装的分层结构。**

关键机制（来源：官方文档 · reference/subsystems/system-prompt）：

1. **PromptSection 结构**：`{ name, order, text, complete }`。`order` 决定排序，约定：
   - `-100`：harness 身份；
   - `0`：部署角色 / persona；
   - `100–199`：工具使用指引。

2. **作用域遮蔽（scoping）**：作用域同名段落会遮蔽全局段落；但**工具 provider 例外**——全局与作用域的工具 provider 都贡献，不互相遮蔽。

3. **工具 schema 注入**：通过 `tools(provider)` 注入，返回 `schemas + knownNames`，保留名 `TOOL_ORDER_REST`。

4. **`system-prompt/assemble` 是 Expert Waterfall 事件**：组装流程为「收集全局 + 匹配作用域 providers → 分离工具参数 → 规范排序 → 组装 waterfall → complete 段落恢复」。

5. **变量插值**：`{{var}}` 由 `variable(name, provider)` 注册，在 `renderPrompt` 阶段插值。

6. **动态上下文**：`context(context)` 注册动态上下文；`suppressRuntimeContext()` 抑制运行时上下文注入。

7. **整体替换**：`complete: true` 标记该段落可替换整个提示词。

### 1.4 小结

| 机制 | dsh 实现 | 关键词 |
|---|---|---|
| 意图识别 | 数据驱动（inbox + pre-step waterfall + 事件溯源） | 无 NLP、无 intent 枚举 |
| harness 协同 | AgentHandle 投递 + Subagent seam + MessageSource 归因 | 事件可回溯、one-shot/continuable |
| 系统提示词 | PromptSection 分层组装 + assemble waterfall | 分层、遮蔽、schema 注入 |

---

## 2. 界面交互设计

### 2.1 工具调用与思考内容的展示：类型化内容块隔离

**核心结论：dsh 在**协议层**就对「思考」与「正文」做了类型隔离，前端渲染只是对协议块的自然呈现。**

流式协议 `StreamChunk` 是一个封闭联合类型（来源：官方文档 · reference/subsystems/llm-streaming）：

```
StreamChunk =
  | block-start
  | text-delta          // 可见正文增量
  | reasoning-delta     // 思考过程增量
  | tool-call-delta     // 工具调用增量
  | block-end
  | usage
  | finish
```

- `ContentBlockMap` 含 `text / reasoning / image / tool-call / tool-result` 等块类型；
- `reasoning-delta` 传输 `ReasoningBlock.thinking`（思考内容），`text-delta` 传输 `TextBlock`（可见正文）——**二者在类型上永不混淆**；
- `usage` 在 `finish` 之前到达，`finish` 后无分片；`BlockAssembler` 把增量折叠回完整块；
- `TokenUsage` 含 `inputTokens / outputTokens / cacheRead / cacheWrite / reasoningTokens`（互不重叠）。

这带来的 UI 效果是：**思考内容可以天然折叠/展开，正文永远干净**，前端无需用「截断正文前 N 字」这类启发式来区分思考与正文。

### 2.2 长链接会话的执行逻辑与状态管理：事件溯源 + surface 投影

**核心结论：dsh 的会话不是「消息表」，而是 append-only 的类型化事件日志；用户看到的消息是「投影（surface）」出来的。**

关键机制（来源：官方文档 · reference/subsystems/session）：

1. **Session = append-only SessionEvent 日志，唯一真源**。LLM 消息历史不是单独存储的，而是通过 `deriveMessages()` 从事件日志**派生**出来的。

2. **`seq = log.length` 严格连续**，保证事件顺序与幂等。

3. **surface 投影**：只有三类事件会投影为用户可见消息——`user/message`、`assistant/message`、`tool/result`；其余（`agent/*`、`turn/*`、`step/*`、`assistant/chunk` 等）**不投影**。`SurfaceOp` 含 `append` 与 `replace(start, end)`（后者用于 compaction 压缩）。

4. **双后端持久化**：JSONL（默认 zstd 压缩）与 SQLite（wal 模式）。

5. **Fork API**：可从任意事件点分支出一个新会话——这是事件溯源的直接红利，关系表模型难以等价实现。

6. **SessionStore** 提供 `get / list / deriveMessages / surface / events` 等查询；生命周期事件 `session/created / disposed / event / flush`。

**执行逻辑**：Agent 主循环（agent-loop）一轮流经六步——driver 认领 → 开启轮次 → 组装请求前缀（system-prompt）→ 流式获取响应（LLM seam）→ 分发工具调用（tools seam）→ 追加事实回日志。**每步都产生事件，事件是可重放的**，因此「长链接会话」的断线重连、状态恢复、审计回溯都有统一答案。

---

## 3. Web 界面布局与动效设计

**核心结论：dsh 的 Web 端采用 React + Vite，渲染层被抽象为「conversation node + slot」体系，投影层与渲染层严格分离；动效依赖 React 组件状态切换 + CSS 过渡，无第三方动画库。**

关键机制（来源：官方文档 · reference/subsystems/session-projection + cookbook/adding-a-conversation-node）：

1. **投影层与渲染层分离**：投影层只输出协议层的 JSON 全量值，**不关心如何渲染**；渲染完全归 slot 体系。

2. **ConversationNodeDefinition**：从持久事件族**增量**构造业务状态，结构为 `kind / target / match / start / update / publication / buildLocationData / buildViewNode`。

3. **渲染约束**：renderer 只能消费 `node.data` 与受限的 Location hook，**禁止扫描 Session 窗口**——这保证了渲染是无副作用的纯视图。

4. **publication 选项**：`immediate / animation-frame / none`——控制节点在帧内、下一动画帧、或不发布，是**动效与性能**的接入点。

5. **动效**：靠 React 组件状态切换 + CSS 过渡实现（轻量），**不引入第三方动画库**。

> ⚠️【待核实】旧笔记中「presentCall / presentResult 纯函数」与「六类工具卡片（generic/terminal/diff/search/read/web）」的说法，本次官方文档/源码核查未直接证实。官方文档将 UI 卡片分类归入 slot 体系而非固定枚举，故本节不将其作为确定结论。

---

## 4. 与本项目差异对比

### 4.1 七维度对照表

| 维度 | DeepSeek Harness（dsh） | 本项目 DataAgent Pro |
|---|---|---|
| **意图识别** | 无 NLP，数据驱动（inbox 双队列 + `agent/pre-step` waterfall + 事件溯源） | 传统模式：关键词快速通道（`_fast_other`/`_chart_keywords`）+ LLM `clarify_and_plan` 合并调用（intent 枚举 5 类）；DeepAgent 模式：system_prompt 硬编码触发词 |
| **harness 协同** | AgentHandle 投递（followup/steer/inject/send/cancel）+ Subagent seam（one-shot/continuable）+ `MessageSource` 因果归因 | `CompiledSubAgent` 预编译子图（data-query / knowledge-retrieval）+ `task` 工具委派；**无**因果归因、**无** one-shot/continuable 区分 |
| **系统提示词** | `PromptSection` 分层组装（order 排序 + 作用域遮蔽 + 工具 schema 注入 + `assemble` waterfall + 变量插值 + `complete` 整体替换） | `build_system_prompt()` 返回**单一字符串**（角色定义 + 触发词 + 示例 + Skills 指令拼接） |
| **会话/事件存储** | append-only `SessionEvent` 唯一真源 + `deriveMessages` 派生 + surface 投影 + JSONL/SQLite 双后端 + Fork API | `chat_sessions`/`chat_nodes` 关系表（MySQL）+ 每轮独立 `run_id` + Redis checkpoint；历史消息靠 `_get_last_run_state`/`get_session_messages` 从 Redis 状态**反推重建** |
| **流式协议** | `StreamChunk` 封闭联合类型，`reasoning-delta` 与 `text-delta` **类型化隔离**；`TokenUsage` 细分 reasoningTokens | SSE 事件 `token/thinking/tool_call/tool_result/...`；思考（`thinking`）与正文（`token`）**未类型化隔离**，正文由 `activeTokenMsgId` 增量拼接 |
| **UI 渲染** | 投影层（协议 JSON）与渲染层（slot 体系 / ConversationNodeDefinition）分离，renderer 禁止扫描 Session | Vue3 + Pinia，`stores/chat.ts` 维护 `messages` 数组 + `tasks` 清单，事件回调直接改状态；`tool_call`+`tool_result` 合并为 `tool_chain` 单卡片 |
| **布局动效** | React + Vite；conversation node / slot；publication（immediate/animation-frame/none）；CSS 过渡，无第三方动画库 | Vue3 + Element Plus + AntDesignX（`/chat-x` 页）；`components/` 组件化；动效依赖组件状态切换 + CSS |

### 4.2 本项目 SSE 事件类型全量清单（供方案设计参考）

从 `backend/app/api/v1/chat.py` 与 `frontend/src/composables/useSSE.ts` 核对，当前 SSE 协议事件类型为：

| 事件 type | 后端产出 | 前端处理 | 说明 |
|---|---|---|---|
| `thread_id` | ✅ | ✅ `onThreadId` | 流开始推送会话 ID |
| `status` | ✅ | ✅ `onStatus` | 状态文本（如"正在分析..."） |
| `thinking` | ✅ | ✅ `onThinking` | agent/phase/content，思考卡片（content>30 字才展示） |
| `plan` | ✅ | ✅ `onPlan` | intent/intent_label/steps/chart_suitable |
| `clarification` | ✅ | ✅ `onClarification` | 意图追问卡片 |
| `sql` | ✅ | ✅ `onSQL` | SQL 代码卡片 |
| `result` | ✅ | ✅ `onResult` | 查询结果表格 |
| `chart` | ✅ | ✅ `onChart` | ECharts 图表配置 |
| `tool_call` | ✅ | ✅ `onToolCall` | 兼容 `tool_name`(旧)/`name`(新)+`args` |
| `tool_result` | ✅ | ✅ `onToolResult` | 兼容 `name`/`status`/`content`，与 tool_call 合并 |
| `token` | ✅ | ✅ `onToken` | 逐字流式正文 |
| `title` | ✅ | ✅ `onTitle` | 会话标题实时推送 |
| `approval_required` | ✅ | ✅ `onApprovalRequired` | 高危 SQL 审批 |
| `error` | ✅ | ✅ `onError` | 含 code/recoverable |
| `done` | ✅ | ✅ `onDone` | 流结束 |
| `quality_feedback` | ✅ | ❌ **无 case** | quality_gate 质量反馈，前端落入 default 分支 warn |
| `text` | ❌ 不发 | ✅ `onText` | 预留（MEMORY 记录明确不主动发 text） |
| `analysis` | ❌ 不发 | ✅ `onAnalysis` | 预留 |
| `schema` | ❌ 不发 | ✅ `onSchema` | 预留 |
| `node_started` | ❌ 不发 | ✅ `onNodeStarted` | 预留（后端用 thinking 驱动任务清单） |

> 注：上表暴露一个**协议演进缝隙**——后端已产出 `quality_feedback`，前端未实现对应 case；前端预留了 `text/analysis/schema/node_started` 回调但后端未产出。这是集成改造时应一并梳理的兼容性问题。

### 4.3 优缺点分析

**dsh 的优势（可借鉴）**：
- 事件溯源使「可重放、可审计、可 Fork」成为系统级能力，而非事后补丁；
- 能力接缝使 LLM / 存储 / 工具可替换、可组合，测试时可注入 replay 后端；
- PromptSection 分层使提示词可插拔、可遮蔽，避免巨型单一字符串；
- 流式协议类型化隔离思考与正文，前端渲染更干净。

**dsh 的代价（需权衡）**：
- 运行时复杂度高（Cordis 依赖注入 + 事件系统 + seam 抽象），学习曲线陡；
- Developer Preview，接口不稳定（官方声明 breaking changes）；
- TS/React 技术栈与本项目 Python/Vue 不直接兼容。

**本项目的优势（应保留）**：
- 传统 LangGraph StateGraph 显式、易调试、团队熟悉；
- 关系表 + Redis checkpoint 实现简单，已满足当前单用户/小规模场景；
- Vue3 + Element Plus + AntDesignX 组件生态成熟，交付快。

**本项目的短板（改进动机）**：
- 历史消息靠「Redis 状态反推」脆弱（受 checkpoint 生命周期、状态字段演化影响）；
- 单一字符串提示词难以按场景定制、难以审计；
- 思考与正文未类型化隔离，靠 `currentAgent` 去重 + 前端启发式，易出渲染 bug；
- 子 Agent 委派无因果归因，多子 Agent 协作时难以追溯「谁产出、谁消费」。

---

## 5. 借鉴式集成改造方案（新版本）

> **总原则**：不引入 dsh 运行时（不依赖 Cordis / TS / React），只把「事件溯源、PromptSection、能力接缝、投影」四个设计模式**落地到现有 FastAPI + LangGraph + Vue 架构**，以 feature flag 灰度切换，旧模式保持可用。

### 5.1 架构调整

在现有三层（API 层 / Graph 层 / 存储层）之上，新增一个**「事件溯源 + 投影」中间层**作为会话的单一事实来源，逐步替代「关系表 + Redis 反推」：

```
现状：
  API(chat.py) ──astream──▶ Graph(workflow/deepagent)
                              │
                              ├─ MySQL chat_sessions/chat_nodes（元数据）
                              └─ Redis checkpoint（状态，历史靠反推）

目标（新版本）：
  API ──astream──▶ Graph
                     │  每次产出/投递都 append 事件
                     ▼
              SessionEventLog（append-only）
                     │
              surface 投影（deriveMessages / surface）
                     │
              ┌──────┴──────┐
              │   MySQL 表   │   JSONL 文件（可 zstd）
              └─────────────┘
```

关键调整点：
1. **会话持久化**：新增 `SessionEvent` 事件日志，`chat_sessions`/`chat_nodes` 保留为「索引/元数据」而非「事实来源」；
2. **系统提示词**：把 `build_system_prompt()` 单一字符串重构为 `PromptSection` 分层组装；
3. **能力接缝**：抽象 `LLM / Storage / Search / ToolRegistry` 为 seam，支持多 Provider 并列与注入替换；
4. **流式协议**：SSE 协议**扩展**（新增事件，不删除旧事件），将「思考」与「正文」类型化隔离。

### 5.2 模块划分

新增以下模块，与现有 `deepagent/`、`graph/` 并存，不破坏现有模式：

| 新模块 | 职责 | 对应 dsh 设计 |
|---|---|---|
| `app/core/event_sourcing.py` | append-only `SessionEvent` 日志 + `seq` + surface 投影（`deriveMessages` / `surface`）+ Fork | 事件溯源会话 |
| `app/core/prompt_section.py` | `PromptSection` 结构 + order 排序 + 作用域遮蔽 + `assemble` 组装 + 变量插值 | system-prompt 包 |
| `app/core/seam.py` | `ServiceDefinition` / `Provider` / `Consumer` 注册表，运行时选后端 | 能力接缝 |
| `app/core/stream_protocol.py` | SSE 事件类型化的 `StreamChunk` 联合类型（text/reasoning/tool-call 隔离） | llm-streaming |
| `app/core/projection.py`（可并入 event_sourcing） | 从事件投影出用户可见消息，替代 `get_session_messages` 的反推逻辑 | session-projection |

前端新增：
| 新模块 | 职责 | 对应 dsh 设计 |
|---|---|---|
| `frontend/src/components/ReasoningBlock.vue` | 思考内容折叠/展开卡片（替代现在的 `currentAgent` 去重启发式） | reasoning 块 |
| `frontend/src/components/ConversationNode.vue`（可选） | 通用 conversation node 渲染 slot 体系 | slot 体系 |

### 5.3 兼容性处理

1. **feature flag 灰度**：新增环境变量 `EVENT_SOURCING_ENABLED`、`PROMPT_SECTION_ENABLED`、`SEAM_ENABLED`，默认 `false`；旧模式（传统 LangGraph + 现有 SSE 协议 + 关系表存储）保持默认可用，新架构逐步接管。

2. **SSE 协议向后兼容**：只**新增**事件类型（如 `reasoning_token` 与 `token` 分离），**不删除**旧类型；前端 `dispatchEvent` 用 `switch` 分支对未知类型安全降级，因此新事件对旧前端无副作用。

3. **双写过渡**：事件日志开启后，`_stream_chat` / `_stream_chat_deepagent` 在产出 SSE 事件的同时**双写**到 `SessionEvent` 日志；`get_session_messages` 优先读事件日志，回退 Redis（与现有「MySQL 优先、Redis 回退」策略一致）。

4. **协议缝隙修复**：为 `quality_feedback` 补充前端 case；明确 `text/analysis/schema/node_started` 四个预留回调的取舍（保留但标注 deprecated 或补齐后端产出）。

### 5.4 分阶段实施建议

| 阶段 | 内容 | 风险 | 交付物 |
|---|---|---|---|
| **Phase 1** | 事件溯源 + 投影：新增 `SessionEvent` 日志（MySQL 新表 `session_events` 或 JSONL 落盘）、surface 投影、`get_session_messages` 迁移到投影；双写 + 回退 | 中（涉及会话恢复核心路径） | 会话可重放、可 Fork |
| **Phase 2** | 系统提示词分层：`prompt_section.py` + 重构 `build_system_prompt` 为组装器，保留旧字符串作为 `complete:true` 兜底段落 | 低（纯后端，可 A/B 对比） | 提示词可插拔、可审计 |
| **Phase 3** | 能力接缝抽象：`seam.py` + LLM/Storage/Search 三角色化，兼容现有 `ConfigManager` 热加载 | 中（涉及 LLM 路由） | 可注入 replay 后端，测试友好 |
| **Phase 4** | 流式协议类型化 + UI 渲染层：`stream_protocol.py` + `ReasoningBlock.vue`，思考/正文隔离；conversation node 渲染 | 中（前后端联动） | 思考折叠、正文干净 |
| **Phase 5** | 布局与动效对齐：slot 体系渲染、publication 时机（immediate/animation-frame）、CSS 过渡规范 | 低（纯前端） | 统一视觉规范 |

**建议节奏**：Phase 1 → Phase 2 → Phase 3 可并行推进（三者解耦），Phase 4 依赖 Phase 1 的事件类型与 Phase 3 的 seam，Phase 5 独立。每阶段完成后用现有 `scripts/run_full_test.py` 回归 + Chrome DevTools MCP 端到端验证。

---

## 附录：事实来源清单

### A. 官方文档（deepseek-harness.github.io）

| 页面 | 对应机制 | 关键内容 |
|---|---|---|
| `/develop/basic/` | 插件机制 | 插件 `apply(ctx)`、`inject=['tools']`、`ctx.effect()`、三种形态、cordis.yml `--patch` |
| `/develop/framework/events` | 事件系统 | emit/bail/serial/waterfall 四模式、`namespace/action` 命名 |
| `/reference/subsystems/core` | agent-loop 主循环 + inbox | 六步轮次、`InboxTarget` 双队列、inbox 操作 |
| `/reference/agent-lifecycle` | AgentHandle 投递 | followup/steer/inject/send/cancel、whenIdle |
| `/reference/subsystems/system-prompt` | 系统提示词 | PromptSection、order、作用域遮蔽、schema 注入、assemble waterfall、变量插值 |
| `/reference/subsystems/subagent` | 子代理 | one-shot/continuable、Provider、MessageSource 因果归因 |
| `/reference/subsystems/session` | 会话/事件溯源 | append-only、deriveMessages、surface 投影、JSONL/SQLite、Fork |
| `/reference/subsystems/llm-streaming` | 流式协议 | StreamChunk 联合类型、reasoning-delta/text-delta、TokenUsage |
| `/reference/subsystems/session-projection` | UI 投影 | 投影层/渲染层分离、ConversationNodeDefinition |
| `/reference/capability-seams` | 能力接缝 | Service Definition/Provider/Consumer 三角色、core/seam/bundle |
| `/reference/tool-execution-pipeline` | 工具执行 | pre-execute→guard→execute、finalizeContent |
| `/reference/cookbook/adding-a-conversation-node` | conversation node | node 定义结构、publication 选项 |

### B. GitHub 源码（github.com/deepseek-ai/deepseek-harness）

| 来源 | 关键内容 |
|---|---|
| 仓库 README | 定位、Developer Preview、COMPATIBILITY-BREAKING CHANGES、MIT、monorepo 结构 |
| `AGENTS.md`（GitHub API 获取） | 仓库布局、`模型可见⇒记录` 约定、能力接缝三角色不可拆分、无硬编码参数、fail loud、瀑布监听器必须 next() |

### C. 本项目代码（已核对）

| 文件 | 关键内容 |
|---|---|
| `backend/app/graph/workflow.py` | clarify_plan_node、_fast_other、_chart_keywords、clarify_and_plan、子图编排 |
| `backend/app/graph/subagents.py` | build_sql_pipeline_subagent、build_rag_subagent（CompiledSubAgent） |
| `backend/app/deepagent/prompts.py` | build_system_prompt（单一字符串）、build_legacy_prompt |
| `backend/app/deepagent/harness.py` | create_deep_agent、get_deep_agent 单例 |
| `backend/app/core/stream.py` | StreamContext（queue + merge_queue） |
| `backend/app/api/v1/chat.py` | _stream_chat / _stream_chat_deepagent、SSE 事件产出、_get_last_run_state、get_session_messages |
| `backend/app/models/session.py` | ChatSession / ChatNode 表结构 |
| `frontend/src/stores/chat.ts` | messages/tasks、消息卡片类型、sendMessage |
| `frontend/src/composables/useSSE.ts` | fetch + ReadableStream、dispatchEvent 分发 |
| `frontend/src/components/` + `x/` | 组件清单（ChatInput/ChatSidebar/.../XThoughtChain 等） |
| `docs/.vitepress/config.mts` | 导航与侧边栏结构 |

---

## 声明

本报告**严格基于**上述第一手资料撰写，未引入外部假设或未经证实的实现细节。对早期笔记中未被官方文档/源码证实的内容（六类工具卡片、presentCall/presentResult 纯函数）已明确降级标注为 ⚠️【待核实】。本报告不构成对 dsh 接口稳定性的承诺（官方已声明 Developer Preview 存在 breaking changes）；集成方案以「设计模式借鉴」为主，落地路径需在方案确认后结合本项目实际代码迭代细化。
