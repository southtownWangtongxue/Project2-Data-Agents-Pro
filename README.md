<p align="center">
  <img src="assets/logo.png" alt="DataAgent Pro Logo" width="180" />
</p>

# DataAgent Pro

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License" />
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB.svg" alt="Python" />
  <img src="https://img.shields.io/badge/Vue-3-42b883.svg" alt="Vue" />
  <img src="https://img.shields.io/badge/FastAPI-async-009688.svg" alt="FastAPI" />
  <img src="https://img.shields.io/badge/LangGraph-1.x-ff6f61.svg" alt="LangGraph" />
  <img src="https://img.shields.io/badge/Ant%20Design%20X-1.6-7056f8.svg" alt="Ant Design X" />
</p>

<p align="center">
  <b>面向业务人员的多智能体数据分析平台 · 用自然语言对话即可查询、分析与可视化企业数据</b>
</p>

<p align="center">
  Text-to-SQL · Multi-Agent · Human-in-the-Loop · 流式响应 · 暗色 UI
</p>

---

## ✨ 特性

- 🤖 **多智能体协作架构（Hermes 模式）**：编排 Agent + 专家 Worker（Schema / SQL Coder / Security / Analyst / Reporter / RAG / Misc），自动意图路由与任务分解。
- 💬 **自然语言对话式分析（Text-to-SQL）**：把"统计各表数据量"这类问题自动转换为方言特定的 SQL（MySQL / PostgreSQL / Oracle / SQL Server）。
- 🔒 **"读数据随意，改数据必批"**：写类 SQL（INSERT/UPDATE/DELETE/DROP）自动拦截并进入人工审批流，敏感字段（手机号/身份证）自动脱敏。
- 📊 **即时可视化与导出**：自动生成 ECharts 图表配置，支持 Excel / CSV 导出。
- ⚡ **流式响应（SSE）**：执行计划、SQL、工具调用、分析结论逐 token 流式呈现，首字节 < 1s。
- 🧠 **RAG 知识库**：从向量库（Milvus）检索业务口径与指标定义，让回答贴合企业语境。
- 🎨 **全新 Ant Design X Vue 对话页**：基于 `ant-design-x-vue` 的暗色主题对话界面（会话列表 / 思维链 / 欢迎页 / 模型选择器），参考官方样板间精心打磨。
- 🔌 **动态模型路由**：模型 provider 通过配置热加载，前端统一选择，支持 Qwen / GLM 等私有部署模型。
- 🐳 **一键容器化**：Docker Compose 启动 Redis + Milvus + MySQL + 基础设施全套依赖。

## 🏗️ 系统架构

**控制面 + 数据面 + 专家 Worker（Hermes Pattern）**

```
用户自然语言
     │
     ▼
┌──────────────────────────────────────────────────────────┐
│                      Orchestrator Agent                     │
│              意图解析 · 任务分解 · 动态路由 · 状态管理         │
└──────────────────────────────────────────────────────────┘
     │
     ├─ 通用/闲聊 ──────────────► Misc Agent ──────► 流式输出
     │
     └─ 数据分析 ──► Schema Agent (动态加载表结构)
                       │
                       ▼
                   SQL Coder Agent (方言 SQL + 自纠错重试)
                       │
                       ▼
                  Security Agent (读/写分类)
                       ├─ SELECT ─► 执行 SQL ─► Analyst Agent (统计/同比/环比/异常)
                       │                │
                       │                ▼
                       │           Reporter Agent (ECharts / Excel / CSV)
                       │                │
                       │                ▼
                       │           流式输出 ◄── 思维链可视化
                       │
                       └─ 写类 DML/DDL ─► 挂起 Graph ─► 审批流 ─► 管理员通过/拒绝
```

工作流以 **LangGraph 1.x 状态图**实现，通过 Redis `checkpointer` 持久化中断状态（默认 TTL 1 小时），支持 Human-in-the-Loop 的 interrupt / resume。

## 🧩 技术栈

| 层 | 技术 |
|---|---|
| 后端框架 | Python 3.10+ · FastAPI（异步 + SSE 流式） |
| Agent 编排 | LangGraph 1.x（状态图 · Human-in-the-Loop） |
| Agent 框架 | LangChain 1.x · deepAgents 0.5.x |
| 前端 | Vue 3 · Vite · Element Plus · ECharts · Ant Design X Vue |
| ORM / 驱动 | SQLAlchemy（多方言：MySQL / PostgreSQL / SQL Server / Oracle） |
| 向量库 | Milvus 2.x（RAG 知识库） |
| 缓存 / 状态 | Redis（Graph 中断状态快照） |
| LLM | 私有部署 Qwen / GLM |
| 部署 | Docker Compose（开发）· Nginx（前端静态托管） |
| 文档 | VitePress |

