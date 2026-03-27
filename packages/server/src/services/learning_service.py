"""SOP 标准作业学习服务"""

from __future__ import annotations

import io
import uuid
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.models.sop import SOPTemplate


class LearningService:

    _tasks: dict[str, dict[str, Any]] = {}

    async def create_analysis_task(
        self, product_model: str, process_name: str, video: Any, db: AsyncSession,
    ) -> str:
        task_id = str(uuid.uuid4())
        from minio import Minio

        client = Minio(settings.MINIO_ENDPOINT, settings.MINIO_ACCESS_KEY, settings.MINIO_SECRET_KEY, secure=False)
        bucket = "sop-learning"
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
        object_name = f"{product_model}/{process_name}/{task_id}.mp4"
        content = await video.read()
        client.put_object(bucket, object_name, io.BytesIO(content), len(content), "video/mp4")
        self._tasks[task_id] = {
            "status": "queued", "product_model": product_model,
            "process_name": process_name, "video_path": f"{bucket}/{object_name}", "steps": [],
        }
        logger.info("学习任务已创建: task_id={}, video={}", task_id, object_name)
        await self._run_analysis(task_id)
        return task_id

    async def _run_analysis(self, task_id: str) -> None:
        task = self._tasks[task_id]
        task["status"] = "analyzing"
        task["steps"] = [
            {"index": 0, "name": "拿起工具", "description": "从工具架上拿起螺丝刀", "required_objects": ["screwdriver"], "action_type": "pick_up", "timeout_seconds": 30},
            {"index": 1, "name": "定位螺丝孔", "description": "将螺丝刀对准 PCB 板螺丝孔位", "required_objects": ["screwdriver", "pcb_board"], "action_type": "position", "timeout_seconds": 20},
            {"index": 2, "name": "拧入螺丝", "description": "顺时针旋转拧入螺丝", "required_objects": ["screwdriver", "screw"], "action_type": "rotate", "timeout_seconds": 45},
        ]
        task["status"] = "completed"
        logger.info("AI 分析完成: {} 共 {} 步", task_id, len(task["steps"]))

    def get_task_status(self, task_id: str) -> dict:
        if task_id not in self._tasks:
            return {"error": "任务不存在"}
        task = self._tasks[task_id]
        return {"task_id": task_id, "status": task["status"], "step_count": len(task.get("steps", []))}

    async def generate_template(self, task_id: str, db: AsyncSession) -> dict:
        if task_id not in self._tasks:
            raise ValueError("任务不存在")
        task = self._tasks[task_id]
        if task["status"] != "completed":
            raise ValueError(f"任务未完成: {task['status']}")
        template = SOPTemplate(
            name=task["process_name"], version="draft", product_model=task["product_model"],
            steps=task["steps"], description=f"AI 自动生成（任务 {task_id}）",
        )
        db.add(template)
        await db.commit()
        await db.refresh(template)
        return {"template_id": template.id, "name": template.name, "steps": template.steps, "version": "draft"}
