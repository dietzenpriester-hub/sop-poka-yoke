"""边缘端入口：串联 capture / inference / engine / comm。

支持降级模式：
- 无 PLC 硬件时自动跳过 Modbus
- 内存不足时仅使用 YOLO（跳过 VLM）
- 支持 RTSP / HTTP MJPEG / 本地摄像头
"""

from __future__ import annotations

import base64
import dataclasses
import json
import os
import threading
import time
from pathlib import Path
from queue import Empty, Queue

import cv2
import numpy as np
from loguru import logger

from src.capture.motion_detect import KeyframeExtractor
from src.capture.recorder import VideoRecorder
from src.capture.rtsp_client import RTSPStream
from src.comm.data_sync import OfflineDataSync, Priority
from src.comm.mqtt_client import MQTTClient
from src.engine.state_machine import SOPStateMachine, SOPStatus
from src.inference.yolo_detector import ObjectTracker, YOLODetector
from src.storage.sqlite_store import SQLiteStore

# 项目根目录：sop-poka-yoke/packages/edge/src/main.py → parents[2] = sop-poka-yoke/packages/edge
EDGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = EDGE_ROOT.parent.parent


def _load_sop_template() -> dict:
    """从 Server API 拉取 SOP 模板，失败则使用本地演示模板。"""
    api_base = os.environ.get("SOP_API_BASE", "http://localhost:8000")
    template_id = os.environ.get("SOP_TEMPLATE_ID", "")

    if template_id:
        import requests
        try:
            url = f"{api_base}/api/sop/{template_id}"
            headers = {}
            token = os.environ.get("SOP_API_TOKEN", "")
            if token:
                headers["Authorization"] = f"Bearer {token}"
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                logger.info("从 API 加载 SOP 模板: {} (ID={})", data.get("name"), template_id)
                return data
            else:
                logger.warning("API 加载 SOP 模板失败 (HTTP {}), 使用演示模板", resp.status_code)
        except Exception as e:
            logger.warning("API 连接失败: {}, 使用演示模板", e)

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
            model=os.environ.get("SOP_VLM_MODEL", "qwen2.5-vl:7b"),
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


class _VLMWorker:
    """在独立线程中异步执行 VLM 推理，避免阻塞主循环。"""

    def __init__(self, vlm):
        self._vlm = vlm
        self._request_q: Queue = Queue(maxsize=1)
        self._result_q: Queue = Queue(maxsize=1)
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while self._running:
            try:
                frames, context = self._request_q.get(timeout=1.0)
            except Empty:
                continue
            try:
                result = self._vlm.classify_action(frames, context)
            except Exception as e:
                logger.error("VLM 推理异常: {}", e)
                result = {"action": "unknown", "confidence": 0}
            while not self._result_q.empty():
                try:
                    self._result_q.get_nowait()
                except Empty:
                    break
            self._result_q.put(result)

    def submit(self, frames, context):
        """提交推理请求（丢弃旧请求，只保留最新一帧）。"""
        while not self._request_q.empty():
            try:
                self._request_q.get_nowait()
            except Empty:
                break
        self._request_q.put((frames, context))

    def poll_result(self):
        """非阻塞获取最新推理结果，无结果返回 None。"""
        try:
            return self._result_q.get_nowait()
        except Empty:
            return None

    def stop(self):
        self._running = False
        self._thread.join(timeout=3)


