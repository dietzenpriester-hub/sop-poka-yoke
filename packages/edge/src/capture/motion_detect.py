"""基于帧差法 + MOG2 背景减除的关键帧提取器"""

import cv2
import numpy as np


class KeyframeExtractor:

    def __init__(self, diff_threshold: float = 30.0, min_area_ratio: float = 0.01) -> None:
        self.diff_threshold = diff_threshold
        self.min_area_ratio = min_area_ratio
        self.bg_subtractor = self._make_bg_subtractor()
        self._prev_gray: np.ndarray | None = None

    @staticmethod
    def _make_bg_subtractor():
        return cv2.createBackgroundSubtractorMOG2(
            history=200, varThreshold=50, detectShadows=False
        )

    def is_keyframe(self, frame: np.ndarray) -> bool:
        if frame.ndim == 2 or (frame.ndim == 3 and frame.shape[2] == 1):
            gray = frame if frame.ndim == 2 else frame[:, :, 0]
        else:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (11, 11), 0)

        if self._prev_gray is not None:
            diff = cv2.absdiff(self._prev_gray, gray)
            _, thresh = cv2.threshold(diff, self.diff_threshold, 255, cv2.THRESH_BINARY)
            motion_ratio = np.count_nonzero(thresh) / thresh.size
            has_motion = motion_ratio > self.min_area_ratio
        else:
            has_motion = True

        self._prev_gray = gray

        fg_mask = self.bg_subtractor.apply(frame)
        fg_ratio = np.count_nonzero(fg_mask) / fg_mask.size
        has_fg_motion = fg_ratio > self.min_area_ratio

        return has_motion or has_fg_motion

    def reset(self) -> None:
        self._prev_gray = None
        self.bg_subtractor = self._make_bg_subtractor()
