"""边缘端入口：串联 capture / inference / engine / comm。

支持降级模式：
- 无 PLC 硬件时自动跳过 Modbus
- 内存不足时仅使用 YOLO（跳过 VLM）
- 支持 RTSP / HTTP MJPEG / 本地摄像头
"""

from __future__ import annotations

import dataclasses
import json
import os
import time
from pathlib import Path

import numpy as np
from loguru import logger

from src.capture.motion_detect import KeyframeExtractor
from src.capture.recorder import VideoRecorder
from src.capture.rtsp_client import RTSPStream
from src.comm.data_sync import MinIOUploader, OfflineDataSync, Priority
from src.comm.mqtt_client import MQTTClient
from src.engine.material_check import BOMValidator
from src.engine.state_machine import SOPStateMachine
from src.inference.yolo_detector import ObjectTracker, YOLODetector


def _load_sop_template() -> dict:
    """实际项目从 Redis/SQLite/HTTP 拉取；此处占位。"""
    return {
        "name": "演示 SOP",
        "steps": [
            {"name": "拿起螺丝刀", "description": "从工具架取螺丝刀"},
            {"name": "拧螺丝", "description": "拧入 PCB"},
        ],
    }


def _try_init_modbus():
    """尝试初始化 Modbus 控制器，失败则返回空操作替身。"""
    class _NoopAlerter:
        def connect(self): logger.info("Modbus 跳过（无硬件）")
        def disconnect(self): pass
        def alert_ok(self): logger.debug("灯: 绿")
        def alert_warning(self): logger.debug("灯: 黄 + 蜂鸣")
        def alert_error(self): logger.debug("灯: 红闪 + 蜂鸣")
        def alert_idle(self): logger.debug("灯: 关")

    try:
        from src.hardware.alarm import ModbusAlertController
        host = os.environ.get("SOP_MODBUS_HOST", "192.168.1.100")
        alerter = ModbusAlertController(host=host)
        alerter.connect()
        return alerter
    except Exception as e:
        logger.warning("Modbus 初始化失败，使用空操作模式: {}", e)
        return _NoopAlerter()


