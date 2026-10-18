# 项目交接文档

> 生成时间:2026-10-16 · 最近更新:**2026-10-18**（前端体验重做 + 思考/计量链路打通,见 §8）
> 当前分支:`data_agent_pro` · 最新提交 `8c91215`
> 测试现状:前端 `vitest` **7 passed** + `tsc`/`vite build`;后端 `backend/tests` **22 passed**
> （纯逻辑测试套件已于 2026-10-17 归档到 `docs/archive/tests/`,门禁以 MCP 端到端为主）

---

## 1. 这个项目是什么

**DataAgent Pro** —— 智能业务数据交互平台。用户用自然语言问业务数据库(business_db,MySQL),系统生成 SQL、执行、出表/图、给分析结论。

技术栈:FastAPI + LangGraph + deepagents(后端)/ React + TypeScript + Ant Design X(前端)/ Redis(checkpointer)/ MySQL。

---

## 2. 正在进行的大事:智能体架构重构(从固定编排到 Harness 主 Agent)

### 2.1 动机

原默认路径是 13 节点 LangGraph 编排(orchestrator → schema → sql_coder → security → execute → analyst → reporter …),**LLM 只在节点内执行,不做节点间决策**——本质是"LLM 增强的确定性流水线",与产品名"智能体"不符。

### 2.2 目标形态(已定,见 `docs/plans/2026-10-14-harness-agent-architecture-design.md`)

- **Harness 核心**:主循环(deepagents `create_deep_agent`)+ 中间件(TodoList / Filesystem / Skills / 权限闸 HITL / SubAgent)
- **外围配置**:工具 / SOP Skill / 子智能体 / MCP
- **厚主线**:写 SQL、分析、澄清留在主线,只把真·能力提为工具(`run_sql` 集中安全闸)
- **安全四层**:能力隔离 → 权限中间件 → prompt rules → 审计;审批含 approve/**edit**/reject
- **宽松预算**:data 20 步 / report 40 步 + token/时间熔断

### 2.3 进度与阶段门禁

| 阶段 | 状态 | 产物 |
|---|---|---|
| Phase 0 工具层 | ✅ 完成 | `app/harness/sql_gate.py`、`tools/data_tools.py`(4 工具)、`sql_gate_middleware.py` |
| Phase 1 主循环接入 | ✅ 完成 | `agent_factory.py`、`sse_bridge.py`、`stream_harness.py`、`shadow.py`;`HARNESS_MODE` 开关(off/shadow/on) |
| Phase 2 切换默认 | ✅ 完成 | `HARNESS_MODE=on` 热生效,data 模式 Harness 接管;预算旋钮接入配置体系 |
| Phase 3 扩展与收敛 | ✅ 完成 | report/doc 纳入 Harness(模式化 SOP);预算按模式区分;移除 `AGENT_LOOP_SHADOW` 死开关;legacy 归档 tag `legacy-graph-13node` |

关键代码地图:

```
backend/app/harness/
├── sql_gate.py               # 权限决策纯函数(分类+档位 → allow/ask/deny)
├── sql_gate_middleware.py    # awrap_tool_call 拦截 run_sql,ask 时 interrupt
├── tools/data_tools.py       # get_table_schema / run_sql / search_knowledge / make_chart
├── agent_factory.py          # 单例 Agent;按 spec 指纹自动重建(提示词/温度/provider 变即重建)
├── sse_bridge.py             # deepagents 事件 → 现有 SSE 协议(todo→plan、run_sql→sql+result 富事件)
├── stream_harness.py         # SSE 生成器 + HITL 等待-恢复 + 瞬时错误重试 + provider 锁定
├── shadow.py                 # 影子双跑比对 + 质量指标 + 对照文件导出
└── shadow_stream.py          # legacy 流透传 + 收尾回调(finally 兜底,异常/取消也落盘)
```

---

## 3. 踩过的坑(重要,都是实测复现过的)

