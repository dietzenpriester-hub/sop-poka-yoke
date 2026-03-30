"""工业平板 WebSocket 推送"""

from __future__ import annotations

import asyncio
import hmac
import json
import os
from typing import Any

import aiohttp
from loguru import logger

MAX_WS_MESSAGE_BYTES = 65536


class TabletWebSocketServer:

    def __init__(self, host: str = "0.0.0.0", port: int = 8765) -> None:
        self.host = host
        self.port = port
        self._clients: list[aiohttp.web.WebSocketResponse] = []
        self._clients_lock = asyncio.Lock()

    async def handler(self, request: aiohttp.web.Request) -> aiohttp.web.WebSocketResponse:
        ws = aiohttp.web.WebSocketResponse()
        await ws.prepare(request)
        expected = os.environ.get("SOP_WS_TOKEN")
        if not expected:
            is_prod = os.environ.get("SOP_ENV", "").lower() == "production"
            if is_prod:
                logger.error("生产环境未设置 SOP_WS_TOKEN，拒绝 WebSocket 连接")
                await ws.close()
                return ws
            logger.warning("SOP_WS_TOKEN 未设置，跳过认证（仅限开发环境）")
        if expected:
            try:
                msg = await ws.receive()
                if msg.type != aiohttp.WSMsgType.TEXT:
                    logger.warning("WebSocket 认证失败：首条消息非文本")
                    await ws.close()
                    return ws
                data = json.loads(msg.data)
                tok = str(data.get("token", ""))
                exp = str(expected)
                if len(tok) != len(exp) or not hmac.compare_digest(
                    tok.encode("utf-8"), exp.encode("utf-8")
                ):
                    logger.warning("WebSocket 认证失败：token 不匹配")
                    await ws.close()
                    return ws
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning("WebSocket 认证失败：{}", e)
                await ws.close()
                return ws
        async with self._clients_lock:
            self._clients.append(ws)
        logger.info("平板 WebSocket 已连接")
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    logger.debug("平板消息: {}", msg.data)
        finally:
            async with self._clients_lock:
                try:
                    self._clients.remove(ws)
                except ValueError:
                    pass
        return ws

    async def broadcast(self, data: dict[str, Any]) -> None:
        message = json.dumps(data, ensure_ascii=False)
        if len(message.encode("utf-8")) > MAX_WS_MESSAGE_BYTES:
            logger.warning(
                "WebSocket broadcast 消息过大 ({}B > {}B)，已跳过",
                len(message.encode("utf-8")),
                MAX_WS_MESSAGE_BYTES,
            )
            return
        async with self._clients_lock:
            clients = list(self._clients)
        dead_clients: list[aiohttp.web.WebSocketResponse] = []
        for ws in clients:
            try:
                await ws.send_str(message)
            except Exception:
                dead_clients.append(ws)
        if dead_clients:
            async with self._clients_lock:
                for ws in dead_clients:
                    try:
                        self._clients.remove(ws)
                    except ValueError:
                        pass

    async def start(self) -> None:
        app = aiohttp.web.Application()
        app.router.add_get("/ws", self.handler)
        runner = aiohttp.web.AppRunner(app)
        await runner.setup()
        site = aiohttp.web.TCPSite(runner, self.host, self.port)
        await site.start()
        logger.info("平板 WebSocket 服务启动: {}:{}", self.host, self.port)
