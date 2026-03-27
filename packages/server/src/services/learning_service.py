"""SOP 标准作业学习服务 — 增强版"""

import asyncio
import random
import uuid
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import async_session_factory
from src.models.learning_task import LearningTask
from src.models.sop import SOPTemplate

# Common manufacturing action templates for realistic simulation
COMMON_ACTIONS = [
    # assembly
    {"name": "取料", "description": "从物料盒中取出指定零件", "action_type": "pick_up", "required_objects": ["part", "hand"]},
    {"name": "定位", "description": "将零件对准装配位置", "action_type": "position", "required_objects": ["part", "fixture"]},
    {"name": "安装", "description": "将零件安装到指定位置", "action_type": "assemble", "required_objects": ["part", "product"]},
    {"name": "紧固", "description": "使用工具进行紧固操作", "action_type": "fasten", "required_objects": ["tool", "fastener"]},
    {"name": "检查", "description": "目视检查装配质量", "action_type": "inspect", "required_objects": ["product"]},
    {"name": "扫码", "description": "扫描产品序列号绑定追溯", "action_type": "scan", "required_objects": ["scanner", "barcode"]},
    {"name": "涂胶", "description": "在指定区域涂布密封胶", "action_type": "apply", "required_objects": ["glue_gun", "surface"]},
    {"name": "插接", "description": "将连接器插入对应接口", "action_type": "insert", "required_objects": ["connector", "socket"]},
    {"name": "焊接", "description": "对焊点进行锡焊操作", "action_type": "solder", "required_objects": ["soldering_iron", "solder"]},
    {"name": "测试", "description": "使用测试设备进行功能测试", "action_type": "test", "required_objects": ["tester", "product"]},
    {"name": "包装", "description": "将产品放入包装盒", "action_type": "pack", "required_objects": ["product", "box"]},
    {"name": "贴标", "description": "在产品指定位置贴附标签", "action_type": "label", "required_objects": ["label", "product"]},
]


class LearningService:
    def __init__(self) -> None:
        pass

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

        # Start background analysis (don't await)
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

        # Phase 1: Frame extraction (simulated)
        task.status = "phase_1"
        task.analysis_detail = {"phase": "视频分帧与关键帧提取", "current_phase": 1, "total_phases": 3}
        task.progress = 0.1
        await db.commit()
        await asyncio.sleep(2)  # Simulate processing

        task.progress = 0.2
        task.analysis_detail = {
            **(task.analysis_detail or {}),
            "frames_extracted": random.randint(120, 500),
            "keyframes": random.randint(15, 40),
        }
        await db.commit()
        await asyncio.sleep(1)

        # Phase 2: YOLO + VLM analysis
        task.status = "phase_2"
        task.progress = 0.35
        task.analysis_detail = {**(task.analysis_detail or {}), "phase": "YOLO 目标检测 + VLM 动作识别", "current_phase": 2}
        await db.commit()
        await asyncio.sleep(2)

        # Generate realistic steps based on process_name
        num_steps = random.randint(3, 8)
        selected_actions = random.sample(COMMON_ACTIONS, min(num_steps, len(COMMON_ACTIONS)))
        steps = []
        for i, action in enumerate(selected_actions):
            step = {
                "index": i,
                "name": f"步骤{i + 1}: {action['name']}",
                "description": f"{action['description']}（{task.process_name}）",
                "required_objects": action["required_objects"],
                "action_type": action["action_type"],
                "timeout_seconds": random.choice([15, 20, 30, 45, 60]),
                "is_optional": random.random() < 0.15,
                "reference_frame_url": "",
                "ok_criteria": f"检测到{action['required_objects'][0]}在正确位置，动作完成",
                "ng_criteria": f"未检测到{action['required_objects'][0]}或位置偏移超过阈值",
            }
            steps.append(step)

        task.progress = 0.6
        task.steps = steps
        task.analysis_detail = {
            **(task.analysis_detail or {}),
            "objects_detected": random.randint(50, 200),
            "actions_classified": len(steps),
        }
        await db.commit()
        await asyncio.sleep(1)

        # Phase 3: Refinement
        task.status = "phase_3"
        task.progress = 0.8
        task.analysis_detail = {**(task.analysis_detail or {}), "phase": "步骤优化与判定标准生成", "current_phase": 3}
        await db.commit()
        await asyncio.sleep(1)

        task.status = "completed"
        task.progress = 1.0
        task.completed_at = datetime.now(timezone.utc)
        task.analysis_detail = {
            **(task.analysis_detail or {}),
            "phase": "分析完成",
            "confidence": round(random.uniform(0.85, 0.98), 2),
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
        if task.status not in ("completed", "confirmed"):
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
        if task.status not in ("completed", "confirmed"):
            raise ValueError(f"任务状态 {task.status} 不支持生成模板")

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
