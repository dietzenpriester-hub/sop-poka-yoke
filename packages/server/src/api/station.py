"""工位管理"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import get_current_user, require_admin
from src.models.station import Station
from src.schemas.station import StationCreate, StationResponse, StationUpdate

router = APIRouter()


@router.get("/", response_model=list[StationResponse])
async def list_stations(
    line_id: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    q = select(Station)
    if line_id:
        q = q.where(Station.line_id == line_id)
    result = await db.execute(q.order_by(Station.id).offset(skip).limit(limit))
    return list(result.scalars().all())


@router.post("/", response_model=StationResponse, status_code=201)
async def create_station(
    data: StationCreate,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    station = Station(**data.model_dump())
    db.add(station)
    await db.commit()
    await db.refresh(station)
    return station


@router.get("/{station_id}/stats")
async def station_stats(
    station_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """工位关联统计：工单数、报警数。"""
    from src.models.alert import AlertEvent
    from src.models.workorder import WorkOrder

    result = await db.execute(select(Station).where(Station.id == station_id))
    station = result.scalar_one_or_none()
    if not station:
        raise HTTPException(status_code=404, detail="工位不存在")

    wo_count = await db.execute(
        select(func.count(WorkOrder.id)).where(WorkOrder.station_id == station_id)
    )
    alert_count = await db.execute(
        select(func.count(AlertEvent.id)).where(AlertEvent.station_id == station_id)
    )

    return {
        "station_id": station_id,
        "name": station.name,
        "workorder_count": wo_count.scalar_one(),
        "alert_count": alert_count.scalar_one(),
    }


@router.get("/{station_id}", response_model=StationResponse)
async def get_station(
    station_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    result = await db.execute(select(Station).where(Station.id == station_id))
    station = result.scalar_one_or_none()
    if not station:
        raise HTTPException(status_code=404, detail="工位不存在")
    return station


@router.put("/{station_id}", response_model=StationResponse)
async def update_station(
    station_id: int,
    data: StationUpdate,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    result = await db.execute(select(Station).where(Station.id == station_id))
    station = result.scalar_one_or_none()
    if not station:
        raise HTTPException(status_code=404, detail="工位不存在")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(station, field, value)
    await db.commit()
    await db.refresh(station)
    return station


@router.delete("/{station_id}")
async def delete_station(
    station_id: int,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    result = await db.execute(select(Station).where(Station.id == station_id))
    station = result.scalar_one_or_none()
    if not station:
        raise HTTPException(status_code=404, detail="工位不存在")
    await db.delete(station)
    await db.commit()
    return {"message": "工位已删除"}
