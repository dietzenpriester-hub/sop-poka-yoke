"""工单管理服务 — 封装工单生命周期与步骤记录查询逻辑。"""

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.workorder import StepRecord, WorkOrder
from src.schemas.workorder import WorkOrderCreate


class WorkOrderService:

    @staticmethod
    async def list_workorders(
        db: AsyncSession,
        *,
        station_id: int | None = None,
        status: str | None = None,
        sn: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[WorkOrder], int]:
        q = select(WorkOrder)
        conditions = []
        if station_id is not None:
            conditions.append(WorkOrder.station_id == station_id)
        if status:
            conditions.append(WorkOrder.status == status)
        if sn:
            conditions.append(WorkOrder.sn.icontains(sn))
        if start_date is not None:
            start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
            conditions.append(WorkOrder.start_time >= start_dt)
        if end_date is not None:
            end_exclusive = datetime.combine(
                end_date + timedelta(days=1), time.min, tzinfo=timezone.utc
            )
            conditions.append(WorkOrder.start_time < end_exclusive)
        if conditions:
            q = q.where(*conditions)
        count_q = select(func.count(WorkOrder.id))
        if conditions:
            count_q = count_q.where(*conditions)
        total = (await db.execute(count_q)).scalar_one()
        result = await db.execute(
            q.order_by(WorkOrder.id.desc()).offset(skip).limit(limit)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def get_by_id(db: AsyncSession, workorder_id: int) -> WorkOrder | None:
        result = await db.execute(
            select(WorkOrder).where(WorkOrder.id == workorder_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(db: AsyncSession, data: WorkOrderCreate) -> WorkOrder:
        dump = data.model_dump()
        if dump.get("status") == "done":
            dump["end_time"] = datetime.now(timezone.utc)
        wo = WorkOrder(**dump)
        db.add(wo)
        await db.commit()
        await db.refresh(wo)
        return wo

    @staticmethod
    async def complete(db: AsyncSession, wo: WorkOrder) -> None:
        wo.status = "done"
        wo.end_time = datetime.now(timezone.utc)
        await db.commit()

    @staticmethod
    async def delete(db: AsyncSession, wo: WorkOrder) -> None:
        from sqlalchemy import func as sqlfunc

        from src.models.alert import AlertEvent
        from src.models.completion_check import CompletionCheck
        from src.models.material_check import MaterialCheck
        from src.models.override_log import OverrideLog

        wo_id = wo.id
        for model, label in [
            (AlertEvent, "报警"),
            (MaterialCheck, "物料校验"),
            (CompletionCheck, "完工检验"),
            (OverrideLog, "强制放行"),
        ]:
            cnt = (await db.execute(
                select(sqlfunc.count(model.id)).where(model.workorder_id == wo_id)
            )).scalar_one()
            if cnt > 0:
                raise ValueError(
                    f"工单存在关联{label}记录（{cnt} 条），请先处理关联数据再删除"
                )
        await db.delete(wo)
        await db.commit()

    @staticmethod
    async def get_step_records(
        db: AsyncSession, workorder_id: int
    ) -> list[StepRecord]:
        result = await db.execute(
            select(StepRecord)
            .where(StepRecord.workorder_id == workorder_id)
            .order_by(StepRecord.step_index)
        )
        return list(result.scalars().all())
