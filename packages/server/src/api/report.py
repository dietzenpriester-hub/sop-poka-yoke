"""统计报表"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/summary")
async def summary():
    return {"ok_rate": 0.0, "ng_count": 0}
