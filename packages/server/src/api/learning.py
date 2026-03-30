"""SOP 学习模块 API — 增强版"""

import os
import tempfile
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from minio import Minio
from sqlalchemy.ext.asyncio import AsyncSession

MAX_UPLOAD_BYTES = 100 * 1024 * 1024

from src.core.config import settings
from src.core.database import get_db
from src.core.security import get_current_user
from src.schemas.learning import (
    LearningTaskListResponse,
    LearningTaskResponse,
    StepsUpdateRequest,
    TaskCreateResponse,
)
from src.services.learning_service import LearningService

router = APIRouter()
_service = LearningService()


@router.post("/upload-video", response_model=TaskCreateResponse)
async def upload_standard_video(
    product_model: str = Query(..., max_length=100, pattern=r"^[\w\-\u4e00-\u9fff]+$"),
    process_name: str = Query(..., max_length=100, pattern=r"^[\w\-\u4e00-\u9fff]+$"),
    video: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    if not video.content_type or not video.content_type.startswith("video/"):
        raise HTTPException(400, "仅支持视频文件")
    # Upload to MinIO
    client = Minio(
        settings.MINIO_ENDPOINT,
        settings.MINIO_ACCESS_KEY,
        settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )
    bucket = "sop-learning"
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)

    object_name = f"{product_model}/{process_name}/{uuid.uuid4()}.mp4"
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
        tmp_path = tmp.name
        total_read = 0
        while True:
            chunk = await video.read(1024 * 1024)
            if not chunk:
                break
            total_read += len(chunk)
            if total_read > MAX_UPLOAD_BYTES:
                os.unlink(tmp_path)
                raise HTTPException(413, "文件大小不能超过 100MB")
            tmp.write(chunk)
    try:
        length = os.path.getsize(tmp_path)
        with open(tmp_path, "rb") as f:
            client.put_object(bucket, object_name, f, length, "video/mp4")
    finally:
        os.unlink(tmp_path)

    video_path = f"{bucket}/{object_name}"
    task_id = await _service.create_task(product_model, process_name, video_path, db)
    return TaskCreateResponse(task_id=task_id, status="queued")


@router.get("/tasks", response_model=LearningTaskListResponse)
async def list_tasks(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    tasks, total = await _service.list_tasks(db, skip, limit)
    return LearningTaskListResponse(
        items=[LearningTaskResponse.model_validate(t) for t in tasks],
        total=total,
    )


@router.get("/task/{task_id}", response_model=LearningTaskResponse)
async def get_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    task = await _service.get_task(task_id, db)
    if not task:
        raise HTTPException(404, "任务不存在")
    return LearningTaskResponse.model_validate(task)


@router.put("/task/{task_id}/steps")
async def update_steps(
    task_id: str,
    body: StepsUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    try:
        task = await _service.update_steps(task_id, [s.model_dump() for s in body.steps], db)
        return {"task_id": task.task_id, "step_count": len(task.steps or [])}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/task/{task_id}/confirm")
async def confirm_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    try:
        result = await _service.confirm_and_generate(task_id, db)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/task/{task_id}")
async def delete_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    try:
        await _service.delete_task(task_id, db)
        return {"message": "已删除"}
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
