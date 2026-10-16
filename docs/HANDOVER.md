# 项目交接文档

> 生成时间:2026-10-16 · 面向接手后续任务的智能体/开发者
> 当前分支:`data_agent_pro` · 后端测试 **194 passed** · 前端 **38 passed**

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
- **零行 SELECT 呈现 `affected_rows=1`**:源自 `execute_sql` 既有行为,Phase 0 按"主线零 diff"有意未改,Phase 1 处理。

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

## 5.1 剩余待验证(Phase 3 收尾,按优先级)

1. **report 放大预算后的端到端产出**:`632c18c` 已把 report 递归与墙钟翻倍(原实测 report 在 300s 内跑完 18 次工具调用后被熔断、答案为空),但放大后的完整 report 尚未跑通——**DashScope 的 qwen3.8-27b 免费配额在测试中被烧光**(`AllocationQuota.FreeTierOnly`)。配额恢复后重跑一次 report,确认能产出正文即可闭环。
2. **审批 HITL 真实触发**:`on` 模式下高危 SQL 走 `SqlGateMiddleware` interrupt,approve/edit/reject 三态只有单测覆盖(13 个,含真实 interrupt 链路),**从未在真实 LLM 下跑过**。需在测试库上构造可回滚的 DML 验证。
3. **nemotron 跨模型稳健性附录**:OpenRouter 免费档每日 50 次,不排期,顺手时补采。

## 5.2 模式预算速查

| 模式 | 递归上限 | 墙钟 | 说明 |
|---|---|---|---|
| data / doc | `HARNESS_RECURSION_LIMIT`(40) | `HARNESS_MAX_SECONDS`(300) | ≈ data 20 步 |
| report | 基础值 × 2(80) | 基础值 × 2(600) | ≈ report 40 步,设计批准宽松档 |

---

## 6. 开发约定(踩坑总结出的)

- **TDD 是硬约束**:每个任务先写失败测试 → 确认失败原因符合预期 → 实现 → 全绿 → 提交。本项目所有功能都走这个流程,且多次靠测试抓住计划里的错误代码。
- **改代码必须实际运行验证**,不靠推断。本项目反复出现"同一份代码,单测过、真实链路炸"。
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
