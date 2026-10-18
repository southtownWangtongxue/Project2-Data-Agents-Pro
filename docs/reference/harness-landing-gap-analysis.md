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
| TokenUsage 细分与上下文构成 | 集成分析未列入阶段，属可观测性缺口 | ✅ **已落地（2026-10-18）**：`usage` SSE 事件（token 明细 + 上下文三段 + 窗口可配），见 §3.6 |
| 思考流（reasoning）端到端 | 依赖 provider 返回 reasoning_content | ✅ **已打通（2026-10-18）**：langchain 丢弃字段的补丁 + 前端深度思考卡，见 §6.1 |
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

### 3.1 三个 feature flag 默认 False，新架构处于休眠态 🔴 **L1 已落地（2026-10-17 复核）**

- ~~**现状**：`EVENT_SOURCING_ENABLED` / `PROMPT_SECTION_ENABLED` / `SEAM_ENABLED` 均默认 `False`~~
  **复核结论（2026-10-17）**：`EVENT_SOURCING_ENABLED` **代码默认已为 `True`**
  （`config.py` L62，`dump_effective()` 显示 `source=default`，即非 patch 覆盖）。
  故 L1 的「灰度开启」实际早已完成，无需再改配置。
  `PROMPT_SECTION_ENABLED` / `SEAM_ENABLED` 仍为 `False`（L3 / L5 范围）。
- ~~**影响**~~ → 原影响（fork/trajectory 事件为空）**已消除**，见下。
- **L1 端到端验证结论（2026-10-17，真实链路）**：

  | 验证项 | 结果 |
  |---|---|
  | 会话恢复 `GET /sessions/{id}` | ✅ 200，消息数 2，首条 role=user（投影优先） |
  | 轨迹 `GET .../trajectory` | ✅ 200，**4 条事件**：`user_message / turn_start / turn_end / analysis` |
  | fork `POST .../fork` | ✅ 200，**`copied_events: 4`**（L1 判据：fork 有数据） |
  | fork 分支轨迹 | ✅ **4 条事件**——fork 出的分支非空壳 |
  | 导出 `GET .../export` | ✅ 200，JSONL 4 行，事件字段含 `id/thread_id/run_id/node_index/event_type` |

  采集方式：真实前端提问 → 真实 HTTP/API 核验（非单测）。
- **剩余待办（L3 / L5）**：`PROMPT_SECTION_ENABLED`（可 A/B 对比提示词效果）、
  `SEAM_ENABLED`（涉及存储引擎解析，最后做）。

### 3.2 DeepAgent 路径事件溯源不完整 🟠 **已补齐（2026-10-17 复核）**

- **复核结论**：`chat.py` 中 `_track(EventType.X)` 的调用覆盖 9 类——
  `USER_MESSAGE`(2)/`CLARIFICATION`(1)/`PLAN`(1)/`SQL`(1)/`RESULT`(1)/
  `TOOL_CHAIN`(5)/`ANALYSIS`(5)/`CHART`(1)/`ERROR`(1)。
  与本报告初稿所述「仅双写三类」已不符，DeepAgent/deepagent 分支的事件双写
  已在后续迭代补齐。
- **附带变化**：Harness 路径（`stream_harness.py`）也已接入事件溯源
  （import `EventType/SessionEventStore/event_sourcing_enabled/turn_event_enabled`），
  故 `HARNESS_MODE=on` 下的三模式会话同样入事件日志。
- **L2 实测结论（2026-10-17）**：按模式各跑一轮真实会话读 trajectory——

  | 模式 | 修复前事件类数 | 修复后 |
  |---|---|---|
  | data | 4（仅骨架） | **7**（+sql/result/tool_chain） |
  | report | 3 | **6**（+sql/result/tool_chain） |
  | doc | 3 | **4**（+tool_chain） |
  | task | 4 | 4（**无需修复**，见下） |

  task 模式经核实其 SSE 只 yield `status/thread_id/token` 三种，本就不产出
  sql/result/chart 事件——「事件日志只有 4 类」是设计差异而非缺口。
  修复本身：`stream_harness` 增加 `_ES_MAP` 映射 8 类富事件 + finally 兜底
  入库（见 `25ab498`）。
