"""统计报表服务 — 封装生产质量数据聚合查询逻辑。"""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.alert import AlertEvent
from src.models.workorder import StepRecord, WorkOrder


class ReportService:

    @staticmethod
    async def get_summary(
        db: AsyncSession, *, days: int = 7
    ) -> dict[str, Any]:
        since = datetime.now(timezone.utc) - timedelta(days=days)

        total_orders = (
            await db.execute(
                select(func.count(WorkOrder.id)).where(WorkOrder.start_time >= since)
            )
        ).scalar_one()

        done_orders = (
            await db.execute(
                select(func.count(WorkOrder.id)).where(
                    WorkOrder.start_time >= since, WorkOrder.status == "done"
                )
            )
        ).scalar_one()

        ng_count = (
            await db.execute(
                select(func.count(StepRecord.id)).where(
                    StepRecord.created_at >= since, StepRecord.result == "NG"
                )
            )
        ).scalar_one()

        ok_count = (
            await db.execute(
                select(func.count(StepRecord.id)).where(
                    StepRecord.created_at >= since, StepRecord.result == "OK"
                )
            )
        ).scalar_one()

        total_steps = ok_count + ng_count
        ok_rate = round(ok_count / total_steps * 100, 2) if total_steps > 0 else 0.0

        alert_count = (
            await db.execute(
                select(func.count(AlertEvent.id)).where(
                    AlertEvent.created_at >= since
                )
            )
        ).scalar_one()

        return {
            "ok_rate": ok_rate,
            "total_orders": total_orders,
            "done_orders": done_orders,
            "ng_count": ng_count,
            "ok_count": ok_count,
            "alert_count": alert_count,
            "days": days,
        }

    @staticmethod
    async def get_daily_trend(
        db: AsyncSession, *, days: int = 7
    ) -> dict[str, Any]:
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

    @staticmethod
    async def get_alert_distribution(
        db: AsyncSession, *, days: int = 7
    ) -> dict[str, Any]:
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

    @staticmethod
    async def get_station_comparison(
        db: AsyncSession, *, days: int = 7, top_n: int = 20
    ) -> dict[str, Any]:
        since = datetime.now(timezone.utc) - timedelta(days=days)

        q = (
            select(
                AlertEvent.station_code.label("station"),
                func.count(AlertEvent.id).label("alert_count"),
            )
            .where(AlertEvent.created_at >= since, AlertEvent.station_code != "")
            .group_by(AlertEvent.station_code)
            .order_by(func.count(AlertEvent.id).desc())
            .limit(top_n)
        )
        result = await db.execute(q)
        stations: list[str] = []
        alert_counts: list[int] = []
        for row in result:
            stations.append(row.station)
            alert_counts.append(row.alert_count)

        return {"stations": stations, "alert_counts": alert_counts}
