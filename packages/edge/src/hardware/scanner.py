"""扫码枪（USB / Serial）"""

from __future__ import annotations

import threading

from loguru import logger

try:
    import serial
except ImportError:
    serial = None  # type: ignore


class BarcodeScanner:

    def __init__(self, port: str = "/dev/ttyUSB0", baudrate: int = 9600) -> None:
        self.port = port
        self.baudrate = baudrate
        self._serial: serial.Serial | None = None
        self._running = False
        self._callback = None
        self._thread: threading.Thread | None = None

    def start(self, on_scan: callable) -> None:
        if serial is None:
            logger.warning("pyserial 未安装，扫码枪功能不可用")
            return
        self._callback = on_scan
        self._running = True
        self._serial = serial.Serial(self.port, self.baudrate, timeout=1)
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        logger.info("扫码枪已启动: {}", self.port)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        if self._serial:
            self._serial.close()

    def _read_loop(self) -> None:
        while self._running and self._serial:
            try:
                line = self._serial.readline().decode("utf-8").strip()
                if line and self._callback:
                    logger.info("扫码: {}", line)
                    self._callback(line)
            except Exception as e:
                logger.error("扫码异常: {}", e)
