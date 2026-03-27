"""视频回放"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/clips")
async def list_clips():
    return {"items": []}