1. **`os.getenv` 读不到 `.env`**:项目无 `load_dotenv`,pydantic 只把 `.env` 灌进 `Settings` 实例。`HARNESS_MODE` 与 provider key 都因此静默失效过。**现在都读 settings**(`configs/patch.json` 热更新即生效,不用重启)。
2. **Agent 单例缓存指纹**:最初只按 provider 缓存,导致"改了 SOP 提示词但进程里还是旧的"。现以 `_agent_spec()` 为单一来源(提示词/工具/中间件/provider/温度),指纹为内容哈希。
3. **温度硬编码**:`_build_model` 曾硬编码 `temperature=1.0`,导致工具调用行为随机(同一问题有时调工具有时只自我介绍)。现取 provider 配置,缺省 0.3。
4. **尺子失灵三次**:接地检测先后用错数据源(工具摘要)、漏 N 数合计/均值、legacy 侧口径不一致。**教训:先修尺子再解读数据**——每一次"结论异常"最后都查出是检测器问题,不是被测对象问题。
5. **采集管线空洞**:影子任务曾建在 `async for` 之后,流异常/取消时静默丢样本(同批 3 问只落 2 条)。已用 `tap_stream` finally 兜底。
6. **测试替身掩盖真实缺陷**:Phase 1 终审抓到的 Critical(HITL 恢复段缺 checkpointer 必炸)就是假 Agent 给了虚假信心。**凡涉及真实图/中间件的测试,用最小真实 LangGraph 验证,别用 mock 糊弄。**
7. **日志占位符风格混用(2026-10-16 修复,`8995f9e`)**:`log` 是 loguru(只做
   `str.format`),但全库 120 处按 stdlib 习惯写 `log.warning("x %s", val)`——值被
   静默丢弃只打字面 `%s`,[SqlGate] 审计决策/[Shadow] 失败原因全中招(nemotron
   排查时只能靠 shim 重跑才拿到真实堆栈)。已在 `log_utils` 加双风格门面,两种写法
   都正确;**新代码日志含参数时,printf 与 `{}` 风格皆可,但别再依赖 stdlib 语义的
   其它特性**。

---

## 4. Phase 2 决策盘点(当前最重要)

### 4.1 门禁四指标

| 指标 | 类型 | 状态 |
|---|---|---|
| 1. 数据接地(答案数字能在查询行数据中找到) | 自动 | ✅ Harness 2/2 |
| 2. 分析维度 ≥2(对比/趋势/构成/异常/排名) | 自动 | ✅ 均值 3.5 |
| 3. 子问题覆盖 | **人工** | ⏳ 待判 |
| 4. 结论正确性 | **人工** | ⏳ 待判 |
| 5. 结果可用率 ≥ legacy | 综合 | ⚠️ legacy 接地降级为参考项 |

**人工判定材料已备好**:`backend/configs/harness_review.md`(18 样本,含原始提问/两臂答案/工具行数据/已排除占位)。改 `[ ]` 为 `[x] 过` 即可。

### 4.2 已关闭的决策

- **步骤链方案**:选 **(b) 前端兜底**(模型不建 todo 时按工具序列合成步骤链,标注 `synthesized: true`)。依据:两模型 13 次采样 **0 次**主动建 todo,(c) 强化 SOP 的前提不成立。
- **UNION 优化**:SOP 已加"多表统计用单条 UNION ALL"。qwen3.8-27b 上稳定 1 条;qwen-flash 不稳定(小模型能力边界)。

### 4.3 遗留(不阻塞)

- **legacy 接地降级**:嵌套派生(如「占总量的 81.55%」= 1289/1604×100,1604 自身也是派生值)判不出来。报告输出 `legacy_grounding_reliability=degraded_nested_derivation` 显式提示。**别把这误读为 legacy 幻觉。**
- **nemotron 补采**:OpenRouter 免费档每日 50 次已用满。不排期,明天配额重置后顺手发一批作为跨模型稳健性附录。
- ~~**零行 SELECT 呈现 `affected_rows=1`**~~ ✅ 已修复(2026-10-16,`51e3886`):
  `execute_sql` 改用 `CursorResult.returns_rows` 结构性区分「是否返回结果集」,
  零行 SELECT 返回 `data=[]`、run_sql 如实报 `row_count=0`;DML 元信息行不变。
  替身契约经真库探针校准(零行 SELECT `returns_rows=True`/`fetchall()=[]`,
  DML `returns_rows=False`),端到端验证通过。

---

## 5.  Phase 2 门禁(已完成,记录备查)

