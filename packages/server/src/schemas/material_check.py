from datetime import datetime

from pydantic import BaseModel, Field


class MaterialCheckCreate(BaseModel):
    workorder_id: int
    bom_item: str = Field(..., max_length=100)
    detected_material: str = ""
    result: str = Field(..., pattern="^(OK|NG|WARN)$")
    confidence: float = Field(default=0.0, ge=0, le=1)
    snapshot_url: str = ""
    detail: str = ""


class MaterialCheckResponse(BaseModel):
    id: int
    workorder_id: int
    bom_item: str
    detected_material: str
    result: str
    confidence: float
    snapshot_url: str
    detail: str
    checked_at: datetime

    model_config = {"from_attributes": True}


class MaterialCheckStats(BaseModel):
    total: int = 0
    ok_count: int = 0
    ng_count: int = 0
    warn_count: int = 0
    pass_rate: float = 0.0


class MaterialCheckListResponse(BaseModel):
    items: list[MaterialCheckResponse]
    total: int
