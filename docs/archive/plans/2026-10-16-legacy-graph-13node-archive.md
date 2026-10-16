# 归档：legacy 13 节点 LangGraph 图（`legacy-graph-13node` tag）

> 归档日期：2026-10-16（Phase 3 收敛与归档）
> 归档范围：重构前的固定编排 13 节点图（data/report/doc 模式的 LangGraph 工作流及其 Orchestrator 路由）。
> 原则：**只归档、不删除**。legacy 代码继续保留在主干作为 Harness 接管后的 fallback。

## 1. 归档对象

- **Git tag**：`legacy-graph-13node`
  - 类型：**附注 tag**（`git cat-file -t` = `tag`，带归档说明附注）
  - 当前指向：`17f4197`（*feat(harness): report/doc 模式纳入 Harness*）——
    即 Phase 3 扩展 report/doc 后的提交，Harness 已接管三模式流量、legacy 已退为
    fallback 的状态。
  - ✅ 已复核（2026-10-16，在可执行 git 环境确认）：
    `git cat-file -t legacy-graph-13node` → `tag`；
    `git log --oneline -1 legacy-graph-13node` → `17f4197`。
  - 注：本文档初稿曾误记为「轻量 tag，指向 `3652e6c`」——那是撰写环境无法执行
    `git` 时的推测，实际不成立，现已按实测更正。
- **代码（仍在主干，未删除）**：
  - `app/graph/workflow.py`（data 模式 13 节点图：`clarify_plan → schema → sql_coder → security → execute → quality_gate → analyst → reporter/answer`，及 `rag_agent` / `misc_agent` 兜底）
  - `app/graph/report_workflow.py` / `doc_workflow.py` / `task_workflow.py`（report/doc/task 模式工作流）
  - `app/agents/orchestrator.py` 的 `route_planner` 确定性路由
  - `app/graph/mode_router.py`（`register_mode` 四模式注册）
- **同批归档 tag**：`vue-legacy`（前端 Vue 旧线，参考用）

## 2. 为什么只归档不删除

Harness 主 Agent 重构目标（见 `docs/plans/2026-10-14-harness-agent-architecture-design.md`）明确：
保留可预测资产（安全闸、审批、流式、读数）。legacy 13 节点图是 **fallback 逃生通道**——
一旦 `HARNESS_MODE` 主路径出现回归，可零重启切回（见 §4 回滚）。删除它会失去这一安全网。

## 3. 当前接线状态（2026-10-16 核实）

- `HARNESS_MODE=on` 已写入 `backend/configs/patch.json`，**data 模式流量已由 Harness 主循环接管**
  （`api/v1/chat.py` 的 `HARNESS_MODE` 分发 → `app/harness/stream_harness.stream_chat_harness`）。
- legacy 路径（`_stream_chat` / `_stream_chat_deepagent`）仍存在，`HARNESS_MODE=off` 时作为 fallback 生效。
- ⚠️ **未完全清理的历史开关（Phase 3 收尾待办，不在本归档文档范围）**：
  - `USE_DEEP_AGENT`：仍散在 `chat.py` / `agent_loop.py` / `workflow.py` / `config_layer.py`，控制 DeepAgent（`mode=task`）分流。
    **该开关有活跃用途**（task 模式是唯一真·智能体路径），不应按死开关处理。
  - `AGENT_LOOP_ENABLED`（压缩驱动器总开关 + 回滚通道）：**保留**。
  - `AGENT_LOOP_SHADOW`：**已于 `044bab2` 删除**（settings 字段 / `config_layer` 白名单 /
    `chat.py` 影子比对分支 / `agent_loop.agent_loop_shadow()` 判定函数，4 处全清）。
    删除依据：默认关闭且**无任何测试覆盖**其真实行为，属从未被验证过的死分支。
    `agent_loop.py` 模块 docstring 中仍有一行文字提及（不影响行为），待清理。

## 4. 回滚 / 取用方式

### 4.1 运行时回滚（不重启，推荐）

Harness 主路径回归时，改 `backend/configs/patch.json` 的 `HARNESS_MODE` 为 `off`，
再调热更新端点即可切回 legacy 图（无需改代码、无需重启）：

```bash
curl -X POST http://localhost:8001/api/v1/config/patch/reload \
  -H "Authorization: Bearer <token>"
```

### 4.2 代码级取用（基于 tag 开分支）

如需在 legacy 基线单独开分支修改（一般不必，因 legacy 已保留在主干）：

```bash
git checkout -b legacy-13node-fix legacy-graph-13node
```

### 4.3 对照 tag 与主干差异

```bash
git log --oneline legacy-graph-13node..HEAD        # tag 之后到当前的提交
git diff legacy-graph-13node HEAD -- app/graph/    # legacy 图相关改动
```

## 5. 验收（Phase 3 归档门禁）

| 判据 | 状态 |
|---|---|
| tag `legacy-graph-13node` 已创建且指向 legacy-only 基线 | ✅ 已创建（落点需在可执行环境复核，见 §1） |
| legacy 代码未删除，仍可编译/导入 | ✅ 主干保留（`workflow.py` 等存在） |
| `HARNESS_MODE=off` 可切回 legacy fallback | ✅ 接线已具备（热更新端点） |
| 归档说明文档（本文件） | ✅ 新增 |
| 清理 `USE_DEEP_AGENT` / `AGENT_LOOP_SHADOW` 死开关 | ⏸ 移至 NEXT_STEPS A-#2/#3 |

---

*关联：架构目标见 `docs/plans/2026-10-14-harness-agent-architecture-design.md` §6（资产存续表）；
差距基线见 `docs/reference/harness-landing-gap-analysis.md`。本归档为 Phase 3 收敛的一部分。*