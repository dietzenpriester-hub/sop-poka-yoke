from datetime import datetime

from pydantic import BaseModel, Field


class AlertCreate(BaseModel):
    workorder_id: int | None = None
    station_id: int | None = None
    step_index: int = 0
    alert_type: str = Field(..., max_length=64)
    severity: str = Field(default="WARN", pattern="^(INFO|WARN|ERROR|CRITICAL)$")
    message: str = ""
    video_url: str = ""


class AlertResponse(BaseModel):
    id: int
    workorder_id: int | None
    station_id: int | None
    station_code: str = ""
    step_index: int
    alert_type: str
    severity: str
    message: str
    video_url: str
    acknowledged: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AlertStats(BaseModel):
    total: int = 0
    unacknowledged: int = 0
    by_severity: dict[str, int] = {}
