"""
鉴权模块 —— JWT Token、密码哈希、API Key 管理

提供完整的认证/授权工具集：
- JWT 访问令牌/管理员令牌的生成与验证
- 密码的 bcrypt 哈希与验证（需 passlib）
- API Key 的生成与验证（基于 SHA-256 哈希）
"""
import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt  # PyJWT
from jwt.exceptions import InvalidTokenError

logger = logging.getLogger(__name__)

# ── JWT 配置 ────────────────────────────────────────
# 密钥：优先使用环境变量，否则随机生成（重启后旧 token 失效）
_JWT_SECRET = os.environ.get("JWT_SECRET", secrets.token_hex(32))
_JWT_ALGORITHM = "HS256"
_ACCESS_TOKEN_EXPIRE_MINUTES = 30  # 默认 30 分钟过期
_ADMIN_USER_ID = "admin"


# ════════════════════════════════════════════════════
# JWT Token
# ════════════════════════════════════════════════════


def create_access_token(user_id: str, expires_minutes: Optional[int] = None) -> str:
    """
    生成 JWT 访问令牌。

    参数:
        user_id:         用户唯一标识
        expires_minutes: 过期分钟数，默认 30；传入负数可生成已过期 token（用于测试）

    返回:
        JWT 签名字符串
    """
    expire_minutes = (
        expires_minutes if expires_minutes is not None else _ACCESS_TOKEN_EXPIRE_MINUTES
    )
    expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)

    payload = {
        "sub": user_id,
        "type": "access",
        "iat": datetime.now(timezone.utc),
        "exp": expire,
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def verify_access_token(token: str) -> Optional[dict]:
    """
    验证 JWT 访问令牌。

    参数:
        token: JWT 签名字符串

    返回:
        解码后的 payload 字典；验证失败返回 None
    """
    if not token or not token.strip():
        return None
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
        return payload
    except InvalidTokenError:
        return None
    except Exception:
        return None


def create_admin_token() -> str:
    """
    生成管理员 JWT 令牌。

    通过设置 type 字段为 "admin" 与普通访问令牌区分，
    verify_admin_token 据此判断管理员身份。

    返回:
        管理员 JWT 签名字符串
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=_ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": _ADMIN_USER_ID,
        "type": "admin",
        "iat": datetime.now(timezone.utc),
        "exp": expire,
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def verify_admin_token(token: str) -> bool:
    """
    验证是否为有效的管理员令牌。

    参数:
        token: JWT 签名字符串

    返回:
        True 表示是有效的管理员令牌，False 表示不是
    """
    payload = verify_access_token(token)
    if payload is None:
        return False
    return payload.get("type") == "admin"


# ════════════════════════════════════════════════════
# 密码哈希
# ════════════════════════════════════════════════════


def hash_password(password: str) -> str:
    """
    对密码进行 SHA-256 加盐哈希。

    格式: "sha256:<salt>:<hash>"
    salt 为 16 字节随机 hex，hash 为 sha256(salt + password) 的 hex。

    参数:
        password: 明文密码

    返回:
        哈希后的密码字符串
    """
    salt = secrets.token_hex(16)
    salted = salt + password
    hash_value = hashlib.sha256(salted.encode("utf-8")).hexdigest()
    return f"sha256:{salt}:{hash_value}"


def verify_password(password: str, hashed: str) -> bool:
    """
    验证密码是否与存储的哈希值匹配。

    支持两种格式:
        - sha256:<salt>:<hash>  — 新版加盐 SHA-256（由 hash_password 生成）
        - <md5_hex>             — 旧版 MD5 无盐哈希（32位大写 hex）

    参数:
        password: 待验证的明文密码
        hashed:   存储的哈希字符串

    返回:
        True 表示密码正确，False 表示不匹配
    """
    try:
        # 新版格式: sha256:<salt>:<hash>
        if hashed.startswith("sha256:"):
            parts = hashed.split(":", 2)
            if len(parts) != 3:
                return False
            _, salt, stored_hash = parts
            salted = salt + password
            computed = hashlib.sha256(salted.encode("utf-8")).hexdigest()
            return secrets.compare_digest(computed, stored_hash)

        # 旧版格式: 纯 MD5 hex（32字符，字母大写）
        if len(hashed) == 32:
            computed = hashlib.md5(password.encode("utf-8")).hexdigest()
            return secrets.compare_digest(computed.upper(), hashed.upper())

        return False
    except Exception:
        return False


# ════════════════════════════════════════════════════
# API Key
# ════════════════════════════════════════════════════


def generate_api_key() -> tuple[str, str]:
    """
    生成一对 API Key（原始密钥 + 哈希）。

    原始密钥：32 字节随机 hex（64 字符），用于分发给用户。
    哈希值：   SHA-256 哈希后的 hex，用于存储和验证。

    返回:
        (raw_key, hashed_key) 元组
        - raw_key:    64 字符的十六进制原始密钥
        - hashed_key: SHA-256 哈希后的 hex 值
    """
    raw_key = secrets.token_hex(32)
    hashed_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    return raw_key, hashed_key


def verify_api_key(raw_key: str, hashed_key: str) -> bool:
    """
    验证原始 API Key 是否与存储的哈希值匹配。

    参数:
        raw_key:    待验证的原始密钥
        hashed_key: 存储的 SHA-256 哈希值

    返回:
        True 表示匹配，False 表示不匹配
    """
    if not raw_key or not hashed_key:
        return False
    computed = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    return secrets.compare_digest(computed, hashed_key)
