"""线程安全环形帧缓冲（Ring Buffer），供 RTSP、多路复用与单元测试复用。"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any, Optional, Tuple

FrameItem = Tuple[Any, float]


class RingFrameBuffer:
    """环形帧缓冲区：存储 (frame, timestamp) 元组，容量满时丢弃最旧帧。"""

    def __init__(self, max_len: int = 30) -> None:
        self._buffer: deque[FrameItem] = deque(maxlen=max_len)
        self._lock = threading.Lock()

    def append(self, item: FrameItem) -> None:
        with self._lock:
            self._buffer.append(item)

    def get_latest(self) -> Optional[FrameItem]:
        with self._lock:
            return self._buffer[-1] if self._buffer else None

    def get_last_n(self, n: int = 5) -> list[FrameItem]:
        with self._lock:
            return list(self._buffer)[-n:]

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._buffer)
