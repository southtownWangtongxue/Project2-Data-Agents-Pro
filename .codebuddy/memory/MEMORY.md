# 长期记忆 (MEMORY.md)

## 项目：DataAgent Pro（多 Agent 数据分析平台）
- 技术栈：FastAPI(async+SSE) 后端 + Vue3/Vite/ElementPlus/Pinia 前端；LLM 为私有部署 Qwen/GLM。
- 后端根目录 `backend/`，入口 `app/main.py`；前端 `frontend/`（`npm run dev` 端口 5173）。
- 配置由 `backend/configs/*.json` 经 `ConfigManager` 热加载；LLM provider 在 `llm_providers.json`。

## 关键服务/启动
- 后端启动：`cd backend && uv run uvicorn app.main:app --reload --port 8000`
- 默认管理员：`admin` / `12345678`（见 `backend/app/models/seed.py`，写入 `da_sys_user` 表）。

## 数据库约定（重要，2026-07-30 确认）
- 应用与业务库 `jb_bi`（`.env` 的 `MYSQL_DATABASE`）**共用同一 MySQL 实例**。`jb_bi` 既有业务数据，也承载本系统的元数据表。
- 本系统登录账号表 = **`da_sys_user`**（若依风格结构：`user_name` 主键 / `password` / `user_type` / `nick_name` / `status` / `del_flag` / `login_ip` / `login_date`）。**不是** `sys_user`——`jb_bi.sys_user` 是一张结构完全不同的业务表（列：`id/user_code/user_name/passwd/dept_code/allow_login/...`），二者不能混用。
- 历史背景：原 `sys_user` 表名与业务 `sys_user` 冲突导致启动报 `Unknown column 'sys_user.password'`。修复为 `da_sys_user`（`app/models/user.py` 的 `__tablename__`），`chat_sessions`/`chat_nodes` 维持原表名不动。
- 管理员判定：保留内置 `admin` 特殊账号（seed 写入 `da_sys_user`，`user_type='00'`），独立于业务用户。
- 注意：`jb_bi.chat_nodes` 已被应用 ALTER 加过 `run_id` 列（启动自动执行的，已 COMMIT），属正常元数据演进。

## 已验证的坑（重要）
1. **后端 reloader 偶发不可靠**：uvicorn 父进程 logging 配置 `formatter 'default'` 在 stdout 被重定向时抛 `isatty` 错误，导致文件改动后热重载不生效。怀疑改动未生效时，先 `taskkill /f /im python.exe` 干净重启再验证。
2. **Windows 下勿用 `asyncio.create_subprocess_exec`**：uvicorn 事件循环策略下会抛 `NotImplementedError`。子进程相关逻辑改用 `subprocess.Popen` + 线程读取（带超时）。
3. Skill 实体目录：`app/skills/skills/`（已安装落盘）与 `app/skills/catalog/`（安装模板来源）；路径计算需从 `app/api/v1/config_api.py` 上溯 3 层到 `app/`。
4. **LLM 免费额度/限流**：默认 provider `zhipu-glm4-flash` → 实际调用 model=`glm-4.5-air`，base=`https://open.bigmodel.cn/api/paas/v4`（智谱 BigModel）。对话报 `Connection error [INTERNAL_ERROR]` 即该外部端点连接/免费额度问题，非代码缺陷。其他 provider：`qwen-default`→`qwen3.6-35b-a3b`、`qwen-flash`→`qwen3.6-flash`。切勿并发运行多个测试实例，否则免费 LLM 限流 → SSE 流 HTTP200 后无事件 → 超时重试死循环。前端已能正确展示该错误并提供"重试"按钮。
   - **2026-07-31 实测外部额度状态**：① 智谱 Embedding 接口 `embedding-3`（`.env` 的 `EMBEDDING_API_KEY=740b1b92...`，base `https://open.bigmodel.cn/api/paas/v4`）返回 `429 余额不足或无可用资源包` → 知识库上传 .txt 必然失败，需充值。② 对话 LLM 免费额度耗尽时（尤其 task 模式 agentic 多轮调用）会返 `403 Free quota exhausted (AllocationQuota.FreeTierOnly)` 或优雅降级为"无法回答此问题"。**全量测试/浏览器验证中出现的对话失败基本都源于此，非代码缺陷**。
