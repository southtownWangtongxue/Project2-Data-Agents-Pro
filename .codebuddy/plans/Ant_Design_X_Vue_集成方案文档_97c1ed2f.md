---
name: Ant Design X Vue 集成方案文档
overview: 产出一份完整的《Ant Design X Vue 集成方案》Markdown 文档，涵盖前端安装/配置/核心 AI 组件用法，以及后端 API 与消息历史数据设计，并确保前后端数据交互格式与组件库预期 Props 结构对齐。不改动现有代码。
todos:
  - id: brainstorm-integration
    content: 使用 [skill:brainstorming] 探索并确认集成方案的目标、接入路线（全量替换 vs 渐进式嵌入）与文档结构
    status: completed
  - id: write-frontend-section
    content: 撰写前端章节：ant-design-x-vue 安装命令、全局/按需引入、Bubble/Conversations/Sender/Welcome/ThoughtChain/useXAgent/XStream 用法
    status: completed
    dependencies:
      - brainstorm-integration
  - id: write-backend-section
    content: 撰写后端章节：对话发送/接收接口、SSE 流式实现要点、会话历史接口与 MySQL+Redis 数据结构设计
    status: completed
    dependencies:
      - brainstorm-integration
  - id: write-alignment-section
    content: 撰写数据格式对齐章节：SSE 事件与会话接口到组件 Props 的映射表及前端适配层设计
    status: completed
    dependencies:
      - write-frontend-section
      - write-backend-section
  - id: assemble-doc
    content: 汇总成 docs/AntDesignXVue集成方案.md，通读校对字段名、接口路径与现有代码严格一致
    status: completed
    dependencies:
      - write-frontend-section
      - write-backend-section
      - write-alignment-section
---

## 需求概述

基于 Ant Design X Vue 官方文档（antd-design-x-vue.netlify.app），为 DataAgent Pro 项目产出一份**完整的前后端集成方案文档（Markdown）**，不改动现有任何代码。

## 产品范围

方案文档需完整回答用户提出的三个维度：

1. **前端集成**：说明如何安装和配置 `ant-design-x-vue` 组件库——npm 安装命令、全局注册或按需引入方式、以及与 AI 对话相关的核心组件（Bubble/Bubble.List、Conversations、Sender 等）的使用配置。
2. **后端 API 设计**：说明支撑前端 AI UI 组件功能需要哪些接口——对话消息的发送/接收接口、流式响应（SSE/WebSocket）的实现要点、消息历史管理的数据结构设计。
3. **数据格式对齐**：确保前后端的数据交互格式与组件库预期的 Props 结构保持一致，给出字段映射表与前端适配层设计。

## 交付形式

用户已明确选择「完整方案文档（Markdown）」，落盘到 `docs/` 目录（建议 `docs/AntDesignXVue集成方案.md`），不改动现有代码。

## 核心约束

- 文档须与 DataAgent Pro 现有后端契约严格一致（复用现有 `POST /chat/completions` SSE 协议、`/chat/sessions` 系列接口、`/chat/suggestions`），做到"改前端组件、不动后端"即可完成对接。
- 必须准确引用 Ant Design X Vue 官方 API：npm 包名为 `ant-design-x-vue`（依赖 `ant-design-vue` + `@ant-design/icons-vue`）；Conversations 选中回调为 `onActiveChange`；Bubble.List 的 `roles` 支持对象/函数形式；useXAgent 支持预设协议与自定义 request 两种模式。

## 文档依据的现有技术栈（来自代码调研，非新增选型）

- 前端：Vue3 + Vite + TypeScript + ElementPlus + Pinia + marked + sql-formatter + echarts。现有自定义 Chat UI 位于 `frontend/src/views/Chat.vue`，SSE 解析在 `frontend/src/composables/useSSE.ts`，消息状态在 `frontend/src/stores/chat.ts`。
- 后端：FastAPI（async + SSE），对话入口 `backend/app/api/v1/chat.py`。鉴权为 JWT Bearer（`get_current_user`）。
- 历史存储：MySQL `chat_sessions` + `chat_nodes` 表存元数据，Redis checkpointer 存 LangGraph 完整状态用于恢复。

## 文档技术方案要点

### 前端部分

- **npm 安装**：`npm install ant-design-x-vue ant-design-vue @ant-design/icons-vue`，并在文档中明确标注包名坑（`ant-design-x-vue` 而非 `@ant-design-x-vue/ant-design-x-vue`）。
- **引入方式**：给出两种方案——(A) 全局注册 `app.use(...)`；(B) 按需引入，推荐用 `unplugin-vue-components` + `unplugin-auto-import` 配置 `AntDesignXVueResolver`，并配套样式引入。
- **核心组件**：Bubble/Bubble.List（`items`、`roles`、`typing`、`messageRender`）、Conversations（`items` 结构、`onActiveChange`、`menu` 操作）、Sender（`value`/`onSubmit`/`loading`）、Welcome、ThoughtChain、useXAgent/useXChat/XStream（自定义 `request` + `TransformStream` 解析 SSE，`onStream` 获取 AbortController 用于中断）。

### 后端部分（复用现有契约）

- **对话接口**：`POST /chat/completions`（SSE 流式），请求体 `ChatRequest{messages:[{role,content}],stream,thread_id?,mode,web_search,model}`，响应 `text/event-stream`，事件 `data: {json}\n\n`。
- **流式实现要点**：文档对比 SSE vs WebSocket 选型（本项目采用 SSE）；说明事件格式、`X-Accel-Buffering:no`、心跳/空行保持、前端 `AbortController` 中断、重连策略。
- **历史接口**：`GET/PATCH/DELETE /chat/sessions`、`GET /chat/sessions/{thread_id}`、`GET /chat/suggestions`。
- **数据结构**：MySQL `chat_sessions`（thread_id/user_name/title/created_at/updated_at）+ `chat_nodes`（thread_id/node_index/title/question/run_id）+ Redis checkpointer（messages 等状态）。

### 数据格式对齐（核心章节）

- **SSE 事件 type → 组件 Props 映射表**：如 `token` → useXAgent `onUpdate` 增量拼接；`done` → `onSuccess`；`error` → `onError`；`thinking`/`tool_call`/`tool_result`/`clarification`/`plan` → 结构化消息卡片。
- **`/chat/sessions` 返回 → Conversations.items 映射**：`thread_id`→`key`、`title||question`→`label`、`created_at`→分组。
- **`/chat/sessions/{id}` 恢复消息 → Bubble.List items 映射**：`role/type/content`→`role` 与 `messageRender`；将 `sql/result/chart` 等结构化消息渲染为既有 Vue 子组件（SQL 卡片、结果 el-table、VChart 等）。

## 文档落盘

新建 `docs/AntDesignXVue集成方案.md`，章节完整、代码示例可执行、字段名与现有代码逐一对齐。

## Agent Extensions

### Skill

- **brainstorming**
- Purpose: 在正式撰写方案前，对文档结构、前后端数据映射方式、以及"全量替换 vs 渐进式嵌入"两种接入路线进行探索与确认，避免方案偏离用户预期。
- Expected outcome: 确认文档章节骨架、核心映射策略与推荐接入路线，作为撰写依据。