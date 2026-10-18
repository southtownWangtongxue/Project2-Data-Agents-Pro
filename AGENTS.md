# AGENTS.md

> 通用智能体协作指南（适用于 Claude Code / Codex / Cursor / Copilot 等工具）。
> Claude 专属说明见 `CLAUDE.md`；交接与历史决策见 `docs/HANDOVER.md`；
> Harness 架构落地差距见 `docs/reference/harness-landing-gap-analysis.md`。

## 1. 项目一句话

**DataAgent Pro**：自然语言 → SQL → 执行 → 表格/图表 → 分析结论的业务数据分析平台。
后端 FastAPI + LangGraph/deepagents（主路径 `HARNESS_MODE=on`），前端 React 19 + Ant Design X，
状态落 Redis（checkpointer，TTL 1h）+ MySQL + Milvus。

## 2. 命令速查

```bash
# 后端（默认 8001：8000 常被系统占用；前端代理默认 8001）
cd backend
uv sync --group dev
uv run uvicorn app.main:app --reload --port 8001
.venv/Scripts/python.exe -m pytest tests/ -q        # Windows；22 passed
uv run pytest tests/ -q                             # 或 uv

# 前端
cd frontend-react
npm install
npm run dev                        # 5173；BACKEND_PORT=8000 可改代理目标
npx tsc -b --pretty false          # 类型检查
npm run build                      # 生产构建
npx vitest run                     # 7 passed

# 文档
cd docs && npm run docs:dev
```

**Windows 构建坑**：`vite build` / `vitest` 可能因沙箱限制无法写系统 `%TEMP%` →
先把 `$env:TEMP`/`$env:TMP` 指向仓库内目录（如 `frontend-react/.esbuild-tmp`）。

**vite 缓存坑**：`node_modules/.vite` 删不掉时用 `Rename-Item` 移走再启动，不要强行删除。

## 3. 架构地图

```
POST /api/v1/chat/completions (SSE)
└─ HARNESS_MODE=on → backend/app/harness/
   ├─ stream_harness.py   # SSE 生成器：心跳(shield) / 瞬时重试 / HITL / usage 收尾
   ├─ agent_factory.py    # Agent 单例 + spec 指纹重建
   ├─ sse_bridge.py       # deepagents 事件 → SSE（reasoning/tool/sql/result/chart）
   ├─ sql_gate.py(+middleware)  # 读写分类 → allow/ask/deny；ask → interrupt 等审批
   └─ tools/data_tools.py # get_table_schema / run_sql / search_knowledge / make_chart

legacy 13 节点编排：backend/app/graph/（已归档 tag legacy-graph-13node，勿新增功能）
```

关键文件：

| 关注点 | 文件 |
|---|---|
| 事件溯源 / 投影 | `backend/app/core/event_sourcing.py`（`derive_messages` 补 `turn_index`） |
| Token 用量 / 上下文 | `backend/app/core/usage_metrics.py`、`api/v1/chat.py::_usage_window` |
| LLM provider / 思考 / **reasoning 补丁** | `backend/app/core/llm.py` |
| provider 配置与运行时参数 | `backend/app/api/v1/config_api.py`、`backend/configs/llm_providers.json` |
| 前端 SSE 协议 / reducer / 历史映射 | `frontend-react/src/sdk/{protocol,reducer,history}.ts` |
| 会话 / 流 / 用量 / 轮次状态 | `frontend-react/src/stores/chat.ts`（`isGenerating` 才是"生成中"） |
| 深度思考 / 三弹窗 / 轮次切换 | `components/chat/{DeepThink,StatPopovers,TurnNavigator}.tsx` |
| 图标 / Markdown / React Bits | `components/bits/{Icon,Markdown}.tsx`、`components/bits/reactbits/` |

## 4. 协议与契约（改前必读）

**SSE 事件 19 类，只增不改**：`thread_id` `status` `token` `reasoning` `thinking` `tool_call`
`tool_result` `sql` `result` `chart` `plan` `clarification` `error` `title` `done`
`approval_required` `quality_feedback` `node_started` `usage`

