"""SOP 学习分析管线 — 编排帧提取、YOLO 检测、VLM 分析

对标 ActionInsight 的核心改进：
- 时序动作分割：自动将视频切分为动作段
- 逐段 VLM 分析：每个动作段独立识别
- 累积上下文：后续段携带前序结果，避免重复
- 参考帧绑定：每个步骤关联最佳参考帧
- 支持 20 分钟以上长视频
"""

from __future__ import annotations

import asyncio
import base64
import tempfile
from typing import Any, Callable, Coroutine

import cv2
from loguru import logger
from minio import Minio

from src.core.config import settings

from .frame_extractor import ActionSegment, ExtractionResult, FrameExtractor
from .vlm_service import VLMService
from .yolo_service import YOLOService

ProgressCallback = Callable[[float, str, dict[str, Any]], Coroutine[Any, Any, None]]


class AnalysisPipeline:
    """五阶段 SOP 学习分析管线。

    Phase 1 (0-15%):   视频下载 + 帧提取 + 运动分析 + 动作分割
    Phase 2 (15-30%):  YOLO 物体检测
    Phase 3 (30-75%):  VLM 逐段动作识别（核心）
    Phase 4 (75-90%):  步骤组装 + VLM 精炼
    Phase 5 (90-100%): 参考帧绑定 + 最终输出
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
            num_ctx=settings.VLM_NUM_CTX,
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

        # === Phase 1: Download + Frame Extraction + Motion Segmentation ===
        await _report(0.02, "视频下载中", {"current_phase": 1, "total_phases": 5})

        loop = asyncio.get_running_loop()
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp_path = tmp.name
        tmp.close()
        try:
            await self._download_from_minio(video_minio_path, tmp_path)
            await _report(0.05, "时序分析与动作分割", {"current_phase": 1, "total_phases": 5})

            extraction: ExtractionResult = await loop.run_in_executor(
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

        segments = extraction.segments

        await _report(0.15, "动作分割完成", {
            "current_phase": 1, "total_phases": 5,
            "phase": "动作分割完成",
            "total_frames": extraction.total_frames,
            "fps": round(extraction.fps, 1),
            "duration_sec": round(extraction.duration_sec, 1),
            "segments_count": len(segments),
            "keyframes_count": len(extraction.keyframes),
            "segmentation_mode": extraction.segmentation_mode,
        })

        # === Phase 2: YOLO Detection ===
        await _report(0.17, "YOLO 目标检测", {"current_phase": 2, "total_phases": 5, "phase": "YOLO 目标检测"})

        frames_bgr = [kf.frame_bgr for kf in extraction.keyframes]

        yolo_results = await loop.run_in_executor(
            None, self.yolo_service.detect_frames, frames_bgr,
        )

        all_objects: set[str] = set()
        for fd in yolo_results:
            all_objects.update(fd.object_names)

        segment_objects = self._collect_segment_objects(segments, yolo_results, extraction)

        await _report(0.30, "YOLO 检测完成", {
            "current_phase": 2, "total_phases": 5,
            "phase": "YOLO 检测完成",
            "objects_detected": sum(len(fd.detections) for fd in yolo_results),
            "unique_classes": list(all_objects),
        })

        # === Phase 3: VLM Segment-by-Segment Analysis (Core) ===
        await _report(0.32, "VLM 概览分析", {"current_phase": 3, "total_phases": 5, "phase": "VLM 整体概览"})

        sample_indices = [0, len(frames_bgr) // 2, len(frames_bgr) - 1]
        sample_frames = [frames_bgr[i] for i in sample_indices if i < len(frames_bgr)]
        overview = await self.vlm_service.analyze_overview(sample_frames, process_name)
        logger.info("VLM 概览: {}", overview[:200])

        await _report(0.38, "VLM 逐段分析", {"current_phase": 3, "total_phases": 5, "phase": "VLM 逐段动作识别"})

        segment_results: list[dict] = []
        previous_actions: list[str] = []

        for i, seg in enumerate(segments):
            seg_progress = 0.38 + (i / max(len(segments), 1)) * 0.37
            await _report(
                seg_progress,
                f"分析动作段 {i + 1}/{len(segments)}",
                {"current_phase": 3, "total_phases": 5, "phase": f"分析段 {i+1}/{len(segments)}"},
            )

            seg_frames = [kf.frame_bgr for kf in seg.keyframes]
            if not seg_frames:
                continue

            seg_objs = segment_objects.get(seg.segment_id, [])

            result = await self.vlm_service.analyze_segment(
                frames=seg_frames,
                segment_id=seg.segment_id,
                start_sec=seg.start_sec,
                end_sec=seg.end_sec,
                process_name=process_name,
                overview=overview,
                detected_objects=seg_objs,
                previous_actions=previous_actions,
            )

            segment_results.append(result)

            if not result.get("is_same_as_previous"):
                previous_actions.append(result.get("action", ""))

        await _report(0.75, "VLM 逐段分析完成", {
            "current_phase": 3, "total_phases": 5,
            "phase": "VLM 逐段分析完成",
            "segments_analyzed": len(segment_results),
            "unique_actions": len(set(r.get("action", "") for r in segment_results)),
        })

        # === Phase 4: Step Assembly + Refinement ===
        await _report(0.77, "步骤组装与判定标准生成", {
            "current_phase": 4, "total_phases": 5,
            "phase": "步骤组装与精炼",
        })

        if segment_results:
            steps = await self.vlm_service.assemble_steps_from_segments(
                segment_results, process_name, overview,
            )
        else:
            logger.warning("无分段结果，回退到全局分析")
            steps = await self._fallback_global_analysis(
                frames_bgr, extraction, yolo_results, process_name, overview,
            )

        await _report(0.90, "步骤组装完成", {
            "current_phase": 4, "total_phases": 5,
            "phase": "步骤组装完成",
            "step_count": len(steps),
        })

        # === Phase 5: Reference Frame Binding ===
        await _report(0.92, "参考帧绑定", {
            "current_phase": 5, "total_phases": 5,
            "phase": "参考帧与截图绑定",
        })

        steps = self._bind_reference_frames(steps, segments, video_minio_path)

        await _report(1.0, "分析完成", {
            "current_phase": 5, "total_phases": 5,
            "phase": "分析完成",
            "step_count": len(steps),
            "segments_count": len(segments),
            "segmentation_mode": extraction.segmentation_mode,
            "confidence": self._compute_overall_confidence(segment_results),
        })

        logger.info("分析管线完成: {} 个 SOP 步骤（{} 个动作段）", len(steps), len(segments))
        return steps

    @staticmethod
    def _collect_segment_objects(
        segments: list[ActionSegment],
        yolo_results: list,
        extraction: ExtractionResult,
    ) -> dict[int, list[str]]:
        """收集每个动作段中 YOLO 检测到的物体。"""
        kf_index_to_yolo_idx: dict[int, int] = {}
        for yi, kf in enumerate(extraction.keyframes):
            kf_index_to_yolo_idx[kf.index] = yi

        segment_objects: dict[int, list[str]] = {}
        for seg in segments:
            objects: set[str] = set()
            for kf in seg.keyframes:
                yolo_idx = kf_index_to_yolo_idx.get(kf.index)
                if yolo_idx is not None and yolo_idx < len(yolo_results):
                    objects.update(yolo_results[yolo_idx].object_names)
            segment_objects[seg.segment_id] = list(objects)

        return segment_objects

    @staticmethod
    def _bind_reference_frames(
        steps: list[dict],
        segments: list[ActionSegment],
        video_minio_path: str,
    ) -> list[dict]:
        """为每个步骤绑定参考帧的 base64 缩略图。"""
        seg_map = {seg.segment_id: seg for seg in segments}

        for step in steps:
            seg_ids = step.get("segment_ids", [])
            if not seg_ids:
                start_sec = step.get("start_sec", 0)
                for seg in segments:
                    if seg.start_sec <= start_sec <= seg.end_sec:
                        seg_ids = [seg.segment_id]
                        break

            ref_frame = None
            for sid in seg_ids:
                seg = seg_map.get(sid)
                if seg and seg.representative_frame:
                    ref_frame = seg.representative_frame
                    break

            if ref_frame is not None:
                h, w = ref_frame.frame_bgr.shape[:2]
                thumb_w = min(320, w)
                scale = thumb_w / w
                thumb = cv2.resize(
                    ref_frame.frame_bgr,
                    (thumb_w, int(h * scale)),
                    interpolation=cv2.INTER_AREA,
                )
                _, buffer = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 70])
                b64 = base64.b64encode(buffer).decode("utf-8")
                step["reference_frame_b64"] = b64
                step["reference_frame_timestamp"] = ref_frame.timestamp_sec
            else:
                step.setdefault("reference_frame_b64", "")
                step.setdefault("reference_frame_timestamp", 0)

        return steps

    @staticmethod
    def _compute_overall_confidence(segment_results: list[dict]) -> float:
        if not segment_results:
            return 0.0
        confs = [r.get("confidence", 0.5) for r in segment_results if not r.get("is_same_as_previous")]
        return round(sum(confs) / len(confs), 2) if confs else 0.5

    async def _fallback_global_analysis(
        self,
        frames_bgr: list,
        extraction: ExtractionResult,
        yolo_results: list,
        process_name: str,
        overview: str,
    ) -> list[dict]:
        """回退到全局分析模式（兼容无分段时的场景）。"""
        timestamps = [kf.timestamp_sec for kf in extraction.keyframes]
        objects_per_frame = [fd.object_names for fd in yolo_results]

        raw_steps = await self.vlm_service.analyze_steps(
            frames=frames_bgr,
            timestamps=timestamps,
            detected_objects_per_frame=objects_per_frame,
            process_name=process_name,
            overview=overview,
        )

        if raw_steps:
            return await self.vlm_service.refine_steps(raw_steps, process_name, overview)

        return self._fallback_steps_from_yolo(yolo_results, extraction, process_name)

    async def _download_from_minio(self, minio_path: str, local_path: str) -> None:
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
        """最终回退：基于 YOLO 物体出现变化生成基础步骤。"""
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
