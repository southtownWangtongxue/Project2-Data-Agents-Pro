# 后续任务路线图（交接后复核，2026-10-16）

> 本文件由接手方在读完 `docs/HANDOVER.md`、Harness 架构设计、落地差距分析与当前代码后整理。
> 目的：把交接文档里的"待办"与**代码真实状态**对齐，给出可执行、带验收判据的工作线，
> 供接手方逐条认领。涉及运行时验证的步骤需在可运行 `pytest` / 服务的环境执行（见 §0）。

## 0. 环境约束（重要）

- 交接强调 **TDD 硬约束**：写失败测试 → 确认失败 → 实现 → 全绿 → 运行验证。
- 但本工作沙箱 **无法启动任何进程**（`git` / `uv` / `python` / `pwsh` 均被拒绝），
  因此"跑 pytest / 起服务 / 端到端走查"这一半无法在此环境完成。
- 本路线图里凡是"纯代码 + 写测试"的交付，可在此环境落盘；凡是"需 pytest 全绿 / 起服务回归"的步骤，
  需在有执行权限的环境由你（或 CI）运行并回填结果。
- 已修正 `CLAUDE.md` 的 Known Issues（#1/#3 实际已修复，原表未同步），避免误判为待办。

## 1. 已核实：交接文档"遗留"中有两项已修复（不再阻塞）

| 原登记项 | 代码现状（已核实） | 结论 |
|---|---|---|
| CLAUDE.md #1：`schema`/`sql_coder` 缺错误短路边 | `graph/workflow.py` 的 `route_schema` / `route_sql_coder` 均检查 `error_message` 短路（`route_schema`→`finish`，`route_sql_coder`→`rag_agent` 兜底） | ✅ 已修复 |
| CLAUDE.md #3：`execute_node` 丢失 SQL 自纠错 | `execute_node` 已调用 `generate_and_execute_sql(max_retries=2, initial_sql=sql)`；`workflow.py` 节点 docstring 已更新 | ✅ 已修复 |
| `quality_gate` 仅降级路由、非打回重试 | 设计如此（ReAct 质量门职责），非缺陷 | 保持 |

## 2. 工作线 A：Phase 3 收敛与归档（代码就绪，需决策 + 运行时回归）

交接里 Phase 3 目标的产物尚未全部落地，代码核实如下：

- ✅ **已复核（2026-10-16，在可执行 git 环境）**：`legacy-graph-13node` 是**附注 tag**，指向 `17f4197`（非本文档初稿推测的「轻量 tag → `3652e6c`」——那是撰写环境无法执行 `git` 时的推测）。归档说明文档已建于 `docs/archive/plans/2026-10-16-legacy-graph-13node-archive.md`（已按实测结果订正 tag 类型与落点）。**本项已完成，无需再打 tag。**
- 历史开关现状（已核实）：
  - `USE_DEEP_AGENT`：`chat.py` / `agent_loop.py` / `workflow.py` / `config_layer.py` 仍有引用，**但它有活跃用途**（`mode=task` 走 DeepAgent，是当前唯一真·智能体路径）——不是死开关。
  - `AGENT_LOOP_SHADOW`：**已删除**（`044bab2`：settings 字段 / 白名单 / chat.py 影子比对分支 / 判定函数 4 处全清）。依据：默认关闭 + 无任何测试覆盖 = 从未被验证的死分支。`agent_loop.py` 中残留的 docstring 文字已于本次同步清理。
  - `AGENT_LOOP_ENABLED`：**保留**（压缩驱动器总开关 + 回滚通道，有活跃用途）。
- `HARNESS_MODE=on` 已在 `patch.json` 生效，**data / report / doc 三模式**流量均已由 Harness 主循环接管（report/doc 于 `17f4197` 纳入），legacy 退为 `off` 模式 fallback。

**建议任务（按风险从低到高）：**

1. ~~**打 tag 归档**~~ ✅ 已完成（附注 tag `legacy-graph-13node` → `17f4197` + 归档说明文档）。
2. ~~**清理 `AGENT_LOOP_SHADOW` 死开关**~~ ✅ 已完成（`044bab2`）。注意：**不建议**彻底删除 `agent_loop.py`——`agent_loop_enabled()` 是压缩驱动器总开关且为回滚通道，删掉会失去逃生口。
3. **`USE_DEEP_AGENT` 去留决策**：当前 `select_profile` 仍按 `USE_DEEP_AGENT`/`mode=task` 分流到 DeepAgent。若 Phase 3 目标"单一架构"，需确认 DeepAgent（`mode=task`）是否仍保留——它是唯一真·智能体路径。建议改为**保留**：`mode=task` 的 DeepAgent 有活跃职责（TodoList / 子 Agent / Skills），删除全局开关等于放弃 task 模式能力。若确要收敛为「单一架构」，也应只删开关、保留 task 模式本身，而非删掉 DeepAgent 路径。

**验收判据**：`pytest backend/tests/` 全绿；前端 `npm run build` 通过；`/api/v1/chat/completions` 在 `HARNESS_MODE=on/off` 两档均回归走通；文档同步（架构/启动说明）。

## 3. 工作线 B：三个 Harness feature flag 灰度落地（L1–L6）

