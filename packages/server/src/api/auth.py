"""用户认证"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import create_access_token
from src.models.user import UserAccount
from src.api.user import _verify_password

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(UserAccount).where(UserAccount.username == req.username)
    )
    user = result.scalar_one_or_none()
    if not user or not _verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(user_id=user.id, role=user.role)
    return {"access_token": token, "token_type": "bearer"}
