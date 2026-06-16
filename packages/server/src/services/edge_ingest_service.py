"""边缘端数据入库服务 — 将 MQTT 上报的步骤记录/视频证据持久化到数据库。

服务端此前仅消费 `alert/raise`，导致边缘端产生的步骤记录（StepRecord）无法落库，
仪表盘/报表/回放虽接好接口却长期无数据。本服务补齐这一数据闭环：

- `ingest_step_record`：消费 `step/complete` 事件 → 写入 StepRecord；`complete` 事件同时收尾工单。
- `attach_step_video`：消费 `step/video` 事件 → 为已落库的步骤记录与报警补充视频 URL。
"""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.alert import AlertEvent
from src.models.workorder import StepRecord, WorkOrder


async def _resolve_workorder(session: AsyncSession, sn: str) -> WorkOrder | None:
    """按工单号解析工单：优先 running 状态，其次取最新一条。"""
    if not sn:
        return None
    running = await session.execute(
        select(WorkOrder)
        .where(WorkOrder.sn == sn, WorkOrder.status == "running")
        .order_by(WorkOrder.id.desc())
        .limit(1)
    )
    wo = running.scalar_one_or_none()
    if wo is not None:
        return wo
    latest = await session.execute(
        select(WorkOrder).where(WorkOrder.sn == sn).order_by(WorkOrder.id.desc()).limit(1)
    )
    return latest.scalar_one_or_none()


async def ingest_step_record(
    session: AsyncSession, station_id: str, payload: dict
) -> StepRecord | None:
    """将一条边缘步骤事件写入 StepRecord；`complete` 事件同时收尾工单。

    payload 约定字段：work_order_sn, step_index, step_name, result, confidence,
    event, video_url, snapshot_url。无法解析到工单时跳过（不伪造数据）。
    """
    sn = str(payload.get("work_order_sn") or "").strip()
    wo = await _resolve_workorder(session, sn)
    if wo is None:
        logger.warning("step/complete 未找到匹配工单，已跳过: station={} sn={}", station_id, sn)
        return None

    event = str(payload.get("event") or "")
    result = str(payload.get("result") or "").upper() or "UNKNOWN"
    try:
        step_index = int(payload.get("step_index", 0))
    except (TypeError, ValueError):
        step_index = 0
    confidence = payload.get("confidence", 0)
    try:
        confidence_str = str(round(float(confidence), 3))
    except (TypeError, ValueError):
        confidence_str = "0"

    record = StepRecord(
        workorder_id=wo.id,
        step_index=step_index,
        step_name=str(payload.get("step_name") or ""),
        result=result,
        confidence=confidence_str,
        snapshot_url=str(payload.get("snapshot_url") or ""),
        video_url=str(payload.get("video_url") or ""),
        detail={"event": event, "station_id": station_id},
    )
    session.add(record)

    if event == "complete" and wo.status != "done":
        wo.status = "done"
        wo.end_time = datetime.now(timezone.utc)

    await session.commit()
    await session.refresh(record)
    logger.info(
        "步骤记录已入库: id={} wo={} step={} result={} station={}",
        record.id, wo.id, step_index, result, station_id,
    )
    return record


async def attach_step_video(
    session: AsyncSession, station_id: str, payload: dict
) -> bool:
    """为已落库的步骤记录与报警补充视频 URL（录像异步上传 MinIO 完成后回填）。"""
    sn = str(payload.get("work_order_sn") or "").strip()
    video_url = str(payload.get("video_url") or "").strip()
    if not video_url:
        return False
    try:
        step_index = int(payload.get("step_index", 0))
    except (TypeError, ValueError):
        step_index = 0

    wo = await _resolve_workorder(session, sn)
    updated = False

    if wo is not None:
        sr = await session.execute(
            select(StepRecord)
            .where(StepRecord.workorder_id == wo.id, StepRecord.step_index == step_index)
            .order_by(StepRecord.id.desc())
            .limit(1)
        )
        record = sr.scalar_one_or_none()
        if record is not None and not record.video_url:
            record.video_url = video_url
            updated = True

    alert_q = await session.execute(
        select(AlertEvent)
        .where(
            AlertEvent.station_code == station_id,
            AlertEvent.step_index == step_index,
            (AlertEvent.video_url == "") | (AlertEvent.video_url.is_(None)),
        )
        .order_by(AlertEvent.id.desc())
        .limit(1)
    )
    alert = alert_q.scalar_one_or_none()
    if alert is not None:
        alert.video_url = video_url
        updated = True

    if updated:
        await session.commit()
        logger.info(
            "视频 URL 已回填: station={} sn={} step={} url={}",
            station_id, sn, step_index, video_url,
        )
    else:
        logger.debug("视频回填未匹配到记录: station={} sn={} step={}", station_id, sn, step_index)
    return updated
