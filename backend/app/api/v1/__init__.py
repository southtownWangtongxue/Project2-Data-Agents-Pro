"""
API v1 路由汇总 —— 将所有子路由注册到统一入口
"""
from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.approve import router as approve_router
from app.api.v1.datasource import router as datasource_router
from app.api.v1.export import router as export_router
from app.api.v1.stop import router as stop_router
from app.api.v1.config_api import router as config_router
from app.api.v1.knowledge_api import router as knowledge_router
from app.api.v1.schedule_api import router as schedule_router

router = APIRouter(prefix="")

router.include_router(auth_router)
router.include_router(chat_router)
router.include_router(approve_router)
router.include_router(datasource_router)
router.include_router(export_router)
router.include_router(stop_router)
router.include_router(config_router)
router.include_router(knowledge_router)
router.include_router(schedule_router)
