"""审计日志中间件 — 自动记录写操作"""

import re
from datetime import datetime, timezone

import jwt
from fastapi import Request, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from src.core.config import get_settings
from src.core.database import async_session_factory
from src.models.audit_log import AuditLog

_METHOD_ACTION = {
    "POST": "create",
    "PUT": "update",
    "PATCH": "update",
    "DELETE": "delete",
}

_SKIP_PATHS = {"/health", "/metrics", "/api/auth/login"}
_SKIP_PREFIXES = ("/api/export/",)

_RESOURCE_PATTERN = re.compile(r"^/api/([^/]+)")
_ID_PATTERN = re.compile(r"^/api/[^/]+/(\d+)")


def _extract_user(request: Request) -> tuple[int | None, str]:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return None, ""
    token = auth[7:]
    try:
        settings = get_settings()
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        user_id = int(payload.get("sub", 0))
        return user_id, str(user_id)
    except Exception:
        return None, ""


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        method = request.method
        path = request.url.path

        if method not in _METHOD_ACTION:
            return await call_next(request)
        if path in _SKIP_PATHS or any(path.startswith(p) for p in _SKIP_PREFIXES):
            return await call_next(request)

        response = await call_next(request)

        try:
            action = _METHOD_ACTION[method]
            resource_match = _RESOURCE_PATTERN.match(path)
            resource = resource_match.group(1) if resource_match else path
            id_match = _ID_PATTERN.match(path)
            resource_id = id_match.group(1) if id_match else None

            user_id, username = _extract_user(request)

            detail = f"{method} {path}"
            if path.endswith("/acknowledge"):
                action = "acknowledge"
            elif path.endswith("/batch-acknowledge"):
                action = "batch_acknowledge"

            ip = request.client.host if request.client else ""
            ua = request.headers.get("user-agent", "")[:256]

            log_entry = AuditLog(
                user_id=user_id,
                username=username,
                action=action,
                resource=resource,
                resource_id=resource_id,
                detail=detail,
                ip_address=ip,
                user_agent=ua,
                status_code=response.status_code,
                created_at=datetime.now(timezone.utc),
            )

            async with async_session_factory() as session:
                session.add(log_entry)
                await session.commit()
        except Exception as e:
            logger.debug("审计日志记录失败（不影响请求）: {}", e)

        return response