def _try_init_vlm():
    """尝试初始化 VLM 客户端，失败则返回 None。"""
    try:
        from src.inference.vlm_recognizer import VLMClient
        vlm = VLMClient(
            base_url=os.environ.get("SOP_OLLAMA_URL", "http://localhost:11434"),
            model=os.environ.get("SOP_VLM_MODEL", "qwen2.5vl:3b"),
        )
        warmup_frame = np.zeros((100, 100, 3), dtype=np.uint8)
        result = vlm.classify_action([warmup_frame], {"steps": [{"name": "warmup"}], "current_step_index": 0})
        if result.get("action") != "unknown" or result.get("confidence", 0) > 0:
            logger.info("VLM 预热成功")
        else:
            logger.info("VLM 已连接（预热返回默认结果）")
        return vlm
    except Exception as e:
        logger.warning("VLM 初始化失败，将仅使用 YOLO: {}", e)
        return None


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    log_dir = repo_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        str(log_dir / "edge_{time}.log"),
        rotation="100 MB",
        retention="30 days",
        compression="gz",
        level="INFO",
    )

    camera_url = os.environ.get("SOP_RTSP_URL", "0")
    station_id = os.environ.get("SOP_STATION_ID", "ST-01")
    mqtt_broker = os.environ.get("SOP_MQTT_HOST", "localhost")
    mqtt_port = int(os.environ.get("SOP_MQTT_PORT", "1883"))
    mqtt_prefix = os.environ.get("SOP_MQTT_PREFIX", "sop")

    logger.info("═══ SOP 边缘计算启动 ═══")
    logger.info("  摄像头: {}", camera_url)
    logger.info("  工位: {}", station_id)
    logger.info("  MQTT: {}:{}", mqtt_broker, mqtt_port)

    if camera_url.isdigit():
        camera_url_parsed: str | int = int(camera_url)
    else:
        camera_url_parsed = camera_url

    stream = RTSPStream(
        str(camera_url_parsed) if isinstance(camera_url_parsed, int) else camera_url_parsed,
        use_gstreamer=os.environ.get("SOP_USE_GSTREAMER", "0") == "1",
    )
    motion = KeyframeExtractor()
    recorder = VideoRecorder(output_dir=str(repo_root / "data/clips"))

    logger.info("加载 YOLO 模型...")
    detector = YOLODetector(model_path=os.environ.get("SOP_YOLO_MODEL", "yolo11n.pt"))
    tracker = ObjectTracker()

    warmup_frame = np.zeros((640, 640, 3), dtype=np.uint8)
    detector.detect(warmup_frame)
    logger.info("YOLO 预热完成")

    vlm = _try_init_vlm()
    alerter = _try_init_modbus()

    mqtt_client = MQTTClient(broker=mqtt_broker, port=mqtt_port, client_id=f"edge-{station_id}")
    try:
        mqtt_client.connect()
    except Exception as e:
        logger.error("MQTT 连接失败: {}（检测结果将只记录日志）", e)
        mqtt_client = None

    def send_detection(payload: dict) -> None:
        topic = f"{mqtt_prefix}/{station_id}/detection"
        if mqtt_client:
            mqtt_client.publish(topic, payload)
        logger.info("[检测] {}", json.dumps(payload, ensure_ascii=False)[:200])

    def send_alert(payload: dict) -> None:
        topic = f"{mqtt_prefix}/{station_id}/alert/raise"
        if mqtt_client:
            mqtt_client.publish(topic, payload)
        logger.warning("[报警] {}", json.dumps(payload, ensure_ascii=False)[:200])

    sync = OfflineDataSync(sender=lambda p: send_detection(p))
    sync.start_worker()

    fsm = SOPStateMachine(
        _load_sop_template(),
        debounce_seconds=float(os.environ.get("SOP_DEBOUNCE_SEC", "0.5")),
    )

    if vlm:
        bom = BOMValidator(vlm, detector)
    else:
        bom = None

    stream.start()
    alerter.connect()
    fsm.start("DEMO-SN-001")

    logger.info("═══ 开始实时检测循环 ═══")
    detect_count = 0

    try:
        while True:
            timeout_evt = fsm.check_timeout()
            if timeout_evt:
                logger.warning("SOP 步骤超时: {}", timeout_evt)
                alerter.alert_error()
                send_alert({
                    "alert_code": "STEP_TIMEOUT",
                    "severity": "WARN",
                    "message": f"步骤超时: {timeout_evt}",
                    "step_index": fsm.current_step_index,
                })

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
            detect_count += 1

            det_dicts = [dataclasses.asdict(d) for d in dets] if isinstance(dets, list) else []
            det_classes = [
                d.get("class_name", d.get("label", "")) for d in det_dicts
            ] if det_dicts else []
            send_detection({
                "station_id": station_id,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "detect_count": detect_count,
                "detections": det_dicts,
                "object_count": len(det_dicts),
                "unique_classes": list(set(det_classes)),
            })

            if vlm:
                action = vlm.classify_action(
                    [frame],
                    {
                        "steps": [
                            {"name": s.name, "description": s.description,
                             "required_objects": s.required_objects,
                             "action_type": s.action_type,
                             "timeout_seconds": s.timeout_seconds,
                             "is_optional": s.is_optional}
                            for s in fsm.steps
                        ],
                        "current_step_index": fsm.current_step_index,
                    },
                )
                result = fsm.process_action(action)
            else:
                result = {"event": "yolo_only"}

            if result.get("event") == "step_ng":
                alerter.alert_error()
                path = recorder.trigger_save("STEP_NG", fsm.work_order_sn or "", fsm.current_step_index)
                send_alert({
                    "alert_code": "STEP_NG",
                    "severity": "ERROR",
                    "message": f"步骤 NG: {result}",
                    "step_index": fsm.current_step_index,
                })
                sync.enqueue(Priority.P3, {"type": "video", "local_path": path})
            elif result.get("event") == "step_ok":
                alerter.alert_ok()
            elif result.get("event") == "complete":
                alerter.alert_ok()
                logger.info("所有 SOP 步骤完成！")
                break

            recorder.feed(frame, ts)

    except KeyboardInterrupt:
        logger.info("用户中断，正在停止...")
    finally:
        stream.stop()
        alerter.disconnect()
        sync.stop_worker()
        if mqtt_client:
            mqtt_client.disconnect()
        if vlm:
            vlm.close()
        logger.info("═══ 边缘计算已停止（共 {} 次检测）═══", detect_count)


if __name__ == "__main__":
    main()
