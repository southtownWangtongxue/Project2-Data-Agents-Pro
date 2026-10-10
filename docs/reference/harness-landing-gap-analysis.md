# Harness 架构落地差距分析

> 版本：v1.0（落地状态基线报告）
> 日期：2026-10-10
> 定位：2026-10-10 项目文档已完成「Hermes → Harness」称谓统一（7 个文档，纯措辞更名，未动代码）。本报告以《DeepSeek Harness 源码分析与本项目集成评估》（v1.0，2026-08-17，下称「集成分析」）的 5 阶段方案为基准，**逐项核实代码层的实际落地状态**，给出差距项与分阶段建议。本报告仅做分析与文档对齐，不改代码。

---

## 0. 摘要

### 0.1 一句话结论

「Harness 架构」在代码层**已大部分落地**：集成分析规划的 Phase 1~4（事件溯源、分层提示词、能力接缝、类型化流式协议）四类核心模块均已实现并以 feature flag 门控接入；真正的差距集中在 **① 三个 flag 默认关闭且无灰度计划（新架构处于休眠态）、② DeepAgent 路径事件溯源不完整、③ 子代理无因果归因、④ Phase 5 渲染投影层未实施** 四处。

### 0.2 结论速览

| 维度 | 集成分析规划 | 当前状态 |
|---|---|---|
| Phase 1 事件溯源 + 投影 | `event_sourcing.py` + surface 投影 + Fork | ✅ 已落地（有 1 处集成缺口，见 §3.2） |
| Phase 2 系统提示词分层 | `prompt_section.py` + 组装器 | ✅ 已落地（flag 门控） |
| Phase 3 能力接缝 | `seam.py` + search/storage 两个 seam | ✅ 已落地（LLM seam 按设计留待后续） |
| Phase 4 流式协议类型化 | `stream_protocol.py` + ReasoningBlock | ✅ 已落地（且已演进至 channel/step_id） |
| Phase 5 渲染投影层 | slot 体系 / ConversationNodeDefinition | ❌ 未实施 |
| 会话能力（fork/trajectory/goal） | 事件溯源红利 | ✅ API 已全量提供 |
| 数据驱动意图（inbox/pre-step waterfall） | 设计模式借鉴，非必选项 | ❌ 保留 LLM clarify_and_plan（符合「借鉴式」定位） |

> 证据分级标注沿用集成分析约定：【代码核实】= 本次逐文件核实；【commit】= git 历史可查。

---

## 1. 背景

- **称谓统一**：2026-10-10，README.md、CLAUDE.md、docs/guide/architecture.md、docs/index.md、docs/项目审计与改进计划.md、docs/项目需求规格说明书.md 及交付记录共 7 处，将架构称谓由「Hermes 模式」统一更名为「Harness 模式」。全仓库 grep 确认已无 Hermes 残留。
- **为什么这次更名是「名实对齐」而非单纯换词**：集成分析（2026-08-17）即以 DeepSeek Harness（dsh）为参考基准规划了「借鉴式集成改造」5 阶段方案；其后代码已按方案实施（见 §2）。文档称谓此番对齐，是把「对外叙事」追平「代码事实」。
- **本报告要回答的问题**：距离「Harness 架构完整落地」还差什么、差多少、按什么顺序补。

---

## 2. 已落地清单（逐项核实）

### 2.1 Phase 1：事件溯源 + surface 投影 ✅

| 规划项 | 落地状态 | 证据 |
|---|---|---|
| `SessionEvent` append-only 事件日志（唯一事实来源） | ✅ `session_events` 表，自增 `id` 承担 seq 单调性，会话内按 id 排序即事件顺序 | 【代码核实】`backend/app/core/event_sourcing.py` L93-169；`backend/app/models/session.py` L65-104 |
| 类型化事件 `EventType`（最终态 6 类 + 过程态 3 类） | ✅ user_message/sql/result/analysis/chart/error + plan/clarification/tool_chain | `event_sourcing.py` L33-53 |
| surface 投影（仅最终态三类可见，过程态不投影） | ✅ `SURFACE_EVENT_TYPES` 集合，语义与 dsh `agent/*`/`turn/*` 不投影约定一致 | `event_sourcing.py` L55+ |
| `deriveMessages()` 派生用户可见消息 | ✅ `derive_messages()`，且 `get_session_messages` 已迁移为「事件投影优先、Redis 回退」 | `chat.py` L1707-1724 |
| Fork API | ✅ `SessionEventStore.fork` + `POST /sessions/{thread_id}/fork`（复制事件 + 补写会话元数据） | `chat.py` L1892-1916 |
| 双写过渡 | ✅（传统路径）`_stream_chat` 经 `_track` 覆盖 9 类事件（USER_MESSAGE/CLARIFICATION/PLAN/SQL/RESULT/TOOL_CHAIN/ANALYSIS/CHART/ERROR） | `chat.py` L346-684 |
| 轨迹查询 | ✅ `GET /sessions/{thread_id}/trajectory`（事件日志投影为时间线） | `chat.py` L1858 |

