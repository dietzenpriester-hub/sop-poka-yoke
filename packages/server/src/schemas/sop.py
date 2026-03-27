from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SOPCreate(BaseModel):
    name: str = Field(..., max_length=100)
    version: str = "1.0"
    steps: list[dict[str, Any]]
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
