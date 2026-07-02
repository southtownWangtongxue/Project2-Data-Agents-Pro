# 架构设计

本文档详细阐述 DataAgent Pro 的整体分层架构、多智能体协作模式及技术选型理由。

## 整体分层架构

系统采用 **六层架构**，自顶向下分别为：

```
┌──────────────────────────────────────────────┐
│  表现层     Vue 3 + Element Plus + ECharts    │  用户界面
├──────────────────────────────────────────────┤
│  网关层     FastAPI (REST + SSE Streaming)    │  请求路由
├──────────────────────────────────────────────┤
│  编排层     LangGraph 1.x StateGraph          │  工作流引擎
├──────────────────────────────────────────────┤
│  智能体层   8 个专职 Agent (Hermes 模式)       │  业务逻辑
├──────────────────────────────────────────────┤
│  基座层     LLM Client / RAG / DB Connector   │  基础设施
├──────────────────────────────────────────────┤
│  存储层     MySQL / PG / Milvus / Redis       │  数据持久化
└──────────────────────────────────────────────┘
```

### 表现层

- 基于 **Vue 3** Composition API + **Vite** 构建
- UI 组件库：**Element Plus**
- 可视化：**ECharts**（图表渲染）+ **ECharts JSON** 动态配置
- 状态管理：**Pinia**
- 流式通信：**EventSource (SSE)** 接收后端流式响应

### 网关层

- **FastAPI** 异步框架，提供 REST 接口和 SSE 流式端点
- 核心路由：
  - `POST /api/v1/chat/completions` — 对话入口（SSE 流式返回）
  - `POST /api/v1/chat/approve` — 管理员审批回调
  - `POST /api/v1/chat/stop` — 中断 Agent 执行
  - `GET /api/v1/datasource/list` — 数据源列表
  - `POST /api/v1/export/excel` — 文件导出

### 编排层

- **LangGraph 1.x StateGraph** 作为工作流引擎
- 全局状态对象 `AgentState` 在节点间流转
- 支持 **Human-in-the-loop** 中断/恢复（基于 Redis 快照）
- 条件边实现动态路由和错误短路

### 智能体层

