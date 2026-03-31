"""SOP 模板服务单元测试。"""

import pytest

from src.models.sop import SOPTemplate
from src.schemas.sop import SOPCreate, SOPStepSchema
from src.services.sop_service import SOPService


_svc = SOPService()


@pytest.mark.asyncio
async def test_create_sop_template(db_session):
    data = SOPCreate(
        name="模板A",
        steps=[SOPStepSchema(name="检查", description="目视")],
    )
    t = await _svc.create(db_session, data)
    assert t.id is not None
    assert t.name == "模板A"
    assert t.is_active is True


@pytest.mark.asyncio
async def test_list_templates_active_only(db_session):
    db_session.add(
        SOPTemplate(
            name="活跃",
            steps=[{"name": "x"}],
            is_active=True,
        )
    )
    db_session.add(
        SOPTemplate(
            name="停用",
            steps=[{"name": "y"}],
            is_active=False,
        )
    )
    await db_session.commit()

    active_only = await _svc.list_templates(db_session, active_only=True)
    assert len(active_only) == 1
    assert active_only[0].name == "活跃"


@pytest.mark.asyncio
async def test_deactivate_template(db_session):
    data = SOPCreate(
        name="待停用",
        steps=[SOPStepSchema(name="s")],
    )
    t = await _svc.create(db_session, data)
    await _svc.soft_delete(db_session, t)
    await db_session.refresh(t)
    assert t.is_active is False
