"""报警记录 CRUD + 统计 + 确认"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import get_current_user
from src.models.alert import AlertEvent
from src.schemas.alert import AlertCreate, AlertResponse, AlertStats

router = APIRouter()


class AlertBatchAck(BaseModel):
    alert_ids: list[int]


@router.get("/")
async def list_alerts(
    station_id: int | None = None,
    station_code: str | None = None,
    severity: str | None = None,
    alert_type: str | None = None,
    acknowledged: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    """查询报警列表，支持工位、严重度、类型、确认状态筛选。"""
    conditions = []
    if station_id is not None:
        conditions.append(AlertEvent.station_id == station_id)
    if station_code:
        conditions.append(AlertEvent.station_code == station_code)
    if severity:
        conditions.append(AlertEvent.severity == severity)
    if alert_type:
        conditions.append(AlertEvent.alert_type == alert_type)
    if acknowledged is not None:
        conditions.append(AlertEvent.acknowledged == acknowledged)
    q = select(AlertEvent)
    count_q = select(func.count(AlertEvent.id))
    if conditions:
        q = q.where(*conditions)
        count_q = count_q.where(*conditions)
    total = (await db.execute(count_q)).scalar_one()
    result = await db.execute(q.order_by(AlertEvent.id.desc()).offset(skip).limit(limit))
    return {"items": list(result.scalars().all()), "total": total}


@router.get("/unacknowledged-count")
async def unacknowledged_count(
    station_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """获取未确认报警数量。"""
    q = select(func.count(AlertEvent.id)).where(AlertEvent.acknowledged == "0")
    if station_id is not None:
        q = q.where(AlertEvent.station_id == station_id)
    result = await db.execute(q)
    return {"count": result.scalar_one()}


@router.get("/stats", response_model=AlertStats)
async def alert_stats(
    station_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """报警统计：按严重度分组计数。"""
    q = select(AlertEvent.severity, func.count(AlertEvent.id).label("count"))
    if station_id is not None:
        q = q.where(AlertEvent.station_id == station_id)
    q = q.group_by(AlertEvent.severity)
    result = await db.execute(q)
    by_severity = {row.severity: row.count for row in result}
    total = sum(by_severity.values())
    unack_q = select(func.count(AlertEvent.id)).where(AlertEvent.acknowledged == "0")
    if station_id is not None:
        unack_q = unack_q.where(AlertEvent.station_id == station_id)
    unack_result = await db.execute(unack_q)
    return AlertStats(
        total=total,
        unacknowledged=unack_result.scalar_one(),
        by_severity=by_severity,
    )


@router.post("/", response_model=AlertResponse, status_code=201)
async def create_alert(
    data: AlertCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """手动创建报警（通常由边缘端通过 MQTT 自动创建）。"""
    alert = AlertEvent(**data.model_dump())
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return alert


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """获取单条报警详情。"""
    result = await db.execute(select(AlertEvent).where(AlertEvent.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="报警不存在")
    return alert


@router.put("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """确认（处理）报警。"""
    result = await db.execute(select(AlertEvent).where(AlertEvent.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="报警不存在")
    if alert.acknowledged == "1":
        return {"message": "该报警已确认", "id": alert_id}
    alert.acknowledged = "1"
    await db.commit()
    return {"message": "已确认", "id": alert_id}


@router.put("/batch-acknowledge")
async def batch_acknowledge(
    body: AlertBatchAck,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """批量确认报警。"""
    alert_ids = body.alert_ids
    result = await db.execute(
        select(AlertEvent).where(AlertEvent.id.in_(alert_ids), AlertEvent.acknowledged == "0")
    )
    alerts = list(result.scalars().all())
    for alert in alerts:
        alert.acknowledged = "1"
    await db.commit()
    return {"message": f"已确认 {len(alerts)} 条报警", "acknowledged_ids": [a.id for a in alerts]}
