"""用户认证"""

import asyncio
import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import create_access_token
from src.models.user import UserAccount
from src.api.user import _verify_password

router = APIRouter()

_LOGIN_WINDOW = 300  # 5 分钟窗口
_MAX_ATTEMPTS = 10
_login_attempts: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(client_ip: str) -> None:
    now = time.monotonic()
    attempts = _login_attempts[client_ip]
    _login_attempts[client_ip] = [t for t in attempts if now - t < _LOGIN_WINDOW]
    if len(_login_attempts[client_ip]) >= _MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="登录尝试过于频繁，请稍后再试")
    _login_attempts[client_ip].append(now)


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(req: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)
    result = await db.execute(
        select(UserAccount).where(UserAccount.username == req.username)
    )
    user = result.scalar_one_or_none()
    if not user or not _verify_password(req.password, user.password_hash):
        await asyncio.sleep(0.5)
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(user_id=user.id, role=user.role)
    return {"access_token": token, "token_type": "bearer"}
