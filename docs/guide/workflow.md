# 工作流与状态机详解

本文档详细描述 LangGraph 工作流的 `AgentState` 字段定义、节点拓扑、实时任务清单、SSE 流式架构及 Human-in-the-loop 中断/恢复流程。

> **最后更新**: 2026-06-26 — 反映 clarify_plan 合并、node_started 实时推送、任务清单 UI 等最新优化。

---

## AgentState 字段定义

`AgentState` 是 LangGraph 全局状态对象，在工作流各节点间流转。定义于 `backend/app/graph/state.py`：

```python
class AgentState(MessagesState):
    """全局工作流状态"""

    # === 用户输入 ===
    user_question: str            # 用户原始自然语言问题

    # === 意图澄清 + 执行计划（clarify_plan 合并节点） ===
    is_clear: bool                # 意图是否明确
    clarification_text: str       # 追问文本（不明确时）
    clarification_options: list   # 追问选项列表
    clarifier_count: int          # 追问次数（防止死循环，上限2次）
    intent: str                   # query_data / ask_help / write_data / chart_interaction / other_questions
    intent_confidence: float      # 意图分类置信度
    plan_steps: list[dict]        # 执行计划：[{"step": "load_schema", "agent": "schema", "priority": 1}, ...]
    chart_suitable: bool          # Planner 阶段判断是否适合生成图表

    # === 表结构 ===
    schema_info: str              # 筛选后相关表的 DDL 信息
    relevant_tables: list[str]    # Schema Agent 筛选出的相关表名

    # === SQL 生成 ===
    generated_sql: str            # SQL Coder 生成的 SQL
    sql_category: str             # safe / dangerous

    # === 执行结果 ===
    query_result: list[dict]      # SQL 执行结果（行列表）
    query_columns: list[str]      # 列名列表

    # === 质量评估 ===
    query_quality: str            # good / insufficient（ReAct 反馈）
    quality_feedback: str         # 质量评估反馈

    # === 分析结果 ===
    analysis_text: str            # Analyst 实时流式输出的 Markdown 分析文本
    dynamic_chart_suitable: bool  # Analyst 动态判断是否适合图表

    # === 图表 ===
    chart_config: dict            # Reporter 生成的 ECharts JSON 配置

    # === 缓存（多轮对话用）===
    _cached_query_result: list    # 上一轮查询结果缓存
    _cached_query_columns: list   # 上一轮查询列名缓存

    # === 流程控制 ===
    stage: str                    # 当前流程阶段标识
    error_message: str            # 错误信息
    node_index: int               # 对话轮次索引
```

---

## 工作流节点拓扑

当前为 **Plan-and-Execute + ReAct** 架构，共 **13 个节点**：

| 序号 | 节点名称 | 职责 | 路由去向 |
|------|---------|------|----------|
| 1 | `clarify_plan` | **合并** 意图澄清 + 执行计划生成（单次 LLM） | → schema_agent / rag_agent / misc_agent / chart_direct / finish |
| 2 | `schema_agent` | 加载并筛选相关表结构 | → sql_coder / finish |
| 3 | `sql_coder` | Text-to-SQL 生成（流式输出） | → security / rag_agent |
| 4 | `security` | SQL 安全审计（正则 + LLM 双检） | → execute_sql / finish |
| 5 | `execute_sql` | 执行 SQL（含自纠错重试） | → quality_gate / misc_agent |
| 6 | `quality_gate` | ReAct 质量评估（LLM 判断结果是否充分） | → analyst / misc_agent |
| 7 | `analyst` | 数据分析 + 实时流式 Markdown | → reporter / answer |
| 8 | `reporter` | 生成 ECharts 图表配置 | → finish |
| 9 | `answer` | 纯文本回答（数据不适合图表时） | → finish |
| 10 | `misc_agent` | 杂项处理/降级兜底 | → finish |
| 11 | `rag_agent` | RAG 知识库检索 | → finish |
| 12 | `chart_direct` | 图表追问快捷路径（复用缓存数据） | → analyst |
| 13 | `finish` | 结束标记 + 标题生成 | → END |

### Graph 拓扑图

```
clarify_plan ──┬── schema_agent → sql_coder → security → execute_sql
               │                                              │
               ├── rag_agent → finish                     quality_gate
               │                                              │
               ├── misc_agent → finish                ┌──────┴──────┐
               │                                      analyst      misc_agent
               ├── chart_direct → analyst → reporter       │
               │                           │           ┌───┴───┐
               └── finish               finish      reporter  answer
                                                        │       │
                                                      finish  finish
```

### 关键设计变更（vs 初版）

| 初版 | 当前 | 说明 |
|------|------|------|
| clarifier → planner 两次 LLM | `clarify_plan` 一次 LLM | 节省 ~2-3s |
| 10 节点 | 13 节点 | 新增 quality_gate / answer / chart_direct / misc_agent |
| Analyst 输出 JSON 后回放 | Analyst 实时流式 Markdown | 消除 5-10s 等待 |
| 水平进度条 | 可折叠任务清单 | 每步 spinner→checkmark 动画 |

---

## 实时任务清单机制

每个节点开始时通过 `StreamContext.push_priority()` 直写 SSE 主循环队列，前端立即显示该节点为 **running** 状态（带旋转 spinner）。节点完成后通过 `thinking` 事件标记为 **completed**。

```
节点开始 → _push_node_started → push_priority → merge_queue（绕过 token 队列）→ SSE → 前端 🔵 running
节点完成 → thinking 事件 → 前端 ✅ completed → 下一个节点 🔵 running
全部完成 → completeAllTasks() → 2 秒后自动折叠任务清单
```

