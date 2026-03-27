from datetime import datetime

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    display_name: str = ""
    role: str = Field(default="operator", pattern="^(admin|supervisor|operator)$")
    badge_id: str = ""
    password: str = Field(..., min_length=4, max_length=128)


class UserUpdate(BaseModel):
    display_name: str | None = None
    role: str | None = None
    badge_id: str | None = None


class UserPasswordChange(BaseModel):
    new_password: str = Field(..., min_length=4, max_length=128)


class UserResponse(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    badge_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
