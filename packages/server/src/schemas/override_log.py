from datetime import datetime

from pydantic import BaseModel, Field


class OverrideLogCreate(BaseModel):
    workorder_id: int
    step_index: int = Field(..., ge=0)
    operator_badge: str = Field(..., max_length=64)
    reason: str = ""
    video_url: str = ""


class OverrideLogResponse(BaseModel):
    id: int
    workorder_id: int
    step_index: int
    operator_badge: str
    reason: str
    video_url: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TopOperatorItem(BaseModel):
    badge: str
    count: int


class DailyCountItem(BaseModel):
    date: str
    count: int


class OverrideStatsResponse(BaseModel):
    total: int
    top_operators: list[TopOperatorItem]
    daily_counts: list[DailyCountItem]


class OverrideLogListResponse(BaseModel):
    """分页列表（与前端表格分页配套）。"""

    items: list[OverrideLogResponse]
    total: int
