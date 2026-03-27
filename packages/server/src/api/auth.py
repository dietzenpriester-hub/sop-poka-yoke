"""用户认证/授权（占位）"""
from fastapi import APIRouter

router = APIRouter()


@router.post("/login")
async def login():
    return {"access_token": "dev-token", "token_type": "bearer"}
