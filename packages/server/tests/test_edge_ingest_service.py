"""边缘数据入库服务测试：step/complete 落库、complete 收尾工单、step/video 回填。"""

import pytest

from src.models.alert import AlertEvent
from src.models.workorder import StepRecord, WorkOrder
from src.schemas.workorder import WorkOrderCreate
from src.services.edge_ingest_service import (
    attach_step_video,
    ingest_step_record,
)
from src.services.workorder_service import WorkOrderService

_svc = WorkOrderService()


@pytest.mark.asyncio
async def test_ingest_step_record_writes_record(db_session):
    wo = await _svc.create(db_session, WorkOrderCreate(sn="SN-STEP", status="running"))
    rec = await ingest_step_record(
        db_session,
        "ST-01",
        {
            "work_order_sn": "SN-STEP",
            "step_index": 0,
            "step_name": "拧螺丝",
            "result": "ok",
            "confidence": 0.91,
            "event": "step_ok",
        },
    )
    assert rec is not None
    assert rec.workorder_id == wo.id
    assert rec.result == "OK"
    assert rec.step_name == "拧螺丝"
    assert rec.confidence == "0.91"
    assert rec.detail["event"] == "step_ok"


@pytest.mark.asyncio
async def test_ingest_complete_marks_workorder_done(db_session):
    wo = await _svc.create(db_session, WorkOrderCreate(sn="SN-DONE2", status="running"))
    await ingest_step_record(
        db_session,
        "ST-01",
        {
            "work_order_sn": "SN-DONE2",
            "step_index": 1,
            "result": "OK",
            "confidence": 0.95,
            "event": "complete",
        },
    )
    refreshed = await _svc.get_by_id(db_session, wo.id)
    assert refreshed.status == "done"
    assert refreshed.end_time is not None


@pytest.mark.asyncio
async def test_ingest_skips_when_no_workorder(db_session):
    rec = await ingest_step_record(
        db_session,
        "ST-01",
        {"work_order_sn": "SN-NOT-EXIST", "step_index": 0, "result": "NG", "event": "step_ng"},
    )
    assert rec is None
    total = (await db_session.execute(__import__("sqlalchemy").select(StepRecord))).scalars().all()
    assert total == []


@pytest.mark.asyncio
async def test_ingest_prefers_running_workorder(db_session):
    await _svc.create(db_session, WorkOrderCreate(sn="SN-DUP", status="done"))
    running = await _svc.create(db_session, WorkOrderCreate(sn="SN-DUP", status="running"))
    rec = await ingest_step_record(
        db_session,
        "ST-01",
        {"work_order_sn": "SN-DUP", "step_index": 0, "result": "OK", "event": "step_ok"},
    )
    assert rec.workorder_id == running.id


@pytest.mark.asyncio
async def test_attach_step_video_backfills_record_and_alert(db_session):
    wo = await _svc.create(db_session, WorkOrderCreate(sn="SN-VID", status="running"))
    sr = StepRecord(workorder_id=wo.id, step_index=2, step_name="装配", result="NG")
    alert = AlertEvent(station_code="ST-01", step_index=2, alert_type="STEP_NG", severity="ERROR")
    db_session.add_all([sr, alert])
    await db_session.commit()

    ok = await attach_step_video(
        db_session,
        "ST-01",
        {
            "work_order_sn": "SN-VID",
            "step_index": 2,
            "video_url": "sop-videos/SN-VID_step2_STEP_NG_20250101_120000.mp4",
        },
    )
    assert ok is True
    await db_session.refresh(sr)
    await db_session.refresh(alert)
    assert sr.video_url.endswith(".mp4")
    assert alert.video_url == sr.video_url


@pytest.mark.asyncio
async def test_attach_step_video_empty_url_noop(db_session):
    ok = await attach_step_video(db_session, "ST-01", {"work_order_sn": "SN-X", "step_index": 0, "video_url": ""})
    assert ok is False
