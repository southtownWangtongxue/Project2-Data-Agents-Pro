# DataAgent Pro 开发计划

## 项目目标

构建基于 Multi-Agent 协同架构的智能业务数据交互平台，让业务人员通过自然语言安全、高效地获取、分析业务数据并生成报表。

核心原则：**读数据随意，改数据必批**（Human-in-the-loop 强制人工审批）。

## 核心工作流

```
用户输入 → 意图路由 → Schema Agent(表结构) → SQL Coder(生成SQL) → Security Agent(审计)
  ├─ SELECT → 执行 → Analyst(分析) → Reporter(图表) → 流式输出
  └─ DML/DDL → 冻结Graph → 推送审批 → 管理员通过/驳回 → 继续/拒绝
```

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
| 大模型 | 私有化部署 Qwen/GLM |
| 部署 | Docker Compose (开发), K8s (生产) |
| 文档 | VitePress |

## 目录结构

```
data-agent-pro/
├── backend/
│   ├── app/
│   │   ├── api/                  # FastAPI 路由层
│   │   │   ├── v1/
│   │   │   │   ├── chat.py       # 核心对话接口 (SSE 流式)
│   │   │   │   ├── approve.py    # 人工审批回调接口
│   │   │   │   ├── datasource.py # 数据源管理接口
│   │   │   │   └── export.py     # 文件导出接口
│   │   │   └── deps.py           # 依赖注入 (鉴权、限流)
│   │   ├── agents/               # Multi-Agent 实现
│   │   │   ├── orchestrator.py   # 控制枢纽 — 意图路由 + 任务拆解
│   │   │   ├── rag_agent.py      # RAG 规范检索专家
│   │   │   ├── schema_agent.py   # 元数据专家 — 表结构加载
│   │   │   ├── sql_coder.py      # SQL 生成 + 自纠错
│   │   │   ├── security.py       # 安全审计 — SQL 分类分级
│   │   │   ├── analyst.py        # 数据分析师 — 统计与洞察
│   │   │   └── reporter.py       # 报表生成 — ECharts/Excel
│   │   ├── graph/                # LangGraph 工作流定义
│   │   │   ├── state.py          # 全局 State 定义
│   │   │   ├── workflow.py       # 状态图构建 (节点 + 边 + 中断)
│   │   │   └── checkpointer.py   # Redis 状态快照持久化
│   │   ├── rag/                  # RAG 检索增强
│   │   │   ├── embeddings.py     # 文档切片 + 向量化
│   │   │   ├── retriever.py      # Milvus 检索链
│   │   │   └── knowledge.py      # 知识库管理 (上传/更新)
│   │   ├── db/                   # 数据库层
│   │   │   ├── session.py        # SQLAlchemy 会话管理
│   │   │   ├── dialects/         # 各数据库方言模板
│   │   │   │   ├── mysql.py
│   │   │   │   ├── postgresql.py
│   │   │   │   ├── sqlserver.py
│   │   │   │   └── oracle.py
│   │   │   └── models.py         # ORM 基础模型
│   │   ├── core/                 # 核心配置
│   │   │   ├── config.py         # 配置管理 (Pydantic Settings)
│   │   │   ├── security.py       # 鉴权 + 数据脱敏工具
│   │   │   └── llm.py            # LLM 客户端初始化 (Qwen/GLM)
│   │   └── main.py               # FastAPI 应用入口
│   ├── tests/                    # 后端测试
│   │   ├── test_agents/
│   │   ├── test_api/
│   │   └── test_graph/
│   ├── pyproject.toml            # uv 项目配置 + 依赖
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── views/                # 页面视图
│   │   ├── components/           # 通用组件 (ChatBox, ChartRenderer...)
│   │   ├── composables/          # 组合式函数 (useSSE, useAuth...)
│   │   ├── api/                  # API 调用封装
│   │   ├── router/               # Vue Router
│   │   └── stores/               # Pinia 状态管理
│   ├── package.json
│   ├── vite.config.ts
│   └── Dockerfile
├── docs/                         # VitePress 项目文档 (交付物)
│   ├── index.md
│   ├── guide/
│   ├── api/
│   ├── advanced/
│   └── develop/
├── docker-compose.yml            # 开发环境编排
├── .env.example                  # 环境变量模板
└── CLAUDE.md
```

## 开发阶段

### 阶段 0：基础设施搭建（预计 3-5 天）✅ 完成

- [x] 初始化 `pyproject.toml`，用 `uv` 管理 Python 依赖（FastAPI + LangChain + LangGraph + deepAgents + SQLAlchemy + Milvus client）
- [x] 用 `npm create vue@latest` 初始化前端项目（Vue 3 + Vite + Element Plus + ECharts + Pinia）
- [x] 配置 Docker Compose（Redis + Milvus + 模拟业务库 MySQL/PostgreSQL）
- [x] 搭建 FastAPI 应用骨架 + SSE 流式输出的 Hello World
- [x] 初始化 VitePress 文档目录结构

### 阶段 1：核心链路 — "一句话查数据"（预计 2-3 周）✅ 完成

