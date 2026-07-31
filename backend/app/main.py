"""
FastAPI 应用入口
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as v1_router
from app.graph.workflow import init_checkpointer, close_checkpointer
from app.models import create_tables
from app.utils.log_utils import log


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时打印日志，关闭时清理资源。"""
    log.info("[DataAgent Pro] 服务启动中...")
    await create_tables()
    from app.core.config_manager import get_config_manager
    get_config_manager().start_watcher()  # 启动配置文件热更新监听
    log.info("[DataAgent Pro] API 文档: http://localhost:8000/docs")
    log.info("[DataAgent Pro] 前端开发地址: http://localhost:5173")
    await init_checkpointer()  # ✅ 启动时初始化（async 环境）
    yield
    await close_checkpointer()  # ✅ 关闭时清理
    log.info("[DataAgent Pro] 服务已关闭。")


# 创建 FastAPI 实例
app = FastAPI(
    title="DataAgent Pro",
    description="智能业务数据助手 — 基于 LLM 的多模态数据分析平台",
    version="0.1.0",
    lifespan=lifespan,
)

# 配置 CORS 中间件，允许前端开发服务器跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite 默认前端开发服务器
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载 /api/v1 路由（所有子路由统一通过 v1_router 注册）
app.include_router(v1_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {"status": "ok", "version": "0.1.0"}


def main():
    """uvicorn 启动入口，通过 `data-agent` 命令调用。"""
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
