"""数据生命周期管理 — 差异化视频存储清理"""

from datetime import datetime, timedelta, timezone

from loguru import logger
from minio import Minio
from minio.error import S3Error
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.services.storage_service import resolve_minio_bucket_and_object
from src.core.database import async_session_factory
from src.models.alert import AlertEvent
from src.models.cleanup_log import CleanupLog
from src.models.completion_check import CompletionCheck
from src.models.material_check import MaterialCheck
from src.models.override_log import OverrideLog
from src.models.workorder import StepRecord

# Default retention policies (days)
RETENTION_POLICIES = {
    "step_ok": 30,  # OK screenshots
    "step_ng": 180,  # NG video clips
    "step_skip": 7,  # SKIP warning video
    "alert": 180,  # Alert event videos
    "material_check": 90,  # Material check snapshots
    "completion_check": 90,  # Completion check photos
    "override_log": 365,  # Override audit videos
}


def _get_minio_client() -> Minio:
    return Minio(
        settings.MINIO_ENDPOINT,
        settings.MINIO_ACCESS_KEY,
        settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )


def _delete_minio_object(client: Minio, url: str) -> None:
    """Safely delete a MinIO object by its stored URL/path."""
    if not url:
        return
    object_name = url
    if url.startswith("http"):
        parts = url.split("/", 4)
        if len(parts) >= 5:
            object_name = parts[4].split("?")[0]
        else:
            return
    bucket, key = resolve_minio_bucket_and_object(object_name, settings.MINIO_BUCKET_VIDEOS)
    try:
        client.remove_object(bucket, key)
    except S3Error:
        logger.debug("MinIO 对象删除失败（可能已不存在）: {}", object_name)