### 2.2 Phase 2：系统提示词分层 ✅

| 规划项 | 落地状态 | 证据 |
|---|---|---|
| `PromptSection`（order 排序 + 作用域遮蔽 + 变量插值） | ✅ `PromptSection`（order/scope/排序权重约定）+ `PromptAssembler`（`_resolve_scope` 遮蔽、`assemble` 按 order 稳定排序拼接、`_interpolate` 插值） | 【代码核实】`backend/app/core/prompt_section.py` L38-141 |
| 组装器接管 `build_system_prompt`，旧字符串兜底 | ✅ `PROMPT_SECTION_ENABLED` 门控：开启走 `build_system_prompt_sections`，关闭走 `_build_system_prompt_legacy` 单一字符串 | `backend/app/deepagent/prompts.py` L28-30, L139 |

### 2.3 Phase 3：能力接缝 ✅

| 规划项 | 落地状态 | 证据 |
|---|---|---|
| `ServiceDefinition / Provider / Consumer` 三角色 | ✅ `ServiceDefinition`/`Provider`/`SeamRegistry`（`define`/`register`/`select`/`resolve`/`selected`），core/seam/bundle 分类语义齐备 | 【代码核实】`backend/app/core/seam.py` L46-174 |
| search seam（联网搜索后端可替换） | ✅ `deepagent/tools.py` `_register_search_seam` 注册 baidu provider，`SEAM_ENABLED` 门控解析 | `deepagent/tools.py` L79-104 |
| storage seam（存储后端可替换） | ✅ `db/session.py` 注册 mysql/postgresql provider，flag 门控解析引擎 | `backend/app/db/session.py` L61-84 |
| LLM seam | 按设计留待后续（`get_llm`/`get_langchain_llm` 返回类型不同、由 contextvars provider 路由，与 seam「单例后端选择」语义冲突，待统一 LLM 接口后再抽象） | `seam.py` L20-27 注释明确记录该决策 |

### 2.4 Phase 4：流式协议类型化 + UI ✅（且已演进超出原规划）

| 规划项 | 落地状态 | 证据 |
|---|---|---|
| `stream_protocol.py` 类型化事件常量 | ✅ `SSEEventType`（含 REASONING/NODE_STARTED/QUALITY_FEEDBACK）+ `make_event`；注释明确「新增类型只增不删」的兼容约定 | 【代码核实】`backend/app/core/stream_protocol.py` L14-46 |
| 思考/正文类型化隔离（reasoning） | ✅ DeepAgent 路径推送 `reasoning` 事件（兼容 `additional_kwargs.reasoning_content` 与属性两种取法）；前端 `ReasoningBlock.vue` 折叠卡片 | `chat.py` L892-898；`frontend/src/components/ReasoningBlock.vue`（Chat.vue L19/L836 使用） |
| 协议演进（2026-09-28 流式链路优化，commit fef4974/cefdca7/e3a7230）【commit】 | ✅ 超出原规划：token 事件携带 `channel` 字段（sql/answer 路由，注入点在 `StreamContext.push_token`，`sql_coder.py` L68 传 `channel="sql"`）；全事件统一注入 `step_id`（contextvar + `_sse_event`，done/title/thread_id 除外）；前端 `steps: Map` 步骤分组渲染（`Chat.vue` `renderMessages` 按类型序稳定排序）；15s SSE 心跳；`quality_feedback` 补前端 case；`node_started` 事件全节点产出 | `backend/app/core/stream.py` L50-62；`chat.py` L46-47, L120-133, L395-398；`frontend/src/stores/chat.ts` L113-116, L424-432；`frontend/src/views/Chat.vue` L364-409 |

### 2.5 会话能力（事件溯源红利）✅

