"""统计报表 — 路由层仅做参数校验与响应包装，业务逻辑委托 ReportService。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import get_current_user
from src.services.report_service import ReportService

router = APIRouter()
_svc = ReportService()


@router.get("/summary")
async def summary(
    days: int = Query(default=7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    return await _svc.get_summary(db, days=days)


@router.get("/daily-trend")
async def daily_trend(
    days: int = Query(default=7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    return await _svc.get_daily_trend(db, days=days)


@router.get("/alert-distribution")
async def alert_distribution(
    days: int = Query(default=7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    return await _svc.get_alert_distribution(db, days=days)


@router.get("/station-comparison")
async def station_comparison(
    days: int = Query(default=7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    return await _svc.get_station_comparison(db, days=days)
