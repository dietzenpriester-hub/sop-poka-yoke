"""审计日志查询 API"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import require_admin
from src.models.audit_log import AuditLog

router = APIRouter()


@router.get("/")
async def list_audit_logs(
    username: str | None = None,
    action: str | None = None,
    resource: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    conditions = []
    if username:
        conditions.append(AuditLog.username == username)
    if action:
        conditions.append(AuditLog.action == action)
    if resource:
        conditions.append(AuditLog.resource == resource)
    if start_date:
        conditions.append(AuditLog.created_at >= start_date)
    if end_date:
        conditions.append(AuditLog.created_at <= end_date)

    q = select(AuditLog)
    count_q = select(func.count(AuditLog.id))
    if conditions:
        q = q.where(*conditions)
        count_q = count_q.where(*conditions)

    total = (await db.execute(count_q)).scalar_one()
    result = await db.execute(q.order_by(AuditLog.id.desc()).offset(skip).limit(limit))
    items = result.scalars().all()
    return {
        "items": [
            {
                "id": r.id,
                "user_id": r.user_id,
                "username": r.username,
                "action": r.action,
                "resource": r.resource,
                "resource_id": r.resource_id,
                "detail": r.detail,
                "ip_address": r.ip_address,
                "status_code": r.status_code,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in items
        ],
        "total": total,
    }


@router.get("/stats")
async def audit_stats(
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    by_action = {}
    result = await db.execute(
        select(AuditLog.action, func.count(AuditLog.id).label("count"))
        .group_by(AuditLog.action)
    )
    for row in result:
        by_action[row.action] = row.count

    by_user = {}
    result2 = await db.execute(
        select(AuditLog.username, func.count(AuditLog.id).label("count"))
        .where(AuditLog.username != "")
        .group_by(AuditLog.username)
        .order_by(func.count(AuditLog.id).desc())
        .limit(10)
    )
    for row in result2:
        by_user[row.username] = row.count

    total_q = await db.execute(select(func.count(AuditLog.id)))

    return {
        "total": total_q.scalar_one(),
        "by_action": by_action,
        "by_user": by_user,
    }