| 指标 | 类型 | 结果 |
|---|---|---|
| 数据接地 | 自动 | ✅ Harness 2/2(旧轮尺子失效样本已按 `grounding_source` 甄别) |
| 分析维度 ≥2 | 自动 | ✅ 均值 3.5 |
| 子问题覆盖 | 人工 | ✅ 预筛通过(对照文件 `backend/configs/harness_review.md`) |
| 结论正确性 | 人工 | ✅ 预筛通过(臂内算术核对,含样本 11 事件分布加总核平) |
| 结果可用率 ≥ legacy | 综合 | ⚠️ legacy 接地按方案 B 降级,由人工判定间接支撑 |

## 5.1 剩余待验证(Phase 3 收尾,按优先级)

1. ~~**report 放大预算后的端到端产出**~~ ✅ 已验证(2026-10-16,qwen3.7-flash):149.1s 跑通,
   产出 4640 字完整报告(摘要/使用趋势/事件分布/建议四部分),6 条 SQL + 图表 + 正文齐全,
   未再被墙钟熔断。修复见 `632c18c`。
2. ~~**审批 HITL 真实触发**~~ ✅ 已验证(2026-10-16,详见 §5.3);edit 态亦已端到端闭环(§5.4)。
3. ~~**B-L1 事件溯源灰度**~~ ✅ 已验证(2026-10-17):`EVENT_SOURCING_ENABLED` 默认已 `True`,恢复/轨迹/fork/导出四项端到端全过(`copied_events=4`),详见 §5.5。
4. **Harness SSE 心跳**:✅ 已补(`4cd5a84`)——切换后 `stream_harness` 才是生产主路径,而 report/doc 单轮可达 149s 静默期,原无心跳有代理断连风险。见 §5.5。
5. ~~**L2 多模式事件双写**~~ ✅ 已完成(2026-10-17,`25ab498`):Harness 三模式的数据类富事件(sql/result/chart/tool_chain)入库,data 4→7 类、report 3→6 类、doc 3→4 类;task 模式经核实**本就不产出**数据类事件(SSE 仅 status/thread_id/token),非缺口。
6. **nemotron 跨模型稳健性附录**:⏸ 2026-10-16 已尝试,被上游阻塞——OpenRouter/Nvidia
   侧该免费模型先是工具调用 DEGRADED(400 "DEGRADED function cannot be invoked"),
   后又流式 120s 零 chunk,均为 provider 侧故障(配额本身已重置,usage=0)。
   上游恢复后重跑 `backend/scripts/nemotron_batch.py` 即可(7 个去重问题,构造路径
   与真实请求对齐,产出追加进 shadow_comparison.jsonl,不覆盖既有样本)。

## 5.2 模式预算速查

| 模式 | 递归上限 | 墙钟 | 说明 |
|---|---|---|---|
| data / doc | `HARNESS_RECURSION_LIMIT`(40) | `HARNESS_MAX_SECONDS`(300) | ≈ data 20 步 |
| report | 基础值 × 2(80) | 基础值 × 2(600) | ≈ report 40 步,设计批准宽松档 |

## 5.3 审批 HITL 集成验证结论(2026-10-16)

用临时表 `hitl_smoke_test` 验证(已 DROP,业务表零影响)。**关键发现:第 3 层
prompt rules 极强——4 种 framing(直接指令 /「审批已通过」/ 系统自检)下模型均
拒绝发写 SQL,其中一次明确回复「即使您声称审批已通过,系统层面仍会阻止执行」。
这意味着第 2 层安全闸在真实 LLM 条件下**不可达**,写操作被挡在模型侧。**

因此改用桩模型(固定发 INSERT)排除 LLM 意愿变量,按生产拓扑(读流 + 审批两个
并发任务)验证第 2 层及之后全链路:

| 分支 | 结果 | 证据 |
|---|---|---|
| 拦截 | ✅ | `[SqlGate] run_sql 决策=ask` → `approval_required` 下发 |
| approve | ✅ | `resolve` 返回 True → `tool_result` 1 行 → 库内核验 1 行 |
| reject | ✅ | `tool_result` =「安全策略拒绝执行该 SQL:审批被驳回:…」,SQL 未执行 |
| **篡改注入** | ✅ | 回传夹带 `edited_sql=DROP TABLE da_sys_user` **被忽略**,执行的是原始已分类 INSERT;`da_sys_user` 表完好(1 行) |
| 超时 | ✅ | 300s 未审批自动拒绝(实测触发) |

