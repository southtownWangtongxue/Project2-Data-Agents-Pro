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
  - icon: 🛡️
    title: 安全可控
    details: 读数据随意，改数据必批——所有写操作须经管理员人工审批后执行，搭配正则+LLM 双重 SQL 审计。
  - icon: ⚡
    title: 实时流式体验
    details: SQL 生成、数据分析全程逐字流式输出，节点进度通过任务清单实时更新（running spinner→completed checkmark），完成后自动折叠。
  - icon: 🔌
    title: 多方言适配
    details: 支持 MySQL、PostgreSQL、SQL Server、Oracle 四种数据库方言，新增数据库仅需配置，无需修改 Agent 核心代码。
  - icon: 🧠
    title: Plan-and-Execute + ReAct
    details: 13 节点 LangGraph 工作流（意图合并、质量评估、降级兜底），支持多轮对话追问、图表快捷路径、Human-in-the-loop 审批中断。
  - icon: 📋
    title: 智能去重展示
    details: SQL 仅格式化卡片一处展示，分析文本流式 Markdown 输出，工具卡片过滤冗余字段，避免信息重复干扰阅读。
  - icon: ⚡
    title: 流式响应
    details: 基于 FastAPI SSE 流式传输，首字节延迟 < 1s，简单查询端到端 < 5s，复杂查询 < 15s。
---

## 架构全景图

```
┌─────────────────────────────────────────────────────────────┐
│                        表现层 (Frontend)                     │
│          Vue 3 + Element Plus + ECharts + Pinia             │
│            ChatBox  │  ChartRenderer  │  AdminPanel          │
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
| [架构设计](./guide/architecture.md) | 分层架构、Hermes 多智能体模式、技术选型 |
| [工作流详解](./guide/workflow.md) | LangGraph 状态图、Human-in-the-loop 机制 |
| [API 文档](./api/introduction.md) | 接口鉴权、对话接口、审批回调 |
| [RAG 知识库](./advanced/rag-config.md) | Milvus 配置、文档上传、检索调优 |
| [新增数据库](./advanced/database-access.md) | 方言配置、连接接入 |
| [安全机制](./advanced/security.md) | SQL 审计、数据脱敏、审批流 |
| [前端开发](./develop/frontend-dev.md) | Vue 3 组件开发、SSE 集成 |
| [Agent 开发](./develop/agent-dev.md) | 新增 Worker Agent、Graph 注册 |

## 核心原则

> **读数据随意，改数据必批** —— 所有 SELECT 查询自动执行，所有 INSERT/UPDATE/DELETE/DROP 等写操作必须经过管理员人工审批后执行。

## 技术栈

| 层级 | 技术选型 |
|------|---------|
| 后端框架 | Python 3.10+, FastAPI (SSE 流式) |
| Agent 编排 | LangGraph 1.x (有状态工作流 + 人工打断) |
| Agent 框架 | LangChain 1.x, deepAgents 0.5.x |
| 前端 | Vue 3 + Vite + Element Plus + ECharts |
| ORM | SQLAlchemy (多方言适配) |
| 向量库 | Milvus 2.x |
| 缓存/状态 | Redis |
| 大模型 | 私有化部署 Qwen / GLM |
| 部署 | Docker Compose (开发), Kubernetes (生产) |
