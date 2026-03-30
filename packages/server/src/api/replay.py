"""视频回放：查询步骤/报警关联的视频片段，生成 MinIO 预签名 URL。"""

import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import get_current_user
from src.models.alert import AlertEvent
from src.models.workorder import StepRecord, WorkOrder
from src.services.storage_service import get_storage_service

router = APIRouter()

_CLIP_ALLOWED_PREFIXES = ("sop-videos/", "sop-learning/")
_CLIP_SAFE_RELATIVE = re.compile(r"^[a-zA-Z0-9_.\-/]+$")


def _validate_clip_object_name(object_name: str) -> None:
    """限制预签名 URL 仅能访问允许的 object key，防止路径遍历。"""
    if not object_name or not object_name.strip():
        raise HTTPException(status_code=400, detail="object_name 不能为空")
    name = object_name.strip()
    if ".." in name:
        raise HTTPException(status_code=400, detail="非法路径")
    if name.startswith(("/", "\\")):
        raise HTTPException(status_code=400, detail="不允许绝对路径")
    if len(name) > 1 and name[1] == ":":
        raise HTTPException(status_code=400, detail="不允许绝对路径")
    if any(name.startswith(p) for p in _CLIP_ALLOWED_PREFIXES):
        return
    if _CLIP_SAFE_RELATIVE.fullmatch(name):
        return
    raise HTTPException(status_code=400, detail="object_name 格式不允许")


@router.get("/clips")
async def list_clips(
    sn: str | None = None,
    station_code: str | None = None,
    event_type: str = Query(default="step", description="step 或 alert", pattern="^(step|alert)$"),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    """查询视频片段列表。合并步骤视频和报警视频。"""
    clips: list[dict] = []
    storage = get_storage_service()

    if event_type != "alert":
        q = (
            select(StepRecord, WorkOrder.sn)
            .join(WorkOrder, StepRecord.workorder_id == WorkOrder.id)
            .where(StepRecord.video_url != "", StepRecord.video_url.isnot(None))
        )
        if sn:
            q = q.where(WorkOrder.sn.ilike(f"%{sn}%"))
        if date_from:
            q = q.where(StepRecord.created_at >= date_from)
        if date_to:
            q = q.where(StepRecord.created_at <= date_to)
        q = q.order_by(StepRecord.created_at.desc())
        result = await db.execute(q.offset(skip).limit(limit))
        for record, wo_sn in result:
            url = storage.get_video_url(record.video_url)
            snapshot = storage.get_video_url(record.snapshot_url) if record.snapshot_url else None
            clips.append({
                "id": f"step-{record.id}",
                "type": "step",
                "sn": wo_sn,
                "step_index": record.step_index,
                "step_name": record.step_name,
                "result": record.result,
                "video_url": url,
                "snapshot_url": snapshot,
                "created_at": record.created_at.isoformat() if record.created_at else None,
            })

    if event_type != "step":
        aq = select(AlertEvent).where(
            AlertEvent.video_url != "", AlertEvent.video_url.isnot(None)
        )
        if station_code:
            aq = aq.where(AlertEvent.station_code == station_code)
        if date_from:
            aq = aq.where(AlertEvent.created_at >= date_from)
        if date_to:
            aq = aq.where(AlertEvent.created_at <= date_to)
        aq = aq.order_by(AlertEvent.created_at.desc())
        alert_result = await db.execute(aq.offset(skip).limit(limit))
        for alert in alert_result.scalars():
            url = storage.get_video_url(alert.video_url)
            clips.append({
                "id": f"alert-{alert.id}",
                "type": "alert",
                "sn": "",
                "station_code": alert.station_code,
                "alert_type": alert.alert_type,
                "severity": alert.severity,
                "message": alert.message,
                "video_url": url,
                "snapshot_url": None,
                "created_at": alert.created_at.isoformat() if alert.created_at else None,
            })

    clips.sort(key=lambda c: c.get("created_at") or "", reverse=True)
    return {"items": clips}


@router.get("/clip-url")
async def get_clip_url(
    object_name: str,
    _: dict = Depends(get_current_user),
):
    """获取单个视频的预签名播放 URL。"""
    _validate_clip_object_name(object_name)
    storage = get_storage_service()
    url = storage.get_video_url(object_name)
    if not url:
        raise HTTPException(status_code=404, detail="视频文件不存在")
    return {"url": url}
