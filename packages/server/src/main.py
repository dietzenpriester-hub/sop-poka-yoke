"""FastAPI 应用入口"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from starlette.responses import JSONResponse

from src.api.router import api_router
from src.core.config import settings
from src.core.database import engine, init_db
from src.tasks.mqtt_consumer import start_mqtt_consumer_in_thread, stop_mqtt_consumer


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.warn_default_secrets()
    await init_db()
    start_mqtt_consumer_in_thread()
    logger.info("SOP 服务端启动完成")
    yield
    stop_mqtt_consumer()
    try:
        from src.api.learning import _service as learning_svc
        if learning_svc._pipeline is not None:
            await learning_svc._pipeline.vlm_service.close()
            logger.info("VLM 服务已关闭")
    except Exception as e:
        logger.debug("VLM 关闭时异常（可忽略）: {}", e)
    logger.info("SOP 服务端正在关闭")


app = FastAPI(
    title="SOP 防呆系统 API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    logger.warning("请求参数错误: {}", exc)
    return JSONResponse(status_code=400, content={"detail": str(exc) or "请求参数错误"})


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    logger.warning("数据库完整性错误: {}", exc.orig)
    return JSONResponse(
        status_code=409,
        content={"detail": "数据完整性冲突（关联数据或唯一约束）"},
    )


@app.get("/health")
async def health():
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ok", "service": settings.APP_NAME, "database": "connected"}
