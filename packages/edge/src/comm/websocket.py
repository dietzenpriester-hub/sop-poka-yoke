"""工业平板 WebSocket 推送"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import aiohttp
from loguru import logger


class TabletWebSocketServer:

    def __init__(self, host: str = "0.0.0.0", port: int = 8765) -> None:
        self.host = host
        self.port = port
        self._clients: list[aiohttp.web.WebSocketResponse] = []

    async def handler(self, request: aiohttp.web.Request) -> aiohttp.web.WebSocketResponse:
        ws = aiohttp.web.WebSocketResponse()
        await ws.prepare(request)
        # 若设置 SOP_WS_TOKEN，首条消息须为 {"token": "<token>"}；未设置则跳过校验（开发模式）
        expected = os.environ.get("SOP_WS_TOKEN")
        if expected:
            try:
                msg = await ws.receive()
                if msg.type != aiohttp.WSMsgType.TEXT:
                    logger.warning("WebSocket 认证失败：首条消息非文本")
                    await ws.close()
                    return ws
                data = json.loads(msg.data)
                if data.get("token") != expected:
                    logger.warning("WebSocket 认证失败：token 不匹配")
                    await ws.close()
                    return ws
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning("WebSocket 认证失败：{}", e)
                await ws.close()
                return ws
        self._clients.append(ws)
        logger.info("平板 WebSocket 已连接")
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    logger.debug("平板消息: {}", msg.data)
        finally:
            self._clients.remove(ws)
        return ws

    async def broadcast(self, data: dict[str, Any]) -> None:
        message = json.dumps(data, ensure_ascii=False)
        dead_clients = []
        for ws in list(self._clients):
            try:
                await ws.send_str(message)
            except Exception:
                dead_clients.append(ws)
        for ws in dead_clients:
            if ws in self._clients:
                self._clients.remove(ws)

    async def start(self) -> None:
        app = aiohttp.web.Application()
        app.router.add_get("/ws", self.handler)
        runner = aiohttp.web.AppRunner(app)
        await runner.setup()
        site = aiohttp.web.TCPSite(runner, self.host, self.port)
        await site.start()
        logger.info("平板 WebSocket 服务启动: {}:{}", self.host, self.port)
