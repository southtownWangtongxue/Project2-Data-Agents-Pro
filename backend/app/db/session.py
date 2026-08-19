"""
数据库会话管理
基于 SQLAlchemy async engine 管理业务数据库连接
支持 MySQL（通过 asyncmy）和 PostgreSQL（通过 asyncpg）两种后端，
根据 config 中的 DB_TYPE 配置自动切换。
"""
import logging

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
    AsyncEngine,
)
from app.core.config import get_settings
from app.utils.log_utils import log

settings = get_settings()

# 全局引擎和会话工厂（懒加载）
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _mysql_url() -> str:
    """构建 MySQL 连接串。"""
    return (
        f"mysql+asyncmy://{settings.MYSQL_USER}:{settings.MYSQL_PASSWORD}"
        f"@{settings.MYSQL_HOST}:{settings.MYSQL_PORT}/{settings.MYSQL_DATABASE}"
    )


def _postgresql_url() -> str:
    """构建 PostgreSQL 连接串。"""
    return (
        f"postgresql+asyncpg://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DATABASE}"
    )


def _build_database_url() -> str:
    """根据 DB_TYPE 配置构建对应的数据库连接 URL（兼容旧路径）"""
    if settings.DB_TYPE == "postgresql":
        return _postgresql_url()
    # 默认使用 MySQL
    return _mysql_url()


def _build_engine(database_url: str) -> AsyncEngine:
    """根据连接串创建异步引擎（统一连接池配置）。"""
    log.info(database_url)
    return create_async_engine(
        database_url,
        echo=settings.DEBUG,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )


def _register_storage_seam() -> None:
    """注册 storage seam（Phase 3 能力接缝）。

    未来新增存储后端只需 register + select，无需改动 get_engine。
    """
    from app.core.seam import get_seam

    seam = get_seam()
    if not seam.providers("storage"):
        default = "postgresql" if settings.DB_TYPE == "postgresql" else "mysql"
        seam.define("storage", "数据库存储后端", default=default)
        seam.register("storage", "mysql", lambda: _build_engine(_mysql_url()), "MySQL (asyncmy)")
        seam.register("storage", "postgresql", lambda: _build_engine(_postgresql_url()), "PostgreSQL (asyncpg)")


def get_engine() -> AsyncEngine:
    """返回全局异步数据库引擎实例（懒加载，首次调用时创建）"""
    global _engine
    if _engine is None:
        from app.core.seam import get_seam, seam_enabled

        if seam_enabled():
            _register_storage_seam()
            _engine = get_seam().resolve("storage")
        else:
            _engine = _build_engine(_build_database_url())
    return _engine


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """返回异步会话工厂（懒加载）"""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_db():
    """
    提供数据库会话的异步生成器，用于 FastAPI 依赖注入。

    使用示例:
        @app.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(Item))
            return result.scalars().all()
    """
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
