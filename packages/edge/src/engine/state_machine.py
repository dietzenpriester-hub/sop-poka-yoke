"""SOP 有限状态机（含防抖机制）"""

import time
from dataclasses import dataclass, field, fields
from enum import Enum

from loguru import logger


class SOPStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    STEP_OK = "step_ok"
    STEP_NG = "step_ng"
    ERROR = "error"
    OVERRIDE = "override"
    TIMEOUT = "timeout"
    COMPLETE = "complete"


@dataclass
class StepDefinition:
    index: int
    name: str
    description: str = ""
    required_objects: list[str] = field(default_factory=list)
    action_type: str = ""
    timeout_seconds: float = 60.0
    is_optional: bool = False


@dataclass
class StepResult:
    step_index: int
    step_name: str
    result: str
    confidence: float
    timestamp: float
    video_clip_url: str = ""
    snapshot_url: str = ""


_STEP_KW_FIELDS = {f.name for f in fields(StepDefinition)} - {"index"}


class SOPStateMachine:

    def __init__(self, sop_template: dict, debounce_seconds: float = 0.5) -> None:
        self.template_name = sop_template["name"]
        self.steps = []
        for i, raw in enumerate(sop_template["steps"]):
            step = raw if isinstance(raw, dict) else {}
            filtered = {k: v for k, v in step.items() if k in _STEP_KW_FIELDS}
            filtered.setdefault("name", f"步骤{i + 1}")
            self.steps.append(StepDefinition(index=i, **filtered))
        self.debounce_seconds = debounce_seconds
        self.status = SOPStatus.IDLE
        self.current_step_index = 0
        self.results: list[StepResult] = []
        self.work_order_sn: str | None = None
        self.start_time: float | None = None
        self._step_start_time: float | None = None
        self._pending_match: dict | None = None
        self._pending_since: float = 0.0

    def start(self, work_order_sn: str) -> None:
        self.work_order_sn = work_order_sn
        self.status = SOPStatus.RUNNING
        self.current_step_index = 0
        self.results = []
        self.start_time = time.time()
        self._step_start_time = time.time()
        self._pending_match = None
        self._pending_since = 0.0
        logger.info("工单开始: SN={}, SOP={}", work_order_sn, self.template_name)

    def get_current_step(self) -> StepDefinition | None:
        if self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    def process_action(self, action_result: dict) -> dict:
        if self.status not in (SOPStatus.RUNNING, SOPStatus.STEP_OK, SOPStatus.STEP_NG):
            return {"event": "ignored", "message": f"当前状态 {self.status.value} 不接受动作（超时请先 override 或 reset）"}
        current_step = self.get_current_step()
        if not current_step:
            return {"event": "error", "message": "无更多步骤"}

        matches = action_result.get("matches_expected", False)
        confidence = action_result.get("confidence", 0.0)

        if matches and confidence >= 0.6:
            now = time.time()
            if self._pending_match is None:
                self._pending_match = action_result
                self._pending_since = now
                return {"event": "debounce", "message": f"动作匹配中，等待防抖确认（{self.debounce_seconds}s）"}
            if now - self._pending_since < self.debounce_seconds:
                return {"event": "debounce", "message": f"防抖中… {now - self._pending_since:.1f}/{self.debounce_seconds}s"}
            self._pending_match = None
        else:
            self._pending_match = None

        if matches and confidence >= 0.6:
            self.results.append(StepResult(
                step_index=self.current_step_index, step_name=current_step.name,
                result="OK", confidence=confidence, timestamp=time.time(),
            ))
            self.current_step_index += 1
            self._step_start_time = time.time()
            if self.current_step_index >= len(self.steps):
                self.status = SOPStatus.COMPLETE
                logger.info("工单完成: SN={}", self.work_order_sn)
                return {"event": "complete", "message": "所有步骤已完成"}
            self.status = SOPStatus.STEP_OK
            return {"event": "step_ok", "message": f"步骤 {current_step.name} 完成", "next_step": self.steps[self.current_step_index].name}
        else:
            self.status = SOPStatus.STEP_NG
            return {"event": "step_ng", "message": f"动作不匹配: 期望 [{current_step.name}]", "confidence": confidence}

    def check_timeout(self) -> dict | None:
        # STEP_OK 时已进入下一步等待，仍需检测当前步超时（RUNNING 与 STEP_OK 均表示工单进行中）
        if self.status not in (SOPStatus.RUNNING, SOPStatus.STEP_OK):
            return None
        current_step = self.get_current_step()
        if not current_step or self._step_start_time is None:
            return None
        elapsed = time.time() - self._step_start_time
        if elapsed > current_step.timeout_seconds:
            self.status = SOPStatus.TIMEOUT
            return {"event": "timeout", "message": f"步骤 {current_step.name} 超时 ({elapsed:.0f}s)", "step_index": self.current_step_index}
        return None

    def override(self, operator_badge: str, reason: str) -> dict:
        current_step = self.get_current_step()
        if not current_step:
            return {"event": "error", "message": "无法放行：无当前步骤"}
        self.results.append(StepResult(
            step_index=self.current_step_index, step_name=current_step.name,
            result="OVERRIDE", confidence=0.0, timestamp=time.time(),
        ))
        self.current_step_index += 1
        self._step_start_time = time.time()
        self.status = SOPStatus.RUNNING
        logger.warning("强制放行: step={}, badge={}, reason={}", current_step.name, operator_badge, reason)
        if self.current_step_index >= len(self.steps):
            self.status = SOPStatus.COMPLETE
            return {"event": "complete", "message": "所有步骤已完成（含放行）"}
        return {"event": "override_ok", "message": f"步骤 {current_step.name} 已强制放行"}

    def reset(self) -> None:
        self.status = SOPStatus.IDLE
        self.current_step_index = 0
        self.results = []
        self.work_order_sn = None
        self.start_time = None
        self._step_start_time = None
        self._pending_match = None
        self._pending_since = 0.0
