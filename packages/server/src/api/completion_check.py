"""完工确认记录 CRUD + 统计"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import get_current_user
from src.models.completion_check import CompletionCheck
from src.models.workorder import WorkOrder
from src.schemas.completion_check import (
    CompletionCheckCreate,
    CompletionCheckListResponse,
    CompletionCheckResponse,
    CompletionCheckStats,
)

router = APIRouter()


def _completion_check_filters(
    workorder_id: int | None,
    result: str | None,
):
    q = select(CompletionCheck)
    if workorder_id is not None:
        q = q.where(CompletionCheck.workorder_id == workorder_id)
    if result:
        q = q.where(CompletionCheck.result == result)
    return q


@router.get("/", response_model=CompletionCheckListResponse)
async def list_completion_checks(
    workorder_id: int | None = None,
    result: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    base = _completion_check_filters(workorder_id, result)
    count_q = select(func.count()).select_from(base.subquery())
    total = int((await db.execute(count_q)).scalar_one())
    q = base.order_by(CompletionCheck.id.desc()).offset(skip).limit(limit)
    rows = await db.execute(q)
    return CompletionCheckListResponse(items=list(rows.scalars().all()), total=total)


@router.post("/", response_model=CompletionCheckResponse, status_code=201)
async def create_completion_check(
    data: CompletionCheckCreate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    wo = await db.execute(select(WorkOrder.id).where(WorkOrder.id == data.workorder_id))
    if not wo.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="工单不存在")
    row = CompletionCheck(**data.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.get("/stats", response_model=CompletionCheckStats)
async def completion_check_stats(
    workorder_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    total_q = select(func.count(CompletionCheck.id))
    if workorder_id is not None:
        total_q = total_q.where(CompletionCheck.workorder_id == workorder_id)
    total = (await db.execute(total_q)).scalar_one()

    grp = select(CompletionCheck.result, func.count(CompletionCheck.id).label("cnt"))
    if workorder_id is not None:
        grp = grp.where(CompletionCheck.workorder_id == workorder_id)
    grp = grp.group_by(CompletionCheck.result)
    by_result = {r.result: r.cnt for r in (await db.execute(grp)).all()}

    pass_count = by_result.get("PASS", 0)
    fail_count = by_result.get("FAIL", 0)
    rework_count = by_result.get("REWORK", 0)
    pass_rate = round((pass_count / total) * 100.0, 2) if total else 0.0

    return CompletionCheckStats(
        total=total,
        pass_count=pass_count,
        fail_count=fail_count,
        rework_count=rework_count,
        pass_rate=pass_rate,
    )


@router.get("/workorder/{workorder_id}", response_model=list[CompletionCheckResponse])
async def list_by_workorder(
    workorder_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    wo = await db.execute(select(WorkOrder.id).where(WorkOrder.id == workorder_id))
    if not wo.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="工单不存在")
    q = (
        select(CompletionCheck)
        .where(CompletionCheck.workorder_id == workorder_id)
        .order_by(CompletionCheck.id.desc())
    )
    rows = await db.execute(q)
    return list(rows.scalars().all())


@router.get("/{check_id}", response_model=CompletionCheckResponse)
async def get_completion_check(
    check_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    row = await db.execute(select(CompletionCheck).where(CompletionCheck.id == check_id))
    cc = row.scalar_one_or_none()
    if not cc:
        raise HTTPException(status_code=404, detail="完工确认记录不存在")
    return cc
