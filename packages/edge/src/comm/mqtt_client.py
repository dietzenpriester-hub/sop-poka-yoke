"""MQTT 消息收发"""

from __future__ import annotations

import json
import os
from typing import Any, Callable

import paho.mqtt.client as mqtt
from loguru import logger

MAX_PAYLOAD_BYTES = 1024 * 1024  # 1 MB


class MQTTClient:

    def __init__(self, broker: str = "localhost", port: int = 1883, client_id: str = "edge-01") -> None:
        self.broker = broker
        self.port = port
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._handlers: dict[str, Callable] = {}

    def connect(self) -> None:
        username = os.environ.get("SOP_MQTT_USERNAME", "")
        password = os.environ.get("SOP_MQTT_PASSWORD", "")
        if username:
            self._client.username_pw_set(username, password)
        use_tls = os.environ.get("SOP_MQTT_TLS", "0") == "1"
        if use_tls:
            self._client.tls_set()
        self._client.connect(self.broker, self.port, 60)
        self._client.loop_start()
        logger.info("MQTT 已连接: {}:{} (TLS={})", self.broker, self.port, use_tls)

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if len(data) > MAX_PAYLOAD_BYTES:
            logger.warning("MQTT publish 消息过大 ({}B)，已丢弃: topic={}", len(data), topic)
            return
        info = self._client.publish(topic, data)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.warning("MQTT publish 失败: rc={} topic={}", info.rc, topic)

    def subscribe(self, topic: str, handler: Callable) -> None:
        self._handlers[topic] = handler
        self._client.subscribe(topic)

    def disconnect(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        if reason_code == 0:
            logger.info("MQTT 连接成功")
            for topic in self._handlers:
                self._client.subscribe(topic)
        else:
            logger.error("MQTT 连接失败: {}", reason_code)

    def _on_message(self, client, userdata, msg) -> None:
        if len(msg.payload) > MAX_PAYLOAD_BYTES:
            logger.warning("MQTT 消息过大 ({}B)，已丢弃: topic={}", len(msg.payload), msg.topic)
            return
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except json.JSONDecodeError:
            payload = {"raw": msg.payload.decode("utf-8", errors="replace")}
        handler = self._handlers.get(msg.topic)
        if handler:
            handler(payload)
