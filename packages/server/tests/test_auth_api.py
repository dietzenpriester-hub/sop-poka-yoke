"""登录 API 测试（内存库 + 覆盖 get_db）。"""

import pytest

from src.api import auth as auth_module


@pytest.mark.asyncio
async def test_login_success(async_client, user_with_password):
    r = await async_client.post(
        "/api/auth/login",
        json={"username": "testuser", "password": "correct-password"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("token_type") == "bearer"
    assert "access_token" in body and len(body["access_token"]) > 0


@pytest.mark.asyncio
async def test_login_wrong_password(async_client, user_with_password):
    r = await async_client.post(
        "/api/auth/login",
        json={"username": "testuser", "password": "wrong-password"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(async_client, user_with_password):
    r = await async_client.post(
        "/api/auth/login",
        json={"username": "nobody", "password": "whatever"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_login_rate_limit(async_client, user_with_password, monkeypatch):
    """连续失败达到上限后返回 429；去掉 sleep 以加快执行。"""

    async def _noop_sleep(*_a, **_k):
        return None

    monkeypatch.setattr("src.api.auth.asyncio.sleep", _noop_sleep)
    auth_module._LOGIN_ATTEMPTS.clear()

    try:
        for _ in range(10):
            r = await async_client.post(
                "/api/auth/login",
                json={"username": "testuser", "password": "bad"},
            )
            assert r.status_code == 401

        r429 = await async_client.post(
            "/api/auth/login",
            json={"username": "testuser", "password": "bad"},
        )
        assert r429.status_code == 429
    finally:
        auth_module._LOGIN_ATTEMPTS.clear()
