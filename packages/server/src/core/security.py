"""JWT 认证与授权"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger

from src.core.config import get_settings

security_scheme = HTTPBearer(auto_error=False)

_DEV_TOKEN = "dev-token"


def create_access_token(user_id: int, role: str | None = None, expires_delta: timedelta | None = None) -> str:
    """签发 HS256 JWT，包含 exp、sub（user_id）、role（缺省为 operator）。"""
    settings = get_settings()
    if expires_delta is None:
        expires_delta = timedelta(hours=settings.JWT_EXPIRE_HOURS)
    expire = datetime.now(timezone.utc) + expires_delta
    effective_role = role if role is not None and str(role).strip() != "" else "operator"
    payload = {
        "exp": expire,
        "sub": str(user_id),
        "role": effective_role,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def verify_token(token: str) -> dict:
    """校验 token 并返回 {"user_id": int, "role": str}。DEV_MODE 下可接受 dev-token。"""
    settings = get_settings()
    is_production = os.environ.get("SOP_ENV", "").lower() == "production"
    if is_production and settings.DEV_MODE:
        logger.warning("DEV_MODE 与 SOP_ENV=production 同时设置，已忽略 DEV_MODE（按生产校验 JWT）")
    elif settings.DEV_MODE and not is_production and token == _DEV_TOKEN:
        logger.debug("DEV_MODE: 接受 dev-token（仅限非生产环境）")
        return {"user_id": 1, "role": "admin"}
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        sub = payload.get("sub")
        if sub is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效 token")
        try:
            if isinstance(sub, int):
                user_id = sub
            elif isinstance(sub, str):
                user_id = int(sub)
            else:
                user_id = int(str(sub))
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效 token") from e
        role = str(payload.get("role", ""))
        return {"user_id": user_id, "role": role}
    except jwt.PyJWTError as e:
        logger.debug("JWT 校验失败: {}", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效 token") from e


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> dict:
    """FastAPI 依赖：从 Bearer token 获取当前用户。"""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未提供认证凭据")
    return verify_token(credentials.credentials)


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """需要管理员角色。"""
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user