**`usage`（扁平）**：`input_tokens/output_tokens/cached_tokens/uncached_input_tokens/total_tokens/
cache_hit_ratio/estimated/turns/steps` + `context{system_prompt,tool_defs,messages,window,used_pct}`。
窗口优先级：`provider.context_window` > `settings.CONTEXT_WINDOW` > 192000。

**字段口径（踩过坑，别改回去）**：

- `sql` 事件可能是 `ev.sql` 或 `ev.content` → 前端取 `ev.sql || ev.content`。
- 落库 `_es_flush` 取 `payload.content or payload.sql`；`_project` 对旧数据从 `payload.sql` 兜底。
- `reasoning` 是流式增量：**落库前必须合并连续片段**（否则历史碎成每 2 字一张卡），前端
  `mapProjectedMessages` 也会合并相邻片段。
- 投影消息的 `turn_index` 来自 `session_events.node_index`；前端据此做「第 N/M 轮」切换，
  旧数据无该字段时自动平铺。

## 5. 硬约束（违反会出事）

1. **读数据随意，改数据必批**：写类 SQL 必须经 `sql_gate` 人工审批；正则 + LLM 双重分类；敏感字段脱敏。
2. **HITL 要求同进程**：`core/hitl.py` 的 waiter 是进程内字典；多 worker/多副本前必须改 Redis
   pub/sub 或粘性会话。
3. **不要重启用户的服务**：后端/前端进程由用户掌控；代码改动靠 `--reload`，配置改
   `backend/configs/*.json`（watchdog 热更新）。
4. **`core/llm.py` 的 reasoning 补丁是模块加载期执行的**——改动后必须整进程重启才生效。
5. **`enable_thinking` / `reasoning_effort` 必须走 `extra_body`**：放 `model_kwargs` 会让
   openai SDK 抛 `unexpected keyword argument`（thinking=false 时必现）。
6. **前端生成中判断用 `store.isGenerating`**，不要用 `isLoading`（它同时用于历史加载，
   会把历史会话误显示成"深度思考中"）。
7. 新方言走 `app/db/dialects/`，不改核心 Agent 逻辑。

## 6. 前端视觉约定（2026-10 定版）

- **单深色主题**，无亮色切换。层级靠背景明度：`#0a0a0b / #101012 / #141416 / #1c1c1f`；
  边框用 `rgba(255,255,255,0.07)`；**不要新增分隔线**（侧栏底、读数条、弹窗标题行都已去掉）。
- 图标只走 `<Icon name="..." size={14|16} />`（语义名 → `@ant-design/icons`）；
  不要再引入图标库或自建字体图标（本项目曾因漏搬 webfont 的 3229 条字形映射导致全站空白）。
- 字体：`--font-sans`（MiSans VF）、`--font-mono`（JetBrains Mono，**必须带 MiSans 中文兜底**）；
  最小字号 12px，弹窗键值行 14px。
- 交互语言：hover 用背景 `rgba(255,255,255,0.05~0.08)`，不用描边；模型菜单参数面板为**悬浮展开**。

## 7. 验证（门禁）

1. `npx tsc -b --pretty false` + `npm run build`
2. `npx vitest run`（7）+ `pytest tests/ -q`（22）
3. **MCP 端到端**（chrome-devtools 真实页面 + 真实 HTTP/SSE/DB）——**单测全绿不代表可用**，
   本仓库反复出现「单测通过但真实链路炸」（温度硬编码、事件字段名不匹配、checkpointer 缺失、
   reasoning 被适配层丢弃、`enable_thinking` 参数位置错误）。
4. 改动涉及真实流式时，至少验证：`thread_id → reasoning? → tool_call → sql → result →
   token → usage → done` 事件序列完整。

## 8. 当前环境注意

- **DashScope 免费额度已耗尽**（2026-10-18 实测 `qwen3.7-flash` → `403 Free quota exhausted`），
  对话不可用；需充值或在配置中心启用其他 provider（`nemotron` 需 OpenRouter key）。
- `reasoning_effort` 是否被 DashScope 兼容模式接受，待额度恢复后验证；不支持时保持空值。
- 人工门禁样本 `backend/configs/harness_review.md` 指标 3/4 仍待判；nemotron 附录待上游恢复。
