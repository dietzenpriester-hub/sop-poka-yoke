"""SOP 模板管理服务 — 封装模板的 CRUD 业务逻辑。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.sop import SOPTemplate
from src.schemas.sop import SOPCreate


class SOPService:

    @staticmethod
    async def list_templates(
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 50,
        active_only: bool = True,
    ) -> list[SOPTemplate]:
        q = select(SOPTemplate)
        if active_only:
            q = q.where(SOPTemplate.is_active == True)  # noqa: E712
        result = await db.execute(q.offset(skip).limit(limit))
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id(db: AsyncSession, template_id: int) -> SOPTemplate | None:
        result = await db.execute(
            select(SOPTemplate).where(SOPTemplate.id == template_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(db: AsyncSession, data: SOPCreate) -> SOPTemplate:
        template = SOPTemplate(**data.model_dump())
        db.add(template)
        await db.commit()
        await db.refresh(template)
        return template

    @staticmethod
    async def update(
        db: AsyncSession,
        template: SOPTemplate,
        data: SOPCreate,
    ) -> SOPTemplate:
        for key, value in data.model_dump().items():
            setattr(template, key, value)
        await db.commit()
        await db.refresh(template)
        return template

    @staticmethod
    async def soft_delete(db: AsyncSession, template: SOPTemplate) -> None:
        template.is_active = False
        await db.commit()
