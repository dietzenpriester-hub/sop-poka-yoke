"""SOP API 测试（使用 conftest 中的 test_app，避免连接生产库与 MQTT）。"""

import pytest


@pytest.mark.asyncio
async def test_health(async_client):
    r = await async_client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
