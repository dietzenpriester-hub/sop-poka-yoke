"""循环缓冲录制器：持续缓存最近 N 秒，异常时保存前后文"""

import threading
import time
from collections import deque
from pathlib import Path

import cv2
from loguru import logger


class VideoRecorder:

    def __init__(
        self,
        buffer_seconds: int = 10,
        fps: int = 25,
        resolution: tuple = (2560, 1440),
        output_dir: str = "./clips",
    ) -> None:
        self.buffer_seconds = buffer_seconds
        self.fps = fps
        self.resolution = resolution
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._buffer: deque = deque(maxlen=buffer_seconds * fps)
        self._lock = threading.Lock()
        self._recording_post = False
        self._post_frames: list = []
        self._post_count = 0
        self._post_target = 0
        self._save_meta: dict = {}

    def feed(self, frame, timestamp: float) -> None:
        with self._lock:
            self._buffer.append((frame.copy(), timestamp))
            if self._recording_post:
                self._post_frames.append(frame.copy())
                self._post_count += 1
                if self._post_count >= self._post_target:
                    self._do_save_clip()

    def trigger_save(
        self, event_type: str, work_order_sn: str, step_index: int, post_seconds: int = 5
    ) -> str:
        with self._lock:
            self._recording_post = True
            self._post_frames = []
            self._post_count = 0
            self._post_target = post_seconds * self.fps
            self._save_meta = {
                "event_type": event_type,
                "sn": work_order_sn,
                "step": step_index,
                "timestamp": time.strftime("%Y%m%d_%H%M%S"),
            }
            clip_path = self._get_clip_path()
        logger.info("触发视频保存: {} SN={} step={}", event_type, work_order_sn, step_index)
        return clip_path

    def save_snapshot(self, frame, work_order_sn: str, step_index: int) -> str:
        filename = f"{work_order_sn}_step{step_index}_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
        filepath = self.output_dir / "snapshots" / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(filepath), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return str(filepath)

    def _get_clip_path(self) -> str:
        m = self._save_meta
        return str(self.output_dir / f"{m['sn']}_step{m['step']}_{m['event_type']}_{m['timestamp']}.mp4")

    def _do_save_clip(self) -> None:
        self._recording_post = False
        clip_path = self._get_clip_path()
        pre_frames = list(self._buffer)
        all_frames = [f for f, _ in pre_frames] + self._post_frames
        self._post_frames = []
        if not all_frames:
            return
        h, w = all_frames[0].shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(clip_path, fourcc, self.fps, (w, h))
        if not writer.isOpened():
            logger.error("VideoWriter 无法打开，跳过保存: {}", clip_path)
            return
        for frame in all_frames:
            writer.write(frame)
        writer.release()
        logger.info("视频片段已保存: {} ({} 帧)", clip_path, len(all_frames))
