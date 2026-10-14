# 智能体架构重构设计:从固定编排到 Harness 主 Agent

- 日期:2026-10-14
- 状态:已评审,待实现
- 关联:`docs/reference/chat-ui-playground-alignment.md`(前端对话界面规范)

## 1. 背景与诊断

### 1.1 现状:默认路径是固定编排,不是智能体

对三条执行路径的代码级核查结论:

1. **data/report/doc 模式走 `app/graph/workflow.py` 的 13 节点图**。所有边在编译期焊死
   (`_build_data_graph` / `_compile_data_edges`),路由函数(`route_schema` / `route_security` /
   `route_quality_gate` …)全是确定性 if/else——判断依据是 `error_message` 字符串与状态标志,
   **没有任何 LLM 参与"下一步去哪"的决策**。
2. **"Plan-and-Execute" 名不副实**:`clarify_plan` 让 LLM 生成 `plan_steps`
   (`orchestrator.py:522`),但图执行时不读它——只用于前端步骤链展示,执行顺序是写死的。
3. **全链路唯一的真实循环**是 `execute_node` 内的 SQL 自纠错(`max_retries=2`),
   是节点内循环,不是"观察-反思-重规划"的智能体循环。QualityGate 虽名 ReAct,
   实际是在两个预先焊死的目的地之间做一次 LLM 选择题。
4. **已存在但未启用的真智能体**:`app/deepagent/`(deepagents 库:TodoList + Filesystem +
   SubAgent + Skills + MCP),`USE_DEEP_AGENT` 默认 false,只有 `mode=task` 走它。
   于是同一产品有三套执行语义:legacy 流水线、DeepAgent 智能体、
   `agent_loop.py` 影子驱动器(骨架)。**双轨维护是当前最贵的架构成本。**

### 1.2 但"是流水线"不必然是错

对当前产品形态(只读数据库 + 安全白名单 + 审批闸 + 步骤链流式 UX),固定流水线有真实优势:
可预测(LLM 调用次数有界,读数条敢展示耗时)、可审计(高危 SQL 必经 security 节点)、
UX 与固定步骤绑定。

**因此本次重构的目标不是"把流水线拆了显得智能",而是**:在保留可预测性资产
(安全闸、审批、流式、读数)的前提下,把 LLM 的决策权从"节点内执行"扩大到"节点间编排",
对齐 DeepSeek Harness / WorkBuddy / Cursor 的主流形态——**Harness 核心引擎 + 外围配置**。

## 2. 目标架构

```
┌─────────────────────────────────────────────────────────────┐
│ Harness 核心(引擎,不随业务变化)                                │
│  ├─ 主循环(langchain create_agent / deepagents)               │
│  │    推理 → 工具调用 → 观察 → 反思,直到任务完成或预算耗尽        │
│  ├─ TodoList 中间件     动态计划(替代"先定 plan 再执行")         │
│  ├─ Filesystem 中间件   中间结果/上轮数据持久化                   │
│  │                      (替代 _cached_query_result hack)        │
│  ├─ Skills 中间件       渐进式披露 SOP(替代 quality_gate 节点)   │
│  ├─ 权限中间件 + HITL   工具调用拦截(替代 security 节点)          │
│  └─ SubAgent 中间件     重型任务隔离上下文                       │
├─────────────────────────────────────────────────────────────┤
│ 外围配置(业务全在这一层,可增删,配置中心可管)                      │
│  ├─ 工具(能力)   get_table_schema / run_sql / search_knowledge │
│  │               / make_chart / export / notify                │
│  ├─ Skills(SOP) 数据分析 SOP / 图表选择 SOP / 指标口径 SOP       │
│  ├─ 子智能体     深度研究报告 / 文档智读                         │
│  └─ MCP          配置中心已接入的 server 直接挂载                 │
└─────────────────────────────────────────────────────────────┘
```

### 2.1 节点映射(厚主线)

| 现有节点 | 目标角色 | 理由 |
|---|---|---|
| clarify_plan | 主循环 + TodoList | 计划动态生成,不再"先计划后执行" |
| sql_coder | **主循环自身** | 写 SQL 是模型的文本输出,不是能力 |
| analyst | 主循环自身 | 分析是模型强项 |
| misc_agent | 主循环自身 | 闲聊直接答 |
| schema_agent | 工具 `get_table_schema` | 真·只读能力 |
| execute_sql | 工具 `run_sql`(含自纠错) | **唯一持库能力的工具,安全闸口集中于它** |
| security | **权限中间件** + HITL + tier + prompt rules | 结构性安全,不依赖 Agent 自觉 |
| quality_gate | Skill(分析 SOP 的自检步骤) | 从节点降级为过程规范 |
| reporter | 工具 `make_chart` | ECharts option 生成保留确定性 |
| rag_agent | 工具 `search_knowledge` | 能力 |
| chart_direct / answer / finish | 消失 | 上轮数据走 Filesystem;主循环自然终止 |

主线只做编排决策,模型分内的事(写 SQL、分析、闲聊、澄清、决定下一步)全部留在主线。

### 2.2 工具清单(Phase 0 蓝图)

