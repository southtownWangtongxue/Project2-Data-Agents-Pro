# 快速开始

本文档将指导你从零搭建 DataAgent Pro 的本地开发环境。

## 环境要求

| 组件 | 最低版本 | 说明 |
|------|---------|------|
| Python | 3.10+ | 推荐 3.11，使用 uv 管理依赖 |
| Node.js | 18+ | 前端构建与开发服务器 |
| Docker | 20.10+ | 运行 Redis、Milvus、测试数据库 |
| Docker Compose | 2.0+ | 编排多容器服务 |
| Git | 2.30+ | 版本控制 |

## 第一步：克隆项目

```bash
git clone <your-repo-url> data-agent-pro
cd data-agent-pro
```

## 第二步：配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，至少需要配置以下变量：

```ini
# LLM 配置（私有化部署的 Qwen 或 GLM）
LLM_BASE_URL=http://your-llm-server:8000/v1
LLM_API_KEY=your-api-key
LLM_MODEL_NAME=qwen2.5-72b-instruct

# Milvus 向量库
MILVUS_HOST=localhost
MILVUS_PORT=19530

# 业务数据库（示例）
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your-password
DB_NAME=business_db
DB_DIALECT=mysql

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
```

## 第三步：启动基础设施

```bash
# 启动 Redis + Milvus + 测试数据库（MySQL + PostgreSQL）
docker-compose up -d

# 验证服务状态
docker-compose ps
```

预期看到 `redis`、`milvus-standalone`、`mysql`、`postgres` 四个容器均为 `Up` 状态。

## 第四步：安装后端依赖

```bash
cd backend

# 安装 uv（如果尚未安装）
pip install uv

# 同步所有依赖（含开发依赖）
uv sync --group dev
```

`uv` 会自动创建虚拟环境并安装 `pyproject.toml` 中定义的所有依赖。

## 第五步：启动后端

```bash
# 使用 uv 启动（推荐）
uv run data-agent

# 或者直接使用 uvicorn
uv run uvicorn app.main:app --reload --port 8000
```

启动成功后，后端服务运行在 `http://localhost:8000`，API 文档自动生成在：

- Swagger UI：`http://localhost:8000/docs`
- ReDoc：`http://localhost:8000/redoc`

## 第六步：安装前端依赖

```bash
cd frontend-react
npm install
```

::: tip 前端目录说明
当前维护的前端位于 `frontend-react/`（React 19 + Ant Design X）。仓库中的 `frontend/` 是已冻结的历史 Vue 3 版本，仅作归档参考，镜像构建与开发脚本均不再引用。
:::

## 第七步：启动前端

```bash
npm run dev
```

前端开发服务器运行在 `http://localhost:5173`。

## 第八步：验证

打开浏览器访问 `http://localhost:5173`，根路由会自动进入 `/chat` 对话工作台，你会看到：

1. 左侧会话栏 —— 新建 / 切换 / 删除会话，设置会话长期目标
2. 中间消息区 —— 输入自然语言问题（例如"上个月销售额最高的 10 个产品"），流式展示步骤链、SQL 卡片、数据表格与可视化图表
3. 底部输入区 —— 切换模式（数据分析 / 研究报告 / 文档智读 / 通用任务）、联网搜索开关、模型选择；生成中显示停止按钮
4. 对话内审批 —— 命中高危 SQL 时，流会在断点挂起并在对话中弹出审批卡片，管理员通过或拒绝后同一条流继续输出

## 常见问题

### Docker 服务启动失败

```bash
# 清理旧容器和卷，重新启动
docker-compose down -v
docker-compose up -d
```

### 前端无法连接后端

确保 `frontend-react/vite.config.ts` 中的代理配置正确指向后端地址：

```typescript
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true,
    },
  },
}
```

### LLM 连接失败

检查 `.env` 中的 `LLM_BASE_URL` 和 `LLM_API_KEY` 配置，确认私有化部署的大模型服务可正常访问。

## 下一步

- 阅读[架构设计](./architecture.md)了解系统整体设计
- 阅读[工作流详解](./workflow.md)了解 Agent 编排机制
- 阅读 [API 文档](../api/introduction.md)了解接口规范