- **建议**：该项可关闭。

### 3.3 子代理无 MessageSource 因果归因 🟡

- **现状**：全仓库代码无 MessageSource/因果归因机制；`subagents.py` 的 `CompiledSubAgent` 仅为节点包装工厂（【代码核实】grep 仅命中研究文档）。
- **影响**：多子代理协作时无法追溯「谁产出、谁消费」（集成分析 §4.1 已识别）。
- **建议**：中优先级。可在事件溯源层为子代理产出事件增加 `source` 字段（coordinator/subagent_report/subagent_settled），复用现有 `session_events.payload`，无需新表。

### 3.4 Phase 5 渲染投影层 ❌ **本项已作废（2026-10-17 复核）**

- **现状**：主视图 `Chat.vue` 为「事件回调直改 Pinia 状态 + renderMessages 步骤分组排序」的自研方案；`components/x/` 下存在一套 ant-design-x 风格并行实现（XConversations/XBubbleList/XMessageRenderer 等）但**仅被实验路由 `/chat-x` 引用**，无 ConversationNodeDefinition/slot 投影层。
- **影响**：渲染层仍消费到达顺序（步骤分组已缓解），投影层与渲染层未分离。
- **复核结论（2026-10-17）**：**整项作废**。其立论前提「`components/x/` 下存在一套
  ant-design-x 风格并行实现、仅被 `/chat-x` 实验页引用」已不成立——前端已全量
  React 重写（`frontend-react/`），Vue 代码与 `components/x` 已清空
  （0 个 `.vue` 文件）。无「双前端并存」可取舍，渲染层即 React 主线自身。
- **建议**：从路线图移除；若将来真需要投影层，应在 React 侧重新立项。

### 3.5 数据驱动意图（inbox / pre-step waterfall）❌ 按设计保留

- **现状**：传统路径意图识别仍为 `orchestrator.py` 的 `clarify_and_plan`（单次 LLM 调用，intent 枚举 5 类）；全后端无 inbox/waterfall 机制（【代码核实】）。
- **评估**：这**符合**集成分析「只借鉴设计模式、不引入 dsh 运行时」的定位（其 5 阶段方案本就未包含意图机制重写）。建议在报告与后续规划中显式标注为「有意不采用」，避免被误判为遗漏。

### 3.6 TokenUsage 未细分 ✅ **已落地（2026-10-18）**

- **原现状**：后端无 token 用量统计上报代码；前端性能条为字符数估算。
- **已实施**：
  - `app/core/usage_metrics.py`：`UsageMeter` 从流末块 `usage_metadata` 聚合
    `input/output/cached/uncached/total`；legacy 路径经 `_RequestUsageCallback` 回灌。
  - LLM 客户端（`core/llm.py` / `deepagent/harness.py`）开启 `stream_usage=True`。
  - 三条流式路径（harness / legacy / deepagent）在 `done` 前下发 **`usage` SSE 事件**（协议只增）：
    扁平 token 字段 + `context{system_prompt,tool_defs,messages,window,used_pct}`。
  - **上下文窗口可配**：`LLMProvider.context_window`（默认 192000），`_usage_window()`
    优先级 = provider > `settings.CONTEXT_WINDOW` > 192K；运行时接口
    `PATCH /config/llm/{id}/runtime`（模型选择器悬浮面板 / 配置中心双向同步）。
  - 历史会话：`GET /chat/sessions/{id}` 在投影路径**现场估算**并返回 `usage`
    （`estimated: true`），避免切换会话后弹窗全空。
  - 前端：底部读数条三弹窗（会话统计 / Token 用量 / 上下文已用），分母随窗口实时联动。

### 3.7 其他核实中发现的工程缝隙 🟢

