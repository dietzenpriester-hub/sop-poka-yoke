from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SOPStepSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    required_objects: list[str] = []
    action_type: str = ""
    timeout_seconds: float = Field(default=60.0, ge=0)
    is_optional: bool = False


class SOPCreate(BaseModel):
    name: str = Field(..., max_length=100)
    version: str = "1.0"
    steps: list[SOPStepSchema]
    product_model: str | None = None
    description: str = ""


class SOPResponse(BaseModel):
    id: int
    name: str
    version: str
    steps: list[dict[str, Any]]
    product_model: str | None
    description: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
