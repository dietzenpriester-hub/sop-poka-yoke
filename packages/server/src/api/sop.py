"""SOP 模板 CRUD — 路由层仅做参数校验与响应包装，业务逻辑委托 SOPService。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import get_current_user
from src.schemas.sop import SOPCreate, SOPResponse
from src.services.sop_service import SOPService

router = APIRouter()
_svc = SOPService()


@router.get("/", response_model=list[SOPResponse])
async def list_sop_templates(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    return await _svc.list_templates(db, skip=skip, limit=limit)


@router.post("/", response_model=SOPResponse)
async def create_sop_template(
    data: SOPCreate,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    return await _svc.create(db, data)


@router.get("/{template_id}", response_model=SOPResponse)
async def get_sop_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    template = await _svc.get_by_id(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    return template


@router.put("/{template_id}", response_model=SOPResponse)
async def update_sop_template(
    template_id: int,
    data: SOPCreate,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    template = await _svc.get_by_id(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    return await _svc.update(db, template, data)


@router.delete("/{template_id}")
async def delete_sop_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    template = await _svc.get_by_id(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    await _svc.soft_delete(db, template)
    return {"message": "已删除"}
