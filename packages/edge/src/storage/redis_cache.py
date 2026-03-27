"""Redis 状态缓存"""

from __future__ import annotations

import json
from typing import Any

import redis
from loguru import logger


class RedisCache:

    def __init__(self, url: str = "redis://localhost:6379/0") -> None:
        self._client = redis.from_url(url, decode_responses=True)
        logger.info("Redis 已连接: {}", url)

    def set_json(self, key: str, value: Any, ttl: int | None = None) -> None:
        data = json.dumps(value, ensure_ascii=False)
        if ttl:
            self._client.setex(key, ttl, data)
        else:
            self._client.set(key, data)

    def get_json(self, key: str) -> Any | None:
        data = self._client.get(key)
        if data:
            return json.loads(data)
        return None

    def delete(self, key: str) -> None:
        self._client.delete(key)

    def set_station_status(self, station_id: str, status: dict) -> None:
        self.set_json(f"station:{station_id}:status", status, ttl=300)

    def get_station_status(self, station_id: str) -> dict | None:
        return self.get_json(f"station:{station_id}:status")

    def cache_sop_template(self, template_name: str, template: dict) -> None:
        self.set_json(f"sop:template:{template_name}", template)

    def get_sop_template(self, template_name: str) -> dict | None:
        return self.get_json(f"sop:template:{template_name}")
