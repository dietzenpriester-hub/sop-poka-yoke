"""报表服务 ReportService 单元测试。"""

import pytest

from src.services.report_service import ReportService


_svc = ReportService()


@pytest.mark.asyncio
async def test_get_summary_empty_db(db_session):
    summary = await _svc.get_summary(db_session, days=7)
    assert summary["total_orders"] == 0
    assert summary["done_orders"] == 0
    assert summary["ng_count"] == 0
    assert summary["ok_count"] == 0
    assert summary["alert_count"] == 0
    assert summary["ok_rate"] == 0.0
    assert summary["days"] == 7


@pytest.mark.asyncio
async def test_get_daily_trend_format(db_session):
    trend = await _svc.get_daily_trend(db_session, days=7)
    assert "dates" in trend
    assert "ok" in trend
    assert "ng" in trend
    assert "skip" in trend
    assert "override" in trend
    assert isinstance(trend["dates"], list)
    assert isinstance(trend["ok"], list)
    assert len(trend["dates"]) == len(trend["ok"])
