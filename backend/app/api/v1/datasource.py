"""
数据源管理接口
获取当前用户有权限访问的数据源列表
"""
from fastapi import APIRouter, Depends
from app.api.deps import get_current_user
from app.core.config import get_settings

router = APIRouter(prefix="/datasource", tags=["datasource"])


@router.get("/list", summary="获取数据源列表")
async def list_datasources(user: dict = Depends(get_current_user)):
    """
    返回当前系统配置的所有可用数据源。
    后续将对接权限系统，仅返回当前用户有权限的数据源。
    """
    settings = get_settings()

    datasources = [
        {
            "id": "mysql",
            "name": "MySQL 业务库",
            "type": "mysql",
            "host": settings.MYSQL_HOST,
            "port": settings.MYSQL_PORT,
            "database": settings.MYSQL_DATABASE,
            "status": "available",
        },
        {
            "id": "postgresql",
            "name": "PostgreSQL 业务库",
            "type": "postgresql",
            "host": settings.POSTGRES_HOST,
            "port": settings.POSTGRES_PORT,
            "database": settings.POSTGRES_DATABASE,
            "status": "available",
        },
    ]

    return {
        "total": len(datasources),
        "datasources": datasources,
    }
