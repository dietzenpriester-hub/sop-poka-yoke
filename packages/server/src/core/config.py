"""配置管理"""

from functools import lru_cache
from typing import List

from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SOP_", env_file=".env", extra="ignore")

    APP_NAME: str = "sop-pokayoke-server"
    DATABASE_URL: str = "postgresql+asyncpg://sop_admin:changeme@localhost:5432/sop_pokayoke"
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    REDIS_URL: str = "redis://localhost:6379/0"
    MQTT_BROKER_HOST: str = "localhost"
    MQTT_BROKER_PORT: int = 1883
    MQTT_TOPIC_PREFIX: str = "sop"
    MQTT_USERNAME: str = ""
    MQTT_PASSWORD: str = ""

    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "changeme"
    MINIO_BUCKET_VIDEOS: str = "sop-videos"
    MINIO_SECURE: bool = False

    JWT_SECRET: str = "sop-pokayoke-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24
    DEV_MODE: bool = False

    # AI 分析配置
    OLLAMA_URL: str = "http://localhost:11434"
    VLM_MODEL: str = "qwen2.5vl:3b"
    VLM_TIMEOUT: float = 120.0
    YOLO_MODEL: str = "yolo11n.pt"
    YOLO_DEVICE: str = ""  # 空字符串 = 自动选择 (MPS > CPU)
    MAX_KEYFRAMES: int = 30

    def warn_default_secrets(self) -> None:
        """若仍使用开发环境占位密钥，记录警告（不修改默认值，便于本地开发）。"""
        if self.JWT_SECRET == "sop-pokayoke-secret-key-change-in-production":
            logger.warning("JWT_SECRET 仍为默认占位值，生产环境请务必修改")
        if ":changeme@" in self.DATABASE_URL:
            logger.warning("DATABASE_URL 中数据库密码仍为占位值 (changeme)，生产环境请务必修改")
        if self.MINIO_ACCESS_KEY == "minioadmin" and self.MINIO_SECRET_KEY == "changeme":
            logger.warning("MINIO_ACCESS_KEY / MINIO_SECRET_KEY 仍为默认占位值，生产环境请务必修改")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
