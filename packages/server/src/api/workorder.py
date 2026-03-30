"""工单管理 — 路由层仅做参数校验与响应包装，业务逻辑委托 WorkOrderService。"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import get_current_user, require_admin
from src.schemas.workorder import StepRecordResponse, WorkOrderCreate, WorkOrderResponse
from src.services.workorder_service import WorkOrderService

router = APIRouter()
_svc = WorkOrderService()


@router.get("/")
async def list_workorders(
    station_id: int | None = None,
    status: str | None = None,
    sn: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    items, total = await _svc.list_workorders(
        db,
        station_id=station_id,
        status=status,
        sn=sn,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=limit,
    )
    return {"items": items, "total": total}


@router.post("/", response_model=WorkOrderResponse, status_code=201)
async def start_workorder(
    data: WorkOrderCreate,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    return await _svc.create(db, data)


@router.get("/{workorder_id}", response_model=WorkOrderResponse)
async def get_workorder(
    workorder_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    wo = await _svc.get_by_id(db, workorder_id)
    if not wo:
        raise HTTPException(status_code=404, detail="工单不存在")
    return wo


@router.put("/{workorder_id}/complete")
async def complete_workorder(
    workorder_id: int,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    wo = await _svc.get_by_id(db, workorder_id)
    if not wo:
        raise HTTPException(status_code=404, detail="工单不存在")
    if wo.status == "done":
        raise HTTPException(status_code=400, detail="工单已完成")
    await _svc.complete(db, wo)
    return {"message": "工单已完成"}


@router.get("/{workorder_id}/steps", response_model=list[StepRecordResponse])
async def get_workorder_steps(
    workorder_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    wo = await _svc.get_by_id(db, workorder_id)
    if not wo:
        raise HTTPException(status_code=404, detail="工单不存在")
    return await _svc.get_step_records(db, workorder_id)


@router.delete("/{workorder_id}")
async def delete_workorder(
    workorder_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    wo = await _svc.get_by_id(db, workorder_id)
    if not wo:
        raise HTTPException(status_code=404, detail="工单不存在")
    try:
        await _svc.delete(db, wo)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"message": "工单已删除"}
