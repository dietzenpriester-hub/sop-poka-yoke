"""WebSocket 实时推送"""

import json
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from loguru import logger

from src.core.security import verify_token

router = APIRouter()

active_connections: dict[str, list[WebSocket]] = {}


def _validate_station_id(station_id: str) -> bool:
    """基础校验：station_id 仅允许字母数字与连字符，长度限制。"""
    if not station_id or len(station_id) > 64:
        return False
    return all(c.isalnum() or c in ("-", "_") for c in station_id)


@router.websocket("/ws/live/{station_id}")
async def websocket_live(websocket: WebSocket, station_id: str):
    if not _validate_station_id(station_id):
        await websocket.close(code=4400)
        return

    await websocket.accept()

    try:
        raw = await websocket.receive_text()
    except WebSocketDisconnect:
        return
    try:
        auth_msg = json.loads(raw)
    except json.JSONDecodeError:
        await websocket.close(code=4401)
        return
    token = auth_msg.get("token") if isinstance(auth_msg, dict) else None
    if not token:
        await websocket.close(code=4401)
        return
    try:
        user_payload = verify_token(token)
    except HTTPException:
        await websocket.close(code=4401)
        return

    user_role = user_payload.get("role", "") if isinstance(user_payload, dict) else ""
    if not user_role:
        await websocket.close(code=4403)
        return

    if station_id not in active_connections:
        active_connections[station_id] = []
    active_connections[station_id].append(websocket)
    logger.info("WebSocket 连接: station={}", station_id)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                logger.warning("无效 JSON: station={}", station_id)
                continue
            logger.debug("收到消息: station={}, msg={}", station_id, msg)
    except WebSocketDisconnect:
        pass
    finally:
        if station_id in active_connections:
            try:
                active_connections[station_id].remove(websocket)
            except ValueError:
                pass
            if not active_connections[station_id]:
                del active_connections[station_id]
        logger.info("WebSocket 断开: station={}", station_id)


async def broadcast_to_station(station_id: str, message: dict[str, Any]) -> None:
    if station_id not in active_connections:
        return
    dead: list[WebSocket] = []
    for ws in list(active_connections[station_id]):
        try:
            await ws.send_json(message)
        except Exception as e:
            logger.exception("WebSocket 广播失败: station={} error={}", station_id, e)
            dead.append(ws)
    for ws in dead:
        try:
            active_connections[station_id].remove(ws)
        except ValueError:
            pass
    if station_id in active_connections and not active_connections[station_id]:
        del active_connections[station_id]
