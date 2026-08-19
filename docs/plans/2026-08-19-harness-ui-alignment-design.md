# Harness 界面对齐改造设计（2026-08-19）

> 参考基准：本地部署 DeepSeek Harness（http://127.0.0.1:3080/）实测界面逻辑与交互。
> 背景：2026-08-19 端到端测试（Chrome DevTools MCP）发现 7 项缺陷（见 `test-screens/端到端测试报告-2026-08-19.md`），本设计基于测试结论对齐 Harness 交互。

---

## 一、对齐目标

| 维度 | Harness 实测行为 | 本项目现状 | 对齐动作 |
|------|-----------------|-----------|----------|
| 界面交互 | 模型/权限/命令菜单均可 **click 展开** | 模型/模式/轮次菜单 **hover-only** | A：click 化 + 外部点击关闭 |
| 历史会话 | 工作区树 + **搜索框** + 相对时间 | 无搜索、无虚拟滚动、100+ 会话堆积 | B：搜索框 + 虚拟滚动 + fork 修复 |
| 多轮对话 | 底部 `1 轮 · 5 步` 统计 | `第 2/2 轮` 导航 | C：轮次统计 + 步骤数 |
| 性能指标 | `用时/首token/tok/s` + LLM/工具耗时明细 | 缺少 LLM/工具耗时拆分，短文本 `0 tok/s` | C：拆分 + 下限保护 |
| 渲染 | 工具行折叠，详情可读 | `tool_chain` 显示 `[object Object]` | D：对象 JSON 序列化 |

---

## 二、改造明细

### A. 菜单 click 化（frontend）

**A1. `Chat.vue` 模型选择器**（约 427-458 行）
- `@mouseenter/@mouseleave` 改为 `@click` 切换 `showModelMenu`
- 加全局点击监听：点击菜单外区域关闭、`Esc` 关闭
- 下拉项仍 `@click` 选择

**A2. `ChatInput.vue` 模式选择器**（约 185-215 行）
- 同上：`@click` 展开 + 外部点击关闭 + `Esc`
- 移除 `modeMenuTimer` 延迟逻辑

**A3. `Chat.vue` 轮次导航**（约 461-499 行）
- 同上 click 化

### B. 历史会话对齐（frontend + backend）

**B1. 搜索框**（`ChatSidebar.vue`）
- 新增顶部搜索输入，按标题/问题过滤 `store.sessions`
- 空结果提示「无匹配会话」

**B2. 虚拟滚动**（`ChatSidebar.vue`）
- 轻量分批渲染：基于容器滚动位置 + IntersectionObserver 增量渲染，避免引入 `vue-virtual-scroller` 重依赖
- 或直接复用原生 `<ul>` + `max-height` + CSS `content-visibility: auto`（浏览器级渲染优化）

**B3. fork 修复（backend）**（`backend/app/api/v1/chat.py` `fork_session` ~1850 行）
- 在复制事件后调用 `_upsert_chat_session(new_thread_id, user_name, title=f"{源标题}(分支)")`
- 需先从 `chat_sessions` 查询源会话标题

**B4. fork 修复（frontend）**（`chat.ts` `forkSession` ~630 行）
- 成功后 `sessions.value.unshift({ thread_id, title, question, created_at, message_count })`
- 并 `loadSessions()` 确保与后端一致

### C. 多轮统计 + 性能条对齐（frontend）

**C1. 轮次统计**（`Chat.vue` statbar 附近）
- 显示「第 N 轮 · M 步」：N 复用 `store.turns.length`，M 复用 `store.tasks.length`（或按节点计数）

**C2. 性能条拆分**（`chat.ts` `finalizePerf` ~229 行）
- `lastPerf` 扩展字段：`llmMs`（首 token 至结束）、`toolMs`（工具执行累计）、`inputTokens`
- 前端累计：SSE `tool_call`/`tool_result` 事件间隔计入 toolMs；token 流计入 llmMs
- **修 0 tok/s**：`tokPerSec = generateMs >= 1000 ? Math.round(tokenCount/generateMs*1000) : null`，前端 `null` 显示「—」

**C3. 性能条 UI**（`Chat.vue` ~872-885 行）
- 对齐 Harness：`用时 Xs · 首token Ys · Z tok/s` + 详情行 `LLM Xs · 工具 Ys · 输出 N tok · 输入 M tok · 缓存命中?%`

### D. 渲染修复（frontend）

**D1. `Chat.vue` `toolExpandContent`**（~266-296 行）
- 对象类型用 `JSON.stringify(v, null, 2)` 替代 `String(v)`，并截断到 500 字符

**D2. `chat.ts` `onToolCall`**（~379-400 行）
- `meta.args` 若为对象则 `JSON.stringify`，杜绝 `[object Object]`

---

## 三、实施顺序

1. D（渲染修复，最严重，改动最小）
2. B（历史会话 + fork，中-严重）
3. A（菜单 click 化，纯前端交互）
4. C（性能条 + 多轮统计）
5. 端到端验证（Chrome DevTools MCP）

---

## 四、验证清单

- [ ] `tool_chain` 展开显示结构化 JSON 而非 `[object Object]`
- [ ] fork 后在侧边栏「今天」立即出现新会话（标题带"(分支)"）
- [ ] 侧边栏搜索过滤正常、长列表滚动流畅
- [ ] 模型/模式/轮次菜单点击展开、点击外部关闭
- [ ] 性能条：短文本显示「— tok/s」而非 0；显示 LLM/工具耗时拆分
- [ ] 多轮显示「第 N 轮 · M 步」
