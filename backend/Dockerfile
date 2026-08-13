# syntax=docker/dockerfile:1
# ==========================================================================
# DataAgent Pro — 后端服务镜像（FastAPI + uv）
# 构建：docker build -t <user>/data-agent-backend ./backend
# 运行：docker run -d --env-file .env -p 8000:8000 <user>/data-agent-backend
# ==========================================================================
FROM python:3.12-slim

# 环境变量：关闭字节码缓存 / 缓冲，uv 编译字节码、copy 链接模式
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# 系统依赖：gcc（编译 asyncmy/asyncpg 等二进制依赖兜底）、curl（健康检查）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates python3-dev && \
    rm -rf /var/lib/apt/lists/*

# 安装 uv（Python 依赖管理器）
RUN pip install --no-cache-dir uv

# 复制依赖清单与源码
# 注意：uv sync 会构建项目本身（pyproject 的 hatchling 打包 app 包），
#       故必须先 COPY app/，否则构建阶段报「找不到 app 包」。
COPY pyproject.toml uv.lock ./
COPY app/ ./app/

# 安装生产依赖：--frozen 严格按 uv.lock 复现；--no-group dev 排除测试依赖组
RUN uv sync --frozen --no-group dev --verbose

# 复制配置（ConfigManager 热加载目录）与资源
COPY configs/ ./configs/
COPY resources/ ./resources/

EXPOSE 8000

# 健康检查：/health 端点
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 生产启动（不使用 --reload）
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
