"""SOP 标准作业学习服务 — AI 真实分析版"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import async_session_factory
from src.models.learning_task import LearningTask
from src.models.sop import SOPTemplate
from src.services.ai.analysis_pipeline import AnalysisPipeline


QUALITY_MIN_CONFIDENCE = 0.65
QUALITY_MIN_MULTI_STEP_SEC = 5.0
# 单个步骤跨度占全片比例上限：超过说明这一步很可能吞掉了相邻的其他动作
QUALITY_MAX_STEP_SPAN_RATIO = 0.6
# 动作段合并成步骤的比例上限，以及触发该检查所需的最少段数
QUALITY_MAX_MERGE_RATIO = 3.0
QUALITY_MERGE_CHECK_MIN_SEGMENTS = 3
GENERIC_CONTEXT_VALUES = {
    "测试", "测试1", "测试2", "test", "demo", "sample", "验证", "演示", "试验", "1", "2", "3"
}
SCENE_NOISE_OBJECTS = {
    "person", "chair", "cell phone", "laptop", "keyboard", "mouse", "monitor", "桌子", "椅子", "人", "手"
}
REVIEW_STATUS_PENDING = "pending"
REVIEW_STATUS_CONFIRMED = "confirmed"
REVIEW_STATUS_IGNORED = "ignored"
REVIEW_STATUS_NEEDS_REWORK = "needs_rework"
VALID_REVIEW_STATUSES = {
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_CONFIRMED,
    REVIEW_STATUS_IGNORED,
    REVIEW_STATUS_NEEDS_REWORK,
}
EVIDENCE_STATUS_SUPPORTED = "supported"
EVIDENCE_STATUS_WEAK = "weak"
EVIDENCE_STATUS_MISSING = "missing"


class LearningService:
    def __init__(self) -> None:
        self._pipeline: AnalysisPipeline | None = None

    @property
    def pipeline(self) -> AnalysisPipeline:
        if self._pipeline is None:
            self._pipeline = AnalysisPipeline()
        return self._pipeline

    async def create_task(self, product_model: str, process_name: str, video_path: str, db: AsyncSession) -> str:
        task_id = str(uuid.uuid4())
        task = LearningTask(
            task_id=task_id,
            product_model=product_model,
            process_name=process_name,
            video_path=video_path,
            status="queued",
            progress=0.0,
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)

        asyncio.create_task(self._run_analysis_background(task_id))
        return task_id

    async def _run_analysis_background(self, task_id: str) -> None:
        """Run analysis in background with separate DB session."""
        async with async_session_factory() as db:
            try:
                await self._run_analysis(task_id, db)
            except Exception as e:
                logger.exception("分析任务失败 {}: {}", task_id, e)
                result = await db.execute(select(LearningTask).where(LearningTask.task_id == task_id))
                task = result.scalar_one_or_none()
                if task:
                    task.status = "failed"
                    task.error_message = str(e)[:500]
                    await db.commit()

    async def _run_analysis(self, task_id: str, db: AsyncSession) -> None:
        result = await db.execute(select(LearningTask).where(LearningTask.task_id == task_id))
        task = result.scalar_one_or_none()
        if task is None:
            logger.warning("分析任务 {} 已被删除，跳过", task_id)
            return

        _last_commit_progress = 0.0

        async def progress_callback(progress: float, phase_name: str, detail: dict[str, Any]):
            nonlocal _last_commit_progress
            task.progress = progress
            task.analysis_detail = {**(task.analysis_detail or {}), **detail, "phase": phase_name}
            if progress < 0.15:
                task.status = "phase_1"
            elif progress < 0.30:
                task.status = "phase_2"
            elif progress < 0.75:
                task.status = "phase_3"
            elif progress < 0.90:
                task.status = "phase_4"
            elif progress < 1.0:
                task.status = "phase_5"
            if progress - _last_commit_progress >= 0.03 or progress >= 1.0:
                _last_commit_progress = progress
                await db.commit()

        steps = await self.pipeline.run(
            video_minio_path=task.video_path,
            process_name=task.process_name,
            progress_cb=progress_callback,
        )

        task.progress = 1.0
        task.steps = self._prepare_steps_for_review(steps, manual_reviewed=False)
        task.completed_at = datetime.now(timezone.utc)
        analysis_detail = {
            **(task.analysis_detail or {}),
            "phase": "分析完成",
        }
        quality = self._evaluate_quality(
            task.steps,
            analysis_detail,
            product_model=task.product_model,
            process_name=task.process_name,
        )
        analysis_detail["quality"] = quality
        task.analysis_detail = analysis_detail
        task.status = "completed" if quality["passed"] else "needs_review"
        await db.commit()
        logger.info("AI 分析完成: {} 共 {} 步，质量状态={}", task_id, len(steps), quality["status"])

    async def get_task(self, task_id: str, db: AsyncSession) -> LearningTask | None:
        result = await db.execute(select(LearningTask).where(LearningTask.task_id == task_id))
        return result.scalar_one_or_none()

    async def retry_analysis(self, task_id: str, db: AsyncSession) -> LearningTask:
        result = await db.execute(select(LearningTask).where(LearningTask.task_id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            raise ValueError("任务不存在")
        if task.status not in {"failed", "needs_review", "completed"}:
            raise ValueError(f"任务状态 {task.status} 不支持重试分析")
        if task.template_id is not None:
            raise ValueError("任务已生成模板，无法重试分析")

        task.status = "queued"
        task.progress = 0.0
        task.steps = []
        task.error_message = ""
        task.completed_at = None
        task.analysis_detail = {
            **(task.analysis_detail or {}),
            "phase": "重新排队",
            "retry_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.commit()
        await db.refresh(task)
        asyncio.create_task(self._run_analysis_background(task_id))
        return task

    async def list_tasks(self, db: AsyncSession, skip: int = 0, limit: int = 20) -> tuple[list[LearningTask], int]:
        from sqlalchemy import func as sqlfunc

        count_r = await db.execute(select(sqlfunc.count(LearningTask.id)))
        total = count_r.scalar_one()
        result = await db.execute(select(LearningTask).order_by(LearningTask.id.desc()).offset(skip).limit(limit))
        return list(result.scalars().all()), total

    async def update_steps(self, task_id: str, steps: list[dict[str, Any]], db: AsyncSession) -> LearningTask:
        result = await db.execute(select(LearningTask).where(LearningTask.task_id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            raise ValueError("任务不存在")
        if task.status == "confirmed":
            raise ValueError("任务已确认，无法编辑步骤")
        if task.status not in {"completed", "needs_review"}:
            raise ValueError(f"任务状态 {task.status} 不支持编辑步骤")
        normalized_steps = self._prepare_steps_for_review(steps, manual_reviewed=True)
        task.steps = normalized_steps
        analysis_detail = {
            **(task.analysis_detail or {}),
            "phase": "人工复核完成",
        }
        quality = self._evaluate_quality(
            normalized_steps,
            analysis_detail,
            manual_reviewed=True,
            product_model=task.product_model,
            process_name=task.process_name,
        )
        analysis_detail["quality"] = quality
        task.analysis_detail = analysis_detail
        task.status = "completed" if quality["passed"] else "needs_review"
        await db.commit()
        await db.refresh(task)
        return task

    async def confirm_and_generate(self, task_id: str, db: AsyncSession) -> dict:
        result = await db.execute(select(LearningTask).where(LearningTask.task_id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            raise ValueError("任务不存在")
        if task.template_id is not None:
            tpl_r = await db.execute(select(SOPTemplate).where(SOPTemplate.id == task.template_id))
            existing = tpl_r.scalar_one_or_none()
            if existing:
                return {
                    "template_id": existing.id,
                    "name": existing.name,
                    "step_count": len(task.steps or []),
                }
        if task.status == "needs_review":
            raise ValueError("学习结果需要人工复核并保存后，才能确认生成模板")
        if task.status != "completed":
            raise ValueError(f"任务状态 {task.status} 不支持确认生成（仅 completed 可确认）")
        quality = (task.analysis_detail or {}).get("quality")
        if isinstance(quality, dict) and not quality.get("passed", False):
            raise ValueError("学习结果质量评估未通过，请复核步骤后再生成模板")

        template_steps = self._build_template_steps(task.steps or [])
        if not template_steps:
            raise ValueError("没有已确认的有效步骤，无法生成模板")

        template = SOPTemplate(
            name=task.process_name,
            version="draft",
            product_model=task.product_model,
            steps=template_steps,
            description=f"AI 辅助学习 + 人工复核生成（任务 {task_id[:8]}...）",
        )
        db.add(template)
        await db.flush()

        task.status = "confirmed"
        task.template_id = template.id
        await db.commit()
        await db.refresh(template)

        return {"template_id": template.id, "name": template.name, "step_count": len(template_steps)}

    @classmethod
    def _prepare_steps_for_review(
        cls,
        steps: list[dict[str, Any]] | None,
        *,
        manual_reviewed: bool,
    ) -> list[dict[str, Any]]:
        """补齐人工复核字段。AI 生成的步骤默认只作为候选步骤。"""
        prepared: list[dict[str, Any]] = []
        reviewed_at = datetime.now(timezone.utc).isoformat()
        for index, raw in enumerate(steps or []):
            step = dict(raw)
            try:
                step["index"] = int(step.get("index", index))
            except (TypeError, ValueError):
                step["index"] = index

            status = str(step.get("review_status") or REVIEW_STATUS_PENDING).strip()
            if status not in VALID_REVIEW_STATUSES:
                status = REVIEW_STATUS_PENDING
            step["review_status"] = status

            evidence_status = str(step.get("evidence_status") or "").strip()
            if evidence_status not in {EVIDENCE_STATUS_SUPPORTED, EVIDENCE_STATUS_WEAK, EVIDENCE_STATUS_MISSING}:
                evidence_status = cls._infer_evidence_status(step)
            step["evidence_status"] = evidence_status

            step["confirmation_note"] = str(step.get("confirmation_note") or "").strip()
            step["human_reviewed"] = status in {
                REVIEW_STATUS_CONFIRMED,
                REVIEW_STATUS_IGNORED,
                REVIEW_STATUS_NEEDS_REWORK,
            }
            if manual_reviewed and step["human_reviewed"] and not step.get("reviewed_at"):
                step["reviewed_at"] = reviewed_at
            prepared.append(step)
        return prepared

    @staticmethod
    def _infer_evidence_status(step: dict[str, Any]) -> str:
        name = str(step.get("name") or "")
        if step.get("grounding_supported") is False or name == "无法确认动作":
            return EVIDENCE_STATUS_MISSING
        raw_confidence = step.get("grounding_confidence")
        try:
            confidence = float(raw_confidence)
        except (TypeError, ValueError):
            confidence = None
        if confidence is not None and confidence < QUALITY_MIN_CONFIDENCE:
            return EVIDENCE_STATUS_WEAK
        if not step.get("reference_frame_b64") and not step.get("reference_frame_url"):
            return EVIDENCE_STATUS_WEAK
        return EVIDENCE_STATUS_SUPPORTED

    @staticmethod
    def _build_template_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        template_steps: list[dict[str, Any]] = []
        review_only_keys = {
            "review_status",
            "evidence_status",
            "confirmation_note",
            "human_reviewed",
            "reviewed_at",
            "grounding_supported",
            "grounding_confidence",
            "grounding_issue",
            "source_confidence",
            "segment_ids",
        }
        for step in steps:
            if step.get("review_status") != REVIEW_STATUS_CONFIRMED:
                continue
            item = {
                key: value
                for key, value in step.items()
                if key not in review_only_keys
            }
            item["index"] = len(template_steps)
            template_steps.append(item)
        return template_steps

    @staticmethod
    def _evaluate_quality(
        steps: list[dict[str, Any]] | None,
        analysis_detail: dict[str, Any] | None,
        *,
        manual_reviewed: bool = False,
        product_model: str = "",
        process_name: str = "",
    ) -> dict[str, Any]:
        """评估学习结果是否适合直接生成 SOP 模板。"""
        steps = steps or []
        active_steps = [
            s for s in steps
            if s.get("review_status") != REVIEW_STATUS_IGNORED
        ]
        detail = analysis_detail or {}
        candidate_step_count = len(steps)
        ignored_step_count = candidate_step_count - len(active_steps)
        step_count = len(active_steps)
        duration_sec = float(detail.get("duration_sec") or 0.0)
        segments_count = int(detail.get("segments_count") or 0)
        confidence_raw = detail.get("confidence")
        confidence = float(confidence_raw) if isinstance(confidence_raw, int | float) else None
        segmentation_mode = str(detail.get("segmentation_mode") or "")
        reference_frame_count = sum(1 for s in active_steps if s.get("reference_frame_b64") or s.get("reference_frame_url"))
        grounding_confidences: list[float] = []
        for step in active_steps:
            raw = step.get("grounding_confidence")
            if isinstance(raw, int | float):
                grounding_confidences.append(float(raw))
        unsupported_grounding_count = sum(1 for s in active_steps if s.get("grounding_supported") is False)
        low_grounding_count = sum(1 for v in grounding_confidences if v < QUALITY_MIN_CONFIDENCE)
        confirmed_step_count = sum(
            1 for s in active_steps
            if s.get("review_status") == REVIEW_STATUS_CONFIRMED
        )
        needs_rework_count = sum(
            1 for s in active_steps
            if s.get("review_status") == REVIEW_STATUS_NEEDS_REWORK
        )
        unconfirmed_step_count = max(0, step_count - confirmed_step_count)
        max_step_span_ratio = 0.0
        if duration_sec > 0:
            for step in active_steps:
                start = step.get("start_sec")
                end = step.get("end_sec")
                if not isinstance(start, int | float) or not isinstance(end, int | float):
                    continue
                if end > start:
                    max_step_span_ratio = max(max_step_span_ratio, (end - start) / duration_sec)

        issues: list[dict[str, str]] = []

        def add_issue(code: str, message: str, severity: str = "warning") -> None:
            issues.append({"code": code, "message": message, "severity": severity})

        if step_count == 0:
            add_issue("empty_steps", "未识别到任何 SOP 步骤", "error")

        missing_name_count = sum(1 for s in active_steps if not str(s.get("name") or "").strip())
        if missing_name_count:
            add_issue("missing_step_name", f"{missing_name_count} 个步骤缺少名称", "error")

        missing_criteria_count = sum(
            1
            for s in active_steps
            if not str(s.get("ok_criteria") or "").strip()
            or not str(s.get("ng_criteria") or "").strip()
        )
        if missing_criteria_count:
            add_issue("missing_criteria", f"{missing_criteria_count} 个步骤缺少 OK/NG 判定标准", "error")

        if confidence is not None and confidence < QUALITY_MIN_CONFIDENCE:
            add_issue(
                "low_confidence",
                f"整体识别置信度 {confidence:.2f} 低于 {QUALITY_MIN_CONFIDENCE:.2f}",
            )

        if duration_sec >= QUALITY_MIN_MULTI_STEP_SEC and step_count <= 1:
            add_issue("few_steps_for_duration", f"{duration_sec:.1f} 秒视频仅生成 {step_count} 个步骤")

        if duration_sec >= QUALITY_MIN_MULTI_STEP_SEC and segments_count <= 1:
            add_issue("coarse_segmentation", "动作分割过粗，建议人工确认是否需要拆分步骤")

        if duration_sec > 0 and max_step_span_ratio >= QUALITY_MAX_STEP_SPAN_RATIO:
            add_issue(
                "step_spans_whole_video",
                f"单个步骤覆盖了全片 {max_step_span_ratio * 100:.0f}% 的时长，"
                "可能把多个动作并成了一步",
            )

        if (
            step_count > 0
            and segments_count >= QUALITY_MERGE_CHECK_MIN_SEGMENTS
            and segments_count / step_count >= QUALITY_MAX_MERGE_RATIO
        ):
            add_issue(
                "over_merged_segments",
                f"{segments_count} 个动作段被合并成 {step_count} 个步骤，"
                "合并可能过度，建议确认是否漏掉了动作",
            )

        if segmentation_mode == "uniform_fallback":
            add_issue("segmentation_fallback_used", "运动分割过粗，系统已启用均匀细分兜底", "info")

        if step_count > 0 and reference_frame_count < step_count:
            add_issue("missing_reference_frame", f"{step_count - reference_frame_count} 个步骤缺少参考帧", "info")

        if unsupported_grounding_count:
            add_issue("ungrounded_steps", f"{unsupported_grounding_count} 个步骤缺少连续画面证据支持")

        if low_grounding_count:
            add_issue("low_grounding_confidence", f"{low_grounding_count} 个步骤视觉证据置信度低于 {QUALITY_MIN_CONFIDENCE:.2f}")

        if needs_rework_count:
            add_issue("step_marked_needs_rework", f"{needs_rework_count} 个步骤被标记为需重新分析", "error")

        if unconfirmed_step_count:
            add_issue("step_confirmation_required", f"{unconfirmed_step_count} 个有效步骤尚未人工确认", "error")

        normalized_context = {
            "".join(product_model.strip().lower().split()),
            "".join(process_name.strip().lower().split()),
        }
        if normalized_context & GENERIC_CONTEXT_VALUES:
            add_issue("generic_context", "产品型号或工序名称过于泛化，无法确认学习视频是否匹配真实作业")

        required_objects = sorted({
            str(obj).strip()
            for step in active_steps
            for obj in (step.get("required_objects") or [])
            if str(obj).strip()
        })
        noise_objects = [obj for obj in required_objects if obj.lower() in SCENE_NOISE_OBJECTS]
        if noise_objects:
            add_issue("scene_noise_objects", f"必选对象包含现场背景物体：{', '.join(noise_objects[:6])}")

        hard_codes = {
            "empty_steps",
            "missing_step_name",
            "missing_criteria",
            "step_confirmation_required",
            "step_marked_needs_rework",
        }
        reviewable_codes = {
            "low_confidence",
            "few_steps_for_duration",
            "coarse_segmentation",
            "step_spans_whole_video",
            "over_merged_segments",
            "generic_context",
            "scene_noise_objects",
            "ungrounded_steps",
            "low_grounding_confidence",
        }
        blocking_issues = [
            i for i in issues
            if i["code"] in hard_codes or (i["code"] in reviewable_codes and not manual_reviewed)
        ]

        score = 1.0
        if confidence is not None:
            score = min(score, confidence)
        score -= 0.2 * sum(1 for i in issues if i["severity"] == "error")
        score -= 0.1 * sum(1 for i in issues if i["severity"] == "warning")
        score = max(0.0, round(score, 2))

        passed = len(blocking_issues) == 0
        return {
            "passed": passed,
            "status": "passed" if passed else "needs_review",
            "score": score,
            "manual_reviewed": manual_reviewed,
            "issues": issues,
            "metrics": {
                "step_count": step_count,
                "candidate_step_count": candidate_step_count,
                "confirmed_step_count": confirmed_step_count,
                "unconfirmed_step_count": unconfirmed_step_count,
                "ignored_step_count": ignored_step_count,
                "needs_rework_count": needs_rework_count,
                "duration_sec": round(duration_sec, 1),
                "segments_count": segments_count,
                "max_step_span_ratio": round(max_step_span_ratio, 2),
                "confidence": confidence,
                "reference_frame_count": reference_frame_count,
                "segmentation_mode": segmentation_mode or "unknown",
                "unsupported_grounding_count": unsupported_grounding_count,
                "low_grounding_count": low_grounding_count,
                "grounding_confidences": grounding_confidences,
                "required_objects": required_objects,
                "product_model": product_model,
                "process_name": process_name,
            },
        }

    async def delete_task(self, task_id: str, db: AsyncSession) -> None:
        result = await db.execute(select(LearningTask).where(LearningTask.task_id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            raise ValueError("任务不存在")
        video_path = task.video_path
        await db.delete(task)
        await db.commit()
        if video_path:
            try:
                from src.services.storage_service import get_storage_service, resolve_minio_bucket_and_object
                from src.core.config import settings as _s
                storage = get_storage_service()
                bucket, key = resolve_minio_bucket_and_object(video_path, _s.MINIO_BUCKET_VIDEOS)
                storage.client.remove_object(bucket, key)
                logger.info("已清理学习任务视频: {}", video_path)
            except Exception as e:
                logger.warning("清理学习任务视频失败（可忽略）: {}", e)