| 能力 | 证据 |
|---|---|
| 会话列表 `GET /sessions`（admin 全量查看） | 【代码核实】`chat.py` L1415 |
| 历史恢复 `GET /sessions/{id}`（投影优先） | `chat.py` L1644 |
| 标题修改 `PATCH /sessions/{id}` | `chat.py` L1601 |
| 长期目标 `GET/PUT /sessions/{id}/goal` | `chat.py` L1959/L1970 |
| 事件导出 `GET /sessions/{id}/export`（JSONL） | `chat.py` L1802 |
| 轨迹 `GET .../trajectory`、分支 `POST .../fork`、删除 `DELETE /sessions/{id}`（MySQL+Redis 双删） | `chat.py` L1858/L1892/L2005 |
| 停止生成 `POST /cancel` | `chat.py` L1099 |

---

## 3. 差距项（本轮不实施，仅列分析与建议）

### 3.1 三个 feature flag 默认 False，新架构处于休眠态 🔴 最高优先

- **现状**：`EVENT_SOURCING_ENABLED` / `PROMPT_SECTION_ENABLED` / `SEAM_ENABLED` 均默认 `False`（`backend/app/core/config.py` L62/L67/L72）。生产运行仍走「关系表 + Redis 反推 + 单一字符串提示词 + 直连后端」的旧行为，事件溯源/分层提示词/接缝的**代码已就绪但未被启用**。
- **影响**：文档宣称的 Harness 能力（可重放、可 Fork、可审计）在默认配置下不可用；fork/trajectory 依赖事件日志，不开 flag 时事件为空。
- **建议**：制定灰度计划——先在测试环境开启 `EVENT_SOURCING_ENABLED`（收益最大、回退成本最低，Redis 回退路径保留），回归会话恢复/fork/trajectory 后再开 `PROMPT_SECTION_ENABLED`（可 A/B 对比提示词效果），`SEAM_ENABLED` 最后（涉及存储引擎解析）。

### 3.2 DeepAgent 路径事件溯源不完整 🟠

- **现状**：`_stream_chat_deepagent` 仅双写 USER_MESSAGE / TOOL_CHAIN / ANALYSIS 三类（`chat.py` L829-983）；SQL/RESULT/CHART/PLAN/CLARIFICATION/ERROR 在 DeepAgent 模式下不入事件日志。
- **影响**：DeepAgent 会话的 `derive_messages` 投影、fork、trajectory 内容不完整（开 flag 后该模式的历史恢复退化）。
- **建议**：补齐 DeepAgent 主循环的事件双写（`__end__` 时按最终态聚合 SQL/RESULT/CHART/ERROR），或明确 DeepAgent 模式下历史恢复仍走 Redis 并在文档标注。

### 3.3 子代理无 MessageSource 因果归因 🟡

- **现状**：全仓库代码无 MessageSource/因果归因机制；`subagents.py` 的 `CompiledSubAgent` 仅为节点包装工厂（【代码核实】grep 仅命中研究文档）。
- **影响**：多子代理协作时无法追溯「谁产出、谁消费」（集成分析 §4.1 已识别）。
- **建议**：中优先级。可在事件溯源层为子代理产出事件增加 `source` 字段（coordinator/subagent_report/subagent_settled），复用现有 `session_events.payload`，无需新表。

### 3.4 Phase 5 渲染投影层未实施 🟡

- **现状**：主视图 `Chat.vue` 为「事件回调直改 Pinia 状态 + renderMessages 步骤分组排序」的自研方案；`components/x/` 下存在一套 ant-design-x 风格并行实现（XConversations/XBubbleList/XMessageRenderer 等）但**仅被实验路由 `/chat-x` 引用**，无 ConversationNodeDefinition/slot 投影层。
- **影响**：渲染层仍消费到达顺序（步骤分组已缓解），投影层与渲染层未分离。
- **建议**：低优先级。`/chat-x` 实验页可作为 Phase 5 的试验田；在投入前应先决策「双前端并存」的取舍（保留实验线或合并回主线），避免两套实现长期漂移。

### 3.5 数据驱动意图（inbox / pre-step waterfall）❌ 按设计保留

- **现状**：传统路径意图识别仍为 `orchestrator.py` 的 `clarify_and_plan`（单次 LLM 调用，intent 枚举 5 类）；全后端无 inbox/waterfall 机制（【代码核实】）。
- **评估**：这**符合**集成分析「只借鉴设计模式、不引入 dsh 运行时」的定位（其 5 阶段方案本就未包含意图机制重写）。建议在报告与后续规划中显式标注为「有意不采用」，避免被误判为遗漏。

