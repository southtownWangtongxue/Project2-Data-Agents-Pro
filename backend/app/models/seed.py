"""
种子数据 —— 首次启动时创建默认管理员账号
"""
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import SysUser
from app.core.security import hash_password
from app.db.session import get_engine
from app.models import Base

logger = logging.getLogger(__name__)

# 默认管理员账号
DEFAULT_ADMIN_USER = "admin"
DEFAULT_ADMIN_PASSWORD = "12345678"


async def seed_default_users(session: AsyncSession):
    """确保至少存在一个管理员账号（首次启动时创建）"""
    result = await session.execute(
        select(SysUser).where(SysUser.user_name == DEFAULT_ADMIN_USER)
    )
    existing = result.scalar_one_or_none()

    if existing is None:
        admin = SysUser(
            user_name=DEFAULT_ADMIN_USER,
            password=hash_password(DEFAULT_ADMIN_PASSWORD),
            user_type="00",  # Admin
            nick_name="管理员",
            status="0",
            del_flag="0",
            login_ip="",
            login_date="",
        )
        session.add(admin)
        await session.commit()
        logger.info(
            "[seed] 已创建默认管理员账号: %s / %s",
            DEFAULT_ADMIN_USER,
            DEFAULT_ADMIN_PASSWORD,
        )
    else:
        logger.info("[seed] 管理员账号已存在，跳过创建")
