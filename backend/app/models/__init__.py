"""
ORM 模型注册中心 —— 管理所有 SQLAlchemy 模型和表创建
"""
import logging
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_engine, _get_session_factory

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类"""
    pass


async def create_tables():
    """在应用启动时创建所有模型对应的数据库表（不存在则创建），并播种初始数据"""
    from app.models.user import SysUser  # noqa: F401
    from app.models.session import ChatSession, ChatNode, SessionEvent  # noqa: F401

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # 兼容性迁移：为旧版 chat_nodes 表添加 run_id 列（若尚未存在）
        try:
            await conn.run_sync(
                lambda sync_conn: sync_conn.execute(
                    __import__("sqlalchemy").text(
                        "ALTER TABLE chat_nodes ADD COLUMN run_id VARCHAR(128) NULL COMMENT 'LangGraph 运行 ID'"
                    )
                )
            )
            logger.info("[models] chat_nodes.run_id 列已添加")
        except Exception:
            # 列已存在或表不存在，跳过
            pass

        # 兼容性迁移：为旧版 chat_sessions 表添加 goal 列（阶段4 B6，若尚未存在）
        try:
            await conn.run_sync(
                lambda sync_conn: sync_conn.execute(
                    __import__("sqlalchemy").text(
                        "ALTER TABLE chat_sessions ADD COLUMN goal TEXT NULL COMMENT '会话长期目标（阶段4 B6）'"
                    )
                )
            )
            logger.info("[models] chat_sessions.goal 列已添加")
        except Exception:
            # 列已存在或表不存在，跳过
            pass

    logger.info("[models] 数据库表创建/同步完成")

    # 播种默认管理员账号
    from app.models.seed import seed_default_users
    factory = _get_session_factory()
    async with factory() as session:
        await seed_default_users(session)
        try:
            await session.commit()
        except Exception:
            await session.rollback()


async def get_db_session() -> AsyncSession:
    """获取异步数据库会话（用于非 FastAPI 依赖注入场景）"""
    factory = _get_session_factory()
    return factory()
