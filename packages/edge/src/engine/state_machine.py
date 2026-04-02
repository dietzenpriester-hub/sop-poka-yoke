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
    timeout_seconds: float = 120.0
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
    MIN_CONFIDENCE = 0.75

    def __init__(self, sop_template: dict, debounce_seconds: float = 0.5,
                 ng_tolerance: int = 3, global_detect: bool = False,
                 min_consecutive_pass: int = 3) -> None:
        self.template_name = sop_template["name"]
        self.steps = []
        for i, raw in enumerate(sop_template["steps"]):
            step = raw if isinstance(raw, dict) else {}
            filtered = {k: v for k, v in step.items() if k in _STEP_KW_FIELDS}
            filtered.setdefault("name", f"步骤{i + 1}")
            self.steps.append(StepDefinition(index=i, **filtered))
        self.debounce_seconds = debounce_seconds
        self.ng_tolerance = ng_tolerance
        self.global_detect = global_detect
        self.min_consecutive_pass = max(min_consecutive_pass, 1)
        self.status = SOPStatus.IDLE
        self.current_step_index = 0
        self.completed_indices: set[int] = set()
        self.results: list[StepResult] = []
        self.work_order_sn: str | None = None
        self.start_time: float | None = None
        self._step_start_time: float | None = None
        self._pending_match: dict | None = None
        self._pending_since: float = 0.0
        self._consecutive_ng: int = 0
        self._consecutive_ok: int = 0

    def load_template(self, sop_template: dict) -> None:
        """动态加载新的 SOP 模板（仅在 IDLE 状态允许）。"""
        if self.status != SOPStatus.IDLE:
            logger.warning("状态机非 IDLE（当前={}），拒绝重载模板", self.status.value)
            return
        self.template_name = sop_template["name"]
        self.steps = []
        for i, raw in enumerate(sop_template["steps"]):
            step = raw if isinstance(raw, dict) else {}
            filtered = {k: v for k, v in step.items() if k in _STEP_KW_FIELDS}
            filtered.setdefault("name", f"步骤{i + 1}")
            self.steps.append(StepDefinition(index=i, **filtered))
        logger.info("已重载 SOP 模板: {} ({} 步)", self.template_name, len(self.steps))

    def start(self, work_order_sn: str) -> None:
        self.work_order_sn = work_order_sn
        self.status = SOPStatus.RUNNING
        self.current_step_index = 0
        self.completed_indices = set()
        self.results = []
        self.start_time = time.time()
        self._step_start_time = time.time()
        self._pending_match = None
        self._pending_since = 0.0
        self._consecutive_ng = 0
        self._consecutive_ok = 0
        logger.info("工单开始: SN={}, SOP={}, 全局检测={}, 连续通过要求={}",
                    work_order_sn, self.template_name, self.global_detect, self.min_consecutive_pass)

    def get_current_step(self) -> StepDefinition | None:
        if self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    def process_action(self, action_result: dict) -> dict:
        if self.status == SOPStatus.STEP_NG:
            return {
                "type": "blocked",
                "reason": "STEP_NG 需要 reset 或 override 后才能继续",
            }
        if self.status == SOPStatus.TIMEOUT:
            return {
                "type": "blocked",
                "reason": "TIMEOUT 需要 reset 或 override 后才能继续",
            }
        if self.status not in (SOPStatus.RUNNING, SOPStatus.STEP_OK):
            return {"event": "ignored", "message": f"当前状态 {self.status.value} 不接受动作（请先 override 或 reset）"}
        current_step = self.get_current_step()
        if not current_step:
            return {"event": "error", "message": "无更多步骤"}

        matches = action_result.get("matches_expected", False)
        confidence = action_result.get("confidence", 0.0)

        if matches and confidence >= self.MIN_CONFIDENCE:
            self._consecutive_ng = 0
            self._consecutive_ok += 1
            logger.info("动作匹配 ({}/{}): 步骤 [{}], conf={:.2f}",
                        self._consecutive_ok, self.min_consecutive_pass, current_step.name, confidence)

            if self._consecutive_ok < self.min_consecutive_pass:
                return {"event": "matching", "message": f"动作匹配中 ({self._consecutive_ok}/{self.min_consecutive_pass})", "confidence": confidence}

            self._consecutive_ok = 0
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
            if self._consecutive_ok > 0:
                logger.info("匹配中断 (连续OK {} → 0)，重新计数", self._consecutive_ok)
            self._consecutive_ok = 0
            self._consecutive_ng += 1
            if self._consecutive_ng < self.ng_tolerance:
                logger.info("动作不匹配 ({}/{}): 期望 [{}]，继续观察",
                            self._consecutive_ng, self.ng_tolerance, current_step.name)
                return {"event": "ng_pending", "message": f"动作不匹配 ({self._consecutive_ng}/{self.ng_tolerance})", "confidence": confidence}
            self.status = SOPStatus.STEP_NG
            self._consecutive_ng = 0
            return {"event": "step_ng", "message": f"动作不匹配: 期望 [{current_step.name}]", "confidence": confidence}

    def process_global_action(self, action_result: dict) -> dict:
        """全局检测模式：操作员可以以任意顺序完成步骤。"""
        if self.status not in (SOPStatus.RUNNING, SOPStatus.STEP_OK):
            return {"event": "ignored", "message": f"当前状态 {self.status.value} 不接受动作"}

        matched_step = action_result.get("matched_step", -1)
        confidence = action_result.get("confidence", 0.0)
        action_desc = action_result.get("action", "")

        if matched_step < 0 or confidence < self.MIN_CONFIDENCE:
            return {"event": "observing", "message": f"观察中: {action_desc}"}

        if matched_step >= len(self.steps):
            return {"event": "observing", "message": f"无效步骤编号 {matched_step}"}

        if matched_step in self.completed_indices:
            return {"event": "observing", "message": f"步骤 {self.steps[matched_step].name} 已完成，继续观察"}

        step = self.steps[matched_step]
        self.completed_indices.add(matched_step)
        self.results.append(StepResult(
            step_index=matched_step, step_name=step.name,
            result="OK", confidence=confidence, timestamp=time.time(),
        ))
        logger.info("全局检测: 步骤 {} [{}] 完成 ({}/{})",
                     matched_step, step.name, len(self.completed_indices), len(self.steps))

        if len(self.completed_indices) >= len(self.steps):
            self.status = SOPStatus.COMPLETE
            logger.info("工单完成: SN={}", self.work_order_sn)
            return {"event": "complete", "message": "所有步骤已完成"}

        self.status = SOPStatus.STEP_OK
        remaining = [s.name for i, s in enumerate(self.steps) if i not in self.completed_indices]
        return {
            "event": "step_ok",
            "message": f"步骤 {step.name} 完成",
            "completed": len(self.completed_indices),
            "total": len(self.steps),
            "remaining": remaining,
        }

    def check_timeout(self) -> dict | None:
        if self.global_detect:
            return None
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
        self.completed_indices = set()
        self.results = []
        self.work_order_sn = None
        self.start_time = None
        self._step_start_time = None
        self._pending_match = None
        self._pending_since = 0.0
        self._consecutive_ng = 0
        self._consecutive_ok = 0
