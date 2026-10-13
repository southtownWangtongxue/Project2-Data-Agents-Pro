---
layout: home
hero:
  name: "DataAgent Pro"
  text: "智能业务数据交互平台"
  tagline: 基于 Multi-Agent 协同架构，让业务人员通过自然语言安全、高效地获取数据洞察
  actions:
    - theme: brand
      text: 快速开始
      link: /guide/quick-start
    - theme: alt
      text: 架构设计
      link: /guide/architecture

features:
  - icon: 💬
    title: 零门槛交互
    details: 业务人员无需掌握 SQL，直接用自然语言提问即可获得查询结果、可视化图表和数据分析报告。前端实时任务清单展示每步进度。
  - icon: ⚡
    title: 实时流式体验
    details: SQL 生成、数据分析全程逐字流式输出，节点进度通过任务清单实时更新（running spinner→completed checkmark），完成后自动折叠。
  - icon: 🛡️
    title: 安全可控
    details: 读数据随意，改数据必批——所有写操作须经管理员人工审批后执行，搭配正则+LLM 双重 SQL 审计与数据脱敏。
  - icon: 🧠
    title: Multi-Agent 协同
    details: 8 个专职 Agent 通过 13 节点 LangGraph 工作流协同，Plan-and-Execute + ReAct 质量评估，支持多轮追问与 Human-in-the-loop 审批中断。
  - icon: 📊
    title: 智能可视化
    details: 自动生成 ECharts 图表配置，支持柱状图、饼图、折线图等，查询结果一键导出 CSV / Excel。
  - icon: 🔌
    title: 多数据源适配
    details: 支持 MySQL、PostgreSQL、SQL Server、Oracle 四种数据库方言，新增数据库仅需配置，无需修改 Agent 核心代码。
  - icon: 🧾
    title: 对话内审批
    details: 审批由独立页面收敛为对话内 Human-in-the-loop：图在断点挂起 SSE 流，管理员通过/拒绝并附意见后同一条流续跑到底。
  - icon: 🎛️
    title: 会话化配置中心
    details: 模型能力（工具调用 / 图片输入 / 思考模式与思考强度）、技能、MCP、定时任务与审批策略统一在配置中心管理。
  - icon: 🧩
    title: 官方组件基线
    details: 前端基于 Vite + React 19 + Ant Design X 2.9 构建，交互对齐官方独立式样板间，XStream 解析 SSE，x-markdown 承载流式 Markdown。

## 平台概览

| 指标 | 数值 | 说明 |
|------|------|------|
| Agent 数 | 8 | planner / schema_retriever / sql_coder / executor / analyst / reporter / misc / quality 等专职 Agent |
| 工作流节点 | 13 | LangGraph 状态图节点数（含审批中断与降级兜底） |
| SSE 事件类型 | 18 | thread_id / status / thinking / reasoning / token / tool_call / tool_result / sql / result / chart / plan / clarification / error / title / done / approval_required / quality_feedback / node_started |
| SQL 方言 | 4 | MySQL / PostgreSQL / SQL Server / Oracle |

::: tip 前端已切换为 React 版
应用内不再保留独立介绍首页，根路由直接进入 `/chat` 对话工作台。原前端（Vue 3）已冻结归档在 `frontend/`，历史版本可按 tag `vue-legacy` 检出；当前维护版本位于 `frontend-react/`。
:::
---

## 架构全景图

```
┌─────────────────────────────────────────────────────────────┐
│                        表现层 (frontend-react)                │
│        React 19 + Vite + Ant Design X + XStream + x-markdown  │
│           Chat 工作台  │  轨迹抽屉  │  配置中心                 │
└──────────────────────────┬──────────────────────────────────┘
                           │  HTTP/SSE
┌──────────────────────────▼──────────────────────────────────┐
│                     网关层 (FastAPI Gateway)                  │
│        POST /chat/completions  │  POST /approve             │
│        GET  /datasource/list   │  POST /export/excel        │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                  编排层 (LangGraph 13 节点)                     │
│   ┌────────────────────────────────────────────────────┐    │
│   │  clarify_plan → schema → sql_coder → security     │    │
│   │       ↓                                            │    │
│   │  execute_sql → quality_gate → analyst             │    │
│   │       ↓                                            │    │
│   │  reporter / answer → finish → Stream Output        │    │
│   │       ↓ (写操作)                                    │    │
│   │  [中断] → Human Approval → Resume/Reject           │    │
│   └────────────────────────────────────────────────────┘    │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                   存储层 (Infrastructure)                     │
│   MySQL / PostgreSQL / SQL Server / Oracle    (业务数据库)    │
│   Milvus  (向量知识库)    Redis  (状态快照)                   │
└─────────────────────────────────────────────────────────────┘
```

## 快速链接

| 章节 | 说明 |
|------|------|
| [快速开始](./guide/quick-start.md) | 环境准备、项目启动、首次运行 |
| [架构设计](./guide/architecture.md) | 分层架构、Harness 多智能体模式、事件溯源/能力接缝/分层提示词（feature flag 门控）、技术选型 |
| [Harness 落地差距分析](./reference/harness-landing-gap-analysis.md) | 架构落地状态基线：已落地清单、差距项、分阶段建议 |
| [工作流详解](./guide/workflow.md) | LangGraph 状态图、Human-in-the-loop 机制 |
| [API 文档](./api/introduction.md) | 接口鉴权、对话接口、审批回调 |
| [RAG 知识库](./advanced/rag-config.md) | Milvus 配置、文档上传、检索调优 |
| [新增数据库](./advanced/database-access.md) | 方言配置、连接接入 |
| [安全机制](./advanced/security.md) | SQL 审计、数据脱敏、审批流 |
| [前端开发](./develop/frontend-dev.md) | React 19 + Ant Design X 组件开发、SSE 事件接入 |
| [Agent 开发](./develop/agent-dev.md) | 新增 Worker Agent、Graph 注册 |
| [对话界面设计](./reference/chat-ui-playground-alignment.md) | 对话页对齐官方独立式样板间的结构、组件层级与主题规范 |

## 核心原则

> **读数据随意，改数据必批** —— 所有 SELECT 查询自动执行，所有 INSERT/UPDATE/DELETE/DROP 等写操作必须经过管理员人工审批后执行。

## 技术栈

| 层级 | 技术选型 |
|------|---------|
| 后端框架 | Python 3.10+, FastAPI (SSE 流式) |
| Agent 编排 | LangGraph 1.x (有状态工作流 + 人工打断) |
| Agent 框架 | LangChain 1.x, deepAgents 0.5.x |
| 前端 | React 19 + Vite + Ant Design X 2.9 + x-markdown + ECharts（历史 Vue 3 版冻结于 `frontend/`） |
| ORM | SQLAlchemy (多方言适配) |
| 向量库 | Milvus 2.x |
| 缓存/状态 | Redis |
| 大模型 | 私有化部署 Qwen / GLM |
| 部署 | Docker Compose (开发), Kubernetes (生产) |
