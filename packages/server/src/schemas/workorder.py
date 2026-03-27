from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WorkOrderCreate(BaseModel):
    sn: str = Field(..., max_length=100)
    station_id: int | None = None
    sop_template_id: int | None = None
    status: str = "running"
    operator_id: int | None = None


class WorkOrderResponse(BaseModel):
    id: int
    sn: str
    station_id: int | None
    sop_template_id: int | None
    status: str
    operator_id: int | None
    extra: dict | None = None
    start_time: datetime
    end_time: datetime | None

    model_config = {"from_attributes": True}


class StepRecordResponse(BaseModel):
    id: int
    workorder_id: int
    step_index: int
    step_name: str
    result: str
    confidence: str
    snapshot_url: str
    video_url: str
    detail: dict[str, Any] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
