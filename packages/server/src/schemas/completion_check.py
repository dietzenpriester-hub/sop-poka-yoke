from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CompletionCheckCreate(BaseModel):
    workorder_id: int
    result: str = Field(..., pattern="^(PASS|FAIL|REWORK)$")
    check_items: list[dict[str, Any]] = []
    completion_photo_url: str = ""
    reference_photo_url: str = ""
    similarity_score: float = Field(default=0.0, ge=0, le=1)
    defects: str = ""


class CompletionCheckResponse(BaseModel):
    id: int
    workorder_id: int
    result: str
    check_items: list[dict[str, Any]] | None = None
    completion_photo_url: str
    reference_photo_url: str
    similarity_score: float
    defects: str
    checked_at: datetime

    model_config = {"from_attributes": True}


class CompletionCheckStats(BaseModel):
    total: int = 0
    pass_count: int = 0
    fail_count: int = 0
    rework_count: int = 0
    pass_rate: float = 0.0


class CompletionCheckListResponse(BaseModel):
    items: list[CompletionCheckResponse]
    total: int
