"""配置管理"""

from functools import lru_cache
from typing import List

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

    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "changeme"
    MINIO_BUCKET_VIDEOS: str = "sop-videos"
    MINIO_SECURE: bool = False

    JWT_SECRET: str = "sop-pokayoke-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24
    DEV_MODE: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