```python
get_table_schema(keywords: str = "") -> str
    # 只读。内部复用 schema_agent.filter_relevant_tables + get_table_schemas

run_sql(sql: str, purpose: str) -> {rows, columns, row_count, duration_ms, sql}
    # 唯一持库能力。权限中间件闸口(见 §3);执行含轻量自纠错(语法类错误,
    # 复用 generate_and_execute_sql 的重试循环,最多 2 次);
    # 语义类改写 SQL 由模型观察到错误后自主完成

search_knowledge(query: str) -> str
    # 内部复用 rag_agent.answer_with_rag

make_chart(question: str, rows: list, columns: list, chart_type: str = "") -> {chart_config}
    # 内部复用 reporter.generate_chart_config,确定性产出 ECharts option

export_report(title: str, content: str, format: str) -> {file_url}
    # 复用现有导出端点逻辑

send_notification(...) -> str
    # 复用企业微信 skill executor(已有)
```

> Phase 0 已完成:上述工具与安全闸已落地并通过 96 项后端测试(见
> docs/plans/2026-10-14-harness-phase0-tools.md),尚未挂载到任何 Agent。
> 实现期修正两处设计表述(均以真实契约为准):① `run_sql` 不做 LLM 自纠错,
> 纠错责任交还主线模型(工具只返回结构化错误);② 工具失败语义为
> "业务失败 JSON 返回 / 基础设施异常上抛由 R9 兜底",挂载必须启用 R9。

所有工具统一过 `app/core/tool_pipeline.py`(R9:审计日志/超时/耗时埋点/结果截断/异常兜底)。

## 3. 安全模型(四层,全部结构性保证)

```
第 1 层 能力隔离(硬保证)
  主 Agent 工具箱只有上述受控工具——没有 shell、没有裸 DB 连接。
  "执行 SQL"只存在于 run_sql 一个入口,模型无法绕开。

第 2 层 权限中间件(闸口,替代 security 节点)
  awrap_tool_call 拦截 run_sql → 复用 security.classify_sql
  (只读白名单 + deny-by-default,多语句逐条判定)→ tier 策略:
     read_only       → 全部 ask
     workspace_write → 只读 auto-allow,DML ask
     full_access     → 全 auto-allow
  ask → interrupt() → 对话内审批卡 → Command(resume):
     approve  放行
     edit     审批人修改 SQL 后再放行(新增能力)
     reject   拒绝 → 返回 ToolMessage 说明原因 → 模型自主降级
     (如"当前账号只有只读权限,我可以帮你查询…")
  deny → 直接返回 ToolMessage 拒绝原因,模型换路

第 3 层 prompt rules(软防线)
  只读优先 / 禁止 DDL / 禁止多语句 / 禁止猜测表名(先调 get_table_schema)

第 4 层 审计
  所有工具调用过 R9 tool_pipeline
```

**相比现状的两个实质改进**:① 拒绝后模型自主适应,而不是 finish 终止对话;
② `edit` 决策(审批人改 SQL 再放行)。

**保留资产**:`classify_sql`、`approval_policy`(tier 三档)、R9 流水线、
前端审批卡、非 admin 不可自审校验。

**HITL 实现选型**:优先 `langchain.agents.middleware.HumanInTheLoopMiddleware`
(随 deepagents 引入,`interrupt_on={"run_sql": InterruptOnConfig(allowed_decisions=
["approve","edit","reject"], description=...)}`,与 Cursor/Claude Code 的 command
审批同款);若其 description/参数展示不满足需求,退回自写 `awrap_tool_call`
中间件调 `interrupt()`(同一 langgraph 原语,已在 security 节点验证过)。

## 4. 流式与 UX(SSE 协议零改动)

智能体循环事件全部落进现有 18 类 SSE 事件,**协议只增不改**:

| Agent 事件 | SSE 事件(已有) | 前端渲染 |
|---|---|---|
| TodoList 创建/更新 | `plan` | ThoughtChain 骨架(动态 todo) |
| 模型正文流 | `token(channel=answer)` | ai 气泡流式 |
| 模型写的 SQL 代码块 | `token(channel=sql)` | SQL 流式卡片 |
| reasoning 增量 | `reasoning` | 思考卡(Think 组件) |
| 工具调用 | `tool_call` / `tool_result` | 工具卡(执行中→完成) |
| run_sql 返回 rows | `tool_result`(带 query_result) | 结果表格 + SQL 定稿 |
| make_chart 返回 option | `tool_result`(带 chart_config) | 图表 |
| 子智能体委派 | `subagent` | 子智能体节点卡 |
| interrupt | `approval_required` | 审批卡 |
| 模型反问 | `clarification` | 追问卡 |

### 4.1 步骤链与思考过程展示

一个 ai 气泡内三层(官方"先思考、后回答"结构):