async def run_cleanup(db: AsyncSession, dry_run: bool = False) -> dict:
    """Execute full lifecycle cleanup. Returns summary stats."""
    log = CleanupLog(cleanup_type="full", status="running")
    db.add(log)
    await db.commit()
    await db.refresh(log)
    log_id = log.id

    total_records = 0
    total_objects = 0
    minio_client = _get_minio_client()
    now = datetime.now(timezone.utc)

    try:
        # 1. Clean StepRecord - OK results (snapshots only, 30 days)
        cutoff_ok = now - timedelta(days=RETENTION_POLICIES["step_ok"])
        ok_result = await db.execute(
            select(StepRecord).where(
                StepRecord.result == "OK",
                StepRecord.created_at < cutoff_ok,
                StepRecord.snapshot_url != "",
            )
        )
        ok_records = ok_result.scalars().all()
        for r in ok_records:
            n = 1 if r.snapshot_url else 0
            total_objects += n
            if not dry_run:
                _delete_minio_object(minio_client, r.snapshot_url)
                r.snapshot_url = ""
        total_records += len(ok_records)

        # 2. Clean StepRecord - NG results (videos, 180 days)
        cutoff_ng = now - timedelta(days=RETENTION_POLICIES["step_ng"])
        ng_result = await db.execute(
            select(StepRecord).where(
                StepRecord.result == "NG",
                StepRecord.created_at < cutoff_ng,
                StepRecord.video_url != "",
            )
        )
        ng_records = ng_result.scalars().all()
        for r in ng_records:
            n = (1 if r.video_url else 0) + (1 if r.snapshot_url else 0)
            total_objects += n
            if not dry_run:
                _delete_minio_object(minio_client, r.video_url)
                _delete_minio_object(minio_client, r.snapshot_url)
                r.video_url = ""
                r.snapshot_url = ""
        total_records += len(ng_records)

        # 3. Clean StepRecord - SKIP results (videos, 7 days)
        cutoff_skip = now - timedelta(days=RETENTION_POLICIES["step_skip"])
        skip_result = await db.execute(
            select(StepRecord).where(
                StepRecord.result == "SKIP",
                StepRecord.created_at < cutoff_skip,
                StepRecord.video_url != "",
            )
        )
        skip_records = skip_result.scalars().all()
        for r in skip_records:
            total_objects += 1 if r.video_url else 0
            if not dry_run:
                _delete_minio_object(minio_client, r.video_url)
                r.video_url = ""
        total_records += len(skip_records)

        # 4. Clean AlertEvent videos (180 days)
        cutoff_alert = now - timedelta(days=RETENTION_POLICIES["alert"])
        alert_result = await db.execute(
            select(AlertEvent).where(
                AlertEvent.created_at < cutoff_alert,
                AlertEvent.video_url != "",
            )
        )
        alert_records = alert_result.scalars().all()
        for r in alert_records:
            total_objects += 1 if r.video_url else 0
            if not dry_run:
                _delete_minio_object(minio_client, r.video_url)
                r.video_url = ""
        total_records += len(alert_records)

        # 5. Clean MaterialCheck snapshots (90 days)
        cutoff_mc = now - timedelta(days=RETENTION_POLICIES["material_check"])
        mc_result = await db.execute(
            select(MaterialCheck).where(
                MaterialCheck.checked_at < cutoff_mc,
                MaterialCheck.snapshot_url != "",
            )
        )
        mc_records = mc_result.scalars().all()
        for r in mc_records:
            total_objects += 1 if r.snapshot_url else 0
            if not dry_run:
                _delete_minio_object(minio_client, r.snapshot_url)
                r.snapshot_url = ""
        total_records += len(mc_records)

        # 6. Clean CompletionCheck photos (90 days)
        cutoff_cc = now - timedelta(days=RETENTION_POLICIES["completion_check"])
        cc_result = await db.execute(
            select(CompletionCheck).where(
                CompletionCheck.checked_at < cutoff_cc,
                CompletionCheck.completion_photo_url != "",
            )
        )
        cc_records = cc_result.scalars().all()
        for r in cc_records:
            n = (1 if r.completion_photo_url else 0) + (1 if r.reference_photo_url else 0)
            total_objects += n
            if not dry_run:
                _delete_minio_object(minio_client, r.completion_photo_url)
                _delete_minio_object(minio_client, r.reference_photo_url)
                r.completion_photo_url = ""
                r.reference_photo_url = ""
        total_records += len(cc_records)

        # 7. Clean OverrideLog videos (365 days)
        cutoff_ol = now - timedelta(days=RETENTION_POLICIES["override_log"])
        ol_result = await db.execute(
            select(OverrideLog).where(
                OverrideLog.created_at < cutoff_ol,
                OverrideLog.video_url != "",
            )
        )
        ol_records = ol_result.scalars().all()
        for r in ol_records:
            total_objects += 1 if r.video_url else 0
            if not dry_run:
                _delete_minio_object(minio_client, r.video_url)
                r.video_url = ""
        total_records += len(ol_records)

        if not dry_run:
            await db.commit()

        log.records_cleaned = total_records
        log.objects_deleted = total_objects
        log.status = "completed"
        log.completed_at = datetime.now(timezone.utc)
        await db.commit()

        logger.info("数据清理完成: {} 条记录, {} 个对象", total_records, total_objects)
        return {
            "log_id": log_id,
            "records_cleaned": total_records,
            "objects_deleted": total_objects,
            "status": "completed",
        }

    except Exception as e:
        await db.rollback()
        async with async_session_factory() as session:
            await session.execute(
                update(CleanupLog)
                .where(CleanupLog.id == log_id)
                .values(
                    status="failed",
                    error_message=str(e)[:500],
                    completed_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
        logger.exception("数据清理失败: {}", e)
        raise


async def get_expired_counts(db: AsyncSession) -> dict[str, int]:
    """Get counts of expired records for each category."""
    now = datetime.now(timezone.utc)
    counts: dict[str, int] = {}

    cutoff_ok = now - timedelta(days=RETENTION_POLICIES["step_ok"])
    r = await db.execute(
        select(func.count(StepRecord.id)).where(
            StepRecord.result == "OK",
            StepRecord.created_at < cutoff_ok,
            StepRecord.snapshot_url != "",
        )
    )
    counts["step_ok"] = r.scalar_one()

    cutoff_ng = now - timedelta(days=RETENTION_POLICIES["step_ng"])
    r = await db.execute(
        select(func.count(StepRecord.id)).where(
            StepRecord.result == "NG",
            StepRecord.created_at < cutoff_ng,
            StepRecord.video_url != "",
        )
    )
    counts["step_ng"] = r.scalar_one()

    cutoff_skip = now - timedelta(days=RETENTION_POLICIES["step_skip"])
    r = await db.execute(
        select(func.count(StepRecord.id)).where(
            StepRecord.result == "SKIP",
            StepRecord.created_at < cutoff_skip,
            StepRecord.video_url != "",
        )
    )
    counts["step_skip"] = r.scalar_one()

    cutoff_alert = now - timedelta(days=RETENTION_POLICIES["alert"])
    r = await db.execute(
        select(func.count(AlertEvent.id)).where(
            AlertEvent.created_at < cutoff_alert,
            AlertEvent.video_url != "",
        )
    )
    counts["alert"] = r.scalar_one()

    cutoff_mc = now - timedelta(days=RETENTION_POLICIES["material_check"])
    r = await db.execute(
        select(func.count(MaterialCheck.id)).where(
            MaterialCheck.checked_at < cutoff_mc,
            MaterialCheck.snapshot_url != "",
        )
    )
    counts["material_check"] = r.scalar_one()

    cutoff_cc = now - timedelta(days=RETENTION_POLICIES["completion_check"])
    r = await db.execute(
        select(func.count(CompletionCheck.id)).where(
            CompletionCheck.checked_at < cutoff_cc,
            CompletionCheck.completion_photo_url != "",
        )
    )
    counts["completion_check"] = r.scalar_one()

    cutoff_ol = now - timedelta(days=RETENTION_POLICIES["override_log"])
    r = await db.execute(
        select(func.count(OverrideLog.id)).where(
            OverrideLog.created_at < cutoff_ol,
            OverrideLog.video_url != "",
        )
    )
    counts["override_log"] = r.scalar_one()

    return counts


async def cleanup_expired_data() -> None:
    """供定时任务调用：使用独立会话执行完整清理。"""
    async with async_session_factory() as session:
        await run_cleanup(session, dry_run=False)
