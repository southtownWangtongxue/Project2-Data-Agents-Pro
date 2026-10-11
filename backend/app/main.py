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
    # R19：应用运维补丁层（configs/patch.json 白名单内覆盖特性开关）
    from app.core.config_layer import apply_patch_overrides
    apply_patch_overrides()
    log.info("[DataAgent Pro] API 文档: http://localhost:8000/docs")
    log.info("[DataAgent Pro] 前端开发地址: http://localhost:5173")
    await init_checkpointer()  # ✅ 启动时初始化（async 环境）

    # DEF-009：启动后异步预热 LLM 连接与 DB 连接池。
    # 实测首次 LLM 调用含 TLS/连接建立可拖到 20s+（如 quality_gate 冷启动 20.7s
    # → 热态 1.4s），预热后首个用户请求即享受热态。
    import asyncio as _asyncio

    async def _warmup():
        try:
            from app.core.llm import get_llm, get_model_name, set_provider
            set_provider(get_config_manager().get_llm_config(None))
            t0 = _asyncio.get_event_loop().time()
            await get_llm().chat.completions.create(
                model=get_model_name(),
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            )
            log.info(f"[Warmup] LLM 连接预热完成: {_asyncio.get_event_loop().time() - t0:.1f}s")
        except Exception as exc:
            log.warning(f"[Warmup] LLM 预热失败（不影响服务）: {exc}")
        try:
            from sqlalchemy import text as _text
            from app.db.session import get_engine
            async with get_engine().connect() as conn:
                await conn.execute(_text("SELECT 1"))
            log.info("[Warmup] DB 连接池预热完成")
        except Exception as exc:
            log.warning(f"[Warmup] DB 预热失败（不影响服务）: {exc}")

    _asyncio.get_event_loop().create_task(_warmup())

    yield
    from app.mcp_client import shutdown_mcp_servers
    await __import__("asyncio").to_thread(shutdown_mcp_servers)  # 回收 MCP 子进程（DEF-004）
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
