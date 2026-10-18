# CLAUDE.md

This file provides guidance to coding agents when working with code in this repository.
（面向其他智能体工具的通用版本见 `AGENTS.md`；交接与历史决策见 `docs/HANDOVER.md`。）

## Project Overview

**DataAgent Pro** — 面向业务人员的多智能体数据分析平台：用自然语言提问 → 生成 SQL → 执行 →
出表/图 → 给分析结论。技术栈 **FastAPI + LangGraph/deepagents**（后端）与
**React 19 + Ant Design X**（前端），状态落 Redis（checkpointer）+ MySQL（业务/元数据）+
Milvus（RAG）。

当前主路径是 **Harness 模式**（`HARNESS_MODE=on`）：deepagents 主循环 + 工具，
13 节点固定编排已归档为 legacy（tag `legacy-graph-13node`）。

## Tech Stack

| 层 | 技术 |
|---|---|
| 后端框架 | Python 3.10+ · FastAPI（异步 + SSE） |
| Agent | LangGraph 1.x · LangChain 1.x · deepagents（`create_deep_agent`） · langchain-openai 1.2.x |
| 前端 | **React 19 + Vite + TypeScript** · Ant Design 6 + Ant Design X 2.9（Bubble/Sender/Conversations/ThoughtChain/x-markdown） · zustand · ECharts |
| 前端视觉 | 单深色令牌（`src/index.css`）· `@ant-design/icons` 6.x · MiSans VF（npm `misans`）· JetBrains Mono（`@fontsource`）· motion（React Bits 组件） |
| ORM / 驱动 | SQLAlchemy（MySQL / PostgreSQL / SQL Server / Oracle） |
| 向量库 / 缓存 | Milvus 2.x（RAG） · Redis（checkpointer，TTL 1h） |
| LLM | OpenAI 兼容 provider（DashScope/Qwen、OpenRouter 等），配置热加载 |
| 部署 | 单体镜像（nginx + uvicorn + supervisord）+ Docker Compose |

## Architecture（当前真实形态）

```
用户提问
  └─ POST /api/v1/chat/completions
       ├─ HARNESS_MODE=on ─→ app/harness/stream_harness.py
       │     ├─ agent_factory.build_harness_agent()  # 单例，按 spec 指纹重建
       │     ├─ tools/data_tools.py                  # get_table_schema / run_sql / search_knowledge / make_chart
       │     ├─ sql_gate(+middleware)                # 读写分类 → allow/ask/deny，ask 时 interrupt
       │     ├─ sse_bridge.py                        # deepagents 事件 → SSE 协议（含 reasoning/usage）
       │     └─ HITL 等待-恢复（进程内 waiter，见约束）
       └─ legacy 13 节点（tag legacy-graph-13node，勿在其上新增功能）
```

### 关键模块

| 模块 | 职责 | 状态 |
|---|---|---|
| `app/harness/stream_harness.py` | SSE 生成器：心跳（`asyncio.shield`）、瞬时错误重放、HITL、usage 收尾 | **主路径** |
| `app/harness/agent_factory.py` | Agent 装配与指纹（提示词/工具/provider/温度/思考开关） | 主路径 |
| `app/harness/sse_bridge.py` | deepagents 事件 → SSE；reasoning/tool/sql/result/chart | 主路径 |
| `app/core/event_sourcing.py` | 会话 append-only 事件 + surface 投影（`derive_messages`）+ fork | 默认启用 |
| `app/core/usage_metrics.py` | token 用量 + 上下文三段估算（`UsageMeter`/`context_breakdown`） | 主路径 |
| `app/core/llm.py` | provider 上下文、思考开关/强度、**reasoning_content 补丁** | 主路径 |
| `app/core/prompt_section.py` | 分层提示词（Harness 尚未接入，属 L3 待办） | flag 休眠 |
| `app/core/seam.py` | 能力接缝（search/storage） | flag 休眠 |

## Repository Layout

