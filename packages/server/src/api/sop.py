"""SOP 模板 CRUD"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.models.sop import SOPTemplate
from src.schemas.sop import SOPCreate, SOPResponse

router = APIRouter()


@router.get("/", response_model=list[SOPResponse])
async def list_sop_templates(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SOPTemplate).where(SOPTemplate.is_active == True))  # noqa: E712
    return list(result.scalars().all())


@router.post("/", response_model=SOPResponse)
async def create_sop_template(data: SOPCreate, db: AsyncSession = Depends(get_db)):
    template = SOPTemplate(**data.model_dump())
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


@router.get("/{template_id}", response_model=SOPResponse)
async def get_sop_template(template_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SOPTemplate).where(SOPTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    return template


@router.put("/{template_id}", response_model=SOPResponse)
async def update_sop_template(template_id: int, data: SOPCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SOPTemplate).where(SOPTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    for key, value in data.model_dump().items():
        setattr(template, key, value)
    await db.commit()
    await db.refresh(template)
    return template


@router.delete("/{template_id}")
async def delete_sop_template(template_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SOPTemplate).where(SOPTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    template.is_active = False
    await db.commit()
    return {"message": "已删除"}
