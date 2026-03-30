"""SOP 学习分析管线 — 编排帧提取、YOLO 检测、VLM 分析四阶段流程"""

from __future__ import annotations

import asyncio
import tempfile
from typing import Any, Callable, Coroutine

from loguru import logger
from minio import Minio

from src.core.config import settings

from .frame_extractor import FrameExtractor
from .vlm_service import VLMService
from .yolo_service import YOLOService

ProgressCallback = Callable[[float, str, dict[str, Any]], Coroutine[Any, Any, None]]


class AnalysisPipeline:
    """四阶段 SOP 学习分析管线。

    Phase 1 (0-25%):  视频帧提取 (OpenCV)
    Phase 2 (25-50%): YOLO 物体检测
    Phase 3 (50-85%): VLM 视觉语言分析
    Phase 4 (85-100%): 步骤组装与优化
    """

    def __init__(
        self,
        frame_extractor: FrameExtractor | None = None,
        yolo_service: YOLOService | None = None,
        vlm_service: VLMService | None = None,
    ):
        self.frame_extractor = frame_extractor or FrameExtractor(
            max_keyframes=settings.MAX_KEYFRAMES,
        )
        self.yolo_service = yolo_service or YOLOService(
            model_name=settings.YOLO_MODEL,
            device=settings.YOLO_DEVICE,
        )
        self.vlm_service = vlm_service or VLMService(
            ollama_url=settings.OLLAMA_URL,
            model=settings.VLM_MODEL,
            timeout=settings.VLM_TIMEOUT,
        )

    async def run(
        self,
        video_minio_path: str,
        process_name: str,
        progress_cb: ProgressCallback | None = None,
    ) -> list[dict]:
        """执行完整分析管线，返回结构化 SOP 步骤列表。"""

        async def _report(progress: float, phase: str, detail: dict[str, Any]):
            if progress_cb:
                await progress_cb(progress, phase, detail)

        vlm_ok = await self.vlm_service.check_available()
        if not vlm_ok:
            raise RuntimeError(
                f"VLM 模型不可用 (Ollama: {self.vlm_service.ollama_url}, 模型: {self.vlm_service.model})。"
                f"请确认 Ollama 正在运行且已拉取模型。"
            )

        # --- Phase 1: Download + Frame Extraction ---
        await _report(0.02, "视频下载中", {"current_phase": 1, "total_phases": 4})

        loop = asyncio.get_running_loop()
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp_path = tmp.name
        tmp.close()
        try:
            await self._download_from_minio(video_minio_path, tmp_path)
            await _report(0.08, "视频分帧与关键帧提取", {"current_phase": 1, "total_phases": 4})

            extraction = await loop.run_in_executor(
                None, self.frame_extractor.extract, tmp_path,
            )
        finally:
            import os
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        if not extraction.keyframes:
            raise ValueError("视频中未提取到任何关键帧，请检查视频文件是否有效。")

        await _report(0.25, "帧提取完成", {
            "current_phase": 1, "total_phases": 4,
            "phase": "帧提取完成",
            "total_frames": extraction.total_frames,
            "fps": round(extraction.fps, 1),
            "duration_sec": round(extraction.duration_sec, 1),
            "frames_extracted": extraction.total_frames,
            "keyframes": len(extraction.keyframes),
        })

        # --- Phase 2: YOLO Detection ---
        await _report(0.27, "YOLO 目标检测", {"current_phase": 2, "total_phases": 4, "phase": "YOLO 目标检测"})

        frames_bgr = [kf.frame_bgr for kf in extraction.keyframes]

        yolo_results = await loop.run_in_executor(
            None, self.yolo_service.detect_frames, frames_bgr,
        )

        all_objects: set[str] = set()
        for fd in yolo_results:
            all_objects.update(fd.object_names)

        await _report(0.50, "YOLO 检测完成", {
            "current_phase": 2, "total_phases": 4,
            "phase": "YOLO 检测完成",
            "objects_detected": sum(len(fd.detections) for fd in yolo_results),
            "unique_classes": list(all_objects),
        })

        # --- Phase 3: VLM Analysis ---
        await _report(0.52, "VLM 视觉分析", {"current_phase": 3, "total_phases": 4, "phase": "VLM 整体概览分析"})

        # 3a. Overview
        sample_indices = [0, len(frames_bgr) // 2, len(frames_bgr) - 1]
        sample_frames = [frames_bgr[i] for i in sample_indices if i < len(frames_bgr)]
        overview = await self.vlm_service.analyze_overview(sample_frames, process_name)
        logger.info("VLM 概览: {}", overview[:200])

        await _report(0.60, "VLM 逐帧分析", {"current_phase": 3, "total_phases": 4, "phase": "VLM 逐段步骤识别"})

        # 3b. Step detection
        timestamps = [kf.timestamp_sec for kf in extraction.keyframes]
        objects_per_frame = [fd.object_names for fd in yolo_results]

        async def on_batch_progress(batch_idx: int, total_batches: int) -> None:
            batch_progress = 0.60 + (batch_idx / max(total_batches, 1)) * 0.20
            await _report(
                batch_progress,
                f"VLM 分析批次 {batch_idx + 1}/{total_batches}",
                {"current_phase": 3, "total_phases": 4, "phase": f"VLM 分析 {batch_idx + 1}/{total_batches}"},
            )

        raw_steps = await self.vlm_service.analyze_steps(
            frames=frames_bgr,
            timestamps=timestamps,
            detected_objects_per_frame=objects_per_frame,
            process_name=process_name,
            overview=overview,
            on_batch_progress=on_batch_progress,
        )

        await _report(0.80, "VLM 分析完成", {
            "current_phase": 3, "total_phases": 4,
            "phase": "VLM 分析完成",
            "actions_classified": len(raw_steps),
        })

        # --- Phase 4: Refinement ---
        await _report(0.85, "步骤优化与判定标准生成", {
            "current_phase": 4, "total_phases": 4,
            "phase": "步骤优化与判定标准生成",
        })

        if raw_steps:
            steps = await self.vlm_service.refine_steps(raw_steps, process_name, overview)
        else:
            logger.warning("VLM 未识别出任何步骤，将基于 YOLO 检测结果生成基础步骤")
            steps = self._fallback_steps_from_yolo(yolo_results, extraction, process_name)

        await _report(1.0, "分析完成", {
            "current_phase": 4, "total_phases": 4,
            "phase": "分析完成",
            "confidence": 0.9 if raw_steps else 0.5,
        })

        logger.info("分析管线完成: {} 个 SOP 步骤", len(steps))
        return steps

    async def _download_from_minio(self, minio_path: str, local_path: str) -> None:
        """从 MinIO 下载视频文件到本地临时路径。

        video_path 格式为 "bucket/object/key"，例如 "sop-learning/PCB-A100/xxx.mp4"
        """
        client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )

        parts = minio_path.split("/", 1)
        if len(parts) == 2:
            bucket, object_name = parts
        else:
            bucket = settings.MINIO_BUCKET_VIDEOS
            object_name = minio_path

        logger.info("下载视频: {}/{} → {}", bucket, object_name, local_path)
        await asyncio.get_running_loop().run_in_executor(
            None, client.fget_object, bucket, object_name, local_path,
        )

    @staticmethod
    def _fallback_steps_from_yolo(
        yolo_results: list,
        extraction,
        process_name: str,
    ) -> list[dict]:
        """当 VLM 无法识别步骤时，基于 YOLO 检测结果生成基础步骤。"""
        object_transitions: list[dict] = []
        prev_objects: set[str] = set()

        for i, fd in enumerate(yolo_results):
            current_objects = set(fd.object_names)
            new_objects = current_objects - prev_objects
            if new_objects and i > 0:
                kf = extraction.keyframes[i]
                object_transitions.append({
                    "timestamp": kf.timestamp_sec,
                    "new_objects": list(new_objects),
                    "all_objects": list(current_objects),
                })
            prev_objects = current_objects

        steps = []
        for idx, trans in enumerate(object_transitions[:10]):
            steps.append({
                "index": idx,
                "name": f"步骤{idx + 1}: 操作（{', '.join(trans['new_objects'][:2])}）",
                "description": f"在 t={trans['timestamp']:.1f}s 检测到新物体出现：{', '.join(trans['new_objects'])}",
                "action_type": "other",
                "required_objects": trans["all_objects"][:4],
                "timeout_seconds": 30,
                "is_optional": False,
                "ok_criteria": f"检测到 {trans['new_objects'][0]} 出现",
                "ng_criteria": f"未检测到 {trans['new_objects'][0]}",
                "reference_frame_url": "",
            })

        if not steps:
            steps.append({
                "index": 0,
                "name": f"步骤1: {process_name}",
                "description": f"执行 {process_name} 操作（AI 未能自动分解步骤，请手动编辑）",
                "action_type": "other",
                "required_objects": [],
                "timeout_seconds": 60,
                "is_optional": False,
                "ok_criteria": "",
                "ng_criteria": "",
                "reference_frame_url": "",
            })

        return steps
