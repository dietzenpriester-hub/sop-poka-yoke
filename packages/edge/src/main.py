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
import re
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
from src.engine.vlm_gate import VLMTriggerGate
from src.inference.yolo_detector import ObjectTracker, YOLODetector
from src.storage.sqlite_store import SQLiteStore

# 项目根目录：sop-poka-yoke/packages/edge/src/main.py → parents[2] = sop-poka-yoke/packages/edge
EDGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = EDGE_ROOT.parent.parent


def _load_sop_template(template_id: int | str | None = None) -> dict:
    """从 Server 边缘端专用接口拉取 SOP 模板（共享密钥认证，无需用户登录）。

    参数 template_id 优先级最高，其次读取环境变量 SOP_TEMPLATE_ID，
    都未指定时自动选取第一个激活模板。失败时回退到本地演示模板。
    """
    import requests

    api_base = os.environ.get("SOP_API_BASE", "http://localhost:8000")
    edge_secret = os.environ.get("SOP_EDGE_SECRET", "sop-edge-internal-secret")
    headers = {"X-Edge-Secret": edge_secret}

    tid = str(template_id) if template_id else os.environ.get("SOP_TEMPLATE_ID", "")

    def _fetch(url: str) -> dict | list | None:
        try:
            resp = requests.get(url, headers=headers, timeout=10, proxies={"http": None, "https": None})
            if resp.status_code == 200:
                return resp.json()
            logger.warning("请求失败 (HTTP {}): {}", resp.status_code, url)
        except Exception as e:
            logger.warning("请求异常: {} — {}", url, e)
        return None

    if tid:
        data = _fetch(f"{api_base}/api/edge/sop-templates/{tid}")
        if data and isinstance(data, dict):
            logger.info("从 API 加载 SOP 模板: {} (ID={})", data.get("name"), tid)
            return data
        logger.warning("指定模板 ID={} 加载失败，尝试自动选取", tid)

    templates = _fetch(f"{api_base}/api/edge/sop-templates")
    if isinstance(templates, list):
        if templates:
            tpl = templates[0]
            logger.info("自动选取 SOP 模板: {} (ID={})", tpl.get("name"), tpl.get("id"))
            return tpl
        logger.warning("服务端无激活 SOP 模板")

    logger.warning("回退至本地演示模板，请确保服务端可访问")
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


def _try_init_minio():
    """尝试初始化 MinIO 上传器，未配置凭证或连接失败时返回 None（降级为本地保存）。"""
    try:
        from src.comm.data_sync import MinIOUploader
        uploader = MinIOUploader(
            endpoint=os.environ.get("SOP_MINIO_ENDPOINT", "localhost:9000"),
            bucket=os.environ.get("SOP_MINIO_BUCKET", "sop-videos"),
            secure=os.environ.get("SOP_MINIO_SECURE", "0") == "1",
        )
        logger.info("MinIO 上传器已就绪")
        return uploader
    except Exception as e:
        logger.warning("MinIO 初始化失败，录像仅本地保存、不上传: {}", e)
        return None


_CLIP_NAME_RE = re.compile(r"^(?P<sn>.+)_step(?P<step>\d+)_(?P<event>[A-Za-z_]+)_\d{8}_\d{6}\.mp4$")


def _parse_clip_name(local_path: str) -> tuple[str, int, str] | None:
    """从录像文件名解析 (work_order_sn, step_index, event_type)。

    文件名格式见 VideoRecorder._get_clip_path：{sn}_step{step}_{event}_{ts}.mp4
    """
    name = Path(local_path).name
    m = _CLIP_NAME_RE.match(name)
    if not m:
        return None
    try:
        return m.group("sn"), int(m.group("step")), m.group("event")
    except ValueError:
        return None


