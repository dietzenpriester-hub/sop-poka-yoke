"""统计报表：生产质量数据聚合查询。"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import get_current_user
from src.models.alert import AlertEvent
from src.models.workorder import StepRecord, WorkOrder

router = APIRouter()


@router.get("/summary")
async def summary(
    days: int = Query(default=7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """总体概览：合格率、工单数、NG 数、报警数。"""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    total_q = select(func.count(WorkOrder.id)).where(WorkOrder.start_time >= since)
    total_result = await db.execute(total_q)
    total_orders = total_result.scalar_one()

    done_q = select(func.count(WorkOrder.id)).where(
        WorkOrder.start_time >= since, WorkOrder.status == "done"
    )
    done_result = await db.execute(done_q)
    done_orders = done_result.scalar_one()

    ng_q = select(func.count(StepRecord.id)).where(
        StepRecord.created_at >= since, StepRecord.result == "NG"
    )
    ng_result = await db.execute(ng_q)
    ng_count = ng_result.scalar_one()

    ok_q = select(func.count(StepRecord.id)).where(
        StepRecord.created_at >= since, StepRecord.result == "OK"
    )
    ok_result = await db.execute(ok_q)
    ok_count = ok_result.scalar_one()

    total_steps = ok_count + ng_count
    ok_rate = round(ok_count / total_steps * 100, 2) if total_steps > 0 else 0.0

    alert_q = select(func.count(AlertEvent.id)).where(AlertEvent.created_at >= since)
    alert_result = await db.execute(alert_q)
    alert_count = alert_result.scalar_one()

    return {
        "ok_rate": ok_rate,
        "total_orders": total_orders,
        "done_orders": done_orders,
        "ng_count": ng_count,
        "ok_count": ok_count,
        "alert_count": alert_count,
        "days": days,
    }


@router.get("/daily-trend")
async def daily_trend(
    days: int = Query(default=7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """日趋势：每日 OK/NG/OVERRIDE 数量。"""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    q = (
        select(
            func.date(StepRecord.created_at).label("day"),
            StepRecord.result,
            func.count(StepRecord.id).label("count"),
        )
        .where(StepRecord.created_at >= since)
        .group_by(func.date(StepRecord.created_at), StepRecord.result)
        .order_by(func.date(StepRecord.created_at))
    )
    result = await db.execute(q)

    day_data: dict[str, dict[str, int]] = {}
    for row in result:
        day_str = str(row.day)
        if day_str not in day_data:
            day_data[day_str] = {"OK": 0, "NG": 0, "SKIP": 0, "OVERRIDE": 0}
        if row.result in day_data[day_str]:
            day_data[day_str][row.result] = row.count

    dates = sorted(day_data.keys())
    return {
        "dates": dates,
        "ok": [day_data[d].get("OK", 0) for d in dates],
        "ng": [day_data[d].get("NG", 0) for d in dates],
        "skip": [day_data[d].get("SKIP", 0) for d in dates],
        "override": [day_data[d].get("OVERRIDE", 0) for d in dates],
    }


@router.get("/alert-distribution")
async def alert_distribution(
    days: int = Query(default=7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """报警分布：按报警类型分组计数。"""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    q = (
        select(AlertEvent.alert_type, func.count(AlertEvent.id).label("count"))
        .where(AlertEvent.created_at >= since)
        .group_by(AlertEvent.alert_type)
        .order_by(func.count(AlertEvent.id).desc())
    )
    result = await db.execute(q)
    items = [{"name": row.alert_type, "value": row.count} for row in result]
    return {"items": items}


@router.get("/station-comparison")
async def station_comparison(
    days: int = Query(default=7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """工位对比：各工位的报警数量。"""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    q = (
        select(
            AlertEvent.station_code.label("station"),
            func.count(AlertEvent.id).label("alert_count"),
        )
        .where(AlertEvent.created_at >= since, AlertEvent.station_code != "")
        .group_by(AlertEvent.station_code)
        .order_by(func.count(AlertEvent.id).desc())
        .limit(20)
    )
    result = await db.execute(q)
    stations = []
    alert_counts = []
    for row in result:
        stations.append(row.station)
        alert_counts.append(row.alert_count)

    return {"stations": stations, "alert_counts": alert_counts}
