"""RTSP 视频流拉取器，维护环形帧缓冲区。"""

import threading
import time

import cv2
from loguru import logger

from src.capture.frame_buffer import RingFrameBuffer


class RTSPStream:
    """RTSP 拉流客户端。Jetson 平台建议 use_gstreamer=True 启用硬件解码。"""

    def __init__(
        self,
        url: str,
        buffer_size: int = 30,
        reconnect_interval: float = 5.0,
        use_gstreamer: bool = False,
    ) -> None:
        self.url = url
        self._buffer = RingFrameBuffer(buffer_size)
        self.reconnect_interval = reconnect_interval
        self.use_gstreamer = use_gstreamer
        self._cap: cv2.VideoCapture | None = None
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info("视频流启动: {}", self.url)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("视频流已停止")

    def get_frame(self):
        return self._buffer.get_latest()

    def get_frames(self, n: int = 5):
        return self._buffer.get_last_n(n)

    @staticmethod
    def _validate_gstreamer_rtsp_url(url: str) -> None:
        if not url.startswith("rtsp://"):
            raise ValueError("GStreamer 管道仅允许 rtsp:// 开头的 URL")
        if any(ord(c) < 32 for c in url):
            raise ValueError("RTSP URL 不得包含控制字符")
        # 防止未转义传入 shell/GStreamer 管道时产生注入；location= 未加引号时下列字符会破坏或篡改管道
        _unsafe = set(';|&$`!()<>\\')
        if any(c in url for c in _unsafe):
            raise ValueError("RTSP URL 包含不允许的字符（可能对 shell 或 GStreamer 管道不安全）")
        if " " in url:
            raise ValueError("RTSP URL 不得包含空格")

    @staticmethod
    def _build_gstreamer_pipeline(url: str) -> str:
        RTSPStream._validate_gstreamer_rtsp_url(url)
        return (
            f"rtspsrc location={url} latency=100 ! "
            "rtph264depay ! h264parse ! "
            "nvv4l2decoder ! nvvidconv ! "
            "video/x-raw, format=BGRx ! videoconvert ! "
            "video/x-raw, format=BGR ! "
            "appsink drop=1 max-buffers=1 sync=false"
        )

    def _capture_loop(self) -> None:
        while self._running:
            try:
                if self.use_gstreamer:
                    pipeline = self._build_gstreamer_pipeline(self.url)
                    self._cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
                elif self.url.startswith("http"):
                    self._cap = cv2.VideoCapture(self.url)
                else:
                    self._cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
                self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                if not self._cap.isOpened():
                    raise ConnectionError(f"无法连接: {self.url}")

                logger.info("视频流已连接: {}", self.url)
                fps = self._cap.get(cv2.CAP_PROP_FPS) or 25
                frame_interval = 1.0 / fps

                while self._running and self._cap.isOpened():
                    ret, frame = self._cap.read()
                    if not ret:
                        logger.warning("帧读取失败，尝试重连...")
                        break
                    self._buffer.append((frame, time.time()))
                    time.sleep(max(0, frame_interval - 0.005))

            except Exception as e:
                logger.error("视频流异常: {}", e)
            finally:
                if self._cap:
                    self._cap.release()

            if self._running:
                logger.info("{}s 后重连...", self.reconnect_interval)
                time.sleep(self.reconnect_interval)
