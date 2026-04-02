"""边缘端内部接口 — 使用共享密钥认证，供边缘设备拉取配置。"""

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db
from src.services.sop_service import SOPService

router = APIRouter()


def _verify_edge_secret(x_edge_secret: str = Header(..., alias="X-Edge-Secret")) -> None:
    if x_edge_secret != settings.EDGE_SECRET:
        raise HTTPException(status_code=403, detail="边缘端密钥无效")


@router.get("/sop-templates")
async def get_sop_templates(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_verify_edge_secret),
):
    """返回所有激活的 SOP 模板列表，供边缘端启动时选取。"""
    templates = await SOPService.list_templates(db, active_only=True)
    return [
        {
            "id": t.id,
            "name": t.name,
            "version": t.version,
            "steps": t.steps,
            "is_active": t.is_active,
        }
        for t in templates
    ]


@router.get("/workorders/active")
async def get_active_workorder(
    station_id: str,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_verify_edge_secret),
):
    """返回当前工位进行中的工单，供边缘端轮询启动检测。"""
    from src.models.station import Station
    from src.models.workorder import WorkOrder

    # 支持三种 Station ID 匹配：edge_device_id、name、str(id)
    conditions = [Station.edge_device_id == station_id, Station.name == station_id]
    if station_id.isdigit():
        conditions.append(Station.id == int(station_id))
    st_r = await db.execute(
        select(Station).where(or_(*conditions)).limit(1),
    )
    station = st_r.scalar_one_or_none()
    if not station:
        return {"workorder": None}

    wo_r = await db.execute(
        select(WorkOrder).where(
            WorkOrder.station_id == station.id,
            WorkOrder.status == "running",
        ).order_by(WorkOrder.start_time.desc()).limit(1),
    )
    wo = wo_r.scalar_one_or_none()
    if not wo:
        return {"workorder": None}

    return {"workorder": {
        "id": wo.id,
        "sn": wo.sn,
        "status": wo.status,
        "sop_template_id": wo.sop_template_id,
    }}


@router.get("/sop-templates/{template_id}")
async def get_sop_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_verify_edge_secret),
):
    """按 ID 获取单个 SOP 模板。"""
    tpl = await SOPService.get_by_id(db, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    return {
        "id": tpl.id,
        "name": tpl.name,
        "version": tpl.version,
        "steps": tpl.steps,
        "is_active": tpl.is_active,
    }
