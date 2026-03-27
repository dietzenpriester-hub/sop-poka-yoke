"""物料校验记录 CRUD + 统计"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import get_current_user
from src.models.material_check import MaterialCheck
from src.models.workorder import WorkOrder
from src.schemas.material_check import MaterialCheckCreate, MaterialCheckListResponse, MaterialCheckResponse, MaterialCheckStats

router = APIRouter()


def _material_check_filters(
    workorder_id: int | None,
    result: str | None,
    bom_item: str | None,
):
    q = select(MaterialCheck)
    if workorder_id is not None:
        q = q.where(MaterialCheck.workorder_id == workorder_id)
    if result:
        q = q.where(MaterialCheck.result == result)
    if bom_item:
        q = q.where(MaterialCheck.bom_item.icontains(bom_item))
    return q


@router.get("/", response_model=MaterialCheckListResponse)
async def list_material_checks(
    workorder_id: int | None = None,
    result: str | None = None,
    bom_item: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    base = _material_check_filters(workorder_id, result, bom_item)
    count_q = select(func.count()).select_from(base.subquery())
    total = int((await db.execute(count_q)).scalar_one())
    q = base.order_by(MaterialCheck.id.desc()).offset(skip).limit(limit)
    rows = await db.execute(q)
    return MaterialCheckListResponse(items=list(rows.scalars().all()), total=total)


@router.post("/", response_model=MaterialCheckResponse, status_code=201)
async def create_material_check(
    data: MaterialCheckCreate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    wo = await db.execute(select(WorkOrder.id).where(WorkOrder.id == data.workorder_id))
    if not wo.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="工单不存在")
    row = MaterialCheck(**data.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.get("/stats", response_model=MaterialCheckStats)
async def material_check_stats(
    workorder_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    total_q = select(func.count(MaterialCheck.id))
    if workorder_id is not None:
        total_q = total_q.where(MaterialCheck.workorder_id == workorder_id)
    total = (await db.execute(total_q)).scalar_one()

    grp = select(MaterialCheck.result, func.count(MaterialCheck.id).label("cnt"))
    if workorder_id is not None:
        grp = grp.where(MaterialCheck.workorder_id == workorder_id)
    grp = grp.group_by(MaterialCheck.result)
    by_result = {r.result: r.cnt for r in (await db.execute(grp)).all()}

    ok_count = by_result.get("OK", 0)
    ng_count = by_result.get("NG", 0)
    warn_count = by_result.get("WARN", 0)
    pass_rate = round((ok_count / total) * 100.0, 2) if total else 0.0

    return MaterialCheckStats(
        total=total,
        ok_count=ok_count,
        ng_count=ng_count,
        warn_count=warn_count,
        pass_rate=pass_rate,
    )


@router.get("/workorder/{workorder_id}", response_model=list[MaterialCheckResponse])
async def list_by_workorder(
    workorder_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    wo = await db.execute(select(WorkOrder.id).where(WorkOrder.id == workorder_id))
    if not wo.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="工单不存在")
    q = (
        select(MaterialCheck)
        .where(MaterialCheck.workorder_id == workorder_id)
        .order_by(MaterialCheck.id.desc())
    )
    rows = await db.execute(q)
    return list(rows.scalars().all())


@router.get("/{check_id}", response_model=MaterialCheckResponse)
async def get_material_check(
    check_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    row = await db.execute(select(MaterialCheck).where(MaterialCheck.id == check_id))
    mc = row.scalar_one_or_none()
    if not mc:
        raise HTTPException(status_code=404, detail="物料校验记录不存在")
    return mc