## 🚀 快速开始

### 前置条件

- Python 3.10+、Node.js 18+
- Redis、MySQL、Milvus（可直接用 Docker Compose 启动）
- 一个可用的 LLM provider（Qwen / GLM 等）API Key

### 1. 克隆并启动基础设施

```bash
git clone <your-repo-url> DataAgent-Pro
cd DataAgent-Pro

cp .env.example .env          # 按需填写 LLM Key 与数据库密码
docker-compose up -d          # 启动 Redis / MySQL / Milvus 等
```

### 2. 启动后端

```bash
cd backend
uv sync --group dev           # 安装依赖（建议使用 uv）
uv run uvicorn app.main:app --reload --port 8000
```

后端启动后接口文档：`http://localhost:8000/docs`

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev                   # 开发服务器，默认 http://localhost:5173
```

登录默认管理员账号：`admin` / `12345678`

### 4. 开始对话

打开 `http://localhost:5173`，进入「AI 对话 (X)」即可用自然语言提问，例如：

> 「统计数据库总表数」「帮我分析各区域销售额的同比变化」

## 📁 项目结构

```
DataAgent-Pro/
├── backend/                  # FastAPI 后端
│   ├── app/
│   │   ├── agents/           # Misc / RAG / Schema / SQL Coder / Security / Analyst / Reporter
│   │   ├── api/v1/           # REST + SSE 接口
│   │   ├── core/             # LLM 路由、配置管理
│   │   ├── db/               # 多方言 SQLAlchemy 驱动
│   │   ├── deepagent/        # deepAgents 结构化推理
│   │   ├── graph/            # LangGraph 状态图 / 状态定义
│   │   ├── rag/              # Milvus 检索
│   │   └── skills/           # 技能目录
│   └── configs/              # LLM provider 等配置（热加载）
├── frontend/                 # Vue 3 前端
│   └── src/
│       ├── views/ChatXVue.vue     # Ant Design X Vue 新对话页
│       ├── components/x/          # XConversations / XBubbleList / XSender / XWelcome / XThoughtChain
│       ├── stores/chat.ts         # 对话状态（含 currentModel 路由）
│       └── composables/useSSE.ts  # SSE 事件路由
├── docs/                     # VitePress 文档（开发计划、需求规格、配置体系）
├── init-scripts/             # 数据库初始化 SQL
└── docker-compose.yml        # 基础设施编排
```

## 🔌 核心 API

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/v1/chat/completions` | 核心对话（SSE：文本 / 图表配置 / 中间状态） |
| `POST` | `/api/v1/chat/approve` | 管理员审批回调（高危 SQL） |
| `POST` | `/api/v1/chat/stop` | 中断 Agent 执行 |
| `GET` | `/api/v1/datasource/list` | 列出可访问数据源 |
| `POST` | `/api/v1/export/excel` | 异步导出 Excel / CSV |

SSE 事件类型：`status` · `schema` · `sql` · `text` · `result` · `error` · `done` · `approval_required`。

## 📚 文档

完整文档（需求规格、配置体系、开发计划）基于 VitePress 构建，位于 `docs/`：

- 开发计划与 Ant Design X Vue 接入方案：`docs/plans/2026-08-05-ant-design-x-vue-integration.md`
- 需求规格说明书、配置体系说明书：`docs/`

本地预览文档：

```bash
cd docs
npm install
npm run docs:dev
```

## ✅ 质量验证

- 前端 `vue-tsc --noEmit` 类型检查通过
- 对话全流程经浏览器端到端验证（会话列表 / 消息流 / 思维链 / 欢迎页 / 模型路由 / 暗色主题）
- 回归保障：旧对话页 `/chat` 与新对话页 `/chat-x` 并存可用

## 🤝 贡献

欢迎提交 Issue 与 Pull Request。开发前请阅读 `CLAUDE.md` 了解架构约定与约束（尤其是"读数据随意、改数据必批"的安全红线）。

## 📄 License

[MIT](./LICENSE)
