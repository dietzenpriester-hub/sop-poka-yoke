"""MQTT 消息消费"""

import asyncio
import json
import threading

import paho.mqtt.client as mqtt
from loguru import logger

from src.api.websocket_live import broadcast_to_station
from src.core.config import settings


def _topic_station_id(topic: str) -> str | None:
    parts = topic.split("/")
    if len(parts) >= 2 and parts[0] == settings.MQTT_TOPIC_PREFIX:
        return parts[1]
    return None


def _run_mqtt_loop(loop: asyncio.AbstractEventLoop) -> None:
    def on_connect(client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            client.subscribe(f"{settings.MQTT_TOPIC_PREFIX}/+/+")
            logger.info("MQTT 已订阅 %s/+/+", settings.MQTT_TOPIC_PREFIX)
        else:
            logger.error("MQTT 连接失败: {}", reason_code)

    def on_message(client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except json.JSONDecodeError:
            payload = {"raw": msg.payload.decode("utf-8", errors="replace")}
        station_id = _topic_station_id(msg.topic)
        if not station_id:
            return
        asyncio.run_coroutine_threadsafe(
            broadcast_to_station(station_id, {"topic": msg.topic, "payload": payload}), loop,
        )

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(settings.MQTT_BROKER_HOST, settings.MQTT_BROKER_PORT, 60)
    client.loop_forever()


def start_mqtt_consumer_in_thread() -> threading.Thread:
    loop = asyncio.get_event_loop()
    t = threading.Thread(target=_run_mqtt_loop, args=(loop,), daemon=True)
    t.start()
    return t
