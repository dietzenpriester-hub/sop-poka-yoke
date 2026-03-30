"""数据导出 API"""

from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import require_admin
from src.services import export_service

router = APIRouter()

_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _disposition(prefix: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{ts}.xlsx"
    encoded = quote(filename)
    return f"attachment; filename*=UTF-8''{encoded}"


@router.get("/workorders")
async def export_workorders(
    station_id: int | None = Query(None),
    status: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    data = await export_service.export_workorders(
        db, station_id=station_id, status=status,
        start_date=start_date, end_date=end_date,
    )
    return StreamingResponse(
        iter([data]), media_type=_CONTENT_TYPE,
        headers={"Content-Disposition": _disposition("工单")},
    )


@router.get("/alerts")
async def export_alerts(
    station_id: int | None = Query(None),
    severity: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    data = await export_service.export_alerts(
        db, station_id=station_id, severity=severity,
        start_date=start_date, end_date=end_date,
    )
    return StreamingResponse(
        iter([data]), media_type=_CONTENT_TYPE,
        headers={"Content-Disposition": _disposition("报警记录")},
    )


@router.get("/material-checks")
async def export_material_checks(
    workorder_id: int | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    data = await export_service.export_material_checks(
        db, workorder_id=workorder_id,
        start_date=start_date, end_date=end_date,
    )
    return StreamingResponse(
        iter([data]), media_type=_CONTENT_TYPE,
        headers={"Content-Disposition": _disposition("物料校验")},
    )


@router.get("/completion-checks")
async def export_completion_checks(
    workorder_id: int | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    data = await export_service.export_completion_checks(
        db, workorder_id=workorder_id,
        start_date=start_date, end_date=end_date,
    )
    return StreamingResponse(
        iter([data]), media_type=_CONTENT_TYPE,
        headers={"Content-Disposition": _disposition("完工检查")},
    )


@router.get("/override-logs")
async def export_override_logs(
    workorder_id: int | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    data = await export_service.export_override_logs(
        db, workorder_id=workorder_id,
        start_date=start_date, end_date=end_date,
    )
    return StreamingResponse(
        iter([data]), media_type=_CONTENT_TYPE,
        headers={"Content-Disposition": _disposition("放行记录")},
    )
