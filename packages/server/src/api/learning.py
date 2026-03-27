"""SOP 学习模块 API"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.models.sop import SOPTemplate
from src.services.learning_service import LearningService

router = APIRouter()


@router.post("/upload-video")
async def upload_standard_video(
    product_model: str,
    process_name: str,
    video: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    if not video.content_type or not video.content_type.startswith("video/"):
        raise HTTPException(400, "仅支持视频文件")
    service = LearningService()
    task_id = await service.create_analysis_task(
        product_model=product_model, process_name=process_name, video=video, db=db,
    )
    return {"task_id": task_id, "status": "queued"}


@router.get("/task/{task_id}")
async def get_analysis_status(task_id: str):
    service = LearningService()
    return service.get_task_status(task_id)


@router.post("/generate-template/{task_id}")
async def generate_sop_template(task_id: str, db: AsyncSession = Depends(get_db)):
    service = LearningService()
    template = await service.generate_template(task_id, db)
    return template


@router.get("/templates/draft", response_model=list[dict])
async def list_draft_templates(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SOPTemplate).where(SOPTemplate.version == "draft"))
    return [{"id": t.id, "name": t.name, "product_model": t.product_model} for t in result.scalars().all()]