```
backend/app/
├── api/v1/        # chat.py（对话/会话/归档/目标）、config_api.py（provider/运行时参数）、approve.py…
├── core/          # llm / usage_metrics / event_sourcing / stream_protocol / config_manager / hitl
├── harness/       # stream_harness / agent_factory / sse_bridge / sql_gate(+middleware) / tools
├── deepagent/     # 独立 DeepAgent 路径（mode=task）
├── graph/         # legacy 13 节点工作流（归档）
├── models/        # ChatSession（含 archived/context 相关）/ ChatNode / SessionEvent
└── db/, rag/, skills/, agents/, utils/
frontend-react/src/
├── pages/         # Chat.tsx（工作台）、Login.tsx、admin/LlmConfig.tsx…
├── components/
│   ├── chat/      # MessageList/MessageItem/StepChain/DeepThink/StatPopovers/StatBar/
│   │              # TurnNavigator/SessionPickerModal/ModelSelector/SenderInput/AccountMenu…
│   └── bits/      # Icon（语义图标）、Markdown（x-markdown+hljs+SQL 格式化）、reactbits/（ShinyText/BlurText/SpotlightCard/StarBorder）
├── sdk/           # protocol.ts（SSE 事件类型）、reducer.ts（事件→消息）、history.ts（投影→消息）、blocks.ts
└── stores/        # chat（会话/流/用量/轮次）、auth、config（providers/运行时参数）、theme（恒 dark）
```

## Dev Commands

```bash
# === 后端（端口 8001：本机 8000 常被系统占用，前端代理默认 8001）===
cd backend
.venv/Scripts/python.exe -m uvicorn app.main:app --port 8001          # Windows
uv run uvicorn app.main:app --reload --port 8001                      # 或 uv
.venv/Scripts/python.exe -m pytest tests/ -q                          # 22 passed

# === 前端 ===
cd frontend-react
npm install
npm run dev                     # 5173；后端地址可用 BACKEND_PORT 覆盖（默认 8001）
npx tsc -b --pretty false       # 类型检查
npm run build                   # 生产构建
npx vitest run                  # 7 passed
```

**Windows 构建坑（实测）**：`vite build` / vitest 可能因沙箱限制无法写系统 `%TEMP%`，
构建前把 `TEMP`/`TMP` 指向仓库内目录：

```powershell
$env:TEMP="$PWD/.esbuild-tmp"; $env:TMP="$PWD/.esbuild-tmp"; npm run build
```

**vite 缓存坑**：`node_modules/.vite` 有时无法删除（批量删除保护），用
`Rename-Item node_modules/.vite .vite.stale-<n>` 移走再启动即可。

