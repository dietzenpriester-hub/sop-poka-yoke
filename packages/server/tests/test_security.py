"""安全模块单元测试：JWT、密码校验、管理员依赖。"""

from datetime import timedelta

import jwt
import pytest
from fastapi import HTTPException

from src.core.config import get_settings
from src.core.security import (
    create_access_token,
    require_admin,
    verify_token,
)
from src.api.user import _hash_password, _verify_password


def test_create_access_token_contains_role():
    token = create_access_token(user_id=42, role="admin")
    payload = jwt.decode(token, get_settings().JWT_SECRET, algorithms=[get_settings().JWT_ALGORITHM])
    assert payload["sub"] == "42"
    assert payload["role"] == "admin"


def test_create_access_token_default_role():
    token = create_access_token(user_id=7, role=None)
    payload = jwt.decode(token, get_settings().JWT_SECRET, algorithms=[get_settings().JWT_ALGORITHM])
    assert payload["role"] == "operator"


def test_verify_token_valid():
    token = create_access_token(user_id=99, role="operator")
    info = verify_token(token)
    assert info["user_id"] == 99
    assert info["role"] == "operator"


def test_verify_token_expired():
    token = create_access_token(
        user_id=1,
        role="operator",
        expires_delta=timedelta(hours=-1),
    )
    with pytest.raises(HTTPException) as exc:
        verify_token(token)
    assert exc.value.status_code == 401


def test_verify_token_invalid():
    with pytest.raises(HTTPException) as exc:
        verify_token("totally-not-a-jwt")
    assert exc.value.status_code == 401


def test_hash_password_and_verify():
    raw = "MySecret!234"
    h = _hash_password(raw)
    assert h.startswith("pbkdf2:")
    assert _verify_password(raw, h) is True
    assert _verify_password("wrong", h) is False


@pytest.mark.asyncio
async def test_require_admin_allows_admin():
    user = await require_admin(user={"user_id": 1, "role": "admin"})
    assert user["role"] == "admin"


@pytest.mark.asyncio
async def test_require_admin_blocks_operator():
    with pytest.raises(HTTPException) as exc:
        await require_admin(user={"user_id": 2, "role": "operator"})
    assert exc.value.status_code == 403
