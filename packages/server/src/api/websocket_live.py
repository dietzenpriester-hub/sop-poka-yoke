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
    user_id = user_payload.get("user_id") if isinstance(user_payload, dict) else None
    if not user_role:
        await websocket.close(code=4403)
        return

    # 非管理员用户连接时记录审计日志，便于追踪越权访问
    if user_role != "admin":
        logger.info("非管理员用户(id={}, role={})连接工位 {} 的 WebSocket", user_id, user_role, station_id)

    if station_id not in active_connections:
        active_connections[station_id] = []
    active_connections[station_id].append(websocket)
    logger.info("WebSocket 连接: station={} user_id={} role={}", station_id, user_id, user_role)
    try:
        while True:
            data = await websocket.receive_text()
            if len(data) > 4096:
                logger.warning("消息过长已忽略: station={}, len={}", station_id, len(data))
                continue
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
