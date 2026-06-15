"""VLM 触发门控：用 ROI、检测稳定性和冷却时间减少误判与无效推理。"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
import time
from typing import Any


Roi = tuple[float, float, float, float]


@dataclass
class VLMGateDecision:
    allowed: bool
    reason: str
    stable_hits: int
    matched_objects: list[str] = field(default_factory=list)


@dataclass
class VLMGateConfig:
    enabled: bool = True
    roi: Roi | None = None
    stable_frames: int = 2
    cooldown_seconds: float = 1.0
    min_confidence: float = 0.25
    target_objects: set[str] = field(default_factory=set)


class VLMTriggerGate:
    """在提交 VLM 前做轻量确认，避免单帧噪声和非作业区域触发。"""

    def __init__(self, config: VLMGateConfig | None = None) -> None:
        self.config = config or VLMGateConfig()
        self._stable_hits = 0
        self._last_submit_at = 0.0

    @classmethod
    def from_env(cls) -> "VLMTriggerGate":
        return cls(
            VLMGateConfig(
                enabled=_env_bool("SOP_VLM_GATE_ENABLED", True),
                roi=_parse_roi(os.environ.get("SOP_OPERATION_ROI", "")),
                stable_frames=max(1, int(os.environ.get("SOP_VLM_STABLE_FRAMES", "2"))),
                cooldown_seconds=max(0.0, float(os.environ.get("SOP_VLM_GATE_COOLDOWN", "1.0"))),
                min_confidence=max(0.0, float(os.environ.get("SOP_VLM_MIN_DET_CONF", "0.25"))),
                target_objects=_parse_targets(os.environ.get("SOP_VLM_TARGET_OBJECTS", "")),
            )
        )

    @property
    def stable_hits(self) -> int:
        return self._stable_hits

    def reset(self) -> None:
        self._stable_hits = 0
        self._last_submit_at = 0.0

    def should_submit(
        self,
        detections: list[Any],
        frame_shape: tuple[int, ...],
        *,
        now: float | None = None,
    ) -> VLMGateDecision:
        now = time.monotonic() if now is None else now
        if not self.config.enabled:
            return self._allow(now, "disabled", [])

        elapsed = now - self._last_submit_at
        if elapsed < self.config.cooldown_seconds:
            return VLMGateDecision(
                allowed=False,
                reason="cooldown",
                stable_hits=self._stable_hits,
            )

        matched = self._matched_objects(detections, frame_shape)
        if not matched:
            self._stable_hits = 0
            return VLMGateDecision(allowed=False, reason="no_relevant_detection", stable_hits=0)

        self._stable_hits += 1
        if self._stable_hits < self.config.stable_frames:
            return VLMGateDecision(
                allowed=False,
                reason="warming",
                stable_hits=self._stable_hits,
                matched_objects=matched,
            )

        return self._allow(now, "stable", matched)

    def _allow(self, now: float, reason: str, matched: list[str]) -> VLMGateDecision:
        self._last_submit_at = now
        self._stable_hits = 0
        return VLMGateDecision(
            allowed=True,
            reason=reason,
            stable_hits=self.config.stable_frames,
            matched_objects=matched,
        )

    def _matched_objects(self, detections: list[Any], frame_shape: tuple[int, ...]) -> list[str]:
        matched: list[str] = []
        for det in detections:
            label = _det_label(det)
            if self.config.target_objects and label not in self.config.target_objects:
                continue
            if _det_confidence(det) < self.config.min_confidence:
                continue
            bbox = _det_bbox(det)
            if bbox is None:
                continue
            if self.config.roi is not None and not _bbox_center_in_roi(bbox, self.config.roi, frame_shape):
                continue
            matched.append(label or "unknown")
        return matched


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _parse_targets(raw: str) -> set[str]:
    return {x.strip() for x in raw.split(",") if x.strip()}


def _parse_roi(raw: str) -> Roi | None:
    if not raw.strip():
        return None
    parts = [x.strip() for x in raw.replace(";", ",").split(",") if x.strip()]
    if len(parts) != 4:
        raise ValueError("SOP_OPERATION_ROI 需为 x1,y1,x2,y2")
    x1, y1, x2, y2 = (float(x) for x in parts)
    if x2 <= x1 or y2 <= y1:
        raise ValueError("SOP_OPERATION_ROI 的 x2/y2 必须大于 x1/y1")
    return (x1, y1, x2, y2)


def _det_label(det: Any) -> str:
    if isinstance(det, dict):
        return str(det.get("class_name", det.get("label", "")))
    return str(getattr(det, "class_name", getattr(det, "label", "")))


def _det_confidence(det: Any) -> float:
    if isinstance(det, dict):
        return float(det.get("confidence", 0.0) or 0.0)
    return float(getattr(det, "confidence", 0.0) or 0.0)


def _det_bbox(det: Any) -> tuple[float, float, float, float] | None:
    if isinstance(det, dict):
        bbox = det.get("bbox", det.get("xyxy"))
    else:
        bbox = getattr(det, "bbox", getattr(det, "xyxy", None))
    if bbox is None or len(bbox) < 4:
        return None
    return (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))


def _bbox_center_in_roi(bbox: tuple[float, float, float, float], roi: Roi, frame_shape: tuple[int, ...]) -> bool:
    height, width = int(frame_shape[0]), int(frame_shape[1])
    x1, y1, x2, y2 = roi
    if max(abs(v) for v in roi) <= 1.0:
        x1, x2 = x1 * width, x2 * width
        y1, y2 = y1 * height, y2 * height
    cx = (bbox[0] + bbox[2]) / 2.0
    cy = (bbox[1] + bbox[3]) / 2.0
    return x1 <= cx <= x2 and y1 <= cy <= y2
