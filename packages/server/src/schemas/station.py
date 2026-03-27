from datetime import datetime

from pydantic import BaseModel, Field


class StationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    line_id: str = ""
    edge_device_id: str = ""
    rtsp_url: str = ""
    description: str = ""


class StationUpdate(BaseModel):
    name: str | None = None
    line_id: str | None = None
    edge_device_id: str | None = None
    rtsp_url: str | None = None
    description: str | None = None


class StationResponse(BaseModel):
    id: int
    name: str
    line_id: str
    edge_device_id: str
    rtsp_url: str
    description: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