5. **诊断实际模型**：`app/core.llm.py` 的 `describe_route()` 可打印 `provider_id/model/base_url/api_key前缀`；chat.py 在 `_stream_chat`/`_stream_chat_deepagent` 入口及两处异常均记录该路由，且前端报错信息带 `（实际模型: xxx）`，便于排查"调了哪个模型/为什么报错"。
6. **全量测试脚本** `scripts/run_full_test.py`：一键完成 清理→功能模块 API 测试→对话模式(data/report/doc/task/多轮)→生成 `测试报告.md`。阶段3对话最慢（report 模式生成长文可能超时）；SSE 探针 `_sse_chat` 超时已于 2026-07-21 由 120s 上调至 300s。运行方式：`cd backend && uv run python ../scripts/run_full_test.py`。
7. **Chrome DevTools MCP 浏览器锁**：若报 `browser is already running for ...\chrome-devtools-mcp\chrome-profile`，是上会话遗留 chrome 进程占用 profile 锁。用 PowerShell `Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*chrome-devtools-mcp*' } | Stop-Process -Force` 清理后，MCP 可重新拉起干净浏览器。前端模式切换 `.mode-selector` 菜单由 `mouseenter` 触发（非 click），项 class 为 `.mode-menu-item`，可脚本化点击切到「通用任务」。
8. **DeepAgent 凭证传递陷阱（2026-07-22 修复）**：`harness.py` 原 `_build_model_string()` 返回 `"openai:glm-4.5-air"` 字符串给 `create_deep_agent`，底层 `init_chat_model("openai:...")` 会读 `OPENAI_API_KEY`/`OPENAI_BASE_URL` 环境变量——而 `.env` 中这两个是 DashScope 的 key + 默认 `api.openai.com`，导致 task 模式调用智谱时 Connection error（但独立 `init_chat_model(api_key=..., base_url=...)` 正常）。修复：`_build_model()` 显式构建 `BaseChatModel` 实例，注入当前 provider 的 `api_key`/`base_url` + `use_responses_api=False`（智谱不兼容 Responses API）。注意 `get_deep_agent()` 缓存全局单例，改 `harness.py` 后必须整进程重启（uvicorn reload 不清单例）。
   - **2026-07-31 补充修复**：`_build_model()` 原 `mgr.resolve_api_key(provider)` 在 `provider=None`（未指定 model 且无默认 provider 时 `get_llm_config(None)` 返回 None → `set_provider(None)`）时崩 `AttributeError: 'NoneType' object has no attribute 'get'`，导致 task 模式 SSE 流中断。改为复用 `app/core/llm.py` 的 `_resolve_key_and_base(provider)`（对 None 回退 settings.LLM_API_KEY/LLM_BASE_URL），与 legacy 模式 `_stream_chat` 行为一致。
9. **DeepAgent 不 streaming（2026-07-22 修复）**：原 `_stream_chat_deepagent` 的 `agent.astream()` 默认 `stream_mode="updates"`，按节点整块返回消息。修复：`astream(input_data, config, stream_mode=["updates", "messages"])`，双模式并行——"messages" 模式逐 token 产生 `AIMessageChunk`，"updates" 模式处理工具调用/完成事件。
10. **DeepAgent 流式输出 UI 破碎（2026-07-22 修复）**：逐 token 输出时发了 `type: "text"` 事件 → 前端 `onText` 每事件新建一条消息（`messages.value.push`），导致每个字符独立为一个消息块。修复：改为 `type: "token"` → 前端 `onToken` 通过 `activeTokenMsgId` 增量追加到同一条消息。
11. **侧边栏不显示用户输入（2026-07-22 修复）**：`list_sessions` 永远返回 `"question": ""`，而前端的 `ChatSidebar` 已支持 `{{ s.title || s.question?.slice(0, 30) }}` 兜底显示。修复：`list_sessions` 额外查询 `ChatNode` 取 `node_index=0` 的 `question` 字段。
12. **联网搜索（2026-07-22 实现）**：`web_search` 参数原为死代码（传到 `_stream_chat_deepagent` 后未被使用）。修复：以**固定工具**方式（非 Skill 机制）注册 `web_search_tool`（`app/deepagent/tools.py`，百度搜索 API，key/url 来自 `.env` 的 `BAIDU_API_KEY`/`BAIDU_WEB_SEARCH_URL`），在 `workflow.py` 的 `get_deep_agent()` 中合并到 `all_tools = skill_tools + get_fixed_tools()`。`web_search=True` 时注入系统提示（告知模型可调用该工具）。已清理旧的 DDGS 注入代码和 baidu-search 技能文件。注意 `get_deep_agent()` 缓存全局单例，改 `tools.py`/`workflow.py` 后需整进程重启。
13. **DeepAgent UI 重构（2026-07-22）**：
    - SSE 事件：工具调用从通用 `status` 改为结构化 `tool_call`（含 `name`+`args`）和 `tool_result`（含 `name`+`result`+`status`）。
    - 前端 `onToolResult`：将同名的 `tool_call` 升级为 `tool_chain` 单卡片（合并输入+结果），减少视觉噪音。
    - Chat.vue 新增 `tool_chain` 类型渲染（展开显示输入参数 + 返回结果）。
    - `__end__` 分步诊断日志：抵达、标题生成、节点保存、会话创建各阶段独立日志。
    - 文件：`useSSE.ts`(事件路由)、`chat.ts`(store)、`Chat.vue`(渲染)、`chat.py`(SSE事件)。