1. **心跳覆盖不完整**：✅ **已修复（2026-10-17，`4cd5a84`）**。
   原状态：15s `": ping\n\n"` 仅在传统主循环（`_stream_chat`），`_stream_chat_deepagent` 无心跳。
   **新情况**：`HARNESS_MODE=on` 后 **data/report/doc 全部走 `stream_harness`，
   而它原本也没有心跳**——风险从「一条分支路径」升级为「当前生产主路径」
   （report/doc 单轮实测可达 149s）。已给 `stream_harness` 主事件循环补心跳：
   把 `wait_for` 超时拆成两级，heartbeat(15s) 到点只发 `: ping` 并继续等，
   原有墙钟熔断逻辑不变。端到端验证：真实请求下 15.0s 静默期准时收到心跳。
   `_stream_chat_deepagent`（`mode=task`）仍无心跳，属低流量路径，待后续处理。
2. **多模式事件溯源覆盖**：`mode_router.py` 已注册 data/task/report/doc 四模式，但 task/report/doc 工作流的节点事件是否入 `session_events` 未系统核查，建议随 §3.2 一并补齐。
   - **2026-10-18 补充**：L2 双写已补齐（data 4→7 / report 3→6 / doc 3→4 类）；
     但 **reasoning 事件曾按流式 chunk 逐条落库**（一次对话 72 条 → 历史投影碎成 72 张卡），
     已改为 `_es_flush` 内**先合并连续 REASONING 再入库**，前端 `mapProjectedMessages`
     亦合并相邻片段（兼容旧数据）。
3. ✅ **心跳实现缺陷（2026-10-18 修复）**：§3.7.1 补的 `wait_for(aiter.__anext__(), timeout=15)`
   存在隐性致命问题——`wait_for` 超时会**取消**迭代任务，直接掐死 LangGraph 的 `astream`
   生成器帧。实测 `make_chart` 恰好执行 15s（等于心跳窗），事件流在工具后"干净退出"
   （无 error、无 SQL、无正文），日志表现为 `[pre]` 有、`[post]` 缺失。
   修法：`asyncio.shield(pending_next)` + 持久任务，超时只发 `: ping` 不取消迭代，
   `finally` 回收未决任务。修复后 67 事件完整跑通（工具链 → SQL/结果 → 正文 → usage → done）。
4. ✅ **SQL 事件字段口径不一致（2026-10-18 修复）**：harness 桥接器把 SQL 文本放
   `sql` 字段、legacy 放 `content`，而前端 reducer 只读 `content` → SQL 卡空白。
   已双口径兼容（`ev.sql || ev.content`）；落库侧同样修 `payload.content or payload.sql`，
   `_project` 对旧数据从 `payload.sql` 兜底。
5. ✅ **思考内容被适配层丢弃（2026-10-18 修复）**：`langchain-openai 1.2.x` 明确不提取
   `reasoning_content`（源码注释），导致 SSE 无 reasoning 事件。已在 `core/llm.py`
   模块加载期 monkeypatch `_convert_delta_to_message_chunk` / `_convert_dict_to_message`
   回填 `additional_kwargs["reasoning_content"]`（**改后需整进程重启**）。详见 §6.1。
6. ✅ **`enable_thinking` 参数位置错误（2026-10-18 修复）**：该非标准参数放在
   `model_kwargs` 会让 openai SDK 抛 `unexpected keyword argument`
   （`thinking=false` 时必现，直接打断对话）。已改 `extra_body`
   （`reasoning_effort` 同路径下发）。
7. ✅ **轮次信息缺失（2026-10-18 补齐）**：`_es_flush` 现在写入 `node_index`，
   `derive_messages` 给每条投影消息补 `turn_index`；前端据此实现「第 N/M 轮」切换
   （旧数据无该字段时自动回退为平铺）。

---

## 4. 分阶段建议（承接差距项）

