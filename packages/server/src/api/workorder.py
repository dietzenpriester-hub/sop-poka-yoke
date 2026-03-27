"""工单管理"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import get_current_user, require_admin
from src.models.workorder import StepRecord, WorkOrder
from src.schemas.workorder import StepRecordResponse, WorkOrderCreate, WorkOrderResponse

router = APIRouter()


@router.get("/", response_model=list[WorkOrderResponse])
async def list_workorders(
    station_id: int | None = None,
    status: str | None = None,
    sn: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    q = select(WorkOrder)
    if station_id is not None:
        q = q.where(WorkOrder.station_id == station_id)
    if status:
        q = q.where(WorkOrder.status == status)
    if sn:
        q = q.where(WorkOrder.sn.icontains(sn))
    if start_date:
        q = q.where(WorkOrder.start_time >= start_date)
    if end_date:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        q = q.where(WorkOrder.start_time < end_dt)
    result = await db.execute(q.order_by(WorkOrder.id.desc()).offset(skip).limit(limit))
    return list(result.scalars().all())


@router.post("/", response_model=WorkOrderResponse, status_code=201)
async def start_workorder(
    data: WorkOrderCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    wo = WorkOrder(**data.model_dump())
    db.add(wo)
    await db.commit()
    await db.refresh(wo)
    return wo


@router.get("/{workorder_id}", response_model=WorkOrderResponse)
async def get_workorder(
    workorder_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    result = await db.execute(select(WorkOrder).where(WorkOrder.id == workorder_id))
    wo = result.scalar_one_or_none()
    if not wo:
        raise HTTPException(status_code=404, detail="工单不存在")
    return wo


@router.put("/{workorder_id}/complete")
async def complete_workorder(
    workorder_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    result = await db.execute(select(WorkOrder).where(WorkOrder.id == workorder_id))
    wo = result.scalar_one_or_none()
    if not wo:
        raise HTTPException(status_code=404, detail="工单不存在")
    if wo.status == "done":
        raise HTTPException(status_code=400, detail="工单已完成")
    wo.status = "done"
    wo.end_time = datetime.now(timezone.utc)
    await db.commit()
    return {"message": "工单已完成"}


@router.get("/{workorder_id}/steps", response_model=list[StepRecordResponse])
async def get_workorder_steps(
    workorder_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    wo_check = await db.execute(select(WorkOrder.id).where(WorkOrder.id == workorder_id))
    if not wo_check.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="工单不存在")
    result = await db.execute(
        select(StepRecord)
        .where(StepRecord.workorder_id == workorder_id)
        .order_by(StepRecord.step_index)
    )
    return list(result.scalars().all())


@router.delete("/{workorder_id}")
async def delete_workorder(
    workorder_id: int,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    result = await db.execute(select(WorkOrder).where(WorkOrder.id == workorder_id))
    wo = result.scalar_one_or_none()
    if not wo:
        raise HTTPException(status_code=404, detail="工单不存在")
    await db.delete(wo)
    await db.commit()
    return {"message": "工单已删除"}
