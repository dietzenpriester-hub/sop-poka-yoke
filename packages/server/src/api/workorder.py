"""工单管理"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.models.workorder import WorkOrder
from src.schemas.workorder import WorkOrderCreate, WorkOrderResponse

router = APIRouter()


@router.get("/", response_model=list[WorkOrderResponse])
async def list_workorders(station_id: int | None = None, db: AsyncSession = Depends(get_db)):
    q = select(WorkOrder)
    if station_id is not None:
        q = q.where(WorkOrder.station_id == station_id)
    result = await db.execute(q.order_by(WorkOrder.id.desc()).limit(200))
    return list(result.scalars().all())


@router.post("/", response_model=WorkOrderResponse)
async def start_workorder(data: WorkOrderCreate, db: AsyncSession = Depends(get_db)):
    wo = WorkOrder(**data.model_dump())
    db.add(wo)
    await db.commit()
    await db.refresh(wo)
    return wo


@router.get("/{workorder_id}", response_model=WorkOrderResponse)
async def get_workorder(workorder_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WorkOrder).where(WorkOrder.id == workorder_id))
    wo = result.scalar_one_or_none()
    if not wo:
        raise HTTPException(status_code=404, detail="工单不存在")
    return wo