| 阶段 | 内容 | 对应差距 | 风险 | 交付判据 |
|---|---|---|---|---|
| **L1** | ✅ 灰度开启事件溯源 + 端到端回归 | §3.1 | 中（会话恢复核心路径，Redis 回退兜底） | **已达成（2026-10-17）**：flag 默认已 `True`；恢复/轨迹/fork/导出四项端到端全过，fork `copied_events=4` |
| **L2** | DeepAgent + 多模式事件双写补齐 | §3.2、§3.7.2 | 中 | ✅ **已完成（2026-10-18）**：data 4→7 / report 3→6 / doc 3→4 类；reasoning 落库改为合并写入；事件带 `node_index`（§6.3） |
| **L3** | ⚠️ 分层提示词：**需先把 `PromptAssembler` 接入 `agent_factory`**（当前 `deepagent/prompts.py` 无任何 import 方，开 flag 对 Harness 零效果），再谈 A/B | §3.1 | 低 | 提示词分层默认生效（前提：已接入 Harness） |
| **L4** | 子代理因果归因（事件 payload 增 source 字段） | §3.3 | 低 | 轨迹接口可区分子代理产出 |
| **L5** | 能力接缝灰度 + LLM seam 论证 | §3.1 | 中（存储引擎解析） | `SEAM_ENABLED` 默认生效或明确弃用 |
| ~~**L6**~~ | ~~渲染投影层（slot 体系）试验~~ **已作废**：前端已全量 React 重写，Vue 与 `components/x` 清空，无「双前端并存」可取舍 | §3.4 | — | 从路线图移除 |

> 建议节奏：L1 → L2 → L3 串行（均依赖事件日志数据质量）；L4/L5 可并行；L6 独立。
> **验证方式已变更（2026-10-17 用户决策）**：~~每阶段以 `pytest backend/tests/` + 前端 build
> + 手动 SSE 时序观察回归~~ → 纯逻辑测试套件已归档至 `docs/archive/tests/`，
> 门禁改为 **MCP 端到端**（chrome-devtools 走真实页面 + 真实 HTTP/SSE/DB）+ build。

---

## 5. 本次同步的文档对齐（与报告一并提交）

以下既有文档中与代码现状不符的陈述已同步修正（依据 §2 证据）：

| 文件 | 修正内容 |
|---|---|
| `docs/项目审计与改进计划.md` | §3.2 对照表：流式 Token/思考过程/工具可视化/会话管理由 ❌🟡 改为 ✅；§4.2 事件清单：quality_feedback（已补 case）、node_started（已产出）、补充 reasoning/channel/step_id；§5 问题表：RAG Agent 节点（已存在 `workflow.py` rag_agent 节点）、deepAgents（`subagents.py` 已实际使用）、skills（技能管理已实现）；阶段 C-1/C-2 标注完成 |
| `CLAUDE.md` | 架构节补充四个核心模块（event_sourcing/prompt_section/seam/stream_protocol）与三个 feature flag 说明 |
| `README.md` / `docs/guide/architecture.md` / `docs/index.md` | 最小化补充事件溯源/能力接缝/分层提示词能力一句话说明 |

---

## 6. 2026-10-18 增量：思考流、计量与轮次（`8c91215`）

本轮把报告里「属于可观测性/体验层」的三个缺口一次补齐，全部有端到端实测证据。

### 6.1 思考流端到端（reasoning_content）

**事实链**（三段验证）：

| 环节 | 结论 |
|---|---|
| 上游 DashScope | `qwen3.7-flash` 流式**默认返回** `delta.reasoning_content`（直连实测 5268 字符，`enable_thinking=True` 亦同） |
| 适配层 | `langchain-openai 1.2.1` 的 `chat_models/base.py` 注释明确 `reasoning_content` / `reasoning_details` **不被提取** → 我们的 SSE 永远无 `reasoning` 事件 |
| 前端 | reducer（按 step 累加）与 `DeepThink` 渲染链路本就完整，只是没有数据 |

