"""YOLOv11 目标检测 + 目标追踪封装"""

from dataclasses import dataclass

import numpy as np
from loguru import logger
from ultralytics import YOLO

STABLE_THRESHOLD = 8


@dataclass
class Detection:
    class_id: int
    class_name: str
    confidence: float
    bbox: tuple
    center: tuple


@dataclass
class TrackedObject:
    class_name: str
    present: bool
    present_counter: int = 0
    absent_counter: int = 0


class YOLODetector:

    def __init__(self, model_path: str = "yolo11n.pt", conf_threshold: float = 0.4, device: str = "auto") -> None:
        self.model = YOLO(model_path)
        self.conf_threshold = conf_threshold
        if device == "auto":
            try:
                import torch
                if torch.cuda.is_available():
                    self.device = "cuda:0"
                elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                    self.device = "mps"
                else:
                    self.device = "cpu"
            except ImportError:
                self.device = "cpu"
        else:
            self.device = device
        logger.info("YOLO 模型已加载: {} (device={})", model_path, self.device)

    def detect(self, frame: np.ndarray) -> list[Detection]:
        results = self.model(frame, conf=self.conf_threshold, device=self.device, verbose=False)
        detections = []
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                name = self.model.names[cls_id]
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                detections.append(Detection(
                    class_id=cls_id, class_name=name, confidence=conf,
                    bbox=(int(x1), int(y1), int(x2), int(y2)),
                    center=(int(cx), int(cy)),
                ))
        return detections

    def has_operation(self, detections: list[Detection], target_objects: list[str] | None = None) -> bool:
        if target_objects:
            return any(d.class_name in target_objects for d in detections)
        return len(detections) > 0

    def crop_roi(self, frame: np.ndarray, detection: Detection, padding: int = 50) -> np.ndarray:
        h, w = frame.shape[:2]
        x1 = max(0, detection.bbox[0] - padding)
        y1 = max(0, detection.bbox[1] - padding)
        x2 = min(w, detection.bbox[2] + padding)
        y2 = min(h, detection.bbox[3] + padding)
        return frame[y1:y2, x1:x2]


class ObjectTracker:

    def __init__(self, stable_threshold: int = STABLE_THRESHOLD) -> None:
        self.stable_threshold = stable_threshold
        self.tracked: dict[str, TrackedObject] = {}

    def update(self, detections: list[Detection]) -> list[dict]:
        current_names = {d.class_name for d in detections}
        events = []
        for name, obj in list(self.tracked.items()):
            if name in current_names:
                obj.absent_counter = 0
                obj.present_counter += 1
                if not obj.present and obj.present_counter >= self.stable_threshold:
                    obj.present = True
                    events.append({"type": "object_placed", "object": name})
            else:
                obj.present_counter = 0
                obj.absent_counter += 1
                if obj.present and obj.absent_counter >= self.stable_threshold:
                    obj.present = False
                    events.append({"type": "object_removed", "object": name})
        for name in current_names:
            if name not in self.tracked:
                self.tracked[name] = TrackedObject(class_name=name, present=False, present_counter=1)
        return events

    def reset(self) -> None:
        self.tracked.clear()