## API & SSE Contracts

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/chat/completions` | 核心对话（SSE） |
| POST | `/api/v1/chat/approve` | 审批决策（approve/edit/reject） |
| POST | `/api/v1/chat/cancel` | 中断执行 |
| GET/PATCH/DELETE | `/api/v1/chat/sessions[/{id}]` | 列表（`limit/offset/archived`）/详情/重命名/删除 |
| PATCH | `/api/v1/chat/sessions/{id}/archive` | 归档/恢复（前端已不展示，接口保留） |
| GET/PUT | `/api/v1/chat/sessions/{id}/goal` | 会话长期目标 |
| PATCH | `/api/v1/config/llm/{id}/runtime` | 上下文窗口 + 思考强度（**只改这两项**） |
| POST | `/api/v1/export/{csv,excel}` | 导出 |

**SSE 事件（19 类，只增不改）**：
`thread_id` · `status` · `token` · `reasoning` · `thinking` · `tool_call` · `tool_result` ·
`sql` · `result` · `chart` · `plan` · `clarification` · `error` · `title` · `done` ·
`approval_required` · `quality_feedback` · `node_started` · **`usage`**

**`usage`（扁平字段，done 前下发）**：

```
type, input_tokens, output_tokens, cached_tokens, uncached_input_tokens, total_tokens,
cache_hit_ratio, estimated, turns, steps,
context{ system_prompt, tool_defs, messages, window, used_pct }
```

- 窗口优先级：`provider.context_window` > `settings.CONTEXT_WINDOW` > 192000。
- 历史会话：`GET /chat/sessions/{id}` 现场估算并返回 `usage`（`estimated: true`）。

**字段口径提醒（踩过坑）**：
- `sql` 事件同时可能存在 `sql` 与 `content` 字段——前端取 `ev.sql || ev.content`。
- 落库（`_es_flush`）content 取 `payload.content or payload.sql`。
- 投影消息带 `turn_index`（来自 `session_events.node_index`），前端据此做「第 N/M 轮」切换；
  旧数据无该字段时平铺。

## Important Constraints

- **读数据随意，改数据必批**：写类 SQL 必须走 `sql_gate` → 人工审批；正则 + LLM 双重分类。
- **敏感字段脱敏**（手机号/身份证）后才能返回。
- **HITL 要求同进程**：`app/core/hitl.py` 的 waiter 是进程内字典；多 worker/多副本前必须改
  Redis pub/sub 或粘性会话（见 `docs/HANDOVER.md` §5.4）。
- Redis checkpoint TTL 1 小时。
- **服务由用户掌控**：不要擅自重启用户的后端/前端；代码改动靠 `--reload`，配置改
  `backend/configs/*.json`（watchdog 热更新）。
- 新方言通过 `app/db/dialects/` 扩展，核心 Agent 逻辑不变。
- **reasoning_content 补丁在模块加载期执行**（`core/llm.py`）——修改后必须整进程重启才生效。
- `enable_thinking` / `reasoning_effort` 必须走 **`extra_body`**，放 `model_kwargs` 会让
  openai SDK 抛 `unexpected keyword argument`。

## Verification（门禁）

1. `npx tsc -b --pretty false` + `npm run build`（前端）
2. `npx vitest run`（7）+ `pytest tests/ -q`（22）
3. **MCP 端到端**（chrome-devtools 走真实页面 + 真实 HTTP/SSE/DB）——单测全绿不代表可用，
   本仓库多次出现「单测通过但真实链路炸」。

## Known Issues / 待办

- **DashScope 免费额度**：2026-10-18 实测 `qwen3.7-flash` 返回 `403 Free quota exhausted`，
  对话不可用（账号问题）；额度恢复后需回归实时对话/思考/三弹窗。
- **`reasoning_effort` 上游支持**：已按 `extra_body` 下发，DashScope 兼容模式是否接受待验证；
  不支持时保持空值。
- **L3 分层提示词**未接入 Harness；**L5 能力接缝** flag 仍休眠（见 gap-analysis §5.6）。
- **nemotron 跨模型附录**：上游故障阻塞，恢复后跑 `backend/scripts/nemotron_batch.py`。
- **产品决策**：第 3 层 prompt rules 极强，模型拒绝发写 SQL，审批卡实际不可达（"过度安全"）。
- 历史遗留开关 `USE_DEEP_AGENT` / `AGENT_LOOP_SHADOW` 仍在代码（见 `docs/NEXT_STEPS.md` 工作线 A）。

## 前端约定（2026-10 定版）

- **单深色主题**：无亮色切换；层级靠背景明度（`#0a0a0b / #101012 / #141416 / #1c1c1f`），
  边框用 `rgba(255,255,255,0.07)`，不要新增分隔线。
- 图标统一 `<Icon name="..." size={14|16} />`（`components/bits/Icon.tsx` 语义名 → antd 图标），
  不要引入其他图标库或自建字体图标。
- 字体：`--font-sans`（MiSans VF）、`--font-mono`（JetBrains Mono，**必须带 MiSans 中文兜底**）；
  最小字号 12px。
- 生成中判断用 `store.isGenerating`（**不要用 `isLoading`**——它同时用于历史加载）。
- 思考显隐受 `store.thinking` 开关控制；`DeepThink` 只在有 reasoning 数据时渲染。
