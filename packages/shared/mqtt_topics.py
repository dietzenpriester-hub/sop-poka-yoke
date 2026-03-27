"""MQTT 主题模板：edge / server 共用，禁止硬编码散落。"""


class MQTTTopics:
    """使用 format(station_id=...) 生成最终主题。"""

    STEP_COMPLETE = "sop/{station_id}/step/complete"
    ALERT_RAISE = "sop/{station_id}/alert/raise"
    WORKORDER_START = "sop/{station_id}/workorder/start"
    WORKORDER_DONE = "sop/{station_id}/workorder/done"
    OVERRIDE = "sop/{station_id}/override"
    HEARTBEAT = "sop/{station_id}/heartbeat"
    SYNC_QUEUE = "sop/{station_id}/sync/queue"

    @staticmethod
    def step_complete(station_id: str) -> str:
        return MQTTTopics.STEP_COMPLETE.format(station_id=station_id)

    @staticmethod
    def alert_raise(station_id: str) -> str:
        return MQTTTopics.ALERT_RAISE.format(station_id=station_id)

    @staticmethod
    def workorder_start(station_id: str) -> str:
        return MQTTTopics.WORKORDER_START.format(station_id=station_id)

    @staticmethod
    def workorder_done(station_id: str) -> str:
        return MQTTTopics.WORKORDER_DONE.format(station_id=station_id)

    @staticmethod
    def override(station_id: str) -> str:
        return MQTTTopics.OVERRIDE.format(station_id=station_id)

    @staticmethod
    def heartbeat(station_id: str) -> str:
        return MQTTTopics.HEARTBEAT.format(station_id=station_id)

    @staticmethod
    def sync_queue(station_id: str) -> str:
        return MQTTTopics.SYNC_QUEUE.format(station_id=station_id)
