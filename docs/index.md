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
    details: 业务人员无需掌握 SQL，直接用自然语言提问即可获得查询结果、可视化图表和数据分析报告。
  - icon: ⚡
    title: 实时流式体验
    details: SQL 生成与数据分析全程 SSE 流式输出，任务清单实时展示节点进度。
  - icon: 🛡️
    title: 安全可控
    details: 读数据随意，改数据必批——写操作须经对话内人工审批，正则 + LLM 双重 SQL 审计与数据脱敏。
  - icon: 🧠
    title: Multi-Agent 协同
    details: 专职 Agent 经 LangGraph 工作流协同，支持质量门、多轮追问与 Human-in-the-loop。
  - icon: 📊
    title: 智能可视化
    details: 自动生成 ECharts 配置，查询结果可导出 CSV / Excel。
  - icon: 🔌
    title: 多数据源适配
    details: MySQL、PostgreSQL、SQL Server、Oracle；新增方言以配置扩展，无需改 Agent 核心。
  - icon: 🧾
    title: 对话内审批
    details: 高危 SQL 在 SSE 流内挂起，管理员通过/拒绝后同一条流续跑。
  - icon: 🎛️
    title: 配置中心
    details: 模型、技能、MCP、审批策略在管理台统一配置；运行时 JSON 本地生成、不入库。
  - icon: 🧩
    title: React 工作台
    details: 当前前端在 frontend-react/（React 19 + Ant Design X）；Vue 版冻结于 frontend/。
---

## 从这里开始

| 你想… | 去看 |
|------|------|
| 本地跑起来 | [快速开始](/guide/quick-start) |
| 理解整体架构 | [架构设计](/guide/architecture) · [工作流](/guide/workflow) |
| 接 API / 审批 / 安全 | [鉴权](/api/introduction) · [对话接口](/api/chat-api) · [安全机制](/advanced/security) |
| 改前端或 Agent | [前端开发](/develop/frontend-dev) · [Agent 开发](/develop/agent-dev) |
| 查历史设计/研究笔记 | [归档说明](/archive/) |

::: tip 核心原则
**读数据随意，改数据必批** — SELECT 自动执行；INSERT/UPDATE/DELETE/DDL 等写操作必须经管理员审批。
:::