- [x] Schema Agent：硬编码连接一个测试数据库，实现动态获取表结构
- [x] SQL Coder Agent：实现 Text-to-SQL 生成 + 执行失败自动重试（最多 2 次）
- [x] 不接入 LangGraph，先用单 Agent 链调用验证 LLM 生成 SQL 的质量
- [x] 前端做一个最简聊天界面，展示 SQL + 表格结果

### 阶段 2：LangGraph 工作流编排（预计 1-2 周）✅ 完成

- [x] 定义 `GraphState`（用户输入 → Schema → SQL → 安全标记 → 结果 → 分析 → 图表）
- [x] 用 LangGraph 1.x 构建完整的状态图，串联所有 Agent 节点
- [x] 实现 Human-in-the-loop 中断/恢复机制（Security Agent 检测到写操作 → `interrupt()` → FastAPI 推送审批 → `/approve` 回调 → `Command(resume=...)` 恢复）
- [x] Redis 存储中断状态快照

**阶段 2 已知问题（记录于 2026-04-29）：**

| # | 问题 | 优先级 | 状态 |
|---|------|--------|------|
| 1 | schema/sql_coder 节点缺少错误短路条件边，错误传播链路过长 | 高 | 待修复 |
| 2 | chat.py 中 GraphInterrupt 用字符串匹配捕获，应改为 `except GraphInterrupt` | 高 | 待修复 |
| 3 | execute_node 丢失 Phase1 的 SQL 自纠错重试能力 | 中 | 待修复 |
| 4 | 前端 useSSE.ts/chat store 未适配 `approval_required` 事件类型 | 低 | ✅ 已修复（阶段 4） |

### 阶段 3：安全 + RAG + 分析能力（预计 2-3 周）✅ 完成

- [x] Security Agent：正则 + LLM 双重 SQL 分类，数据脱敏（手机号、身份证打码）（已提前完成于阶段 2）
- [x] RAG Agent：文档上传 → 切片 → Milvus 向量化 → 检索增强 SQL 生成
- [x] Analyst Agent：对查询结果做同比/环比/极值分析，输出自然语言洞察
- [x] Reporter Agent：根据数据特征推荐图表类型，生成 ECharts JSON 配置

### 阶段 4：多方言 + 高阶功能 + 审批流 UI（预计 2 周）✅ 完成

- [x] 新增 PostgreSQL / SQL Server / Oracle 方言模板（4 方言含 LLM 提示和函数映射）
- [x] 前端审批管理页面（管理员查看待审批任务、一键通过/驳回）
- [x] 报表导出（CSV 流式导出 + Excel 占位）
- [x] Skill 集成预留（企业微信通知 + 外部 API 调用注册表）

### 阶段 5：文档 + 部署 + 验收（预计 1 周）✅ 完成

- [x] 完善 VitePress 文档（13 个文件：架构详解、API 参数与报文示例、二次开发指南）
- [x] Dockerfile × 2 + nginx.conf + start-dev.sh 一键启动脚本
- [x] 验收测试（14 个测试全部通过：Agent 单元测试 + API 集成测试）

---

## 项目最终统计

| 维度 | 数据 |
|------|------|
| 总文件数 | 83 |
| 后端 Python 模块 | 30+ |
| 前端 Vue/TS 模块 | 12 |
| VitePress 文档 | 13 |
| 7 个 Agent | Orchestrator, Schema, SQL Coder, Security, Analyst, Reporter, RAG |
| 10 节点 LangGraph | orchestrator → schema → sql → security → execute → analyst → reporter → finish (+ rag_agent) |
| 11 个 API 端点 | chat/completions, approve, stop, datasource/list, export/csv, export/excel, health |
| 4 种 SQL 方言 | MySQL, PostgreSQL, SQL Server, Oracle |
| 验收测试 | 14 passed / 0 failed |
| 已知问题 | 3 个待修复（详见阶段 2 已知问题表）|

### 阶段 5：文档 + 部署 + 验收（预计 1 周）✅ 完成

- [x] 完善 VitePress 文档（13 个文件：架构详解、API 参数与报文示例、二次开发指南）
- [x] Dockerfile × 2 + nginx.conf + start-dev.sh 一键启动脚本
- [x] 验收测试（14 个测试全部通过：Agent 单元测试 + API 集成测试）

---

## 项目最终统计

| 维度 | 数据 |
|------|------|
| 总文件数 | 83 |
| 后端 Python 模块 | 30+ |
| 前端 Vue/TS 模块 | 12 |
| VitePress 文档 | 13 |
| 7 个 Agent | Orchestrator, Schema, SQL Coder, Security, Analyst, Reporter, RAG |
| 10 节点 LangGraph | orchestrator → schema → sql → security → execute → analyst → reporter → finish (+ rag_agent) |
| 11 个 API 端点 | chat/completions, approve, stop, datasource/list, export/csv, export/excel, health |
| 4 种 SQL 方言 | MySQL, PostgreSQL, SQL Server, Oracle |
| 验收测试 | 14 passed / 0 failed |
| 已知问题 | 3 个待修复（详见阶段 2 已知问题表）|
