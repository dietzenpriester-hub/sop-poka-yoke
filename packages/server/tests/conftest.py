# 运行本目录测试前请安装异步 SQLite 驱动：pip install aiosqlite
# （已列入 pyproject.toml optional-dependencies dev：pip install -e ".[dev]"）

"""pytest 共享配置：内存 SQLite、FastAPI 测试应用、JWT fixture。"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.api.router import api_router
from src.core.database import Base, get_db
import src.models  # noqa: F401 — 注册全部 ORM 元数据
from src.core.security import create_access_token


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def db_engine():
    """每个用例独立内存库，避免状态串扰。"""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """单测内使用的异步 Session，关闭时随引擎释放。"""
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
async def test_app(db_engine):
    """不含 MQTT/生产 lifespan 的测试用 FastAPI，并覆盖 get_db。"""
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            yield session

    @asynccontextmanager
    async def empty_lifespan(_app):
        yield

    from fastapi import FastAPI
    from sqlalchemy import text

    app = FastAPI(title="sop-test", lifespan=empty_lifespan)
    app.include_router(api_router, prefix="/api")

    @app.get("/health")
    async def health():
        async with db_engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "service": "test", "database": "connected"}

    app.dependency_overrides[get_db] = override_get_db
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
async def async_client(test_app):
    """httpx AsyncClient + ASGITransport。"""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def token_admin() -> str:
    """管理员角色 JWT。"""
    return create_access_token(user_id=1, role="admin")


@pytest.fixture
def token_operator() -> str:
    """操作员角色 JWT。"""
    return create_access_token(user_id=2, role="operator")


@pytest.fixture
async def async_client_admin(async_client, token_admin):
    """带 Bearer admin token 的客户端（默认头可覆盖）。"""
    async_client.headers.update({"Authorization": f"Bearer {token_admin}"})
    yield async_client
    async_client.headers.pop("Authorization", None)


@pytest.fixture
async def async_client_operator(async_client, token_operator):
    """带 Bearer operator token 的客户端。"""
    async_client.headers.update({"Authorization": f"Bearer {token_operator}"})
    yield async_client
    async_client.headers.pop("Authorization", None)


@pytest.fixture
async def user_with_password(db_session):
    """用于登录 API 测试：用户名 testuser，密码 correct-password。"""
    from src.api.user import _hash_password
    from src.models.user import UserAccount

    u = UserAccount(
        username="testuser",
        password_hash=_hash_password("correct-password"),
        role="operator",
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u
