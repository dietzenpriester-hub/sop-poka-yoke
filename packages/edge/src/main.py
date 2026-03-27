"""边缘端入口：串联 capture / inference / engine / hardware / comm。"""

from __future__ import annotations

import os
import time
from pathlib import Path

import numpy as np
from loguru import logger

from src.capture.motion_detect import KeyframeExtractor
from src.capture.recorder import VideoRecorder
from src.capture.rtsp_client import RTSPStream
from src.comm.data_sync import MinIOUploader, OfflineDataSync, Priority
from src.engine.material_check import BOMValidator
from src.engine.state_machine import SOPStateMachine
from src.hardware.alarm import LightColor, ModbusAlertController
from src.inference.vlm_recognizer import VLMClient
from src.inference.yolo_detector import ObjectTracker, YOLODetector

logger.add("logs/edge_{time}.log", rotation="100 MB", retention="30 days", compression="gz", level="INFO")


def _load_sop_template() -> dict:
    """实际项目从 Redis/SQLite/HTTP 拉取；此处占位。"""
    return {
        "name": "演示 SOP",
        "steps": [
            {"name": "拿起螺丝刀", "description": "从工具架取螺丝刀"},
            {"name": "拧螺丝", "description": "拧入 PCB"},
        ],
    }


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    rtsp_url = os.environ.get("SOP_RTSP_URL", "rtsp://192.168.1.64/stream1")
    station_id = os.environ.get("SOP_STATION_ID", "ST-01")

    stream = RTSPStream(rtsp_url, use_gstreamer=os.environ.get("SOP_USE_GSTREAMER", "0") == "1")
    motion = KeyframeExtractor()
    recorder = VideoRecorder(output_dir=str(repo_root / "data/clips"))
    detector = YOLODetector(model_path=os.environ.get("SOP_YOLO_MODEL", "yolo11n.pt"))
    tracker = ObjectTracker()
    vlm = VLMClient(
        base_url=os.environ.get("SOP_OLLAMA_URL", "http://localhost:11434"),
        model=os.environ.get("SOP_VLM_MODEL", "qwen2-vl:2b"),
    )
    fsm = SOPStateMachine(
        _load_sop_template(),
        debounce_seconds=float(os.environ.get("SOP_DEBOUNCE_SEC", "0.5")),
    )
    alerter = ModbusAlertController()

    warmup_frame = np.zeros((640, 640, 3), dtype=np.uint8)
    logger.info("开始模型预热 (warmup)…")
    detector.detect(warmup_frame)
    vlm.classify_action([warmup_frame], {"steps": [{"name": "warmup"}], "current_step_index": 0})
    logger.info("模型预热完成")

    uploader = MinIOUploader(
        endpoint=os.environ.get("SOP_MINIO_ENDPOINT", "localhost:9000"),
        access_key=os.environ.get("SOP_MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=os.environ.get("SOP_MINIO_SECRET_KEY", "changeme"),
    )

    def _send_mqtt_placeholder(payload: dict) -> None:
        logger.info("[sync] station={} payload={}", station_id, payload)

    sync = OfflineDataSync(sender=_send_mqtt_placeholder)
    sync.start_worker()
    bom = BOMValidator(vlm, detector)
    stream.start()
    alerter.connect()
    fsm.start("DEMO-SN-001")

    try:
        while True:
            item = stream.get_frame()
            if item is None:
                time.sleep(0.01)
                continue
            frame, ts = item
            if not motion.is_keyframe(frame):
                recorder.feed(frame, ts)
                continue
            dets = detector.detect(frame)
            events = tracker.update(dets)
            action = vlm.classify_action(
                [frame],
                {
                    "steps": [
                        {"name": s.name, "description": s.description, "required_objects": s.required_objects,
                         "action_type": s.action_type, "timeout_seconds": s.timeout_seconds, "is_optional": s.is_optional}
                        for s in fsm.steps
                    ],
                    "current_step_index": fsm.current_step_index,
                },
            )
            result = fsm.process_action(action)
            if result.get("event") == "step_ng":
                alerter.alert_error()
                path = recorder.trigger_save("STEP_NG", fsm.work_order_sn or "", fsm.current_step_index)
                sync.enqueue(Priority.P1, {"type": "alert_meta", "station": station_id})
                sync.enqueue(Priority.P3, {"type": "video", "local_path": path})
            elif result.get("event") == "step_ok":
                alerter.alert_ok()
            elif result.get("event") == "complete":
                alerter.alert_ok()
                break
            recorder.feed(frame, ts)
    finally:
        stream.stop()
        alerter.disconnect()
        sync.stop_worker()


if __name__ == "__main__":
    main()
