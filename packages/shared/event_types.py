"""跨服务事件类型常量（MQTT payload、WebSocket、审计日志）。"""

from enum import StrEnum


class EdgeEventType(StrEnum):
    STEP_OK = "step_ok"
    STEP_NG = "step_ng"
    COMPLETE = "complete"
    TIMEOUT = "timeout"
    OVERRIDE = "override"
    MATERIAL_OK = "material_ok"
    MATERIAL_NG = "material_ng"
    COMPLETION_PASS = "completion_pass"
    COMPLETION_FAIL = "completion_fail"
    HEARTBEAT = "heartbeat"
    SYNC_ACK = "sync_ack"


class SyncPriority(StrEnum):
    """离线补传优先级（与 data_sync 一致）。"""

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