```
Bubble(ai)
├─ Think          ← reasoning 流(ReasoningCard,已落地官方 2.9.0 API)
│   流式中: loading + blink(打字动画)+ title="思考中",默认展开
│   完成后: title="思考过程 · N 字",受控 expanded 交还用户(2s 自动折叠语义保留)
├─ ThoughtChain   ← TodoList 骨架
│   └─ 每个 todo item 一个步骤块(未开始灰点/进行中紫点脉冲/完成绿点,
│      "运行中展开、完成 2s 自动折叠、用户点击优先"语义保留),
│      块内按时间线平铺工具卡与中间消息
└─ XMarkdown      ← 正式回答(流式)
```

没有 todo 的简单闲聊 → 直接气泡,不出步骤链。读数条新增"**本次 N 次模型往返**",
让智能体模式的成本形态对用户可见。

### 4.2 多轮与取消

`thread_id` 复用不变(checkpointer 持久化 messages);`/cancel` 取消 astream 任务,
端点保留。"换一种图表"类追问由模型从历史(含 Filesystem 中的上轮结果)自主获取数据,
不再需要 chart_direct 快捷路径。

### 4.3 前端改动范围

仅 `stores/chat.ts` 的步骤分组数据源:从"node_started 的 step_id"改为
"todo item + 工具调用序列";`plan`/`tool`/`subagent`/`clarification` 消息 kind 均已存在。

## 5. 预算与降级(安全带)

```
三层熔断(配置中心可调):
  步数预算   max_steps: data 20 / report 40(宽松档,能力优先)
             达到后系统注入"请基于已获取的信息总结回答",强制收尾
  Token 预算  SummarizationMiddleware 自动压缩;上下文超 60% 触发
  时间预算    整体 5 分钟熔断;单工具 30s 超时(R9 已有)

降级路径:
  run_sql 连续失败 → 工具返回结构化错误 → 模型自主换问法
  预算耗尽         → 强制总结 + quality_feedback 事件告知用户
  模型异常         → error 事件 + 前端重试卡(已有)
  审批超时 5 分钟  → 自动拒绝(已有)
```

## 6. 迁移路径(四阶段渐进,每阶段独立 commit 与门禁)

### Phase 0 工具层落地(不动主线)
- 实现 §2.2 工具(内部复用现有 agents 逻辑),全过 R9 流水线
- 门禁:pytest 52 全绿 + 工具单测(权限闸/tier/审批中断)+ 前端 build

### Phase 1 新主线上线(影子模式)
- Harness 主循环接入,与 legacy 对同一请求双跑,只记录差异不影响返回
  (复用 `AGENT_LOOP_SHADOW` 基建);产出比对报告:真实问题集的产出差异 /
  往返次数 / 耗时 / token
- 门禁:比对报告中"结果可用率" ≥ legacy,无 P0 级差异

### Phase 2 切换默认
- agent 成为 data 模式默认,legacy 降级为 fallback(配置中心开关)
- 门禁:chrome-devtools 全链路走查(对话/查询/审批 HITL/图表/历史会话)+
  读数对比 + 无 console 错误

### Phase 3 收敛与归档
- report/doc  agent 化(工作流简单,预期被主线+工具直接吸收)
- legacy 13 节点图打 tag 归档(不删);移除 `USE_DEEP_AGENT` / `AGENT_LOOP_*`
  历史开关,单一架构
- 门禁:回归通过 + 文档同步(架构文档/启动说明)

### 资产存续

| 现存资产 | 去向 |
|---|---|
| `agents/*.py` | 全保留——工具内部实现或 prompt 模板 |
| `core/tool_pipeline.py` | 工具统一入口,原样 |
| `core/approval_policy.py` | 权限中间件直接调用 |
| `graph/redis_saver.py` | 主循环 thread_id 持久化,原样 |
| `skills/`、`mcp_client` | 直接挂载 |
| 前端 `stores/chat.ts` | 分组逻辑小改,其余不动 |
| `graph/workflow.py`、orchestrator 路由、`agent_loop.py` | Phase 3 归档 |

## 7. 风险与未决

| 风险 | 缓解 |
|---|---|
| 宽松预算下最坏 20 步,延迟/token 显著上升 | 前端停止按钮随时中断;读数条暴露往返次数;按 mode 可收紧 |
| 弱模型(如 glm-4.5-air)在 agent 循环中表现差 | 配置中心提示"agent 模式建议强模型";弱模型自动收紧 max_steps(实现期定策略) |
| 影子双跑 = 2x LLM 成本 | 仅小流量/白名单期开启,Phase 2 关闭 |
| 现有 52 个 pytest 绑在 legacy 图上 | Phase 0 不动图;Phase 1 起补 agent 链路测试 |
| edit 决策的前端交互(审批卡内 SQL 编辑器) | 实现期设计,先 approve/reject 全功能,edit 可随 Phase 2 上线 |

## 8. 验收标准(重构完成定义)

1. data/report/doc 三模式单一执行路径,无 legacy/DeepAgent 双轨;
2. 安全四层全部结构性生效(工具无旁路、tier 生效、审批卡含 edit、审计完整);
3. SSE 协议对前端零破坏,步骤链/思考卡/审批卡/图表/表格全链路可用;
4. 预算熔断可观测(往返次数、耗时、超限收尾均有读数与事件);
5. 真实问题集上"结果可用率"不低于 legacy 基线(Phase 1 比对报告为准)。
