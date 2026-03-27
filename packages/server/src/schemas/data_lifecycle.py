"""数据生命周期 API 模型"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RetentionPolicy(BaseModel):
    type_name: str
    retention_days: int
    description: str = ""


class RetentionPoliciesResponse(BaseModel):
    policies: list[RetentionPolicy]


class CleanupLogResponse(BaseModel):
    id: int
    cleanup_type: str
    records_cleaned: int
    objects_deleted: int
    bytes_freed: float = 0.0
    status: str
    error_message: str = ""
    started_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CleanupRunResponse(BaseModel):
    log_id: int
    status: str
    records_cleaned: int = 0
    objects_deleted: int = 0
    message: str = ""


class StorageStatsResponse(BaseModel):
    total_step_records: int
    total_alerts: int
    total_material_checks: int
    total_completion_checks: int
    total_override_logs: int
    expired_counts: dict[str, int] = Field(default_factory=dict)
