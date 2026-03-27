"""仪表盘数据"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import get_current_user
from src.models.alert import AlertEvent
from src.models.station import Station
from src.models.workorder import StepRecord, WorkOrder

router = APIRouter()


@router.get("/overview")
async def overview(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    """仪表盘总览：活跃工单、今日OK/NG、合格率、未确认报警。"""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # 活跃工单
    active_q = select(func.count(WorkOrder.id)).where(WorkOrder.status == "running")
    active_result = await db.execute(active_q)
    active_orders = active_result.scalar_one()

    # 今日 OK/NG
    ok_q = select(func.count(StepRecord.id)).where(
        StepRecord.created_at >= today_start, StepRecord.result == "OK"
    )
    ok_result = await db.execute(ok_q)
    today_ok = ok_result.scalar_one()

    ng_q = select(func.count(StepRecord.id)).where(
        StepRecord.created_at >= today_start, StepRecord.result == "NG"
    )
    ng_result = await db.execute(ng_q)
    today_ng = ng_result.scalar_one()

    total = today_ok + today_ng
    ok_rate = round(today_ok / total * 100, 1) if total > 0 else 100.0

    # 未确认报警
    unack_q = select(func.count(AlertEvent.id)).where(AlertEvent.acknowledged == "0")
    unack_result = await db.execute(unack_q)
    unacknowledged_alerts = unack_result.scalar_one()

    # 今日报警
    today_alert_q = select(func.count(AlertEvent.id)).where(AlertEvent.created_at >= today_start)
    today_alert_result = await db.execute(today_alert_q)
    today_alerts = today_alert_result.scalar_one()

    return {
        "active_orders": active_orders,
        "today_ok": today_ok,
        "today_ng": today_ng,
        "ok_rate": ok_rate,
        "unacknowledged_alerts": unacknowledged_alerts,
        "today_alerts": today_alerts,
    }


@router.get("/station-status")
async def station_status(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    """各工位状态总览（单次查询避免 N+1）。"""
    active_sub = (
        select(
            WorkOrder.station_id,
            func.count(WorkOrder.id).label("active_count"),
        )
        .where(WorkOrder.status == "running")
        .group_by(WorkOrder.station_id)
        .subquery()
    )
    q = (
        select(
            Station.id,
            Station.name,
            Station.line_id,
            func.coalesce(active_sub.c.active_count, 0).label("active_orders"),
        )
        .outerjoin(active_sub, Station.id == active_sub.c.station_id)
        .order_by(Station.id)
    )
    result = await db.execute(q)
    return [
        {
            "id": row.id,
            "name": row.name,
            "line_id": row.line_id,
            "active_orders": row.active_orders,
            "status": "busy" if row.active_orders > 0 else "idle",
        }
        for row in result
    ]


@router.get("/recent-alerts")
async def recent_alerts(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    """最近 10 条报警。"""
    q = select(AlertEvent).order_by(AlertEvent.id.desc()).limit(10)
    result = await db.execute(q)
    alerts = result.scalars().all()
    return [
        {
            "id": a.id,
            "alert_type": a.alert_type,
            "severity": a.severity,
            "message": a.message,
            "station_code": a.station_code,
            "acknowledged": a.acknowledged,
            "created_at": a.created_at.isoformat() if a.created_at else "",
        }
        for a in alerts
    ]


@router.get("/hourly-trend")
async def hourly_trend(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    """今日逐小时 OK/NG 趋势。"""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    q = (
        select(
            func.extract("hour", StepRecord.created_at).label("hour"),
            StepRecord.result,
            func.count(StepRecord.id).label("count"),
        )
        .where(StepRecord.created_at >= today_start)
        .group_by(func.extract("hour", StepRecord.created_at), StepRecord.result)
        .order_by(func.extract("hour", StepRecord.created_at))
    )
    result = await db.execute(q)

    hour_data: dict[int, dict[str, int]] = {}
    for row in result:
        h = int(row.hour)
        if h not in hour_data:
            hour_data[h] = {"OK": 0, "NG": 0}
        if row.result in ("OK", "NG"):
            hour_data[h][row.result] = row.count

    hours = list(range(24))
    return {
        "hours": [f"{h:02d}:00" for h in hours],
        "ok": [hour_data.get(h, {}).get("OK", 0) for h in hours],
        "ng": [hour_data.get(h, {}).get("NG", 0) for h in hours],
    }