def _try_init_vlm():
    """尝试初始化 VLM 客户端，失败则返回 None。"""
    try:
        from src.inference.vlm_recognizer import VLMClient
        vlm = VLMClient(
            base_url=os.environ.get("SOP_OLLAMA_URL", "http://localhost:11434"),
            model=os.environ.get("SOP_VLM_MODEL", "qwen3-vl:8b-instruct"),
            num_ctx=int(os.environ.get("SOP_VLM_NUM_CTX", "2048")),
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
    """在独立线程中异步执行 VLM 推理，推理完成即可接受下一帧。"""

    def __init__(self, vlm):
        self._vlm = vlm
        self._request_q: Queue = Queue(maxsize=1)
        self._result_q: Queue = Queue(maxsize=1)
        self._running = True
        self._busy = False
        self._infer_count = 0
        self._total_infer_ms = 0.0
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while self._running:
            try:
                frames, context = self._request_q.get(timeout=1.0)
            except Empty:
                continue
            self._busy = True
            t0 = time.monotonic()
            try:
                result = self._vlm.classify_action(frames, context)
            except Exception as e:
                logger.error("VLM 推理异常: {}", e)
                result = {"action": "unknown", "confidence": 0}
            elapsed = (time.monotonic() - t0) * 1000
            self._infer_count += 1
            self._total_infer_ms += elapsed
            result["_infer_ms"] = round(elapsed)
            while not self._result_q.empty():
                try:
                    self._result_q.get_nowait()
                except Empty:
                    break
            self._result_q.put(result)
            self._busy = False

    @property
    def is_idle(self) -> bool:
        """VLM 线程空闲且无待处理请求时返回 True。"""
        return not self._busy and self._request_q.empty()

    @property
    def avg_infer_ms(self) -> float:
        return self._total_infer_ms / max(self._infer_count, 1)

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


_DEFAULT_EDGE_SECRET = "sop-edge-internal-secret"


def main() -> None:
    data_dir = REPO_ROOT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    log_dir = REPO_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    if os.environ.get("SOP_EDGE_SECRET", _DEFAULT_EDGE_SECRET) == _DEFAULT_EDGE_SECRET:
        logger.warning("⚠ SOP_EDGE_SECRET 使用默认值，生产环境请务必设置自定义密钥！")
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
    mjpeg = MJPEGServer(port=mjpeg_port, max_fps=mjpeg_fps, jpeg_quality=85, max_dim=1280)
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

    _DET_COLORS = {
        "person": (0, 255, 0),
        "default": (255, 165, 0),
    }

    def _draw_detections(frame: np.ndarray, dets: list) -> np.ndarray:
        """在帧上绘制 YOLO 检测框和标签。"""
        overlay = frame.copy()
        for d in dets:
            if isinstance(d, dict):
                bbox = d.get("bbox", d.get("xyxy", []))
                label = d.get("class_name", d.get("label", ""))
                conf = d.get("confidence", 0)
            else:
                bbox = getattr(d, "bbox", getattr(d, "xyxy", []))
                label = getattr(d, "class_name", getattr(d, "label", ""))
                conf = getattr(d, "confidence", 0)
            if len(bbox) < 4:
                continue
            x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
            if x2 <= x1 or y2 <= y1:
                continue
            color = _DET_COLORS.get(label, _DET_COLORS["default"])
            cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)
            text = f"{label} {conf:.0%}"
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(overlay, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
            cv2.putText(overlay, text, (x1 + 2, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        return overlay

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

    def send_step_event(payload: dict) -> None:
        """发布步骤记录到服务端可消费的 step/complete 主题（数据闭环）。"""
        topic = f"{mqtt_prefix}/{station_id}/step/complete"
        payload.setdefault("station_id", station_id)
        if mqtt_client:
            mqtt_client.publish(topic, payload)
        logger.info("[步骤] {}", json.dumps(payload, ensure_ascii=False)[:200])

    minio_uploader = _try_init_minio()
    local_db = SQLiteStore(str(data_dir / "edge_local.db"))

    def _sync_send(payload: dict) -> None:
        """补传队列统一发送出口：视频走 MinIO 上传 + URL 回填，其余走检测主题。"""
        if payload.get("type") == "video":
            local_path = payload.get("local_path", "")
            if not minio_uploader:
                logger.warning("MinIO 未就绪，录像保留本地待补传: {}", local_path)
                return
            if not local_path or not Path(local_path).exists():
                logger.warning("录像文件不存在，跳过上传: {}", local_path)
                return
            video_url = minio_uploader.upload_file(local_path)
            parsed = _parse_clip_name(local_path)
            if parsed and mqtt_client:
                sn, step_index, event_type = parsed
                mqtt_client.publish(
                    f"{mqtt_prefix}/{station_id}/step/video",
                    {
                        "station_id": station_id,
                        "work_order_sn": sn,
                        "step_index": step_index,
                        "event_type": event_type,
                        "video_url": video_url,
                    },
                )
            logger.info("录像已上传并回填: {} → {}", local_path, video_url)
            return
        send_detection(payload)

    sync = OfflineDataSync(
        sender=_sync_send,
        dead_letter_store=local_db,
        dead_letter_jsonl=data_dir / "sync_dead_letter.jsonl",
    )
    sync.start_worker()

    recorder = VideoRecorder(
        output_dir=str(data_dir / "clips"),
        on_clip_saved=lambda p: sync.enqueue(Priority.P3, {"type": "video", "local_path": p}),
    )

    global_detect = os.environ.get("SOP_GLOBAL_DETECT", "0") == "1"
    fsm = SOPStateMachine(
        _load_sop_template(),
        debounce_seconds=float(os.environ.get("SOP_DEBOUNCE_SEC", "1.0")),
        ng_tolerance=int(os.environ.get("SOP_NG_TOLERANCE", "5")),
        global_detect=global_detect,
        min_consecutive_pass=int(os.environ.get("SOP_MIN_PASS", "3")),
    )
    vlm_gate = VLMTriggerGate.from_env()
    logger.info(
        "VLM 门控: enabled={}, roi={}, stable_frames={}, cooldown={}s, min_conf={}, targets={}",
        vlm_gate.config.enabled,
        vlm_gate.config.roi or "全画面",
        vlm_gate.config.stable_frames,
        vlm_gate.config.cooldown_seconds,
        vlm_gate.config.min_confidence,
        sorted(vlm_gate.config.target_objects) or "任意",
    )

    # 后台轮询：IDLE 时每 5 秒查询服务端是否有待处理工单
    _workorder_queue: Queue = Queue(maxsize=1)
    _last_polled_sn: list[str] = [""]  # 用列表包装以便闭包内修改

    def _poll_workorder_worker() -> None:
        import requests as _req
        api_base = os.environ.get("SOP_API_BASE", "http://localhost:8000")
        edge_secret = os.environ.get("SOP_EDGE_SECRET", "sop-edge-internal-secret")
        headers = {"X-Edge-Secret": edge_secret}
        url = f"{api_base}/api/edge/workorders/active"
        while True:
            time.sleep(5)
            if fsm.status != SOPStatus.IDLE:
                continue
            try:
                resp = _req.get(url, params={"station_id": station_id}, headers=headers, timeout=3,
                                proxies={"http": None, "https": None})
                if resp.status_code == 200:
                    wo = resp.json().get("workorder")
                    if wo and wo.get("sn") and wo["sn"] != _last_polled_sn[0]:
                        _last_polled_sn[0] = wo["sn"]
                        tpl_id = wo.get("sop_template_id")
                        if tpl_id:
                            tpl = _load_sop_template(template_id=tpl_id)
                            fsm.load_template(tpl)
                            logger.info("轮询发现工单 sn={}，已加载模板 ID={}", wo["sn"], tpl_id)
                        try:
                            _workorder_queue.put_nowait(wo["sn"])
                        except Exception:
                            pass
            except Exception as _e:
                logger.debug("轮询工单失败: {}", _e)

    threading.Thread(target=_poll_workorder_worker, daemon=True, name="workorder-poll").start()
    logger.info("工单轮询线程已启动（间隔 5s，工位={}）", station_id)

    # 订阅 MQTT override/reset/start_workorder 指令
    def _on_mqtt_command(payload: dict):
        cmd = payload.get("command", "")
        if cmd == "start_workorder":
            sn = payload.get("work_order_sn", "")
            if not sn:
                logger.warning("start_workorder 指令缺少 work_order_sn，忽略")
                return
            if fsm.status != SOPStatus.IDLE:
                logger.warning("当前状态 {} 非 IDLE，无法启动新工单", fsm.status)
                return
            tpl_id = payload.get("sop_template_id")
            if tpl_id:
                tpl = _load_sop_template(template_id=tpl_id)
                fsm.load_template(tpl)
                logger.info("工单指定模板 ID={}，已重载: {}", tpl_id, tpl.get("name"))
            fsm.start(sn)
            vlm_gate.reset()
            logger.info("工单已启动: {}", sn)
            alerter.alert_warning()
        elif cmd == "override":
            reason = payload.get("reason", "MQTT 远程放行")
            operator = payload.get("operator_id", "remote")
            result = fsm.override(operator_badge=operator, reason=reason)
            vlm_gate.reset()
            logger.info("MQTT override: {}", result)
            alerter.alert_warning()
        elif cmd == "reset":
            fsm.reset()
            vlm_gate.reset()
            logger.info("MQTT reset: 状态机已重置")
            alerter.alert_idle()

    if mqtt_client:
        cmd_topic = f"{mqtt_prefix}/{station_id}/command"
        mqtt_client.subscribe(cmd_topic, _on_mqtt_command)
        logger.info("已订阅命令主题: {}", cmd_topic)

    stream.start()

    auto_start = os.environ.get("SOP_AUTO_START", "0") == "1"
    # 防呆语义：生产环境下 STEP_NG / TIMEOUT 必须停线，等待人工 reset / override；
    # 仅演示/测试模式（SOP_AUTO_START=1 或显式 SOP_AUTO_RECOVER=1）才自动恢复继续检测。
    auto_recover = auto_start or os.environ.get("SOP_AUTO_RECOVER", "0") == "1"
    if auto_start:
        auto_sn = os.environ.get("SOP_AUTO_START_SN", f"AUTO-{time.strftime('%Y%m%d-%H%M%S')}")
        fsm.start(auto_sn)
        vlm_gate.reset()
        logger.info("自动启动工单: {} (SOP_AUTO_START=1)", auto_sn)
    else:
        logger.info("边缘端就绪，等待工单启动指令（MQTT command: start_workorder）")

    mqtt_min_interval = float(os.environ.get("SOP_MQTT_INTERVAL", "1.0"))
    vlm_idle_max = float(os.environ.get("SOP_VLM_IDLE_MAX", "5.0"))
    last_mqtt_send_time = 0.0
    last_vlm_submit_time = 0.0

    logger.info("═══ 开始实时检测循环 ═══")
    logger.info("  VLM 模式: 推理完成即提交 (空闲超过{}s强制提交), MQTT 最小间隔: {}s", vlm_idle_max, mqtt_min_interval)
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
                send_step_event({
                    "work_order_sn": fsm.work_order_sn or "",
                    "step_index": tidx,
                    "step_name": tstep.name if tstep else "",
                    "result": "TIMEOUT",
                    "confidence": 0.0,
                    "event": "timeout",
                })
                alerter.alert_error()
                send_alert({
                    "alert_code": "STEP_TIMEOUT",
                    "severity": "WARN",
                    "message": f"步骤超时: {timeout_evt}",
                    "step_index": fsm.current_step_index,
                })
                if auto_recover:
                    fsm.status = SOPStatus.RUNNING
                    fsm._step_start_time = time.time()
                    logger.info("自动恢复: TIMEOUT → RUNNING（演示/测试模式）")
                else:
                    logger.warning("步骤超时已停线，等待人工 reset / override（防呆模式）")

            item = stream.get_frame()
            if item is None:
                time.sleep(0.01)
                continue

            frame, ts = item
            _last_dets: list = []
            result = {}

            if fsm.status == SOPStatus.IDLE:
                mjpeg.update_frame(frame)
                try:
                    polled_sn = _workorder_queue.get_nowait()
                    logger.info("轮询启动工单: {}", polled_sn)
                    fsm.start(polled_sn)
                    vlm_gate.reset()
                    alerter.alert_warning()
                except Empty:
                    pass
                recorder.feed(frame, ts)
                continue

            # 定期发送状态心跳（即使在 TIMEOUT/STEP_NG/无运动时），确保前端始终可感知
            _heartbeat_interval = 2.0
            now_hb = time.monotonic()
            if now_hb - last_mqtt_send_time >= _heartbeat_interval:
                snapshot_b64 = _encode_snapshot(frame)
                cur_step = fsm.get_current_step()
                status_msg = {
                    "type": "sop_status",
                    "station_id": station_id,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "work_order_sn": fsm.work_order_sn or "",
                    "sop_name": getattr(fsm, "template_name", ""),
                    "total_steps": len(fsm.steps),
                    "step_names": [s.name for s in fsm.steps],
                    "current_step_index": fsm.current_step_index,
                    "current_step_name": cur_step.name if cur_step else "",
                    "status": fsm.status.value if hasattr(fsm.status, "value") else str(fsm.status),
                    "event": "heartbeat",
                    "vlm_action": "",
                    "vlm_confidence": 0.0,
                    "vlm_matches": False,
                    "yolo_objects": [],
                    "snapshot": snapshot_b64,
                }
                if fsm.global_detect:
                    status_msg["completed_indices"] = sorted(fsm.completed_indices)
                    status_msg["completed_count"] = len(fsm.completed_indices)
                send_status(status_msg)
                last_mqtt_send_time = now_hb

            if fsm.status == SOPStatus.TIMEOUT and auto_recover:
                fsm.status = SOPStatus.RUNNING
                fsm._step_start_time = time.time()
                logger.info("步骤超时自动恢复: TIMEOUT → RUNNING（演示/测试模式）")

            # VLM 结果轮询（不受运动检测约束，确保推理完成后立即处理）
            vlm_action_text = ""
            vlm_confidence = 0.0
            vlm_matches = False
            if vlm_worker:
                action = vlm_worker.poll_result()
                if action is not None:
                    infer_ms = action.pop("_infer_ms", 0)
                    vlm_action_text = action.get("action", "")
                    vlm_confidence = float(action.get("confidence", 0))
                    vlm_matches = bool(action.get("matches_expected", False))
                    logger.info("VLM 动作识别: {} (conf={:.2f}, {}ms, avg {}ms)",
                                vlm_action_text, vlm_confidence, infer_ms,
                                round(vlm_worker.avg_infer_ms))
                    if fsm.global_detect:
                        result = fsm.process_global_action(action)
                    else:
                        result = fsm.process_action(action)

                    cur_step = fsm.get_current_step()
                    snapshot_b64 = _encode_snapshot(frame)
                    send_detection({
                        "station_id": station_id,
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "detect_count": detect_count,
                        "detections": _last_dets,
                        "yolo_objects": [],
                        "vlm_action": vlm_action_text,
                        "vlm_confidence": vlm_confidence,
                        "vlm_matches": vlm_matches,
                        "snapshot": snapshot_b64,
                        "sop_status": fsm.status.value if hasattr(fsm.status, "value") else str(fsm.status),
                        "sop_step_index": fsm.current_step_index,
                        "sop_step_name": cur_step.name if cur_step else "",
                        "sop_total_steps": len(fsm.steps),
                        "event": result.get("event", ""),
                    })
                    last_mqtt_send_time = time.monotonic()

            def _try_submit_vlm(f, dets):
                nonlocal last_vlm_submit_time
                if not vlm_worker or not vlm_worker.is_idle:
                    return
                if fsm.status not in (SOPStatus.RUNNING,):
                    return
                decision = vlm_gate.should_submit(dets, f.shape)
                if not decision.allowed:
                    logger.debug(
                        "VLM 门控未触发: reason={}, stable_hits={}, matched={}",
                        decision.reason,
                        decision.stable_hits,
                        decision.matched_objects,
                    )
                    return
                sop_ctx = {
                    "steps": [
                        {"name": s.name, "description": s.description,
                         "required_objects": s.required_objects,
                         "action_type": s.action_type,
                         "timeout_seconds": s.timeout_seconds,
                         "is_optional": s.is_optional,
                         "ok_criteria": s.ok_criteria,
                         "ng_criteria": s.ng_criteria,
                         "reference_frame_url": s.reference_frame_url,
                         "reference_frame_b64": s.reference_frame_b64,
                         "reference_frame_timestamp": s.reference_frame_timestamp}
                        for s in fsm.steps
                    ],
                    "current_step_index": fsm.current_step_index,
                }
                if fsm.global_detect:
                    sop_ctx["global_detect"] = True
                    sop_ctx["completed_indices"] = list(fsm.completed_indices)
                sop_ctx["vlm_gate"] = {
                    "reason": decision.reason,
                    "matched_objects": decision.matched_objects,
                }
                vlm_worker.submit([f], sop_ctx)
                last_vlm_submit_time = time.monotonic()

            if not motion.is_keyframe(frame):
                # 即使无运动，VLM 空闲超过阈值也强制提交当前帧
                if vlm_worker and vlm_worker.is_idle and (time.monotonic() - last_vlm_submit_time) >= vlm_idle_max:
                    _try_submit_vlm(frame, [])
                mjpeg.update_frame(frame)
                recorder.feed(frame, ts)
                continue

            dets = detector.detect(frame)
            tracker.update(dets)
            detect_count += 1

            det_dicts = [dataclasses.asdict(d) for d in dets] if isinstance(dets, list) else []
            mjpeg.update_frame(_draw_detections(frame, det_dicts))
            det_classes = [
                d.get("class_name", d.get("label", "")) for d in det_dicts
            ] if det_dicts else []

            _try_submit_vlm(frame, dets)

            # MQTT 消息节流：YOLO 检测结果定期发送
            now_mqtt = time.monotonic()
            if now_mqtt - last_mqtt_send_time >= mqtt_min_interval:
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
                status_msg = {
                    "type": "sop_status",
                    "station_id": station_id,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "work_order_sn": fsm.work_order_sn or "",
                    "sop_name": getattr(fsm, "template_name", ""),
                    "total_steps": len(fsm.steps),
                    "step_names": [s.name for s in fsm.steps],
                    "current_step_index": fsm.current_step_index,
                    "current_step_name": cur_step.name if cur_step else "",
                    "status": fsm.status.value if hasattr(fsm.status, "value") else str(fsm.status),
                    "event": "yolo_detect",
                    "vlm_action": vlm_action_text,
                    "vlm_confidence": vlm_confidence,
                    "vlm_matches": vlm_matches,
                    "yolo_objects": list(set(det_classes)),
                    "snapshot": snapshot_b64,
                }
                if fsm.global_detect:
                    status_msg["completed_indices"] = sorted(fsm.completed_indices)
                    status_msg["completed_count"] = len(fsm.completed_indices)
                send_status(status_msg)
                last_mqtt_send_time = now_mqtt

            if result.get("type") == "blocked":
                if fsm.status in (SOPStatus.STEP_NG, SOPStatus.TIMEOUT) and auto_recover:
                    fsm.status = SOPStatus.RUNNING
                    fsm._step_start_time = time.time()
                    logger.info("自动恢复: STEP_NG/TIMEOUT → RUNNING（演示/测试模式）")
                else:
                    # 防呆核心：NG/超时保持停线状态，红灯常亮，直至人工 reset / override
                    alerter.alert_error()
                    logger.debug("状态机已停线（待人工处理）: {}", result.get("reason", ""))
                recorder.feed(frame, ts)
                continue

            if result.get("event") == "step_ng":
                cur = fsm.get_current_step()
                ng_conf = float(result.get("confidence", 0) or 0)
                local_db.save_step_record(
                    fsm.work_order_sn or "",
                    fsm.current_step_index,
                    cur.name if cur else "",
                    "NG",
                    ng_conf,
                    "",
                    "",
                )
                send_step_event({
                    "work_order_sn": fsm.work_order_sn or "",
                    "step_index": fsm.current_step_index,
                    "step_name": cur.name if cur else "",
                    "result": "NG",
                    "confidence": ng_conf,
                    "event": "step_ng",
                })
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
                    send_step_event({
                        "work_order_sn": fsm.work_order_sn or "",
                        "step_index": sr.step_index,
                        "step_name": sr.step_name,
                        "result": sr.result,
                        "confidence": sr.confidence,
                        "event": "step_ok",
                    })
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
                    send_step_event({
                        "work_order_sn": fsm.work_order_sn or "",
                        "step_index": sr.step_index,
                        "step_name": sr.step_name,
                        "result": sr.result,
                        "confidence": sr.confidence,
                        "event": "override_ok",
                    })
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
                    send_step_event({
                        "work_order_sn": fsm.work_order_sn or "",
                        "step_index": sr.step_index,
                        "step_name": sr.step_name,
                        "result": sr.result,
                        "confidence": sr.confidence,
                        "event": "complete",
                    })
                alerter.alert_ok()
                logger.info("所有 SOP 步骤完成！")
                fsm.reset()
                vlm_gate.reset()
                if os.environ.get("SOP_AUTO_START") == "1":
                    new_sn = f"AUTO-{time.strftime('%Y%m%d-%H%M%S')}"
                    fsm.start(new_sn)
                    vlm_gate.reset()
                    logger.info("自动开始新工单: {} (SOP_AUTO_START=1)", new_sn)
                else:
                    logger.info("状态机已重置为 IDLE，等待下一个工单")

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
