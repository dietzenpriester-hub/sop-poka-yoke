"""YOLO 物体检测服务 — 基于 Ultralytics YOLOv11"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from loguru import logger


@dataclass
class Detection:
    class_name: str
    confidence: float
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2


@dataclass
class FrameDetections:
    frame_index: int
    detections: list[Detection] = field(default_factory=list)

    @property
    def object_names(self) -> list[str]:
        return list({d.class_name for d in self.detections})


class YOLOService:
    """YOLO 物体检测封装，支持 Apple Silicon MPS 加速。"""

    def __init__(self, model_name: str = "yolo11n.pt", device: str | None = None, conf: float = 0.35):
        self._model_name = model_name
        self._conf = conf
        self._model = None
        self._device = device

    def _resolve_device(self) -> str:
        if self._device:
            return self._device
        try:
            import torch
            if torch.backends.mps.is_available():
                return "mps"
        except Exception:
            pass
        return "cpu"

    def _ensure_model(self):
        if self._model is not None:
            return
        from ultralytics import YOLO
        device = self._resolve_device()
        logger.info("加载 YOLO 模型: {} (device={})", self._model_name, device)
        self._model = YOLO(self._model_name)
        self._model.to(device)
        logger.info("YOLO 模型加载完成")

    def detect_frames(self, frames: list[np.ndarray]) -> list[FrameDetections]:
        """对一批帧运行 YOLO 检测。"""
        self._ensure_model()
        results_list: list[FrameDetections] = []

        logger.info("开始 YOLO 检测: {} 帧", len(frames))
        results = self._model.predict(frames, conf=self._conf, verbose=False)

        for idx, result in enumerate(results):
            fd = FrameDetections(frame_index=idx)
            if result.boxes is not None:
                boxes = result.boxes
                for i in range(len(boxes)):
                    cls_id = int(boxes.cls[i].item())
                    cls_name = result.names.get(cls_id, f"class_{cls_id}")
                    conf_val = float(boxes.conf[i].item())
                    x1, y1, x2, y2 = boxes.xyxy[i].tolist()
                    fd.detections.append(Detection(
                        class_name=cls_name,
                        confidence=round(conf_val, 3),
                        bbox=(int(x1), int(y1), int(x2), int(y2)),
                    ))
            results_list.append(fd)

        total_dets = sum(len(fd.detections) for fd in results_list)
        logger.info("YOLO 检测完成: {} 帧共检测到 {} 个物体", len(frames), total_dets)
        return results_list
