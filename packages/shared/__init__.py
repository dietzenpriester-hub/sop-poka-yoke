"""SOP 防呆系统 — 共享协议包"""

from .alert_codes import AlertCode, ALERT_DESCRIPTIONS
from .constants import (
    APP_NAME, APP_VERSION,
    CONFIDENCE_OK_THRESHOLD, CONFIDENCE_WARN_THRESHOLD,
    DEFAULT_STEP_TIMEOUT_SECONDS, DEFAULT_DEBOUNCE_SECONDS,
)
from .event_types import EdgeEventType, SyncPriority
from .mqtt_topics import MQTTTopics

__all__ = [
    "AlertCode", "ALERT_DESCRIPTIONS",
    "APP_NAME", "APP_VERSION",
    "CONFIDENCE_OK_THRESHOLD", "CONFIDENCE_WARN_THRESHOLD",
    "DEFAULT_STEP_TIMEOUT_SECONDS", "DEFAULT_DEBOUNCE_SECONDS",
    "EdgeEventType", "SyncPriority",
    "MQTTTopics",
]
