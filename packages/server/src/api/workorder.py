"""工单管理 — 路由层仅做参数校验与响应包装，业务逻辑委托 WorkOrderService。"""

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db
from src.core.security import get_current_user, require_admin
from src.models.station import Station
from src.models.workorder import WorkOrder
from src.schemas.workorder import StepRecordResponse, WorkOrderCreate, WorkOrderResponse
from src.services.workorder_service import WorkOrderService

router = APIRouter()
_svc = WorkOrderService()


async def _publish_start_workorder(db: AsyncSession, wo: WorkOrder) -> str | None:
    """向工单绑定工位的边缘端下发启动指令。"""
    if not wo.station_id:
        return None

    from src.tasks.mqtt_consumer import _mqtt_client

    result = await db.execute(select(Station).where(Station.id == wo.station_id))
    station = result.scalar_one_or_none()
    edge_id = station.edge_device_id if station and station.edge_device_id else str(wo.station_id)

    if not _mqtt_client:
        logger.warning("MQTT 客户端未就绪，无法下发 start_workorder: sn={}", wo.sn)
        return edge_id

    topic = f"{settings.MQTT_TOPIC_PREFIX}/{edge_id}/command"
    payload = json.dumps({
        "command": "start_workorder",
        "work_order_sn": wo.sn,
        "sop_template_id": wo.sop_template_id,
    })
    _mqtt_client.publish(topic, payload)
    logger.info("已向边缘端 {} 发送 start_workorder: sn={}, template_id={}", edge_id, wo.sn, wo.sop_template_id)
    return edge_id


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
    wo = await _svc.create(db, data)

    # 创建工单后向边缘端发送 start_workorder 指令
    if data.station_id:
        try:
            await _publish_start_workorder(db, wo)
        except Exception as e:
            logger.warning("发送 start_workorder 指令失败: {}", e)

    return wo


@router.post("/{workorder_id}/start")
async def start_existing_workorder(
    workorder_id: int,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """将已有运行中工单下发到绑定工位的边缘端。"""
    wo = await _svc.get_by_id(db, workorder_id)
    if not wo:
        raise HTTPException(status_code=404, detail="工单不存在")
    if wo.status != "running":
        raise HTTPException(status_code=400, detail="只能启动运行中的工单")
    if not wo.station_id:
        raise HTTPException(status_code=400, detail="工单未绑定工位")

    try:
        edge_id = await _publish_start_workorder(db, wo)
    except Exception as e:
        logger.warning("下发已有工单失败: {}", e)
        raise HTTPException(status_code=500, detail="下发工单到边缘端失败") from e

    return {"message": "工单已下发", "edge_device_id": edge_id}


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
