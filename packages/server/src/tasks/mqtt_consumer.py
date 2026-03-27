"""MQTT 消息消费：订阅边缘端消息 → 持久化报警 → WebSocket 广播。"""

import asyncio
import json
import threading

import paho.mqtt.client as mqtt
from loguru import logger

from src.api.websocket_live import broadcast_to_station
from src.core.config import settings


def _parse_topic(topic: str) -> tuple[str | None, str | None]:
    """解析 MQTT 主题，返回 (station_id, event_kind)。"""
    parts = topic.split("/")
    if len(parts) >= 3 and parts[0] == settings.MQTT_TOPIC_PREFIX:
        station_id = parts[1]
        event_kind = "/".join(parts[2:])
        return station_id, event_kind
    return None, None


async def _handle_alert(station_id: str, payload: dict) -> None:
    """将报警持久化到数据库并广播到前端。"""
    from src.core.database import async_session_factory
    from src.models.alert import AlertEvent

    alert_id = None
    try:
        async with async_session_factory() as session:
            alert = AlertEvent(
                station_code=station_id,
                alert_type=payload.get("alert_code", "UNKNOWN"),
                severity=payload.get("severity", "WARN"),
                message=payload.get("message", ""),
                step_index=payload.get("step_index", 0),
                video_url=payload.get("video_url", ""),
            )
            session.add(alert)
            await session.commit()
            await session.refresh(alert)
            alert_id = alert.id
            logger.info("报警已入库: id={} type={} station={}", alert.id, alert.alert_type, station_id)
    except Exception as e:
        logger.error("报警入库失败: station={} error={}", station_id, e)

    await broadcast_to_station(station_id, {
        "type": "alert",
        "alert": {
            "id": alert_id,
            "alert_type": payload.get("alert_code", "UNKNOWN"),
            "severity": payload.get("severity", "WARN"),
            "message": payload.get("message", ""),
            "step_index": payload.get("step_index", 0),
            "station_id": station_id,
        },
    })


async def _dispatch_message(station_id: str, event_kind: str, payload: dict) -> None:
    """根据事件类型分发处理逻辑。"""
    if event_kind == "alert/raise":
        await _handle_alert(station_id, payload)
    else:
        await broadcast_to_station(station_id, {"topic": f"{settings.MQTT_TOPIC_PREFIX}/{station_id}/{event_kind}", "payload": payload})


def _run_mqtt_loop(loop: asyncio.AbstractEventLoop) -> None:
    def on_connect(client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            client.subscribe(f"{settings.MQTT_TOPIC_PREFIX}/+/#")
            logger.info("MQTT 已订阅 {}/+/#", settings.MQTT_TOPIC_PREFIX)
        else:
            logger.error("MQTT 连接失败: {}", reason_code)

    def on_message(client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except json.JSONDecodeError:
            payload = {"raw": msg.payload.decode("utf-8", errors="replace")}
        station_id, event_kind = _parse_topic(msg.topic)
        if not station_id or not event_kind:
            return
        asyncio.run_coroutine_threadsafe(
            _dispatch_message(station_id, event_kind, payload), loop,
        )

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(settings.MQTT_BROKER_HOST, settings.MQTT_BROKER_PORT, 60)
        client.loop_forever()
    except Exception as e:
        logger.error("MQTT 连接异常: {}，消费者线程退出", e)


def start_mqtt_consumer_in_thread() -> threading.Thread:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.get_event_loop()
    t = threading.Thread(target=_run_mqtt_loop, args=(loop,), daemon=True, name="mqtt-consumer")
    t.start()
    logger.info("MQTT 消费者线程已启动")
    return t
