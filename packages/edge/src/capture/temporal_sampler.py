"""时序帧采样器：按固定时间间隔抽帧，为动作识别提供足够长的时间跨度。

RingFrameBuffer 保存的是连续帧，30 帧在 25fps 下仅覆盖约 1.2 秒，且相邻帧
差异极小。装配动作通常持续 2-5 秒，判定「正在拧螺丝」还是「刚拧完松手」
必须看到跨度足够的画面演进，因此这里按 interval 抽稀，用同样的帧数换取
数倍的时间跨度。
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any

import numpy as np

DEFAULT_WINDOW = 4
DEFAULT_INTERVAL_SECONDS = 0.4
# 时间戳累加的浮点误差会让恰好等于间隔的帧被判为"太早"而丢弃，
# 导致实际采样间隔退化为两倍。容差保证边界帧仍被收录。
_INTERVAL_TOLERANCE = 1e-6


class TemporalFrameSampler:
    """维持一个按时间抽稀的滑动窗口，供 VLM 做时序动作判定。"""

    def __init__(
        self,
        window: int = DEFAULT_WINDOW,
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    ) -> None:
        if window < 1:
            raise ValueError("window 必须 >= 1")
        if interval_seconds < 0:
            raise ValueError("interval_seconds 不能为负")
        self.window = window
        self.interval_seconds = interval_seconds
        self._frames: deque[tuple[Any, float]] = deque(maxlen=window)
        self._lock = threading.Lock()

    def offer(self, frame: np.ndarray, timestamp: float) -> bool:
        """尝试收录一帧。距上次收录不足 interval_seconds 时丢弃，返回是否被收录。"""
        with self._lock:
            if self._frames:
                elapsed = timestamp - self._frames[-1][1]
                if elapsed < self.interval_seconds - _INTERVAL_TOLERANCE:
                    return False
            self._frames.append((frame, timestamp))
            return True

    def snapshot(self) -> list[np.ndarray]:
        """按时间正序返回当前窗口内的帧。"""
        with self._lock:
            return [frame for frame, _ in self._frames]

    def span_seconds(self) -> float:
        """当前窗口首尾帧的时间跨度，帧数不足 2 时为 0。"""
        with self._lock:
            if len(self._frames) < 2:
                return 0.0
            return self._frames[-1][1] - self._frames[0][1]

    def reset(self) -> None:
        with self._lock:
            self._frames.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._frames)
