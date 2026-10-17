# 项目交接文档

> 生成时间:2026-10-16 · 面向接手后续任务的智能体/开发者
> 当前分支:`data_agent_pro` · 后端测试 **218 passed** · 前端 **38 passed**

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
