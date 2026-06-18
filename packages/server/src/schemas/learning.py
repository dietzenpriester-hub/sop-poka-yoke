from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator


class LearningStepItem(BaseModel):
    index: int
    name: str
    description: str = ""
    required_objects: list[str] = []
    action_type: str = ""
    timeout_seconds: int = 30
    is_optional: bool = False
    reference_frame_url: str = ""
    reference_frame_b64: str = ""
    reference_frame_timestamp: float = 0.0
    ok_criteria: str = ""
    ng_criteria: str = ""
    start_sec: float = 0.0
    end_sec: float = 0.0
    segment_ids: list[int] = []
    review_status: str = "pending"
    evidence_status: str = ""
    confirmation_note: str = ""
    human_reviewed: bool = False
    reviewed_at: str = ""
    grounding_supported: bool | None = None
    grounding_confidence: float | None = None
    grounding_issue: str = ""
    source_confidence: float | None = None

    model_config = {"extra": "allow"}


class LearningTaskResponse(BaseModel):
    id: int
    task_id: str
    product_model: str
    process_name: str
    video_path: str
    status: str
    progress: float
    steps: list[dict[str, Any]]
    analysis_detail: dict[str, Any]
    error_message: str
    template_id: int | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}

    @field_validator("steps", mode="before")
    @classmethod
    def _steps_none(cls, v: Any) -> Any:
        return v if v is not None else []

    @field_validator("analysis_detail", mode="before")
    @classmethod
    def _detail_none(cls, v: Any) -> Any:
        return v if v is not None else {}

    @field_validator("error_message", mode="before")
    @classmethod
    def _err_none(cls, v: Any) -> Any:
        return v if v is not None else ""

    @field_validator("video_path", mode="before")
    @classmethod
    def _path_none(cls, v: Any) -> Any:
        return v if v is not None else ""

    @field_validator("progress", mode="before")
    @classmethod
    def _progress_none(cls, v: Any) -> Any:
        return 0.0 if v is None else v


class LearningTaskListResponse(BaseModel):
    items: list[LearningTaskResponse]
    total: int


class StepsUpdateRequest(BaseModel):
    steps: list[LearningStepItem]


class TaskCreateResponse(BaseModel):
    task_id: str
    status: str
