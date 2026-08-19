# 长期记忆 (MEMORY.md)

## 项目：DataAgent Pro（多 Agent 数据分析平台）
- 技术栈：FastAPI(async+SSE) 后端 + Vue3/Vite/ElementPlus/Pinia 前端。
- **LLM 双配置（2026-08-19 澄清）**：`settings`(`.env`) = dashscope `qwen3.6-flash`（key `sk-8250...`，**可用**）；`llm_providers.json` = `agnes`（apihub，**免费额度已耗尽 403**）+ `qwen-flash`(disabled)。`/suggestions` 走 settings→dashscope；前端聊天走 agnes→**对话当前不可用，须启用 qwen-flash 或等 agnes 充值**。详见 2026-08-19.md。
- 后端根目录 `backend/`，入口 `app/main.py`；前端 `frontend/`（`npm run dev` 端口 5173）。
- 配置由 `backend/configs/*.json` 经 `ConfigManager` 热加载；LLM provider 在 `llm_providers.json`。

## Docker 单体镜像架构（2026-08-13 定稿）
- 单体镜像 `data-agent`（前端+后端一体），根目录 `Dockerfile` 多阶段构建（node dist → python uv sync → `python:3.12-slim`+nginx+supervisor）。
- 容器内：`/app/.venv`、`/usr/share/nginx/html`（dist）、nginx 反代 `/api`→`127.0.0.1:8000`（`proxy_buffering off` 保 SSE）、supervisord 管 backend+nginx。
- 入口 `deploy/entrypoint.sh` 检测空卷复制默认配置后 `exec supervisord`；named volume：agent_configs/skills/resources/logs。
- 热更新边界：configs 改文件即生效；skill 实时落盘；但 **DeepAgent skill 工具集是全局单例 `get_deep_agent()`，新 skill 需重启容器才进工具列表**。部署文档 `docs/guide/deployment.md`。

## 关键服务/启动
- 后端：`cd backend && uv run uvicorn app.main:app --reload --port 8000`。默认管理员 `admin`/`12345678`（写入 `da_sys_user`）。

## JWT 密钥机制（2026-08-17 确认）
- `security.create_access_token()` 用随机 `_JWT_SECRET` 且 payload 无 user_name；login 的 `_generate_token()` 用 `settings.JWT_SECRET`（默认 `dataagent-default-secret-change-in-production`）含 user_name。
- `get_current_user` 用 `settings.JWT_SECRET` 验签 → 生产正常；**测试 token 须用 login 同款逻辑**（`jwt.encode({user_name,user_type,nick_name,exp,iat}, settings.JWT_SECRET, "HS256")`），`tests/test_api.py` 的 `_auth_headers()` 可复用。

## 数据库约定（2026-07-30 确认，重要）
- 应用与业务库 `jb_bi`（`MYSQL_DATABASE`）共用同一 MySQL 实例。
- 登录表 = **`da_sys_user`**（若依风格：`user_name` 主键）；**不是** `sys_user`（`jb_bi.sys_user` 是业务表，结构不同，勿混用）。
- `chat_sessions`/`chat_nodes` 维持原表名；`chat_nodes` 已被 ALTER 加 `run_id` 列（正常）。

## 已验证的坑
1. 后端 reload 偶发不可靠（stdout 重定向时 logging `isatty` 错误）→ 干净重启用 `taskkill /f /im python.exe`。
2. Windows 勿用 `asyncio.create_subprocess_exec`（uvicorn 下抛 NotImplementedError），用 `subprocess.Popen`+线程读取。
3. Skill 目录：`app/skills/skills/`（落盘）与 `app/skills/catalog/`（模板）。
4. Chrome DevTools MCP 浏览器锁：用 PowerShell `Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*chrome-devtools-mcp*' } | Stop-Process -Force` 清理。
5. 前端模型/模式菜单靠 `@mouseenter`/`@mouseleave` 触发（hover-only，键盘/点击不可操作，a11y 差）——已知 UX 缺陷。
6. 全量测试：后端 `cd backend && uv run pytest tests/ -v`；脚本 `scripts/run_full_test.py`（`uv run python ../scripts/run_full_test.py`）。

## DeepAgent 关键架构
- `get_deep_agent()` 全局单例；改 harness/tools/workflow 须整进程重启。
- 凭证：`harness._build_model()` 显式 `BaseChatModel` 注入 provider 的 api_key/base_url + `use_responses_api=False`；用 `_resolve_key_and_base(provider)`，勿用 `init_chat_model("openai:...")`。
- 流式：`astream(stream_mode=["updates","messages"])`，逐 token 发 `type:"token"`（**勿发 `type:"text"`**）。
- 工具事件：SSE 用 `tool_call`(name+args)/`tool_result`(name+result+status)；前端 `onToolResult` 升级为 `tool_chain` 单卡片。
- 联网搜索：固定工具 `web_search_tool`（百度 API，`.env` 的 BAIDU_API_KEY/WEB_SEARCH_URL）。

