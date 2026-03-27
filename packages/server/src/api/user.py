"""用户管理"""

import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import require_admin
from src.models.user import UserAccount
from src.schemas.user import UserCreate, UserPasswordChange, UserResponse, UserUpdate

router = APIRouter()


_PBKDF2_ITERS = 260_000
_PBKDF2_PREFIX = "pbkdf2:"


def _hash_password(password: str, salt: str | None = None) -> str:
    if salt is None:
        salt = secrets.token_hex(16)
    salt_bytes = bytes.fromhex(salt)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, _PBKDF2_ITERS)
    return f"{_PBKDF2_PREFIX}{salt}${dk.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    if stored_hash.startswith(_PBKDF2_PREFIX):
        body = stored_hash[len(_PBKDF2_PREFIX) :]
        if "$" not in body:
            return False
        salt_part, digest_hex = body.split("$", 1)
        try:
            salt_bytes = bytes.fromhex(salt_part)
        except ValueError:
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, _PBKDF2_ITERS)
        return secrets.compare_digest(dk.hex(), digest_hex)
    if "$" in stored_hash:
        salt, digest = stored_hash.split("$", 1)
        legacy = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
        return secrets.compare_digest(legacy, digest)
    return hashlib.sha256(password.encode("utf-8")).hexdigest() == stored_hash


@router.get("/", response_model=list[UserResponse])
async def list_users(
    role: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_admin),
):
    q = select(UserAccount)
    if role:
        q = q.where(UserAccount.role == role)
    result = await db.execute(q.order_by(UserAccount.id).offset(skip).limit(limit))
    return list(result.scalars().all())


@router.post("/", response_model=UserResponse, status_code=201)
async def create_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    existing = await db.execute(select(UserAccount).where(UserAccount.username == data.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="用户名已存在")
    user = UserAccount(
        username=data.username,
        display_name=data.display_name,
        role=data.role,
        badge_id=data.badge_id,
        password_hash=_hash_password(data.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    result = await db.execute(select(UserAccount).where(UserAccount.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    result = await db.execute(select(UserAccount).where(UserAccount.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return user


@router.put("/{user_id}/password")
async def change_password(
    user_id: int,
    data: UserPasswordChange,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    result = await db.execute(select(UserAccount).where(UserAccount.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.password_hash = _hash_password(data.new_password)
    await db.commit()
    return {"message": "密码已更新"}


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    result = await db.execute(select(UserAccount).where(UserAccount.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    await db.delete(user)
    await db.commit()
    return {"message": "用户已删除"}