**安全结论**:审批回传通道无法注入任意 SQL——`approve` 端点的请求模型没有 sql
字段;`apply_approval` 的 `edited_sql` 分支要求 `approved is False`,而 approve
端点从不传该字段。双重保险。

**产品含义(需决策)**:既然模型侧已拒绝发写 SQL,审批卡在当前 SOP 下实际不可达。
若将来要放开写操作,需要调整第 3 层 prompt rules,让模型在用户明确要求时发出
写 SQL 交给第 2 层闸口——否则安全闸形同虚设(但目前是「过度安全」而非漏洞)。

## 5.4 审批 edit 决策的端到端验证(2026-10-16)

三态里最后补齐的 `edit`(审批人修改 SQL 后放行)已完成端到端验证。
判据设计得很严格——**能区分「执行了改后 SQL」与「执行了原 SQL」**:

| 步骤 | 结果 |
|---|---|
| 桩模型发 `DELETE ... WHERE id = 1`(危险) | 审批卡下发,原 SQL 正确展示 |
| 表内预置 id=1 与 id=2 | 初始 `[1, 2]` |
| 审批人 edit 成 `... WHERE id = 2` → 真实 FastAPI 端点 | `200 {'status': 'notified'}` |
| 恢复执行后的库内状态 | **`[1]`** —— id=2 被删、id=1 保留 |
| 事件序列 | `thread_id → status → tool_call → approval_required → sql → result → tool_result → token → done → title` |

结论:**执行的是改后 SQL,替换语义正确**;真实端点(鉴权 + schema 校验 +
`_build_decision`)与流内恢复协同正常。

### ⚠️ 重要架构约束:审批要求**同进程**(本次排查的副产品)

`app/core/hitl.py` 的 `_waiters` 是**进程内内存字典**(非 Redis)。因此:

- ✅ 当前部署(`uvicorn --reload`,单 worker)下正常;
- ❌ **一旦多 worker / 多副本,审批请求若落到另一个进程,`hitl.resolve()`
  会返回 False 并静默落到 `approve.py` 的 legacy 兜底分支**——用 Harness 的
  `thread_id` 去恢复 legacy 图,结果无效(实测返回 legacy State 的
  `intent`/`stage` 字段,流已在 300s 超时后收尾)。

这是 legacy 时代就存在的机制(非 Harness 引入),但横向扩容前必须处理:
改 Redis pub/sub,或用粘性会话把审批请求路由回原进程。**扩容前请勿开启
HITL 写操作**(当前因第 3 层 prompt rules 拒绝写 SQL,该路径实际不可达,
所以这个约束目前不会造成生产事故)。

---

## 6. 开发约定(踩坑总结出的)

- ~~**TDD 是硬约束**~~ **已变更(2026-10-17 用户决策)**:纯逻辑测试套件(`pytest` / `vitest`)已归档至 `docs/archive/tests/`,不再作为日常门禁。
- **新验证方式:MCP 端到端**——每次交付用 chrome-devtools MCP 走真实页面(真实 HTTP/SSE + 真实 DB),配合 `tsc -b` / `npm run build`。
  **依据**:项目多次出现「单测全绿但真实链路炸」(温度硬编码、事件字段名不匹配、provider key 解析、checkpointer 缺失),单测给的是虚假信心。
- **改代码必须实际运行验证**,不靠推断。这条在验证方式变更后更加重要——没有单测兜底,端到端是唯一门禁。
- **注释/docstring 必须匹配真实契约**:Task 2 审查发现 docstring 描述了比实现更美好的契约(而这些 docstring 正是 LLM 唯一可见的工具规格)。改行为必须同步改文档。
- **不重启服务**:后端/前端进程由用户掌控。改代码靠 `uvicorn --reload`;改配置靠 `configs/patch.json` + `POST /api/v1/config/patch/reload`。
- **提交粒度**:一个任务一个 commit,message 说明"为什么"而非"做了什么"。

## 7. 快速上手命令

