# CLAUDE.md
This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**DataAgent Pro** — an intelligent business data interaction platform that enables non-technical users to query, analyze, and visualize business data via natural language (Text-to-SQL), powered by a Multi-Agent collaborative architecture.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend framework | Python 3.10+, FastAPI (async, SSE streaming) |
| Agent orchestration | LangGraph 1.x (stateful workflows, Human-in-the-loop) |
| Agent framework | LangChain 1.x (tools, output parsers), deepAgents 0.5.x (structured reasoning) |
| Frontend | Vue 3 + Vite + Element Plus + Echarts |
| ORM / DB driver | SQLAlchemy (multi-dialect: MySQL, PostgreSQL, SQL Server, Oracle) |
| Vector DB | Milvus 2.x (RAG knowledge base) |
| Cache / State | Redis (Graph interrupt state snapshots) |
| LLM | Privately deployed Qwen or GLM models |
| Deployment | Docker Compose (dev), Kubernetes (prod), Nginx (static frontend) |
| Documentation | VitePress (must be delivered as deployable online docs in `docs/`) |

## Multi-Agent Architecture (Harness Pattern)

The system follows a **Control Plane + Data Plane + Expert Workers** architecture:

1. **Orchestrator Agent** — intent parsing, task decomposition, LangGraph state management, dynamic routing
2. **Misc Agent** — handles non-professional/general questions (杂项节点), prevents non-data questions from polluting the main pipeline
3. **RAG Agent** — retrieves operational standards and metric definitions from Milvus
4. **Schema Agent** — dynamically loads relevant table schemas, filters irrelevant tables to reduce token cost
5. **SQL Coder Agent** — generates dialect-specific SQL (MySQL/PG/Oracle/SQL Server), self-corrects on execution errors (max 2 retries)
6. **Security Agent** — classifies SQL as read (SELECT → allow) or write (INSERT/UPDATE/DELETE/DROP → block, trigger human approval)
7. **Analyst Agent** — performs statistical analysis (YoY, MoM, anomaly detection) on query results
8. **Reporter Agent** — generates Echarts JSON configs for visualization, or Excel/CSV file export

### Harness-Aligned Core Modules (feature-flagged)

借鉴 DeepSeek Harness（dsh）设计模式落地的核心模块，均以 feature flag 门控、默认关闭、旧行为保持可用：

| 模块 | 职责 | Feature Flag（默认 False） |
|------|------|---------------------------|
| `app/core/event_sourcing.py` | 会话事件溯源：append-only `session_events` 表 + surface 投影（`derive_messages`）+ Fork；历史恢复投影优先、Redis 回退 | `EVENT_SOURCING_ENABLED` |
| `app/core/prompt_section.py` | 系统提示词分层组装：order 排序 + 作用域遮蔽 + 变量插值（legacy 单一字符串兜底） | `PROMPT_SECTION_ENABLED` |
| `app/core/seam.py` | 能力接缝：search / storage 后端可替换（Provider 注册 + 运行时选择；LLM seam 留待统一接口） | `SEAM_ENABLED` |
| `app/core/stream_protocol.py` | SSE 类型化事件协议（新增类型只增不删；reasoning 与正文 token 类型化隔离） | 无（默认启用） |

落地状态与差距详见 `docs/reference/harness-landing-gap-analysis.md`。

## Core Workflow

```
User Input → Intent Routing
  ├─ ask_help / non-data → Misc Agent → Stream output
  └─ query_data / write_data → Schema Agent → SQL Coder → Security Agent
        ├─ SELECT → Execute SQL → Analyst Agent → Reporter Agent → Stream output
        └─ DML/DDL → Suspend Graph → Push approval → Admin approve/reject → Resume or reject
```

The workflow is implemented as a **LangGraph 1.x state graph** with interrupt/resume for Human-in-the-loop. Graph state is persisted to Redis via `checkpointer.py` with a default TTL of **1 hour**. The state schema is defined in `app/graph/state.py` (AgentState TypedDict).

## Key API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/chat/completions` | Core chat (SSE streaming: text, chart config, intermediate state) |
| `POST` | `/api/v1/chat/approve` | Admin approval callback (task_id + action: approve/reject) |
| `POST` | `/api/v1/chat/stop` | Interrupt agent execution |
| `GET` | `/api/v1/datasource/list` | List user-accessible data sources |
| `POST` | `/api/v1/export/excel` | Async export to Excel/CSV |

## 开发命令速查

```bash
# === 后端 ===
cd backend
uv sync --group dev              # 安装/同步依赖（含 dev）
uv run data-agent                # 启动后端 (uvicorn, 端口 8000, 热重载)
uv run uvicorn app.main:app --reload --port 8000  # 等效命令
uv run pytest                    # 运行全部测试
uv run pytest -k "test_name"     # 运行匹配名称的单个测试
uv run pytest tests/test_agents.py::TestSecurityAgent::test_mask_phone  # 运行指定测试函数

# === 前端 ===
cd frontend
npm install                      # 安装依赖
npm run dev                      # 启动开发服务器 (端口 5173)
npm run build                    # 生产构建
npx vue-tsc --noEmit             # TypeScript 类型检查

# === 基础设施 ===
cp .env.example .env             # 创建环境变量文件（按需修改 LLM Key 和 DB 密码）
docker-compose up -d             # 启动所有服务 (Redis+etcd+MinIO+Milvus+MySQL+PostgreSQL)
docker-compose ps                # 查看服务状态
docker-compose down -v           # 停止并清理所有服务（含数据卷）
./scripts/start-dev.sh           # 一键启动开发环境

# === 文档 ===
cd docs
npm install                      # 安装 VitePress 依赖
npm run docs:dev                 # 启动文档开发服务器
npm run docs:build               # 构建静态文档站点
```

