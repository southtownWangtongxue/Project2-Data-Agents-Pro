# Docker 部署指南（单体镜像）

DataAgent Pro 采用**单体镜像**（前端 + 后端一体）发布：GitHub Actions 自动构建并推送到 Docker Hub，生产环境通过 `docker-compose.yml` 一条命令全量部署（基础设施 + 应用）。

## 1. 镜像架构

```
┌──────────────────────────────────────────┐
│  data-agent:latest（单个镜像，Linux）     │
│  ├── nginx   :80    托管前端 dist        │
│  │   └── 反代 /api → http://127.0.0.1:8000
│  └── uvicorn:8000   FastAPI 后端          │
│      由 supervisord 同容器管理两个进程    │
│  持久化卷（entrypoint 首次自动初始化）：  │
│  configs / skills / resources / logs     │
└──────────────────────────────────────────┘
```

- **基础镜像**：`python:3.12-slim` + apt 安装 nginx/supervisor
- **多阶段构建**：阶段1 `node:20-alpine` 构建前端 dist → 阶段2 后端 `uv sync` → 阶段3 运行时合并
- **多架构**：`linux/amd64` 与 `linux/arm64`（Buildx + QEMU）

## 2. 镜像发布（CI/CD）

`.github/workflows/docker-image.yml` 自动完成：

| 触发方式 | 生成的 tag | 说明 |
| --- | --- | --- |
| push `data_agent_pro` 分支 | `sha-<短哈希>` | 每次提交可追溯 |
| push `v*` tag（如 `v1.0.0`） | `v1.0.0` + `latest` | 正式版本 |
| 手动 `workflow_dispatch` | `sha-<短哈希>` | 兜底触发 |

**前置配置**（GitHub 仓库 → Settings → Secrets and variables → Actions）：

```
DOCKERHUB_USERNAME   # Docker Hub 用户名
DOCKERHUB_TOKEN      # Docker Hub Access Token（非登录密码）
```

产物镜像：`<username>/data-agent:<tag>`

> 海外 runner 稳定性说明：`backend/pyproject.toml` 中的 `[[tool.uv.index]]` 指向清华 PyPI 源，构建时已通过 Dockerfile 的 `ENV UV_DEFAULT_INDEX=https://pypi.org/simple` 覆盖为官方源，不影响本地开发。

## 3. 一条命令全量部署

```bash
cd DataAgent-Pro

# 1) 准备 .env（至少包含数据库密码与 LLM 密钥）
cp .env.example .env
#    编辑 .env 中的 MYSQL_ROOT_PASSWORD / POSTGRES_PASSWORD / LLM_API_KEY 等

# 2) 设置镜像参数并拉起全部服务
export DOCKERHUB_USERNAME=<你的用户名>
export IMAGE_TAG=latest          # 或 v1.0.0 等发布版本
docker compose up -d

# 3) 查看状态
docker compose ps
```

启动后会拉起 7 个服务：

| 服务 | 用途 | 端口 |
| --- | --- | --- |
| `data-agent-app` | 前端 + 后端单体 | `80:80` |
| `data-agent-redis` | 缓存 / 会话检查点 | `6379` |
| `data-agent-etcd` | Milvus 元数据 | - |
| `data-agent-minio` | Milvus 对象存储 | `9001` |
| `data-agent-milvus` | 向量数据库 | `19530` |
| `data-agent-mysql` | 关系库（业务 + 元数据） | `3306` |
| `data-agent-postgres` | 关系库 | `5432` |

部署完成后访问 `http://localhost`（默认管理员 `admin` / `12345678`）。

> 应用容器内访问基础设施使用**服务名**（`mysql`/`postgres`/`redis`/`milvus`），已在 `docker-compose.yml` 的 `environment` 中自动覆盖 `.env` 里的 `localhost` 地址，无需手动修改。

## 4. 配置持久化与热更新

应用容器挂载 4 个 named volume，**首次启动**由 `deploy/entrypoint.sh` 检测空卷并自动复制镜像内默认配置：

| 卷 | 容器内路径 | 内容 | 说明 |
| --- | --- | --- | --- |
| `agent_configs` | `/app/configs` | `mcp_servers.json` / `skills.json` / `llm_providers.json` / `default.json` | **watchdog 热更新**：改文件即生效，无需重启 |
| `agent_skills` | `/app/app/skills/skills` | 已安装的 Skill 实体目录 | 容器重建不丢，安装/卸载实时落盘 |
| `agent_resources` | `/app/resources` | 资源文件 | 持久化 |
| `agent_logs` | `/app/app/logs` | 运行日志 | 持久化 |

### 热更新行为

- **MCP / LLM / Skill 配置 JSON**：宿主机直接编辑卷中 JSON，或通过前端管理页保存 → 后端 watchdog 检测文件变更 → 内存热更新，**无需重启**。
- **Skill 安装/卸载**：API 直接写 `agent_skills` 卷（复制/删除目录）+ 更新 `skills.json`，立即落盘。
- **注意**：DeepAgent 的 skill 工具列表在**首次初始化时**缓存（`get_deep_agent()` 全局单例）。安装新 skill 后，`skills.json` 会热更新，但 **DeepAgent 工具集需重启容器**（`docker compose restart app`）才能加载新工具。配置本身已持久化，重启不丢。

## 5. 版本升级

```bash
# 拉取新版本镜像并滚动重启
export IMAGE_TAG=v1.1.0
docker compose pull app
docker compose up -d
```

配置卷（`agent_configs` / `agent_skills` 等）在升级后**自动保留**，因为卷的生命周期独立于容器。

## 6. 常用运维命令

```bash
# 查看日志
docker compose logs -f app

# 仅重启应用（不碰基础设施）
docker compose restart app

# 备份配置卷（Linux）
docker run --rm -v agent_configs:/data -v $(pwd):/backup alpine \
  tar czf /backup/agent_configs.tar.gz -C /data .

# 全量停止（保留数据）
docker compose down

# 全量清理（删除所有数据，谨慎！）
docker compose down -v
```

## 7. 本地构建单体镜像（可选）

```bash
docker build -t <username>/data-agent:local .
docker run -d --env-file .env -p 80:80 <username>/data-agent:local
```

## 8. 其他发布方案（备选）

### 方案 B：双镜像分层（原方案，已归档）

前后端独立镜像 `data-agent-backend` / `data-agent-frontend`，适合需要独立伸缩前后端的场景。旧的双镜像 Dockerfile 已随单体镜像方案移除；如需恢复，可从根 `Dockerfile` 中拆分「前端 dist 构建阶段」和「后端依赖阶段」为两个 Dockerfile（前端参考 `deploy/nginx.conf` 反代配置）。

### 方案 C：纯 Buildx 脚本

不用 Compose，脚本直接构建 + 推送，适合 K8s 等场景：

```bash
#!/bin/sh
export DOCKERHUB_USERNAME=yourname
docker buildx build --platform linux/amd64,linux/arm64 \
  -t $DOCKERHUB_USERNAME/data-agent:latest \
  -t $DOCKERHUB_USERNAME/data-agent:v1.0.0 \
  --push .
```