### 3.6 TokenUsage 未细分 🟢 低优先

- **现状**：后端无 token 用量统计上报代码（【代码核实】grep 仅命中研究文档）；前端性能条为字符数估算。
- **建议**：待 LLM seam 统一后一并实施（需在各调用点汇聚 usage 数据）。

### 3.7 其他核实中发现的工程缝隙 🟢

1. **心跳覆盖不完整**：15s `": ping\n\n"` 仅在传统主循环（`chat.py` L395-398），`_stream_chat_deepagent` 长任务无心跳，存在代理空闲断连风险。
2. **多模式事件溯源覆盖**：`mode_router.py` 已注册 data/task/report/doc 四模式，但 task/report/doc 工作流的节点事件是否入 `session_events` 未系统核查，建议随 §3.2 一并补齐。

---

## 4. 分阶段建议（承接差距项）

| 阶段 | 内容 | 对应差距 | 风险 | 交付判据 |
|---|---|---|---|---|
| **L1** | 灰度开启事件溯源：测试环境开 `EVENT_SOURCING_ENABLED` → 回归会话恢复/fork/trajectory/导出 → 生产开启 | §3.1 | 中（会话恢复核心路径，Redis 回退兜底） | 默认配置下 fork/trajectory 有数据 |
| **L2** | DeepAgent + 多模式事件双写补齐 | §3.2、§3.7.2 | 中 | DeepAgent/task/report/doc 会话投影完整 |
| **L3** | 分层提示词灰度：开 `PROMPT_SECTION_ENABLED`，A/B 对比回答质量 | §3.1 | 低（legacy 兜底保留） | 提示词分层默认生效 |
| **L4** | 子代理因果归因（事件 payload 增 source 字段） | §3.3 | 低 | 轨迹接口可区分子代理产出 |
| **L5** | 能力接缝灰度 + LLM seam 论证 | §3.1 | 中（存储引擎解析） | `SEAM_ENABLED` 默认生效或明确弃用 |
| **L6** | 渲染投影层（slot 体系）试验 | §3.4 | 低（/chat-x 实验） | 双前端取舍决策落地 |

> 建议节奏：L1 → L2 → L3 串行（均依赖事件日志数据质量）；L4/L5 可并行；L6 独立。每阶段以 `pytest backend/tests/` + 前端 build + 手动 SSE 时序观察回归。

---

## 5. 本次同步的文档对齐（与报告一并提交）

以下既有文档中与代码现状不符的陈述已同步修正（依据 §2 证据）：

| 文件 | 修正内容 |
|---|---|
| `docs/项目审计与改进计划.md` | §3.2 对照表：流式 Token/思考过程/工具可视化/会话管理由 ❌🟡 改为 ✅；§4.2 事件清单：quality_feedback（已补 case）、node_started（已产出）、补充 reasoning/channel/step_id；§5 问题表：RAG Agent 节点（已存在 `workflow.py` rag_agent 节点）、deepAgents（`subagents.py` 已实际使用）、skills（技能管理已实现）；阶段 C-1/C-2 标注完成 |
| `CLAUDE.md` | 架构节补充四个核心模块（event_sourcing/prompt_section/seam/stream_protocol）与三个 feature flag 说明 |
| `README.md` / `docs/guide/architecture.md` / `docs/index.md` | 最小化补充事件溯源/能力接缝/分层提示词能力一句话说明 |

---

## 附录：事实来源

| 来源 | 说明 |
|---|---|
| 【代码核实】 | 2026-10-10 逐文件核实，路径与行号见各表 |
| 【commit】 | `fef4974`（perf(stream) 阶段一）、`cefdca7`（refactor(stream) 阶段二）、`e3a7230`（chore(stream) 阶段三） |
| 基准文档 | `docs/reference/deepseek-harness-integration-analysis.md` v1.0（2026-08-17） |
| 更名记录 | 2026-10-10 工作区改动：7 文档 Hermes→Harness（未提交，随后单独提交） |

## 声明

本报告基于上述第一手资料撰写，所有「已落地」结论均有代码级证据（文件:行号）；「差距项」均经反证核实（grep 零命中或标注部分属实）。报告不改代码；差距项的实施需另行立项并经方案确认。