**修法**：`app/core/llm.py` 模块加载期 monkeypatch
`langchain_openai.chat_models.base._convert_delta_to_message_chunk`
（及非流式的 `_convert_dict_to_message`），把 `reasoning_content` 回填到
`chunk.additional_kwargs`；`sse_bridge._emit_messages` 已有读取逻辑直接生效。
用 `_reasoning_patched` 标记保证幂等，**必须在后端整进程重启后生效**。

**实测**：`reasoning` 事件 0 → 72（一轮）；前端「深度思考」卡字数 92→258→420 实时增长，
完成后自动折叠为「深度思考 · N 字 · N 轮」。

**配套**：
- 删除 legacy 占位状态「正在分析您的请求…」（`stream_harness` 与 deepagent 两处），
  保留的 `status` 只用于重试/超时/审批超时等真实状态。
- 思考碎片治理：落库合并连续 REASONING（见 §3.7.2 补充）+ 前端相邻片段合并。

### 6.2 计量契约（承接 §3.6）

`usage` 事件字段（扁平，协议只增）：

```
type, input_tokens, output_tokens, cached_tokens, uncached_input_tokens,
total_tokens, cache_hit_ratio, estimated, turns, steps,
context{ system_prompt, tool_defs, messages, window, used_pct }
```

- 窗口优先级：`provider.context_window` > `settings.CONTEXT_WINDOW` > `DEFAULT_CONTEXT_WINDOW(192000)`。
- 运行时改参：`PATCH /api/v1/config/llm/{provider_id}/runtime`
  `{ context_window?, reasoning_effort? }`（只改这两项，不回传 api_key）。
- 历史会话：`GET /api/v1/chat/sessions/{thread_id}` 返回 `usage`（现场估算，`estimated: true`）。
- 前端：`StatPopovers` 三弹窗；无数据时分母仍按当前配置显示（`— / 300.0K` 实测）。

### 6.3 轮次投影（供多轮切换）

- `_es_flush(..., node_index=node_index)` → `session_events.node_index` 有值；
- `derive_messages` 逐条补 `turn_index`；
- 前端 `TurnNavigator`（第 N/M 轮 + 下拉）与 `MessageList` 过滤；
- **兼容**：旧事件 `node_index=NULL` → 消息不带 `turn_index` → 导航条不出现、消息平铺。

### 6.4 本轮遗留

1. **上游额度**：2026-10-18 实测 `qwen3.7-flash` 返回 `403 Free quota exhausted`，
   真实对话回归被阻塞（参数正确性已由「无 400」间接验证）。额度恢复后需重跑
   §6.1/§6.2 的端到端断言。
2. **`reasoning_effort` 上游支持**：已按 `extra_body` 下发，但 DashScope 兼容模式是否接受
   需额度恢复后验证；不支持时保持空值（不下发）。
3. HITL 多进程约束未变（见 `docs/HANDOVER.md` §5.4）。

> 本节与 `docs/HANDOVER.md` §8 互为镜像：本文记录"缺口视角"的闭合，
> HANDOVER 记录"接手视角"的交付与运维注意。

---

## 附录：事实来源

| 来源 | 说明 |
|---|---|
| 【代码核实】 | 2026-10-10 逐文件核实，路径与行号见各表 |
| 【commit】 | `fef4974`（perf(stream) 阶段一）、`cefdca7`（refactor(stream) 阶段二）、`e3a7230`（chore(stream) 阶段三） |
| 基准文档 | `docs/archive/reference/deepseek-harness-integration-analysis.md` v1.0（2026-08-17） |
| 更名记录 | 2026-10-10 工作区改动：7 文档 Hermes→Harness（未提交，随后单独提交） |

## 声明

本报告基于上述第一手资料撰写，所有「已落地」结论均有代码级证据（文件:行号）；「差距项」均经反证核实（grep 零命中或标注部分属实）。报告不改代码；差距项的实施需另行立项并经方案确认。
