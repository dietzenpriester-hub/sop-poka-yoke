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
                logger.error("分析任务失败 {}: {}", task_id, e)
                result = await db.execute(select(LearningTask).where(LearningTask.task_id == task_id))
                task = result.scalar_one_or_none()
                if task:
                    task.status = "failed"
                    task.error_message = str(e)[:500]
                    await db.commit()

    async def _run_analysis(self, task_id: str, db: AsyncSession) -> None:
        result = await db.execute(select(LearningTask).where(LearningTask.task_id == task_id))
        task = result.scalar_one()

        async def progress_callback(progress: float, phase_name: str, detail: dict[str, Any]):
            task.progress = progress
            task.analysis_detail = {**(task.analysis_detail or {}), **detail, "phase": phase_name}
            if progress < 0.25:
                task.status = "phase_1"
            elif progress < 0.50:
                task.status = "phase_2"
            elif progress < 0.85:
                task.status = "phase_3"
            elif progress < 1.0:
                task.status = "phase_4"
            await db.commit()

        steps = await self.pipeline.run(
            video_minio_path=task.video_path,
            process_name=task.process_name,
            progress_cb=progress_callback,
        )

        task.status = "completed"
        task.progress = 1.0
        task.steps = steps
        task.completed_at = datetime.now(timezone.utc)
        task.analysis_detail = {
            **(task.analysis_detail or {}),
            "phase": "分析完成",
        }
        await db.commit()
        logger.info("AI 分析完成: {} 共 {} 步", task_id, len(steps))

    async def get_task(self, task_id: str, db: AsyncSession) -> LearningTask | None:
        result = await db.execute(select(LearningTask).where(LearningTask.task_id == task_id))
        return result.scalar_one_or_none()

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
        if task.status != "completed":
            raise ValueError(f"任务状态 {task.status} 不支持编辑步骤")
        task.steps = steps
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
        if task.status != "completed":
            raise ValueError(f"任务状态 {task.status} 不支持确认生成（仅 completed 可确认）")

        template = SOPTemplate(
            name=task.process_name,
            version="draft",
            product_model=task.product_model,
            steps=task.steps,
            description=f"AI 自动分析生成（任务 {task_id[:8]}...）",
        )
        db.add(template)
        await db.commit()
        await db.refresh(template)

        task.status = "confirmed"
        task.template_id = template.id
        await db.commit()

        return {"template_id": template.id, "name": template.name, "step_count": len(task.steps or [])}

    async def delete_task(self, task_id: str, db: AsyncSession) -> None:
        result = await db.execute(select(LearningTask).where(LearningTask.task_id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            raise ValueError("任务不存在")
        await db.delete(task)
        await db.commit()
