"""MQTT 主题模板：edge / server 共用，禁止硬编码散落。"""

import re

_STATION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


class MQTTTopics:
    """使用 format(station_id=...) 生成最终主题；前缀可通过构造参数配置。"""

    DEFAULT_PREFIX = "sop"

    def __init__(self, prefix: str = DEFAULT_PREFIX) -> None:
        p = prefix.strip().strip("/")
        self._prefix = p if p else self.DEFAULT_PREFIX
        base = self._prefix
        self.STEP_COMPLETE = f"{base}/{{station_id}}/step/complete"
        self.STEP_VIDEO = f"{base}/{{station_id}}/step/video"
        self.ALERT_RAISE = f"{base}/{{station_id}}/alert/raise"
        self.WORKORDER_START = f"{base}/{{station_id}}/workorder/start"
        self.WORKORDER_DONE = f"{base}/{{station_id}}/workorder/done"
        self.OVERRIDE = f"{base}/{{station_id}}/override"
        self.HEARTBEAT = f"{base}/{{station_id}}/heartbeat"
        self.SYNC_QUEUE = f"{base}/{{station_id}}/sync/queue"
        self.DETECTION = f"{base}/{{station_id}}/detection"

    @staticmethod
    def validate_station_id(station_id: str) -> str:
        if not _STATION_ID_PATTERN.match(station_id):
            raise ValueError(f"station_id 含非法字符: {station_id!r} (仅允许 a-zA-Z0-9_-)")
        return station_id

    def _topic(self, template: str, station_id: str) -> str:
        return template.format(station_id=self.validate_station_id(station_id))

    def step_complete(self, station_id: str) -> str:
        return self._topic(self.STEP_COMPLETE, station_id)

    def step_video(self, station_id: str) -> str:
        return self._topic(self.STEP_VIDEO, station_id)

    def alert_raise(self, station_id: str) -> str:
        return self._topic(self.ALERT_RAISE, station_id)

    def workorder_start(self, station_id: str) -> str:
        return self._topic(self.WORKORDER_START, station_id)

    def workorder_done(self, station_id: str) -> str:
        return self._topic(self.WORKORDER_DONE, station_id)

    def override(self, station_id: str) -> str:
        return self._topic(self.OVERRIDE, station_id)

    def heartbeat(self, station_id: str) -> str:
        return self._topic(self.HEARTBEAT, station_id)

    def sync_queue(self, station_id: str) -> str:
        return self._topic(self.SYNC_QUEUE, station_id)

    def detection(self, station_id: str) -> str:
        return self._topic(self.DETECTION, station_id)