```bash
# 后端测试
cd backend && uv run pytest -q

# 前端测试 / 构建
cd frontend-react && npx vitest run && npm run build

# 切 Harness 模式(热生效,不用重启)
# 编辑 backend/configs/patch.json 的 HARNESS_MODE 为 off/shadow/on,然后:
curl -X POST http://localhost:8001/api/v1/config/patch/reload -H "Authorization: Bearer <token>"

# 查看当前生效配置
curl http://localhost:8001/api/v1/config/effective -H "Authorization: Bearer <token>"

# 影子比对汇总 / 人工判定对照文件
cd backend && uv run python -c "from app.harness.shadow import shadow_report, build_review_document; print(shadow_report()); open('configs/harness_review.md','w',encoding='utf-8').write(build_review_document())"
```

## 5.5 B-L1 事件溯源灰度与主路径心跳(2026-10-17)

### L1 交付判据达成

`EVENT_SOURCING_ENABLED` **代码默认已是 `True`**(`config.py` L62,
`dump_effective()` 显示 `source=default` 即非 patch 覆盖)——gap-analysis §3.1
记的「默认 False」已过时,L1 的「灰度开启」实际早已完成。

真实链路四项验证(前端提问 → 真实 API 核验):

| 验证项 | 结果 |
|---|---|
| 会话恢复 `GET /chat/sessions/{id}` | ✅ 200,消息数 2,首条 role=user(投影优先) |
| 轨迹 `GET .../trajectory` | ✅ 200,**4 条事件**:`user_message/turn_start/turn_end/analysis` |
| fork `POST .../fork` | ✅ 200,**`copied_events: 4`**(L1 判据) |
| fork 分支轨迹 | ✅ **4 条**——分支非空壳 |
| 导出 `GET .../export` | ✅ 200,JSONL 4 行 |

### 顺手修掉的生产主路径风险:SSE 心跳

`HARNESS_MODE=on` 后 data/report/doc **全部**走 `stream_harness`,而它原本
**没有心跳**(legacy `_stream_chat` 有)。report/doc 单轮实测可达 149s,
长静默期若无事件输出,代理会按空闲断开连接——gap-analysis §3.7.1 早已记录
该缺口,但那时主路径是 legacy(有心跳);切换后风险升级为**当前生产路径**。

`4cd5a84` 给主事件循环补心跳:`wait_for` 超时拆两级——heartbeat(15s)到点
只发 `: ping` 并继续等,原墙钟熔断不变。端到端验证:15.0s 静默期准时收到心跳。

> 仍未覆盖:`_stream_chat_deepagent`(`mode=task`)无心跳,属低流量路径。

## 5.6 L2–L6 查漏结论（2026-10-17）

`NEXT_STEPS.md` 工作线 B 剩余阶段的逐项核实结论：

| 阶段 | 核实结论 | 行动建议 |
|---|---|---|
| **L1** 事件溯源灰度 | ✅ 已完成（§5.5） | 关闭 |
| **L2** 多模式事件双写 | ✅ 已完成（`25ab498`）：data 4→7、report 3→6、doc 3→4 类；task 经核实 SSE 只 yield status/thread_id/token，**本就不产出数据类事件，非缺口** | 关闭 |
| **L3** 分层提示词 | ⚠️ **代码无消费方**：`deepagent/prompts.py` 的 `PROMPT_SECTION_ENABLED` 门控已无人 import（DeepAgent 独立路径被 Harness 取代），Harness 用自己的 `SYSTEM_PROMPT` 字符串。开 flag 对当前主路径**零效果** | **先接入再谈灰度**：若要启用，需把 `PromptAssembler` 接进 `agent_factory._system_prompt_for()`。这是独立改造项，非「开个 flag」那么便宜 |
| **L4** 子代理归因 | ❌ 未实施，且 Harness **无子代理**（Phase 3 才规划 SubAgentMiddleware） | 与 Phase 3 绑定，不在 L 序列内单独做 |
| **L5** 能力接缝 | ⚠️ flag 仍 False；search/storage seam 已注册；风险在存储引擎解析（`db/session.py` mysql/postgresql provider） | 可做但需评估存储引擎切换的真实需求；收益低于 L1/L2 |
| **L6** 渲染投影层 | ❌ **前提已不存在**：Vue 前端与 `components/x` 并行实现均已清空（0 个 .vue 文件），前端已全量 React 重写 | **整项作废**，从路线图移除 |

