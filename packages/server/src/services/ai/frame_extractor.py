"""视频关键帧提取与时序动作分割 — 基于 OpenCV 运动分析"""

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
    segment_id: int = -1


@dataclass
class ActionSegment:
    """一个时序动作片段，包含起止时间和代表帧。"""
    segment_id: int
    start_sec: float
    end_sec: float
    keyframes: list[KeyFrame] = field(default_factory=list)
    avg_motion: float = 0.0
    label: str = ""

    @property
    def duration_sec(self) -> float:
        return self.end_sec - self.start_sec

    @property
    def representative_frame(self) -> KeyFrame | None:
        if not self.keyframes:
            return None
        mid = len(self.keyframes) // 2
        return self.keyframes[mid]


@dataclass
class ExtractionResult:
    keyframes: list[KeyFrame] = field(default_factory=list)
    segments: list[ActionSegment] = field(default_factory=list)
    total_frames: int = 0
    fps: float = 0.0
    duration_sec: float = 0.0
    sampled_frames_count: int = 0
    motion_profile: list[float] = field(default_factory=list)
    segmentation_mode: str = "motion"


class FrameExtractor:
    """从视频中提取关键帧，结合运动分析与时序动作分割。

    与 ActionInsight 对标的核心改进：
    - 全视频运动强度分析（以 analysis_fps 采样）
    - 基于运动谷值自动分割动作段（ActionSegment）
    - 每段内提取代表帧，保留时间上下文
    - 支持 20 分钟以上长视频
    """

    def __init__(
        self,
        max_keyframes: int = 30,
        scene_threshold: float = 30.0,
        min_interval_sec: float = 0.5,
        analysis_fps: float = 3.0,
        motion_smooth_window: int = 5,
        min_segment_sec: float = 1.5,
        pause_threshold_ratio: float = 0.3,
        frames_per_segment: int = 4,
        coarse_fallback_min_duration_sec: float = 4.0,
    ):
        self.max_keyframes = max_keyframes
        self.scene_threshold = scene_threshold
        self.min_interval_sec = min_interval_sec
        self.analysis_fps = analysis_fps
        self.motion_smooth_window = motion_smooth_window
        self.min_segment_sec = min_segment_sec
        self.pause_threshold_ratio = pause_threshold_ratio
        self.frames_per_segment = frames_per_segment
        self.coarse_fallback_min_duration_sec = coarse_fallback_min_duration_sec

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

        sample_interval = max(1, int(fps / self.analysis_fps))

        motion_values: list[float] = []
        sampled_frames: list[tuple[int, float, np.ndarray]] = []
        prev_gray = None
        frame_idx = 0

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if frame_idx % sample_interval == 0:
                    timestamp = frame_idx / fps
                    small = cv2.resize(frame, (320, 240), interpolation=cv2.INTER_AREA)
                    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

                    if prev_gray is not None:
                        diff = cv2.absdiff(gray, prev_gray)
                        motion = float(np.mean(diff))
                    else:
                        motion = 0.0

                    motion_values.append(motion)
                    sampled_frames.append((frame_idx, timestamp, frame.copy()))
                    prev_gray = gray

                frame_idx += 1
        finally:
            cap.release()

        if not sampled_frames:
            return result

        result.sampled_frames_count = len(sampled_frames)

        smoothed = self._smooth_motion(motion_values)
        result.motion_profile = smoothed

        boundaries = self._detect_segment_boundaries(
            smoothed,
            timestamps=[t for _, t, _ in sampled_frames],
        )

        segments = self._build_segments(sampled_frames, boundaries, fps)
        segmentation_mode = "motion"
        if self._should_use_uniform_fallback(segments, duration_sec, len(sampled_frames)):
            logger.warning(
                "运动分割过粗: {}秒视频仅 {} 段，切换为均匀细分兜底",
                round(duration_sec, 1),
                len(segments),
            )
            segments = self._fallback_uniform_segments(sampled_frames)
            segmentation_mode = "uniform_fallback"
        result.segments = segments
        result.segmentation_mode = segmentation_mode

        all_keyframes: list[KeyFrame] = []
        for seg in segments:
            all_keyframes.extend(seg.keyframes)
        result.keyframes = all_keyframes

        logger.info(
            "时序分割完成: {} 个动作段, {} 个关键帧, 视频时长 {:.1f}s",
            len(segments),
            len(all_keyframes),
            duration_sec,
        )
        return result

    def _should_use_uniform_fallback(
        self,
        segments: list[ActionSegment],
        duration_sec: float,
        sampled_count: int,
    ) -> bool:
        """当运动谷值无法切开视频时，用均匀分段避免整段合成一个步骤。"""
        min_duration = max(self.coarse_fallback_min_duration_sec, self.min_segment_sec * 2)
        return (
            len(segments) <= 1
            and duration_sec >= min_duration
            and sampled_count >= max(8, self.frames_per_segment * 2)
        )

    def _smooth_motion(self, motion: list[float]) -> list[float]:
        if len(motion) <= self.motion_smooth_window:
            return motion

        kernel = np.ones(self.motion_smooth_window) / self.motion_smooth_window
        padded = np.pad(motion, (self.motion_smooth_window // 2,) * 2, mode="edge")
        smoothed = np.convolve(padded, kernel, mode="valid")
        return smoothed[: len(motion)].tolist()

    def _detect_segment_boundaries(
        self,
        motion: list[float],
        timestamps: list[float],
    ) -> list[int]:
        """检测动作段的分割边界（基于运动谷值）。

        原理：人在执行 SOP 时，动作之间通常有短暂停顿（运动强度下降），
        这些谷值就是动作段的自然边界。
        """
        if len(motion) < 3:
            return []

        motion_arr = np.array(motion)
        median_motion = float(np.median(motion_arr[motion_arr > 0])) if np.any(motion_arr > 0) else 1.0
        pause_threshold = median_motion * self.pause_threshold_ratio

        boundaries: list[int] = [0]
        in_pause = False
        pause_start_idx = 0

        for i in range(1, len(motion)):
            if motion[i] < pause_threshold:
                if not in_pause:
                    in_pause = True
                    pause_start_idx = i
            else:
                if in_pause:
                    in_pause = False
                    boundary_idx = (pause_start_idx + i) // 2
                    if timestamps[boundary_idx] - timestamps[boundaries[-1]] >= self.min_segment_sec:
                        boundaries.append(boundary_idx)

        if boundaries[-1] != len(motion) - 1:
            boundaries.append(len(motion) - 1)

        return boundaries

    def _build_segments(
        self,
        sampled_frames: list[tuple[int, float, np.ndarray]],
        boundaries: list[int],
        fps: float,
    ) -> list[ActionSegment]:
        """构建动作段，每段内提取代表性关键帧。"""
        if len(boundaries) < 2:
            n_kf = min(self.frames_per_segment, len(sampled_frames))
            if n_kf <= 1:
                selected_indices = [0]
            else:
                selected_indices = [
                    round(i * (len(sampled_frames) - 1) / (n_kf - 1))
                    for i in range(n_kf)
                ]
            keyframes = [
                KeyFrame(
                    index=sampled_frames[i][0],
                    timestamp_sec=sampled_frames[i][1],
                    frame_bgr=sampled_frames[i][2],
                    segment_id=0,
                )
                for i in sorted(set(selected_indices))
            ]
            seg = ActionSegment(
                segment_id=0,
                start_sec=sampled_frames[0][1],
                end_sec=sampled_frames[-1][1],
                keyframes=keyframes,
            )
            return [seg]

        segments: list[ActionSegment] = []
        for seg_idx in range(len(boundaries) - 1):
            start_i = boundaries[seg_idx]
            end_i = boundaries[seg_idx + 1]

            seg_frames = sampled_frames[start_i:end_i + 1]
            if not seg_frames:
                continue

            start_sec = seg_frames[0][1]
            end_sec = seg_frames[-1][1]

            n_kf = min(self.frames_per_segment, len(seg_frames))
            if n_kf <= 1:
                selected_indices = [0]
            else:
                selected_indices = [
                    round(i * (len(seg_frames) - 1) / (n_kf - 1))
                    for i in range(n_kf)
                ]
                selected_indices = sorted(set(selected_indices))

            keyframes: list[KeyFrame] = []
            for ki in selected_indices:
                frame_idx, ts, frame_bgr = seg_frames[ki]
                kf = KeyFrame(
                    index=frame_idx,
                    timestamp_sec=ts,
                    frame_bgr=frame_bgr,
                    is_scene_change=(ki == 0),
                    segment_id=seg_idx,
                )
                keyframes.append(kf)

            seg = ActionSegment(
                segment_id=seg_idx,
                start_sec=round(start_sec, 2),
                end_sec=round(end_sec, 2),
                keyframes=keyframes,
            )
            segments.append(seg)

        if not segments:
            return self._fallback_uniform_segments(sampled_frames)

        return segments

    def _fallback_uniform_segments(
        self,
        sampled_frames: list[tuple[int, float, np.ndarray]],
    ) -> list[ActionSegment]:
        """回退：均匀分割为固定数量的段。"""
        n_segments = min(10, max(3, len(sampled_frames) // 5))
        seg_size = max(1, len(sampled_frames) // n_segments)

        segments: list[ActionSegment] = []
        for seg_idx in range(n_segments):
            start = seg_idx * seg_size
            end = min(start + seg_size, len(sampled_frames))
            if start >= len(sampled_frames):
                break

            seg_frames = sampled_frames[start:end]
            n_kf = min(self.frames_per_segment, len(seg_frames))
            if n_kf <= 1:
                selected = [0]
            else:
                selected = [round(i * (len(seg_frames) - 1) / (n_kf - 1)) for i in range(n_kf)]

            keyframes = [
                KeyFrame(
                    index=seg_frames[ki][0],
                    timestamp_sec=seg_frames[ki][1],
                    frame_bgr=seg_frames[ki][2],
                    segment_id=seg_idx,
                )
                for ki in sorted(set(selected))
            ]

            segments.append(ActionSegment(
                segment_id=seg_idx,
                start_sec=round(seg_frames[0][1], 2),
                end_sec=round(seg_frames[-1][1], 2),
                keyframes=keyframes,
            ))

        return segments
