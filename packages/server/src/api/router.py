"""路由注册"""

from fastapi import APIRouter

from src.api import alert, auth, learning, replay, report, sop, workorder
from src.api.websocket_live import router as ws_router

api_router = APIRouter()

api_router.include_router(sop.router, prefix="/sop", tags=["SOP 模板"])
api_router.include_router(workorder.router, prefix="/workorder", tags=["工单"])
api_router.include_router(alert.router, prefix="/alert", tags=["报警"])
api_router.include_router(replay.router, prefix="/replay", tags=["回放"])
api_router.include_router(report.router, prefix="/report", tags=["报表"])
api_router.include_router(learning.router, prefix="/learning", tags=["SOP 学习"])
api_router.include_router(auth.router, prefix="/auth", tags=["认证"])
api_router.include_router(ws_router, tags=["WebSocket"])
