from datetime import datetime

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
    start_time: datetime
    end_time: datetime | None

    model_config = {"from_attributes": True}
