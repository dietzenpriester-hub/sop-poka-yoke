"""视频关键帧提取服务 — 基于 OpenCV 场景变化检测"""

from dataclasses import dataclass, field

import cv2
import numpy as np
from loguru import logger


@dataclass
class KeyFrame:
    index: int
    timestamp_sec: float
    frame_bgr: np.ndarray
    is_scene_change: bool = False


@dataclass
class ExtractionResult:
    keyframes: list[KeyFrame] = field(default_factory=list)
    total_frames: int = 0
    fps: float = 0.0
    duration_sec: float = 0.0


class FrameExtractor:
    """从视频中提取关键帧，结合均匀采样与场景变化检测。"""

    def __init__(
        self,
        max_keyframes: int = 30,
        scene_threshold: float = 30.0,
        min_interval_sec: float = 0.5,
    ):
        self.max_keyframes = max_keyframes
        self.scene_threshold = scene_threshold
        self.min_interval_sec = min_interval_sec

    def extract(self, video_path: str) -> ExtractionResult:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"无法打开视频文件: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration_sec = total_frames / fps if fps > 0 else 0.0

        logger.info("视频信息: {}帧, {:.1f}fps, {:.1f}秒", total_frames, fps, duration_sec)

        result = ExtractionResult(
            total_frames=total_frames,
            fps=fps,
            duration_sec=duration_sec,
        )

        if total_frames == 0:
            cap.release()
            return result

        min_interval_frames = int(fps * self.min_interval_sec)
        uniform_interval = max(1, total_frames // (self.max_keyframes * 2))

        prev_gray = None
        scene_changes: list[KeyFrame] = []
        uniform_samples: list[KeyFrame] = []
        frame_idx = 0
        last_keyframe_idx = -min_interval_frames

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            timestamp = frame_idx / fps
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            if prev_gray is not None and (frame_idx - last_keyframe_idx) >= min_interval_frames:
                diff = cv2.absdiff(gray, prev_gray)
                mean_diff = float(np.mean(diff))

                if mean_diff > self.scene_threshold:
                    kf = KeyFrame(
                        index=frame_idx,
                        timestamp_sec=round(timestamp, 2),
                        frame_bgr=frame.copy(),
                        is_scene_change=True,
                    )
                    scene_changes.append(kf)
                    last_keyframe_idx = frame_idx

            if frame_idx % uniform_interval == 0:
                kf = KeyFrame(
                    index=frame_idx,
                    timestamp_sec=round(timestamp, 2),
                    frame_bgr=frame.copy(),
                    is_scene_change=False,
                )
                uniform_samples.append(kf)

            prev_gray = gray
            frame_idx += 1

        cap.release()

        result.keyframes = self._merge_and_limit(scene_changes, uniform_samples)
        logger.info(
            "关键帧提取完成: {} 场景变化 + {} 均匀采样 → {} 最终关键帧",
            len(scene_changes),
            len(uniform_samples),
            len(result.keyframes),
        )
        return result

    def _merge_and_limit(
        self,
        scene_changes: list[KeyFrame],
        uniform_samples: list[KeyFrame],
    ) -> list[KeyFrame]:
        seen_indices: set[int] = set()
        merged: list[KeyFrame] = []

        for kf in scene_changes:
            if kf.index not in seen_indices:
                seen_indices.add(kf.index)
                merged.append(kf)

        for kf in uniform_samples:
            if kf.index not in seen_indices:
                seen_indices.add(kf.index)
                merged.append(kf)

        merged.sort(key=lambda kf: kf.index)

        if len(merged) <= self.max_keyframes:
            return merged

        # 优先保留场景变化帧，再从均匀采样中补充
        sc = [kf for kf in merged if kf.is_scene_change]
        non_sc = [kf for kf in merged if not kf.is_scene_change]

        if len(sc) >= self.max_keyframes:
            step = len(sc) / self.max_keyframes
            selected = [sc[int(i * step)] for i in range(self.max_keyframes)]
        else:
            remaining = self.max_keyframes - len(sc)
            step = max(1, len(non_sc) / remaining) if remaining > 0 else 1
            supplement = [non_sc[int(i * step)] for i in range(min(remaining, len(non_sc)))]
            selected = sc + supplement

        selected.sort(key=lambda kf: kf.index)
        return selected