详见 [Hermes 多智能体模式](#hermes-多智能体模式)。

### 基座层

- **LLM Client**：封装 Qwen/GLM 大模型调用，支持统一接口切换
- **RAG Engine**：文档切片 → Embedding → Milvus 向量检索
- **DB Connector**：SQLAlchemy 多方言会话管理

### 存储层

- **业务数据库**：MySQL / PostgreSQL / SQL Server / Oracle（用户真实数据）
- **向量数据库**：Milvus 2.x（知识库文档索引）
- **缓存/状态**：Redis（Graph 中断状态快照 + 限流计数）

---

## Hermes 多智能体模式

DataAgent Pro 采用 **Plan-and-Execute + ReAct** 架构，8 个 Agent 通过 LangGraph 条件路由协作：

```
                 ┌──────────────────────┐
                 │   clarify_plan       │ ← 意图分析 + 执行计划（合并单次 LLM）
                 │   (原 Orchestrator)   │
                 └──────┬───────┬───────┘
                        │       │ (按 intent 条件路由)
          ┌─────────────┼───────┼──────────────┐
          ▼             ▼       ▼              ▼
    ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
    │schema    │ │rag_agent │ │misc_agent│ │chart     │
    │_agent    │ │          │ │          │ │_direct   │
    └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘
         ▼            ▼            ▼            ▼
    ┌──────────┐ (query_data 主链路)
    │sql_coder │ ← 流式生成 SQL
    └────┬─────┘
         ▼
    ┌──────────┐
    │security  │ ← 安全审计
    └────┬─────┘
         ▼
    ┌──────────┐
    │execute   │ ← 执行 SQL
    │_sql      │
    └────┬─────┘
         ▼
    ┌──────────┐
    │quality   │ ← ReAct 质量评估（可重试）
    │_gate     │
    └────┬─────┘
         ▼
    ┌──────────┐
    │analyst   │ ← 实时流式 Markdown 分析
    └────┬─────┘
         ▼
   ┌─────┴─────┐
   ▼           ▼
┌────────┐ ┌────────┐
│reporter│ │answer  │
│(图表)  │ │(文本)  │
└───┬────┘ └───┬────┘
    └─────┬─────┘
          ▼
    ┌──────────┐
    │  finish  │
    └──────────┘
```

### 8 个 Agent 的职责与协作

| # | Agent | 职责 | 输入 | 输出 |
|---|-------|------|------|------|
| 1 | **clarify_plan** | 意图解析 + 执行计划生成（单次 LLM，原 Clarifier+Planner 合并） | 用户问题 + 历史 | is_clear, intent, plan_steps |
| 2 | **Schema Agent** | 渐进式披露：LLM 语义匹配表名后加载字段详情 | 用户问题 | 精简的 DDL 信息 |
| 3 | **SQL Coder** | 流式生成方言特定的 SQL | Schema + 需求 | 可执行 SQL（不 push_token） |
| 4 | **Security Agent** | SQL 审计分类（读/写） | SQL 文本 | 安全标记 |
| 5 | **Analyst Agent** | 实时流式 Markdown 分析（逐 token 推送前端） | 查询结果 | Markdown 分析文本 |
| 6 | **Reporter Agent** | 图表推荐 + ECharts JSON 生成 | 分析结果 + 数据 | 可视化配置 |
| 7 | **RAG Agent** | 从知识库检索业务规范、指标定义 | 用户问题 | 相关文档片段 |
| 8 | **Misc Agent** | 处理闲聊、帮助请求等非数据查询问题 | 用户问题 | 自然语言回答 |

---

## LangGraph 工作流拓扑 (13 节点)

```
            START → clarify_plan (意图+计划 单次LLM)
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
    schema_agent    rag_agent    misc_agent  chart_direct
          │                            │
          ▼                            ▼
      sql_coder                      answer
          │
          ▼
       security
          │
          ▼
     execute_sql
          │
          ▼
     quality_gate ←── (不合格时自循环 ReAct 重试)
          │
          ▼
       analyst  ───→ reporter (图表) / answer (文本)
          │
          ▼
        finish
```

### 关键设计点

- **`node_started` 实时推送**：每个节点第一行通过 `push_priority` 直写 merge_queue，前端任务清单 0 延迟更新
- **条件边路由**：`clarify_plan` 根据 intent 分发到不同链路（query_data → schema, ask_help → rag, chart_interaction → chart_direct）
- **ReAct 质量门**：`quality_gate` 评估查询结果质量，不合格时返回 `sql_coder` 重试
- **Human-in-the-loop**：写操作触发 `interrupt()`，等待管理员通过 `/approve` 审批

---

## 技术选型说明

### 为什么选择 FastAPI

- 原生异步支持，完美适配 LLM 调用的 I/O 密集场景
- 内置 SSE 支持（`StreamingResponse`），无需额外中间件
- 自动生成 OpenAPI 文档，降低前后端联调成本
- Pydantic 类型校验，减少运行时错误

### 为什么选择 LangGraph 1.x

- 有状态工作流：`AgentState` 贯穿全流程，便于追踪和调试
- 原生 Human-in-the-loop：`interrupt()` + `Command(resume=...)` 机制
- 条件边支持：可根据运行时状态动态路由
- 状态持久化：集成 Redis Checkpointer，服务重启不丢失中断状态

### 为什么选择 SQLAlchemy

- 统一的多方言 API：同一套代码适配 MySQL、PostgreSQL、SQL Server、Oracle
- ORM 与原生 SQL 混合使用，灵活应对复杂查询
- 连接池管理，保障高并发下的数据库连接稳定性

### 为什么选择 Milvus

- 专为向量检索设计的分布式架构，10 亿级数据毫秒级响应
- 支持多种索引类型（IVF_FLAT、HNSW），可根据场景调优
- 与 LangChain 生态无缝集成
