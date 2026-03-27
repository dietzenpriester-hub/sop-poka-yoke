"""数据生命周期管理 API"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import require_admin
from src.models.alert import AlertEvent
from src.models.cleanup_log import CleanupLog
from src.models.completion_check import CompletionCheck
from src.models.material_check import MaterialCheck
from src.models.override_log import OverrideLog
from src.models.workorder import StepRecord
from src.schemas.data_lifecycle import (
    CleanupLogResponse,
    CleanupRunResponse,
    RetentionPoliciesResponse,
    RetentionPolicy,
    StorageStatsResponse,
)
from src.tasks.data_cleanup import RETENTION_POLICIES, get_expired_counts, run_cleanup

router = APIRouter()


@router.get("/policies", response_model=RetentionPoliciesResponse)
async def get_retention_policies(_: dict = Depends(require_admin)):
    """Get current retention policies."""
    descriptions = {
        "step_ok": "OK 步骤截图",
        "step_ng": "NG 异常视频片段",
        "step_skip": "SKIP 跳步视频",
        "alert": "报警事件视频",
        "material_check": "物料校验截图",
        "completion_check": "完工检验照片",
        "override_log": "强制放行审计视频",
    }
    policies = [
        RetentionPolicy(type_name=k, retention_days=v, description=descriptions.get(k, k))
        for k, v in RETENTION_POLICIES.items()
    ]
    return RetentionPoliciesResponse(policies=policies)


@router.get("/stats", response_model=StorageStatsResponse)
async def get_storage_stats(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
):
    """Get storage overview and expired record counts."""
    total_steps = (await db.execute(select(func.count(StepRecord.id)))).scalar_one()
    total_alerts = (await db.execute(select(func.count(AlertEvent.id)))).scalar_one()
    total_mc = (await db.execute(select(func.count(MaterialCheck.id)))).scalar_one()
    total_cc = (await db.execute(select(func.count(CompletionCheck.id)))).scalar_one()
    total_ol = (await db.execute(select(func.count(OverrideLog.id)))).scalar_one()

    expired = await get_expired_counts(db)

    return StorageStatsResponse(
        total_step_records=total_steps,
        total_alerts=total_alerts,
        total_material_checks=total_mc,
        total_completion_checks=total_cc,
        total_override_logs=total_ol,
        expired_counts=expired,
    )


@router.post("/run", response_model=CleanupRunResponse)
async def trigger_cleanup(
    dry_run: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
):
    """Manually trigger a cleanup run. dry_run=true for preview only."""
    result = await run_cleanup(db, dry_run=dry_run)
    return CleanupRunResponse(
        log_id=result["log_id"],
        status=result["status"],
        records_cleaned=result["records_cleaned"],
        objects_deleted=result["objects_deleted"],
        message=(
            f"清理完成：{result['records_cleaned']} 条记录, {result['objects_deleted']} 个存储对象"
            + (" (预览模式)" if dry_run else "")
        ),
    )


@router.get("/history", response_model=list[CleanupLogResponse])
async def get_cleanup_history(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
):
    """Get cleanup execution history."""
    result = await db.execute(
        select(CleanupLog).order_by(CleanupLog.id.desc()).offset(skip).limit(limit)
    )
    return list(result.scalars().all())
