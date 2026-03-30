"""通知服务 — 飞书 Webhook 推送告警消息"""

import asyncio
from datetime import datetime
from typing import Optional

import httpx
from loguru import logger

_SEVERITY_COLOR = {
    "CRITICAL": "red",
    "WARN": "orange",
    "INFO": "blue",
}

_SEVERITY_CN = {
    "CRITICAL": "🔴 严重",
    "WARN": "🟡 警告",
    "INFO": "🔵 信息",
}

_webhook_url: Optional[str] = None
_enabled: bool = False
_min_severity: str = "WARN"
_SEVERITY_ORDER = ["INFO", "WARN", "CRITICAL"]


def configure(webhook_url: str, enabled: bool = True, min_severity: str = "WARN"):
    global _webhook_url, _enabled, _min_severity
    _webhook_url = webhook_url.strip() if webhook_url else None
    _enabled = enabled and bool(_webhook_url)
    _min_severity = min_severity if min_severity in _SEVERITY_ORDER else "WARN"
    logger.info("通知服务配置更新: enabled={} min_severity={}", _enabled, _min_severity)


def get_config() -> dict:
    return {
        "webhook_url": _webhook_url or "",
        "enabled": _enabled,
        "min_severity": _min_severity,
    }


def _should_notify(severity: str) -> bool:
    if not _enabled or not _webhook_url:
        return False
    try:
        return _SEVERITY_ORDER.index(severity) >= _SEVERITY_ORDER.index(_min_severity)
    except ValueError:
        return True


def _build_card(
    alert_type: str,
    severity: str,
    message: str,
    station_code: str = "",
    step_index: int = 0,
    alert_id: Optional[int] = None,
) -> dict:
    """构造飞书消息卡片"""
    severity_text = _SEVERITY_CN.get(severity, severity)
    color = _SEVERITY_COLOR.get(severity, "grey")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    fields = [
        {"is_short": True, "text": {"tag": "lark_md", "content": f"**告警类型**\n{alert_type}"}},
        {"is_short": True, "text": {"tag": "lark_md", "content": f"**严重级别**\n{severity_text}"}},
    ]
    if station_code:
        fields.append({"is_short": True, "text": {"tag": "lark_md", "content": f"**工位**\n{station_code}"}})
    if step_index:
        fields.append({"is_short": True, "text": {"tag": "lark_md", "content": f"**步骤序号**\n{step_index}"}})
    if alert_id:
        fields.append({"is_short": True, "text": {"tag": "lark_md", "content": f"**告警ID**\n#{alert_id}"}})
    fields.append({"is_short": False, "text": {"tag": "lark_md", "content": f"**时间**\n{now}"}})

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"⚠️ SOP 防呆系统告警"},
                "template": color,
            },
            "elements": [
                {"tag": "div", "fields": fields},
                {"tag": "hr"},
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**详情**: {message or '无'}"}},
            ],
        },
    }


async def send_alert_notification(
    alert_type: str,
    severity: str,
    message: str,
    station_code: str = "",
    step_index: int = 0,
    alert_id: Optional[int] = None,
) -> bool:
    if not _should_notify(severity):
        return False

    card = _build_card(alert_type, severity, message, station_code, step_index, alert_id)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(_webhook_url, json=card)
            resp.raise_for_status()
            result = resp.json()
            if result.get("code") == 0 or result.get("StatusCode") == 0:
                logger.info("飞书通知发送成功: alert_id={}", alert_id)
                return True
            logger.warning("飞书通知响应异常: {}", result)
            return False
    except Exception as e:
        logger.error("飞书通知发送失败: {}", e)
        return False


async def send_test_notification() -> dict:
    """发送测试消息验证 webhook 配置"""
    if not _webhook_url:
        return {"success": False, "error": "Webhook URL 未配置"}

    card = _build_card(
        alert_type="TEST",
        severity="INFO",
        message="这是一条测试消息，如果你看到了说明飞书通知配置正确。",
        station_code="测试工位",
    )

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(_webhook_url, json=card)
            resp.raise_for_status()
            result = resp.json()
            if result.get("code") == 0 or result.get("StatusCode") == 0:
                return {"success": True, "message": "测试消息发送成功"}
            return {"success": False, "error": f"飞书返回错误: {result}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def fire_and_forget_alert(
    alert_type: str,
    severity: str,
    message: str,
    station_code: str = "",
    step_index: int = 0,
    alert_id: Optional[int] = None,
):
    """非阻塞发送，不影响主流程"""
    if not _should_notify(severity):
        return
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(
            send_alert_notification(alert_type, severity, message, station_code, step_index, alert_id)
        )
    except RuntimeError:
        pass