## AntDesignX Vue 新对话页（2026-08-05 完成，浏览器验证通过）
- **目标**：渐进式接入 `ant-design-x-vue`，新增 `/chat-x` 路由 → `frontend/src/views/ChatXVue.vue`（XProvider 包裹），后端零改动、前端数据层复用 `stores/chat.ts` + `composables/useSSE.ts`。
- **依赖**：`ant-design-x-vue@1.6.0` / `ant-design-vue@4.2.6` / `@ant-design/icons-vue@7.0.1`。⚠️ **包内无 CSS 文件**，样式由 cssinjs 在 `XProvider` 内运行时注入，勿 `import 'ant-design-x-vue/dist/index.css'`。
- **组件目录** `frontend/src/components/x/`：`XConversations.vue`(+`XConvLabel.vue` 内联重命名)、`XBubbleList.vue`、`MessageRenderer.vue`、`XSender.vue`、`XWelcome.vue`、`XThoughtChain.vue`。
- **官方 API 修正（集成方案文档原有误）**：Welcome 无 `suggestions`/`click`（建议用 `Prompts`，item 主字段 `label`）；Sender 无 `disableSend`/`clear`（`loading` 自动切停止按钮触发 `@cancel`）；ThoughtChainItem 无 `children`；`Sender.Header` 是 `Sender` 静态子组件（props `open/title/closable/onOpenChange`，需 `:open`+`@open-change` 双向绑定，`open=false` 时 DOM 移除除非 `forceRender`）。
- **样式根因（关键！）**：`XProvider` 必须显式传 `:theme="{ algorithm: theme.darkAlgorithm, token: {...} }"`（`theme` 从 `ant-design-vue` 导入），否则 X 组件内部用 antdv 默认浅色 token（白底白字，与深色页面冲突）。品牌色紫色 `#7056F8`（ultramodern 风格）。
- **占满右侧**：清除所有 `max-width` 残留（`XBubbleList` roles、`XWelcome` `.xw-prompts`/提示卡、`ClarifierCard`/`ExecutionCard` `82%`、`.xr-thought` `82%`），容器已全宽 1640px。
- **模型路由（修复 403）**：`stores/chat.ts` 新增 `currentModel`（从 `localStorage.selectedModelId` 读）+ `setCurrentModel()`；`sendMessage` 内 `activeModel = model || currentModel.value`，所有发送入口统一走 `store.sendMessage`。
- **模式切换/联网搜索** 移入 `Sender.Header` 弹出面板，prefix 仅留模型选择器 + 设置按钮。
- 开发计划文档：`docs/plans/2026-08-05-ant-design-x-vue-integration.md`（6 阶段 + 提示词 + 实施记录 4.7/4.8/4.8.1/4.8.2）；已集成到 `docs/.vitepress/config.mts` 与 `docs/index.md`。

## 用户约定
- 规则要求：创造性工作前先走 brainstorming 探索；代码改动后须用 Chrome DevTools MCP 做端到端浏览器验证（前后端都需启动）。