## SSE 事件流时序

```
用户点击发送
    │
    ▼
客户端 ←── event: thread_id         ← 会话 ID
客户端 ←── event: node_started      ← "意图分析" 🔵 running
    │    (clarify_plan 开始)
    ▼
客户端 ←── event: node_started      ← "意图分析" ✅ → "加载表结构" 🔵 running
客户端 ←── event: thinking           ← 更新管道
客户端 ←── event: plan               ← 执行计划卡片
    │
    ▼
客户端 ←── event: node_started      ← "加载表结构" ✅ → "生成SQL" 🔵 running
客户端 ←── event: node_started      ← SQL 流式 token（被抑制，不显示为文本）
客户端 ←── event: sql               ← 格式化 SQL 卡片（仅一次）
    │
    ▼
客户端 ←── event: node_started      ← "生成SQL" ✅ → "安全审核" 🔵 running → ✅
客户端 ←── event: node_started      ← "安全审核" ✅ → "执行查询" 🔵 running
客户端 ←── event: tool_call          ← "调用: execute_sql"
客户端 ←── event: result             ← 查询结果表格
客户端 ←── event: tool_result       ← "完成: execute_sql"
    │
    ▼
客户端 ←── event: node_started      ← "执行查询" ✅ → "质量评估" 🔵 running → ✅
客户端 ←── event: node_started      ← "质量评估" ✅ → "数据分析" 🔵 running
客户端 ←── event: token × N         ← Markdown 分析文本流式输出
    │
    ▼
客户端 ←── event: node_started      ← "数据分析" ✅ → "生成图表"/"生成回答" 🔵 → ✅
客户端 ←── event: chart / (无)      ← 图表配置（如有）
客户端 ←── event: node_started      ← "完成" ✅
客户端 ←── event: title             ← 会话标题
客户端 ←── event: done              ← 流结束
```

### 全部 SSE 事件类型

| 事件类型 | 触发时机 | data 字段 |
|---------|---------|----------|
| `thread_id` | 流开始时 | `thread_id` |
| `node_started` | **每个节点开始时**（实时推送） | `agent`, `label` |
| `thinking` | 节点完成时 | `agent`, `phase`, `content` |
| `clarification` | 意图模糊时 | `text`, `options` |
| `plan` | 执行计划生成后 | `intent`, `intent_label`, `steps`, `chart_suitable` |
| `tool_call` | 工具调用开始 | `tool_name`, `sql`/`rows`/`cols` 等 |
| `tool_result` | 工具调用结束 | `tool_name`, `result`/`row_count` 等 |
| `sql` | SQL 生成完成 | `content` (格式化 SQL) |
| `result` | 查询执行完成 | `data`, `columns` |
| `token` | 流式文本输出 | `content` (逐字追加) |
| `chart` | 图表配置生成 | `config` (ECharts JSON) |
| `title` | 标题生成完成 | `content`, `thread_id`, `node_index` |
| `error` | 任意阶段出错 | `error`, `code`, `recoverable` |
| `approval_required` | 高危 SQL 需审批 | `thread_id`, `sql`, `reason` |
| `done` | 工作流结束 | — |

### 去重机制

- **SQL**：`sql_coder` 不再通过 `push_token` 推送 token，仅由格式化 `sql` 事件展示一次
- **分析文本**：`analyst` 的 token 流正常推送（Markdown 逐字渲染），不再有重复的 `tool_call`/`tool_result`
- **工具卡片**：仅传递有值的 meta 字段，过滤 `undefined`/空值/重复的 `sql_preview`

---

## Human-in-the-loop 中断/恢复流程

### 写操作检测

Security Agent 使用 **正则 + LLM 双重检测** 判断 SQL 类型：

1. **正则快速筛**：匹配 `INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE`
2. **LLM 精判**：提交 SQL 给 LLM 做语义分析，避免正则误判

### 中断流程

```
1. Security Agent 检测到高危 SQL (category == "dangerous")
       │
       ▼
2. 调用 interrupt({"type": "approval_required", "sql": "...", "reason": "..."})
       │
       ▼
3. LangGraph 保存检查点到 Redis + 挂起执行
       │
       ▼
4. 后端返回 SSE 事件: { "type": "approval_required", "thread_id": "xxx", "sql": "..." }
       │
       ▼
5. 前端展示审批提示
```

### 恢复流程

```
1. 管理员在前端审批页面点击"通过"或"驳回"
       │
       ▼
2. 后端调用 graph.invoke(Command(resume={"approved": True/False}), config)
       │
       ▼
3. LangGraph 从 Redis 恢复状态，重新执行 security_node
       │
       ▼
4. interrupt() 返回 Command 中的 resume 值
       │
       ▼
5. 审批通过 → 继续 execute_sql 链路
   审批驳回 → 设置 error_message → 路由至 finish
```

---

## 审批流生命周期

```
┌────────┐   检测到高危SQL    ┌────────┐   管理员通过    ┌────────┐
│  idle  │ ─────────────────→ │pending │ ─────────────→│approved│
└────────┘                    └────────┘                └────────┘
                                   │ 管理员驳回
                                   ▼
                              ┌────────┐
                              │rejected│
                              └────────┘
```

- **idle**：初始状态，无审批任务
- **pending**：等待管理员审批，Graph 处于中断状态
- **approved**：审批通过，SQL 继续执行
- **rejected**：审批驳回，返回拒绝原因给用户

每个审批任务在 Redis 中以 `thread_id` 为键保存完整状态快照。
