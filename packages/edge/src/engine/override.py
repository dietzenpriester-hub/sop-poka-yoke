"""人工强制放行管理（审计日志）"""

import time
from dataclasses import dataclass

from loguru import logger


@dataclass
class OverrideRecord:
    work_order_sn: str
    step_index: int
    step_name: str
    operator_badge: str
    reason: str
    timestamp: float
    video_url: str = ""


class OverrideManager:

    def __init__(self) -> None:
        self._records: list[OverrideRecord] = []

    def record_override(
        self, work_order_sn: str, step_index: int, step_name: str,
        operator_badge: str, reason: str, video_url: str = "",
    ) -> OverrideRecord:
        record = OverrideRecord(
            work_order_sn=work_order_sn, step_index=step_index, step_name=step_name,
            operator_badge=operator_badge, reason=reason, timestamp=time.time(), video_url=video_url,
        )
        self._records.append(record)
        logger.warning(
            "OVERRIDE 审计日志: SN={} step={} badge={} reason={}",
            work_order_sn, step_name, operator_badge, reason,
        )
        return record

    def get_records(self, work_order_sn: str | None = None) -> list[OverrideRecord]:
        if work_order_sn:
            return [r for r in self._records if r.work_order_sn == work_order_sn]
        return list(self._records)
