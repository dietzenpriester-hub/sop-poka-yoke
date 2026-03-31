"""轻量级 MJPEG HTTP 流服务器 —— 供前端直连获取实时视频。"""

from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

import cv2
import numpy as np
from loguru import logger


class _ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

_BOUNDARY = b"--frame"


class MJPEGServer:
    """在独立线程中运行 MJPEG HTTP 流服务器。

    调用 update_frame() 更新最新帧，多个客户端可同时通过
    GET /stream 获取 MJPEG 流。
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8766,
        max_fps: int = 10,
        jpeg_quality: int = 70,
        max_dim: int = 640,
    ) -> None:
        self.host = host
        self.port = port
        self.max_fps = max_fps
        self.jpeg_quality = jpeg_quality
        self.max_dim = max_dim

        self._frame: np.ndarray | None = None
        self._jpeg_buf: bytes = b""
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._server: HTTPServer | None = None

    def update_frame(self, frame: np.ndarray) -> None:
        h, w = frame.shape[:2]
        if max(h, w) > self.max_dim:
            scale = self.max_dim / max(h, w)
            frame = cv2.resize(
                frame, (int(w * scale), int(h * scale)),
                interpolation=cv2.INTER_AREA,
            )
        ok, buf = cv2.imencode(
            ".jpg", frame,
            [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality],
        )
        if ok:
            with self._lock:
                self._jpeg_buf = buf.tobytes()

    def get_jpeg(self) -> bytes:
        with self._lock:
            return self._jpeg_buf

    def start(self) -> None:
        server_ref = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/stream":
                    self._stream()
                elif self.path == "/snapshot":
                    self._snapshot()
                else:
                    self.send_error(404)

            def _snapshot(self):
                data = server_ref.get_jpeg()
                if not data:
                    self.send_error(503, "No frame available")
                    return
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)

            def _stream(self):
                self.send_response(200)
                self.send_header(
                    "Content-Type",
                    "multipart/x-mixed-replace; boundary=frame",
                )
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                interval = 1.0 / server_ref.max_fps
                try:
                    while True:
                        data = server_ref.get_jpeg()
                        if data:
                            self.wfile.write(_BOUNDARY + b"\r\n")
                            self.wfile.write(b"Content-Type: image/jpeg\r\n")
                            self.wfile.write(
                                f"Content-Length: {len(data)}\r\n\r\n".encode()
                            )
                            self.wfile.write(data)
                            self.wfile.write(b"\r\n")
                            self.wfile.flush()
                        time.sleep(interval)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, format, *args):
                pass

        self._server = _ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True,
        )
        self._thread.start()
        logger.info("MJPEG 流服务启动: http://{}:{}/stream", self.host, self.port)

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server = None
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
