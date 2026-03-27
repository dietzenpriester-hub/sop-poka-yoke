"""JWT 认证与授权"""

from datetime import timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger

security_scheme = HTTPBearer(auto_error=False)

# TODO: 生产环境替换为真实 JWT 签发与校验（如 python-jose）
_DEV_TOKEN = "dev-token"


def create_access_token(user_id: int, role: str, expires_delta: timedelta | None = None) -> str:
    """开发阶段返回固定 token；生产需替换为 JWT 签发。"""
    logger.warning("使用开发模式 token，生产必须替换为 JWT")
    return _DEV_TOKEN


def verify_token(token: str) -> dict:
    """校验 token 并返回 payload。开发阶段接受 dev-token。"""
    if token == _DEV_TOKEN:
        return {"user_id": 1, "role": "admin"}
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效 token")


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
