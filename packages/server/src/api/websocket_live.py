"""WebSocket 实时推送"""

import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

router = APIRouter()

active_connections: dict[str, list[WebSocket]] = {}


@router.websocket("/ws/live/{station_id}")
async def websocket_live(websocket: WebSocket, station_id: str):
    await websocket.accept()
    if station_id not in active_connections:
        active_connections[station_id] = []
    active_connections[station_id].append(websocket)
    logger.info("WebSocket 连接: station={}", station_id)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            logger.info("收到消息: station={}, msg={}", station_id, msg)
    except WebSocketDisconnect:
        active_connections[station_id].remove(websocket)
        logger.info("WebSocket 断开: station={}", station_id)


async def broadcast_to_station(station_id: str, message: dict[str, Any]) -> None:
    if station_id not in active_connections:
        return
    for ws in list(active_connections[station_id]):
        try:
            await ws.send_json(message)
        except Exception:
            pass
