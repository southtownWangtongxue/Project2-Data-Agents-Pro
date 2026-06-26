"""
依赖注入模块 —— 提供可复用的 FastAPI 依赖函数
"""
import jwt
from fastapi import Request, HTTPException, Depends
from jwt.exceptions import InvalidTokenError

from app.core.config import Settings, settings


def get_settings() -> Settings:
    """
    获取应用配置实例。
    使用 FastAPI Depends 注入，方便测试时替换。
    """
    return settings


async def get_current_user(request: Request) -> dict:
    """
    JWT 认证依赖 —— 从 Authorization header 解析当前用户。

    返回:
        {"user_name": str, "user_type": str, "nick_name": str}

    异常:
        HTTPException(401) —— 未登录 / token 无效 / 已过期
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录")

    token = auth.split(" ", 1)[1]
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=["HS256"]
        )
        return {
            "user_name": payload["user_name"],
            "user_type": payload.get("user_type", "01"),
            "nick_name": payload.get("nick_name", ""),
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="令牌已过期")
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效令牌")


def optional_user(request: Request) -> dict | None:
    """
    可选的用户认证 —— 不强制要求登录，但如果提供了有效 token 则返回用户信息。
    用于部分公开接口（如健康检查）的可选身份识别。
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.split(" ", 1)[1]
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=["HS256"]
        )
        return {
            "user_name": payload["user_name"],
            "user_type": payload.get("user_type", "01"),
            "nick_name": payload.get("nick_name", ""),
        }
    except Exception:
        return None
    