def main() -> None:
    data_dir = REPO_ROOT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    log_dir = REPO_ROOT / "logs"
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
    mqtt_broker = os.environ.get("SOP_MQTT_BROKER_HOST", os.environ.get("SOP_MQTT_HOST", "localhost"))
    mqtt_port = int(os.environ.get("SOP_MQTT_BROKER_PORT", os.environ.get("SOP_MQTT_PORT", "1883")))
    mqtt_prefix = os.environ.get("SOP_MQTT_TOPIC_PREFIX", os.environ.get("SOP_MQTT_PREFIX", "sop"))

    logger.info("═══ SOP 边缘计算启动 ═══")
    logger.info("  摄像头: {}", camera_url)
    logger.info("  工位: {}", station_id)
    logger.info("  MQTT: {}:{}", mqtt_broker, mqtt_port)

    stream = RTSPStream(
        camera_url,
        use_gstreamer=os.environ.get("SOP_USE_GSTREAMER", "0") == "1",
    )
    motion = KeyframeExtractor()

    logger.info("加载 YOLO 模型...")
    detector = YOLODetector(model_path=os.environ.get("SOP_YOLO_MODEL", "yolo11n.pt"))
    tracker = ObjectTracker()

    warmup_frame = np.zeros((640, 640, 3), dtype=np.uint8)
    detector.detect(warmup_frame)
    logger.info("YOLO 预热完成")

    vlm = _try_init_vlm()
    vlm_worker = _VLMWorker(vlm) if vlm else None
    alerter = _try_init_modbus()

    from src.comm.mjpeg_server import MJPEGServer
    mjpeg_port = int(os.environ.get("SOP_MJPEG_PORT", "8766"))
    mjpeg_fps = int(os.environ.get("SOP_MJPEG_FPS", "30"))
    mjpeg = MJPEGServer(port=mjpeg_port, max_fps=mjpeg_fps, jpeg_quality=92, max_dim=1920)
    mjpeg.start()

    import uuid
    mqtt_uid = uuid.uuid4().hex[:8]
    mqtt_client = MQTTClient(broker=mqtt_broker, port=mqtt_port, client_id=f"edge-{station_id}-{mqtt_uid}")
    try:
        mqtt_client.connect()
    except Exception as e:
        logger.error("MQTT 连接失败: {}（检测结果将只记录日志）", e)
        mqtt_client = None

    _SNAPSHOT_MAX_DIM = 320
    _SNAPSHOT_QUALITY = 50

    def _encode_snapshot(frame: np.ndarray) -> str:
        """将帧压缩为小尺寸 base64 JPEG，用于前端实时预览。"""
        h, w = frame.shape[:2]
        if max(h, w) > _SNAPSHOT_MAX_DIM:
            scale = _SNAPSHOT_MAX_DIM / max(h, w)
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, _SNAPSHOT_QUALITY])
        return base64.b64encode(buf).decode("ascii") if ok else ""

    def send_detection(payload: dict) -> None:
        topic = f"{mqtt_prefix}/{station_id}/detection"
        if mqtt_client:
            mqtt_client.publish(topic, payload)
        log_payload = {k: v for k, v in payload.items() if k != "snapshot"}
        logger.info("[检测] {}", json.dumps(log_payload, ensure_ascii=False)[:200])

    def send_status(payload: dict) -> None:
        topic = f"{mqtt_prefix}/{station_id}/status"
        if mqtt_client:
            mqtt_client.publish(topic, payload)
        log_payload = {k: v for k, v in payload.items() if k != "snapshot"}
        logger.info("[状态] {}", json.dumps(log_payload, ensure_ascii=False)[:200])

    def send_alert(payload: dict) -> None:
        topic = f"{mqtt_prefix}/{station_id}/alert/raise"
        if mqtt_client:
            mqtt_client.publish(topic, payload)
        logger.warning("[报警] {}", json.dumps(payload, ensure_ascii=False)[:200])

    local_db = SQLiteStore(str(data_dir / "edge_local.db"))
    sync = OfflineDataSync(
        sender=lambda p: send_detection(p),
        dead_letter_store=local_db,
        dead_letter_jsonl=data_dir / "sync_dead_letter.jsonl",
    )
    sync.start_worker()

    recorder = VideoRecorder(
        output_dir=str(data_dir / "clips"),
        on_clip_saved=lambda p: sync.enqueue(Priority.P3, {"type": "video", "local_path": p}),
    )

    fsm = SOPStateMachine(
        _load_sop_template(),
        debounce_seconds=float(os.environ.get("SOP_DEBOUNCE_SEC", "0.5")),
    )

    # 订阅 MQTT override/reset 指令以恢复超时状态
    def _on_mqtt_command(topic: str, payload: dict):
        cmd = payload.get("command", "")
        if cmd == "override":
            reason = payload.get("reason", "MQTT 远程放行")
            operator = payload.get("operator_id", "remote")
            result = fsm.override(reason=reason, operator_id=operator)
            logger.info("MQTT override: {}", result)
            alerter.alert_warning()
        elif cmd == "reset":
            fsm.reset()
            logger.info("MQTT reset: 状态机已重置")
            alerter.alert_idle()

    if mqtt_client:
        cmd_topic = f"{mqtt_prefix}/{station_id}/command"
        mqtt_client.subscribe(cmd_topic, _on_mqtt_command)
        logger.info("已订阅命令主题: {}", cmd_topic)

    stream.start()
    fsm.start("DEMO-SN-001")

    vlm_min_interval = float(os.environ.get("SOP_VLM_INTERVAL", "3.0"))
    mqtt_min_interval = float(os.environ.get("SOP_MQTT_INTERVAL", "1.0"))
    last_vlm_submit_time = 0.0
    last_mqtt_send_time = 0.0

    logger.info("═══ 开始实时检测循环 ═══")
    logger.info("  VLM 最小间隔: {}s, MQTT 最小间隔: {}s", vlm_min_interval, mqtt_min_interval)
    detect_count = 0

    try:
        while True:
            timeout_evt = fsm.check_timeout()
            if timeout_evt:
                logger.warning("SOP 步骤超时: {}", timeout_evt)
                tidx = int(timeout_evt.get("step_index", fsm.current_step_index))
                tstep = fsm.steps[tidx] if tidx < len(fsm.steps) else None
                local_db.save_step_record(
                    fsm.work_order_sn or "",
                    tidx,
                    tstep.name if tstep else "",
                    "TIMEOUT",
                    0.0,
                    "",
                    "",
                )
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
            mjpeg.update_frame(frame)
            if fsm.status == SOPStatus.TIMEOUT:
                recorder.feed(frame, ts)
                continue

            if not motion.is_keyframe(frame):
                recorder.feed(frame, ts)
                continue

            dets = detector.detect(frame)
            tracker.update(dets)
            detect_count += 1

            det_dicts = [dataclasses.asdict(d) for d in dets] if isinstance(dets, list) else []
            det_classes = [
                d.get("class_name", d.get("label", "")) for d in det_dicts
            ] if det_dicts else []

            # VLM 异步推理：节流控制，避免每帧都提交
            vlm_action_text = ""
            vlm_confidence = 0.0
            vlm_matches = False
            if vlm_worker:
                now_vlm = time.monotonic()
                if now_vlm - last_vlm_submit_time >= vlm_min_interval:
                    vlm_worker.submit(
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
                    last_vlm_submit_time = now_vlm
                action = vlm_worker.poll_result()
                if action is not None:
                    vlm_action_text = action.get("action", "")
                    vlm_confidence = float(action.get("confidence", 0))
                    vlm_matches = bool(action.get("matches_expected", False))
                    logger.info("VLM 动作识别: {} (conf={:.2f})",
                                vlm_action_text, vlm_confidence)
                    result = fsm.process_action(action)
                else:
                    result = {"event": "vlm_pending"}
            else:
                result = {"event": "yolo_only"}

            # MQTT 消息节流：限制发送频率避免压垮 broker
            now_mqtt = time.monotonic()
            is_important = result.get("event") in ("step_ok", "step_ng", "complete", "override_ok")
            if is_important or (now_mqtt - last_mqtt_send_time >= mqtt_min_interval):
                snapshot_b64 = _encode_snapshot(frame)
                send_detection({
                    "station_id": station_id,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "detect_count": detect_count,
                    "detections": det_dicts,
                    "object_count": len(det_dicts),
                    "unique_classes": list(set(det_classes)),
                    "snapshot": snapshot_b64,
                })
                cur_step = fsm.get_current_step()
                send_status({
                    "type": "sop_status",
                    "station_id": station_id,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "work_order_sn": fsm.work_order_sn or "",
                    "sop_name": getattr(fsm, "template_name", ""),
                    "total_steps": len(fsm.steps),
                    "current_step_index": fsm.current_step_index,
                    "current_step_name": cur_step.name if cur_step else "",
                    "status": fsm.status.value if hasattr(fsm.status, "value") else str(fsm.status),
                    "event": result.get("event", ""),
                    "vlm_action": vlm_action_text,
                    "vlm_confidence": vlm_confidence,
                    "vlm_matches": vlm_matches,
                    "yolo_objects": list(set(det_classes)),
                    "snapshot": snapshot_b64,
                })
                last_mqtt_send_time = now_mqtt

            if result.get("type") == "blocked":
                logger.debug("状态机已阻塞: {}", result.get("reason", ""))
                recorder.feed(frame, ts)
                continue

            if result.get("event") == "step_ng":
                cur = fsm.get_current_step()
                local_db.save_step_record(
                    fsm.work_order_sn or "",
                    fsm.current_step_index,
                    cur.name if cur else "",
                    "NG",
                    float(result.get("confidence", 0) or 0),
                    "",
                    "",
                )
                alerter.alert_error()
                recorder.trigger_save("STEP_NG", fsm.work_order_sn or "", fsm.current_step_index)
                send_alert({
                    "alert_code": "STEP_NG",
                    "severity": "ERROR",
                    "message": f"步骤 NG: {result}",
                    "step_index": fsm.current_step_index,
                })
            elif result.get("event") == "step_ok":
                if fsm.results:
                    sr = fsm.results[-1]
                    local_db.save_step_record(
                        fsm.work_order_sn or "",
                        sr.step_index,
                        sr.step_name,
                        sr.result,
                        sr.confidence,
                        "",
                        "",
                    )
                alerter.alert_ok()
            elif result.get("event") == "override_ok":
                if fsm.results:
                    sr = fsm.results[-1]
                    local_db.save_step_record(
                        fsm.work_order_sn or "",
                        sr.step_index,
                        sr.step_name,
                        sr.result,
                        sr.confidence,
                        "",
                        "",
                    )
            elif result.get("event") == "complete":
                if fsm.results:
                    sr = fsm.results[-1]
                    local_db.save_step_record(
                        fsm.work_order_sn or "",
                        sr.step_index,
                        sr.step_name,
                        sr.result,
                        sr.confidence,
                        "",
                        "",
                    )
                alerter.alert_ok()
                logger.info("所有 SOP 步骤完成！")
                break

            recorder.feed(frame, ts)

    except KeyboardInterrupt:
        logger.info("用户中断，正在停止...")
    finally:
        stream.stop()
        mjpeg.stop()
        alerter.disconnect()
        sync.stop_worker()
        if vlm_worker:
            vlm_worker.stop()
        if mqtt_client:
            mqtt_client.disconnect()
        if vlm:
            vlm.close()
        local_db.close()
        logger.info("═══ 边缘计算已停止（共 {} 次检测）═══", detect_count)


if __name__ == "__main__":
    main()
