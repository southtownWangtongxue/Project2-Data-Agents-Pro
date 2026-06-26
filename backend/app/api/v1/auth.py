"""
认证接口 —— JWT 登录 / 用户信息
"""
import logging
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import get_current_user, get_settings
from app.core.config import Settings
from app.core.security import verify_password
from app.db.session import get_db
from app.models.user import SysUser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


# ── 数据模型 ────────────────────────────────────────

class LoginRequest(BaseModel):
    """登录请求"""
    user_name: str = Field(..., min_length=1, max_length=30, description="用户名")
    password: str = Field(..., min_length=1, description="密码")


class LoginResponse(BaseModel):
    """登录响应"""
    access_token: str
    user_name: str
    nick_name: str
    user_type: str


class UserInfo(BaseModel):
    """当前用户信息"""
    user_name: str
    nick_name: str
    user_type: str


# ── 内部辅助 ────────────────────────────────────────

def _generate_token(user: SysUser, settings: Settings) -> str:
    """为用户生成 JWT token"""
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRE_HOURS)
    payload = {
        "user_name": user.user_name,
        "user_type": user.user_type,
        "nick_name": user.nick_name,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


# ── API 端点 ────────────────────────────────────────

@router.post("/login", summary="用户登录", response_model=LoginResponse)
async def login(body: LoginRequest, db=Depends(get_db), settings=Depends(get_settings)):
    """
    用户登录 —— 验证 user_name + password，返回 JWT token。

    验证流程:
        1. 查 sys_user 表中 user_name 匹配且 status='0' 且 del_flag='0'
        2. 使用 sha256 加盐哈希验证密码
        3. 更新 login_ip / login_date
        4. 生成并返回 JWT
    """
    result = await db.execute(
        select(SysUser).where(
            SysUser.user_name == body.user_name,
            SysUser.status == "0",
            SysUser.del_flag == "0",
        )
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    if not verify_password(body.password, user.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = _generate_token(user, settings)

    logger.info("[auth] 用户登录成功: %s (type=%s)", user.user_name, user.user_type)

    return LoginResponse(
        access_token=token,
        user_name=user.user_name,
        nick_name=user.nick_name,
        user_type=user.user_type,
    )


@router.get("/me", summary="获取当前用户信息", response_model=UserInfo)
async def get_me(user: dict = Depends(get_current_user)):
    """
    获取当前登录用户的信息 —— 从 JWT token 中解析。
    需要 Bearer token 认证。
    """
    return UserInfo(
        user_name=user["user_name"],
        nick_name=user["nick_name"],
        user_type=user["user_type"],
    )