## Known Issues (待修复)

> 注：下表原记录于 2026-04-29（DEVELOPMENT_PLAN 阶段 2 遗留）。经 2026-10-16 交接复核，
> 其中 #1/#3 已在后续提交中修复，但本表未同步，特在此订正，避免误判为待办。

| # | 问题 | 状态 | 订正依据 |
|---|------|------|------|
| 1 | schema/sql_coder 节点缺少错误短路条件边 | ✅ 已修复 | `graph/workflow.py` 的 `route_schema` / `route_sql_coder` 均已检查 `error_message` 短路（前者→finish，后者→rag_agent 兜底） |
| 2 | ~~chat.py 中 GraphInterrupt 用字符串匹配捕获~~ | ✅ 已解决（2026-10-10 复核：已用 `except GraphInterrupt`） | — |
| 3 | execute_node 丢失 SQL 自纠错重试能力 | ✅ 已修复 | `execute_node` 已调用 `generate_and_execute_sql(max_retries=2, initial_sql=sql)`；`quality_gate` 为降级路由，职责不同，非缺陷 |

### 当前真正遗留（详见 `docs/NEXT_STEPS.md`）

- **Phase 3 收敛与归档（部分）**：`legacy-graph-13node` tag 已存在（轻量 tag→`3652e6c`），但归档/回滚文档已补（`docs/archive/plans/2026-10-16-legacy-graph-13node-archive.md`）；`USE_DEEP_AGENT` / `AGENT_LOOP_SHADOW` 等历史开关**仍在代码**（`agent_loop.py` / `chat.py` / `workflow.py` / `config_layer.py`），清理未完（见 `docs/NEXT_STEPS.md` 工作线 A）。
- **三个 Harness feature flag 默认 False**：`EVENT_SOURCING_ENABLED` / `PROMPT_SECTION_ENABLED` / `SEAM_ENABLED` 代码就绪但休眠（见 `docs/reference/harness-landing-gap-analysis.md` L1–L6）。
- **人工门禁待判**：`backend/configs/harness_review.md` 指标 3/4 仍为 `[ ]`；多数样本 legacy 侧"已排除"，对比口径降级。
- **nemotron 跨模型稳健性附录**：被上游 provider 故障阻塞，需配额恢复后跑 `backend/scripts/nemotron_batch.py`。
- **产品决策**：第 3 层 prompt rules 极强，模型拒绝发写 SQL，审批卡实际不可达（"过度安全"），需决定否放开写操作。

## Important Constraints
- 在Python项目测试时，确保项目在虚拟环境中使用uv安装项目依赖进行测试
- **"读数据随意，改数据必批"** — reads are free, writes always require human approval. Use both regex AND LLM double-checking to classify SQL before execution.
- Data masking required on sensitive fields (phone numbers, ID numbers) before returning results.
- Per-user concurrency rate limiting via FastAPI to prevent LLM resource exhaustion.
- Target: simple queries < 5s end-to-end, complex queries < 15s, first-byte SSE < 1s.
- New database dialects are added via config + SQL dialect template (`app/db/dialects/`) — core Agent logic must not change.
- Redis checkpoint TTL is 1 hour (`checkpointer.py:CHECKPOINT_TTL`) — approval-awaiting tasks expire after this.

## SSE Event Types (前端 Backend 协议)

后端通过 SSE 流式推送事件到前端 `useSSE.ts` composable。协议约定「只增不删」（见 `app/core/stream_protocol.py`），事件类型常量以 `SSEEventType` 为准：

| event.type | callback | 用途 |
|-----------|----------|------|
| `thread_id` | onThreadId | 会话 ID（流开始推送，多轮复用） |
| `status` | onStatus | 流程状态 / quality_feedback 复用展示 |
| `sql` | onSQL | SQL 卡片（token 事件 channel=sql 先行流式追加） |
| `result` | onResult | 查询结果数据 + 列名 |
| `token` | onToken | 逐字正文（携带 `channel`: sql=SQL 卡片 / answer=正文） |
| `reasoning` | onReasoning | 思考模型 reasoning_content 增量（折叠卡片） |
| `thinking` | onThinking | Agent 阶段思考卡片（agent/phase/content） |
| `node_started` | onNodeStarted | 节点开始（驱动任务清单 + step_id 分组） |
| `plan` | onPlan | 执行计划（intent/steps/chart_suitable） |
| `clarification` | onClarification | 意图追问卡片 |
| `tool_call` / `tool_result` | onToolCall / onToolResult | 工具调用/结果（合并为 tool_chain 卡片） |
| `chart` | onChart | ECharts 图表配置 |
| `title` | onTitle | 会话标题（done 后异步推送） |
| `error` | onError | 错误信息（code + recoverable） |
| `approval_required` | onApprovalRequired | 高危 SQL 需要审批（thread_id, question, sql, reason） |
| `quality_feedback` | onStatus（复用） | 质量门评估反馈 |
| `done` | onDone | 流正常结束 |

所有节点内事件统一携带自增 `step_id`（`thread_id`/`done`/`title` 除外），前端按步骤分组渲染；15s 无事件时后端发送 `: ping` 注释行心跳。

- 当你在提示词中包含 use context7 时，服务器会获取当前官方文档和代码示例，并直接集成到你的 AI 助手的上下文窗口中