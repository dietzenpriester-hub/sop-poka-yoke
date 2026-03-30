"""强制放行（工牌覆盖）审计日志。"""

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import require_admin
from src.models.override_log import OverrideLog
from src.models.workorder import WorkOrder
from src.schemas.override_log import (
    OverrideLogCreate,
    OverrideLogListResponse,
    OverrideLogResponse,
    OverrideStatsResponse,
)

router = APIRouter()


def _filter_conditions(
    workorder_id: int | None,
    operator_badge: str | None,
    start_date: date | None,
    end_date: date | None,
):
    conditions = []
    if workorder_id is not None:
        conditions.append(OverrideLog.workorder_id == workorder_id)
    if operator_badge:
        conditions.append(OverrideLog.operator_badge == operator_badge)
    if start_date is not None:
        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
        conditions.append(OverrideLog.created_at >= start_dt)
    if end_date is not None:
        next_day = datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
        conditions.append(OverrideLog.created_at < next_day)
    return conditions


@router.get("/", response_model=OverrideLogListResponse)
async def list_override_logs(
    workorder_id: int | None = None,
    operator_badge: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
):
    """分页查询强制放行记录，支持工单、工牌、日期范围筛选。"""
    conds = _filter_conditions(workorder_id, operator_badge, start_date, end_date)
    base = select(OverrideLog)
    count_q = select(func.count(OverrideLog.id))
    if conds:
        base = base.where(and_(*conds))
        count_q = count_q.where(and_(*conds))
    total_result = await db.execute(count_q)
    total = int(total_result.scalar_one())
    result = await db.execute(
        base.order_by(OverrideLog.created_at.desc()).offset(skip).limit(limit)
    )
    items = list(result.scalars().all())
    return OverrideLogListResponse(items=items, total=total)


@router.post("/", response_model=OverrideLogResponse, status_code=201)
async def create_override_log(
    data: OverrideLogCreate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
):
    """创建强制放行记录（仅管理员可调用）。"""
    wo = await db.execute(select(WorkOrder.id).where(WorkOrder.id == data.workorder_id))
    if wo.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="工单不存在")
    row = OverrideLog(
        workorder_id=data.workorder_id,
        step_index=data.step_index,
        operator_badge=data.operator_badge,
        reason=data.reason or "",
        video_url=data.video_url or "",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.get("/stats", response_model=OverrideStatsResponse)
async def override_stats(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
):
    """聚合统计：总次数、高频操作员、近 30 天每日次数（敏感数据，仅管理员）。"""
    total_q = await db.execute(select(func.count(OverrideLog.id)))
    total = int(total_q.scalar_one())

    top_q = (
        select(OverrideLog.operator_badge, func.count(OverrideLog.id).label("cnt"))
        .group_by(OverrideLog.operator_badge)
        .order_by(func.count(OverrideLog.id).desc())
        .limit(10)
    )
    top_result = await db.execute(top_q)
    top_operators = [
        {"badge": row.operator_badge, "count": int(row.cnt)} for row in top_result
    ]

    today = datetime.now(timezone.utc).date()
    day_start = today - timedelta(days=29)
    since_dt = datetime.combine(day_start, datetime.min.time(), tzinfo=timezone.utc)

    daily_q = (
        select(func.date(OverrideLog.created_at).label("d"), func.count(OverrideLog.id).label("cnt"))
        .where(OverrideLog.created_at >= since_dt)
        .group_by(func.date(OverrideLog.created_at))
    )
    daily_result = await db.execute(daily_q)
    by_day: dict[str, int] = {}
    for row in daily_result:
        raw = row.d
        if hasattr(raw, "isoformat"):
            key = raw.isoformat()[:10]
        else:
            key = str(raw)[:10]
        by_day[key] = int(row.cnt)

    daily_counts = []
    for i in range(30):
        d = day_start + timedelta(days=i)
        ds = d.isoformat()
        daily_counts.append({"date": ds, "count": by_day.get(ds, 0)})

    return OverrideStatsResponse(
        total=total,
        top_operators=top_operators,
        daily_counts=daily_counts,
    )


@router.get("/workorder/{workorder_id}", response_model=list[OverrideLogResponse])
async def list_by_workorder(
    workorder_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
):
    """某工单的全部强制放行记录。"""
    result = await db.execute(
        select(OverrideLog)
        .where(OverrideLog.workorder_id == workorder_id)
        .order_by(OverrideLog.created_at.asc())
    )
    return list(result.scalars().all())


@router.get("/{log_id}", response_model=OverrideLogResponse)
async def get_override_log(
    log_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
):
    """单条记录详情。"""
    result = await db.execute(select(OverrideLog).where(OverrideLog.id == log_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return row
