"""工单服务 WorkOrderService 单元测试。"""

import pytest

from src.models.workorder import StepRecord
from src.schemas.workorder import WorkOrderCreate
from src.services.workorder_service import WorkOrderService


_svc = WorkOrderService()


@pytest.mark.asyncio
async def test_create_workorder(db_session):
    data = WorkOrderCreate(sn="SN-001", status="running")
    wo = await _svc.create(db_session, data)
    assert wo.id is not None
    assert wo.sn == "SN-001"
    assert wo.status == "running"


@pytest.mark.asyncio
async def test_create_workorder_done_sets_end_time(db_session):
    data = WorkOrderCreate(sn="SN-DONE", status="done")
    wo = await _svc.create(db_session, data)
    assert wo.status == "done"
    assert wo.end_time is not None


@pytest.mark.asyncio
async def test_list_workorders_with_pagination(db_session):
    for i in range(3):
        await _svc.create(db_session, WorkOrderCreate(sn=f"SN-P{i}", status="running"))
    items, total = await _svc.list_workorders(db_session, skip=0, limit=2)
    assert total == 3
    assert len(items) == 2


@pytest.mark.asyncio
async def test_delete_workorder_with_steps_warns(db_session):
    wo = await _svc.create(db_session, WorkOrderCreate(sn="SN-DEL", status="running"))
    db_session.add(
        StepRecord(
            workorder_id=wo.id,
            step_index=1,
            step_name="一步",
            result="OK",
        )
    )
    await db_session.commit()

    wo2 = await _svc.get_by_id(db_session, wo.id)
    assert wo2 is not None
    with pytest.raises(ValueError) as exc:
        await _svc.delete(db_session, wo2)
    assert "步骤" in str(exc.value)
