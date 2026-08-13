# syntax=docker/dockerfile:1
# ==========================================================================
# DataAgent Pro — 单体镜像（前端 + 后端一体）
#
# 构建：docker build -t <user>/data-agent:latest .
# 运行：docker compose up -d
#
# 镜像内布局：
#   /app/app                    后端源码（FastAPI）
#   /app/.venv                  后端 Python 依赖（uv 管理）
#   /app/configs.default        默认配置模板（MCP/LLM/Skill JSON，供卷初始化）
#   /app/skills.default         默认已安装 Skill 模板
#   /app/resources.default      默认资源模板
#   /usr/share/nginx/html       前端 dist 产物
#   nginx(80) -> 反代 /api 到 127.0.0.1:8000 uvicorn
#
# 多架构：linux/amd64, linux/arm64（GitHub Actions buildx 支持）
# ==========================================================================

# ── 阶段 1：前端构建 ─────────────────────────────────────────────────
FROM node:20-alpine AS frontend-build

WORKDIR /build

# 先复制依赖清单，利用缓存层
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ── 阶段 2：后端依赖 ─────────────────────────────────────────────────
FROM python:3.12-slim AS backend-build

# 环境变量：关闭字节码缓存/缓冲，uv 编译字节码、copy 链接模式
# 关键：覆盖 pyproject.toml 中指向清华源的 [[tool.uv.index]]，
#       保证 GitHub Actions 海外 runner 使用官方 PyPI 稳定构建。
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_DEFAULT_INDEX=https://pypi.org/simple

WORKDIR /app

# 系统依赖：gcc（编译 asyncmy/asyncpg 等二进制依赖兜底）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates python3-dev && \
    rm -rf /var/lib/apt/lists/*

# 安装 uv（Python 依赖管理器）
RUN pip install --no-cache-dir uv

# 复制依赖清单与源码
# 注意：uv sync 会构建项目本身（hatchling 打包 app 包），
#       故必须先 COPY app/，否则构建阶段报「找不到 app 包」。
COPY backend/pyproject.toml backend/uv.lock ./
COPY backend/app/ ./app/

# 安装生产依赖：--frozen 严格按 uv.lock 复现；--no-group dev 排除测试依赖组
RUN uv sync --frozen --no-group dev

# ── 阶段 3：运行时镜像 ───────────────────────────────────────────────
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# 系统依赖：nginx（前端静态+反代）、supervisor（进程管理）、curl（健康检查）
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx supervisor curl ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    rm -f /etc/nginx/conf.d/default.conf

# 后端依赖（从构建阶段拷贝 .venv）
COPY --from=backend-build /app/.venv /app/.venv
COPY --from=backend-build /app/app /app/app

# 默认配置模板（供 entrypoint 初始化空卷；正式配置由卷覆盖）
COPY backend/configs/ /app/configs.default/
COPY backend/app/skills/skills/ /app/skills.default/
COPY backend/resources/ /app/resources.default/

# 前端 dist → nginx
COPY --from=frontend-build /build/dist /usr/share/nginx/html

# nginx / supervisor / 入口脚本
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY deploy/supervisord.conf /etc/supervisor/supervisord.conf
COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 80

# 健康检查：nginx(80) 可达即视为存活
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:80/ || exit 1

ENTRYPOINT ["/entrypoint.sh"]