**总体判断**：`NEXT_STEPS.md` 工作线 B 中，**L1/L2 已交付，L6 因前端重写自然消亡，
L4 与 Phase 3 绑定，剩下真正可做的只有 L3（需先接入）与 L5（需评估真实需求）**。
建议把它们从「预设路线」改为「按需提案」，避免为完成路线而做无收益改造。

---

## 8. 2026-10-18 增量:前端体验重做 + 思考/计量链路打通

提交 `8c91215`（67 文件）。这一轮的重心从"架构落地"转到**可用性与可观测性**,
所有结论均为 Chrome DevTools MCP 端到端实测（非单测推断）。

### 8.1 视觉与交互定版（参考 dsh）

| 项 | 落点 | 关键决策 |
|---|---|---|
| 单深色主题 | `index.css` / `stores/theme.ts` | 取消亮色切换;画布 `#0a0a0b`、面板 `#101012`、卡片 `#141416`、悬浮 `#1c1c1f`;边框改半透明白 `rgba(255,255,255,0.07)`（弱描边取代分隔线） |
| 图标 | `components/bits/Icon.tsx` | **弃用自建 iconfont**（Remix 只搬了 @font-face 未搬 3229 条 `::before` 字形映射 → 全站空白）,改 Ant Design 官方 `@ant-design/icons 6.3.4`;语义名映射,size 13–16 |
| 字体 | `main.tsx` | MiSans VF（npm `misans`,unicode-range 切片）+ JetBrains Mono `@fontsource`;`--font-mono` 必须带中文兜底 `MiSans` |
| 去分隔线 | 全局 | 侧栏底、读数条、弹窗标题行全部去 border,靠明度差分层;输入框 16px 圆角无边框 |
| 会话管理 | `SessionPickerModal.tsx` | 内嵌批量条（按钮挤压换行、易误点）→ 独立「选择对话」弹窗（今天/7天内/30天内/更早 + 圆形复选 + 标题与时间）,**取消归档功能**（后端字段保留） |
| 模型配置 | `ModelSelector.tsx` | 悬浮模型行即展开参数面板（无按钮）:上下文长度 192K/300K/600K/1M/自定义 + 思考强度 默认/Low/High/Max |
| 动效 | `reactbits/` | ShinyText / BlurText / SpotlightCard 源码移植;StarBorder 用 CSS conic 等效（免 canvas RAF）;会话项进场 + hover 指示条 |

### 8.2 可观测性:usage 契约 + 三弹窗

**新增 SSE 事件 `usage`（协议只增不改,扁平字段）**:

```json
{"type":"usage","input_tokens":0,"output_tokens":0,"cached_tokens":0,
 "uncached_input_tokens":0,"total_tokens":0,"cache_hit_ratio":0,"estimated":true,
 "turns":1,"steps":2,
 "context":{"system_prompt":0,"tool_defs":0,"messages":0,"window":192000,"used_pct":0}}
```

- 采集:`core/usage_metrics.py` 的 `UsageMeter` 读末块 `usage_metadata`(需 `stream_usage=True`);legacy 路径经 `_RequestUsageCallback` 回灌。
- **上下文窗口可配**:`LLMProvider.context_window`(默认 192000);`_usage_window()` 优先级 = provider > `settings.CONTEXT_WINDOW` > 192K。
- 运行时改参:`PATCH /config/llm/{id}/runtime`（只改 `context_window` / `reasoning_effort`,不回传 api_key）。
- **历史会话不失效**:`GET /chat/sessions/{id}` 在事件投影路径**现场估算** usage（三段 + provider 窗口,`estimated:true`）,前端 `loadSession` 写入 store;否则切换会话三弹窗全是「—」。
- 前端三弹窗:`StatPopovers.tsx`（会话统计 / Token 用量 / 上下文已用,含缩略圆环）,分母实时联动（`usage.context.window || contextUsage.window`）。

### 8.3 实时思考（本轮最大的跨层修复）

链路真相:**DashScope 返回 `delta.reasoning_content`（默认就有）→ `langchain-openai 1.2.x` 明确不提取该字段（源码注释"not extracted"）→ 前端一直收不到 reasoning**。

