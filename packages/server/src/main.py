"""FastAPI 应用入口"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from sqlalchemy import text
from starlette.responses import JSONResponse

from src.api.router import api_router
from src.core.config import settings
from src.core.database import engine, init_db
from src.tasks.mqtt_consumer import start_mqtt_consumer_in_thread


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    start_mqtt_consumer_in_thread()
    logger.info("SOP 服务端启动完成")
    yield
    logger.info("SOP 服务端正在关闭")


app = FastAPI(
    title="SOP 防呆系统 API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/health")
async def health():
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ok", "service": settings.APP_NAME, "database": "connected"}