来自 `docs/reference/harness-landing-gap-analysis.md`。三个 flag：`EVENT_SOURCING_ENABLED` / `PROMPT_SECTION_ENABLED` / `SEAM_ENABLED` 默认 False，代码就绪但休眠。

| 阶段 | 内容 | 对应差距 | 验收判据（均需运行时） |
|---|---|---|---|
| L1 | 灰度开启 `EVENT_SOURCING_ENABLED`；回归 fork/trajectory/导出 | §3.1 | 默认配置下 fork/trajectory 有数据；Redis 回退保留 |
| L2 | DeepAgent + 多模式事件双写补齐（目前 DeepAgent 仅双写 3 类） | §3.2、§3.7 | DeepAgent/task/report/doc 会话投影完整 |
| L3 | 分层提示词灰度 `PROMPT_SECTION_ENABLED`，A/B 对比质量 | §3.1 | 提示词分层默认生效；legacy 兜底保留 |
| L4 | 子代理因果归因（事件 payload 增 `source` 字段） | §3.3 | 轨迹接口可区分子代理产出 |
| L5 | 能力接缝灰度 `SEAM_ENABLED` + LLM seam 论证 | §3.1 | `SEAM_ENABLED` 默认生效或明确弃用 |
| L6 | 渲染投影层（slot 体系）试验（`/chat-x` 实验页） | §3.4 | 双前端取舍决策落地 |

**节奏**：L1→L2→L3 串行（依赖事件日志数据质量）；L4/L5 可并行；L6 独立。每阶段以 `pytest` + 前端 build + 手动 SSE 时序观察回归。

**注意**：每个阶段改动都涉及**默认行为切换**，属于高风险变更，必须配 feature flag + 回滚（改 `patch.json` 即可，无需重启）。此线纯代码在沙箱可写，但**每个阶段验收都要运行时**，建议每阶段单独 commit 并在可执行环境走查。

## 4. 工作线 C：人工门禁与跨模型附录（外部 / 人依赖）

- **人工判定**：✅ **已完成**（2026-10-16）。用户对 `backend/configs/harness_review.md` 18 样本
  做了逐样本预筛，指标 3（子问题覆盖）/ 4（结论正确性）**均通过**，Phase 2 门禁随之关闭。
  预筛同时纠正了两处误判：
  - 样本 11 的「事件类型分布」加总实为 `253+253+242+134+60+52+42+17+17+9 = 1079`，
    与 `session_events` 记录数**完全一致（差额 0）**，此前"差 47"是核对遗漏；
  - 样本 14 的 `grounded=False` 属**尺子误报**（该轮采集在接地检测改用 `result.data`
    之前，`grounding_source` 为空即表示尺子不适用），不是模型幻觉。
  > 遗留的口径问题：样本 1–13 全部 `grounding_source=None`（尺子不适用），
  > 指标 1 的有效样本实为 16/17/18 三条（均 True）。**统计接地率时应按
  > `grounding_source` 甄别，不要把旧轮的 False 计入分母。**
- **nemotron 附录**：`backend/scripts/nemotron_batch.py` 被 OpenRouter/Nvidia 上游故障阻塞（DEGRADED / 流式零 chunk）。上游恢复后重跑，产出追加进 `configs/shadow_comparison.jsonl`，**不覆盖**既有样本。纯外部依赖，无代码改动。

## 5. 工作线 D：产品决策（写操作放开与否）

交接 §5.3 结论：第 3 层 prompt rules 极强，4 种 framing 下模型均拒绝发写 SQL，审批卡当前**实际不可达**（"过度安全"）。安全结论：审批回传通道无法注入任意 SQL（双重保险）。

**待决策**：是否要放开写操作？若放开，需调整第 3 层 prompt rules，让模型在用户明确要求时发写 SQL 交给第 2 层闸口——否则第 2 层安全闸形同虚设。当前是"过度安全"而非漏洞，短期不阻塞，但影响产品形态，需产品/安全拍板。此决策影响工作线 B 中 `SEAM_ENABLED`/审批流程的最终形态。

## 6. 建议的启动顺序（接手方视角）

1. **工作线 A 的 #1 已实质完成**：`legacy-graph-13node` tag 已存在；归档/回滚文档已新建（`docs/archive/plans/2026-10-16-legacy-graph-13node-archive.md`）。剩余是 A-#2/#3 的死开关清理（需运行时回归）。
2. **并行推进 B-L1（事件溯源灰度）**：收益最大、回退成本最低，且 Redis 回退路径保留。代码改动 + 测试在此环境可写，验收在可执行环境走查。
3. **工作线 C 的人工判定**：随时可做（纯判读），建议尽快补齐以关闭 Phase 2 门禁。
4. **D 的产品决策**：尽早对齐，避免后续 B-L5 回头改。

---

*生成说明：本路线图基于 `docs/HANDOVER.md`(2026-10-16)、`docs/plans/2026-10-14-harness-agent-architecture-design.md`、
`docs/reference/harness-landing-gap-analysis.md` 与对 `backend/app/graph/workflow.py`、`core/agent_loop.py`、`api/v1/chat.py` 的代码核实。*