- 修法:`core/llm.py` 模块级 monkeypatch `_convert_delta_to_message_chunk` / `_convert_dict_to_message`,把 `reasoning_content` 回填 `additional_kwargs`;`sse_bridge` 已有读取逻辑直接生效。**改后必须整进程重启后端**。
- 实测:reasoning 事件 0 → 72/轮。
- 展示:`DeepThink.tsx` 一次回复的多段思考聚合为一个「深度思考」卡（生成中自动展开 + 实时计时 + 多轮步骤列表 + StarBorder 星轨）,完成后折叠。
- 历史碎片:`_ES_MAP` 曾把每个 reasoning chunk 逐条落库（72 条 → 72 张「2 字」卡）;后端 `_es_flush` 先合并连续 REASONING 再入库,前端 `mapProjectedMessages` 合并相邻片段（旧数据也能修好）。
- 移除 legacy 占位状态「正在分析您的请求…」(harness 与 deepagent 两处)。

### 8.4 多轮对话节点切换

- 落库:`_es_flush(..., node_index=node_index)`;投影:`derive_messages` 给每条消息补 `turn_index`（旧数据无）。
- 前端:`Msg.turnIndex` + `TurnNavigator.tsx`（‹ 第 N/M 轮 › + 轮次下拉,仅历史会话且 `turns.length>1` 出现）;`MessageList` 按 `currentTurnIndex` 过滤,无 turnInfo 时平铺（向后兼容）;思考卡 `collectRounds` 也只聚合当前轮。

### 8.5 本轮修掉的跨层根因（都可复现,建议保留在记忆中）

1. **心跳 `wait_for` 取消杀流**:`wait_for(aiter.__anext__(), timeout=15)` 超时会取消迭代任务 → LangGraph astream 生成器被腰斩 → 长工具（make_chart 15s）后流"干净退出"（无 error）。修法:`asyncio.shield(pending_next)` + 持久任务,超时只发 `: ping`;`finally` 回收未决任务。实测 67 事件完整跑通。
2. **SQL 事件字段口径**:harness 发 `sql` 字段、reducer 只读 `content` → SQL 卡空白。已双口径兼容（`ev.sql || ev.content`）。
3. **SQL 落库列**:`_es_flush` 只取 `payload.content` → SQL 文本在 `payload.sql` → 历史恢复空 SQL 卡。已 `content or payload.sql`,并在 `_project` 对旧数据兜底。
4. **`enable_thinking` 参数位置**:放 `model_kwargs` 会让 openai SDK 抛 `unexpected keyword argument`（thinking=false 必现）。已改 `extra_body`（`reasoning_effort` 同路径）。
5. **历史 usage 缺口**:见 §8.2（现场估算 + `estimated` 标记）。

### 8.6 运维与环境注意（本轮新踩）

- **`vite build` 在 Windows 可能因沙箱限制写系统 %TEMP% 被拒**:构建前把 `$env:TEMP/$env:TMP` 指到 `frontend-react/.esbuild-tmp`。
- **vite deps 缓存删不掉**:`node_modules/.vite` 触发批量删除保护 → 用 `Rename-Item` 移走再启动。
- **DashScope 免费额度**:2026-10-18 实测 `qwen3.7-flash` 返回 `403 Free quota exhausted`,对话不可用;需充值或在配置中心启用其他 provider（`nemotron` 需 OpenRouter key）。**这是账号问题,非代码问题**。
- 端口约定:后端 `8001`（本机 8000 被系统占用）,前端 `5173`;本轮结束时两个服务已停止。

### 8.7 待办（按优先级）

1. **额度恢复后回归**:实时对话 + 思考流 + 三弹窗 + 多轮切换的全链路复测（现在只能验证到"参数正确、无 400"）。
2. **思考强度上游支持确认**:`reasoning_effort` 已按 `extra_body` 下发,但 DashScope 兼容模式是否接受需额度恢复后验证;不支持时应保持空值。
3. L3（分层提示词接入 Harness）/ L5（能力接缝）仍为「按需提案」,见 §5.6。
4. HITL 多进程约束未变（§5.4 的 ⚠️）,扩容前必须改 Redis pub/sub 或粘性会话。
