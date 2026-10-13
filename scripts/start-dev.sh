#!/bin/bash
set -e

echo "=== DataAgent Pro 开发环境启动 ==="

# 检查 .env 文件
if [ ! -f .env ]; then
    echo "[*] 创建 .env 文件（从 .env.example 复制）"
    cp .env.example .env
    echo "   请编辑 .env 配置 LLM_API_KEY 等参数"
fi

# 启动 Docker 服务
echo "[1/4] 启动 Docker 服务（Redis + Milvus + MySQL + PostgreSQL）..."
docker-compose up -d

# 后端依赖
echo "[2/4] 安装后端依赖..."
cd backend
uv sync --group dev
cd ..

# 前端依赖
echo "[3/4] 安装前端依赖..."
cd frontend-react
npm install
cd ..

# 启动服务
echo "[4/4] 启动开发服务器..."
echo "  后端: http://localhost:8000/docs"
echo "  前端: http://localhost:5173"
echo ""
echo "  启动后端: cd backend && uv run uvicorn app.main:app --reload"
echo "  启动前端: cd frontend-react && npm run dev"
