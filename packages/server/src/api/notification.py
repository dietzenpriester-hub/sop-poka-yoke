"""通知配置管理 API"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.core.security import require_admin
from src.services import notification_service

router = APIRouter()


class NotificationConfig(BaseModel):
    webhook_url: str = ""
    enabled: bool = True
    min_severity: str = "WARN"


@router.get("/config")
async def get_notification_config(_admin: dict = Depends(require_admin)):
    return notification_service.get_config()


@router.put("/config")
async def update_notification_config(
    config: NotificationConfig,
    _admin: dict = Depends(require_admin),
):
    notification_service.configure(
        webhook_url=config.webhook_url,
        enabled=config.enabled,
        min_severity=config.min_severity,
    )
    return {"message": "通知配置已更新", **notification_service.get_config()}


@router.post("/test")
async def test_notification(_admin: dict = Depends(require_admin)):
    result = await notification_service.send_test_notification()
    return result