## 五大改造阶段（2026-08-17 完成，验证通过）
- Phase1 事件溯源 `app/core/event_sourcing.py`（append-only `session_events`，feature `EVENT_SOURCING_ENABLED`）
- Phase2 PromptSection `app/core/prompt_section.py`（feature `PROMPT_SECTION_ENABLED`，7 段 order）
- Phase3 Seam `app/core/seam.py`（feature `SEAM_ENABLED`，search/storage 落地，llm_client 未落地）
- Phase4 流式类型化+ReasoningBlock（`stream_protocol.py` + `ReasoningBlock.vue` 折叠卡片，默认模型可能不输出 reasoning）
- Phase5 动效规范（`design-system.css`：`--motion-duration-*`+`--motion-ease-*`，禁止与 `--transition-*` 简写混用）

## Harness 对齐改造（2026-08-18，16/16 项全部落地，pytest 30/30）
- 后端端点：`/chat/sessions/{tid}/export|fork|trajectory|goal`、`POST /chat/cancel`、`approve.py` 权限校验。
- 前端：`TrajectoryView.vue`、`ChatInput.vue` 命令面板（/export /clear /fork /help /goal）、性能指标条+上下文监控+导出/轨迹按钮+消息反馈（赞/踩）、`ChatSidebar.vue` 按日期分组、`chat.ts` 排队发送+停止生成（用 `asyncio.Event` 标志让 SSE 正常 EOF，勿只 task.cancel()）、`SubagentNode.vue`（task 模式子代理可视化）、`goal` 列。
- 关键坑：SSE 停止不能只 task.cancel()，须 asyncEvent 让生成器 break 正常结束。
- 参考文档：`docs/reference/deepseek-harness-hands-on.md`、`docs/reference/harness-ui-analysis.md`。

## AntDesignX Vue 新对话页（/chat-x，2026-08-05 完成）
- `views/ChatXVue.vue` + `components/x/`（XConversations/XBubbleList/MessageRenderer/XSender/XWelcome/XThoughtChain）。
- `XProvider` 须显式 `:theme="{ algorithm: theme.darkAlgorithm, token }"`；包内无 CSS，勿 import dist css。品牌色紫 `#7056F8`。

## 2026-08-19 端到端测试（用户视角，Chrome DevTools MCP）→ 已全部修复
- **[严重→已修]** `tool_chain` 显示 `[object Object]`：`Chat.vue` `toolExpandContent` 新增 `stringifyValue()`（JSON.stringify），`chat.ts` onToolCall args 对象序列化。
- **[中-严重→已修]** fork 会话不可见：后端 `fork_session` 补写 `chat_sessions`（标题带「(分支)」），前端 `forkSession` unshift + loadSessions。
- **[中→已修]** 模型/模式/轮次菜单 hover-only：全部改为 click 展开 + document 外部点击关闭 + Esc。
- **[中→已修]** 侧边栏无搜索/长列表卡顿：`ChatSidebar.vue` 加搜索框 + `content-visibility:auto` 轻量虚拟滚动。
- **[中→已修]** `0 tok/s`：`lastPerf.tokPerSec` generateMs<1000 时为 null，前端显示「—」。
- **[中→已修]** 性能条增强：`lastPerf` 扩展 `llmMs/toolMs/inputTokens`，statbar 显示 `LLM/工具/输出/输入/轮次步数`。
- **[中→已修]** 首轮问候耗时过长：misc_agent 双重推送（StreamContext.push_token + `_stream_tokens` 二次流式）已移除重复；剩余延迟为模型首 token 本身慢。
- **[低→已修]** 新建/切换会话输入框未聚焦：`ChatInput` onMounted focus + `:key` 绑定 currentThreadId 重建。
- **[已修]** 14天前旧会话空白：`get_session_messages` 加 `chat_nodes.question` 节点题兜底。
- **[已修]** 切换会话工具卡片消失：`_project()` 补 TOOL_CHAIN 投影；传统模式 misc_agent/execute_sql/reporter 补 `_track(TOOL_CHAIN)`；工具卡片统一 `🔧 工具名+摘要` 单行折叠。
- **[已知瞬态]** `loadSessions()` fetch abort 后 sessions 空（页面重载时）→ 刷新恢复，可加自动重试。
- 报告：`test-screens/端到端测试报告-2026-08-19.md`；设计：`docs/plans/2026-08-19-harness-ui-alignment-design.md`、`docs/plans/2026-08-19-issues-fix-design.md`。

## 用户约定
- 创造性工作前先走 brainstorming 探索；代码改动后须用 Chrome DevTools MCP 做端到端浏览器验证（前后端都需启动）。
