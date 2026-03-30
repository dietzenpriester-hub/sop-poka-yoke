"""路由注册"""

from fastapi import APIRouter

from src.api import alert, auth, completion_check, dashboard, data_lifecycle, export, learning, material_check, override_log, replay, report, sop, station, user, workorder
from src.api.websocket_live import router as ws_router

api_router = APIRouter()

api_router.include_router(sop.router, prefix="/sop", tags=["SOP 模板"])
api_router.include_router(workorder.router, prefix="/workorder", tags=["工单"])
api_router.include_router(material_check.router, prefix="/material-check", tags=["物料校验"])
api_router.include_router(station.router, prefix="/station", tags=["工位"])
api_router.include_router(alert.router, prefix="/alert", tags=["报警"])
api_router.include_router(replay.router, prefix="/replay", tags=["回放"])
api_router.include_router(report.router, prefix="/report", tags=["报表"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["仪表盘"])
api_router.include_router(learning.router, prefix="/learning", tags=["SOP 学习"])
api_router.include_router(auth.router, prefix="/auth", tags=["认证"])
api_router.include_router(user.router, prefix="/user", tags=["用户"])
api_router.include_router(completion_check.router, prefix="/completion-check", tags=["完工确认"])
api_router.include_router(override_log.router, prefix="/override-log", tags=["强制放行"])
api_router.include_router(data_lifecycle.router, prefix="/lifecycle", tags=["数据生命周期"])
api_router.include_router(export.router, prefix="/export", tags=["数据导出"])
api_router.include_router(ws_router, tags=["WebSocket"])
