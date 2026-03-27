"""MinIO 存储服务"""

from datetime import timedelta
from functools import lru_cache

from loguru import logger
from minio import Minio
from minio.error import S3Error

from src.core.config import settings


class StorageService:

    def __init__(self) -> None:
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            settings.MINIO_ACCESS_KEY,
            settings.MINIO_SECRET_KEY,
            secure=False,
        )
        self._ensure_bucket(settings.MINIO_BUCKET_VIDEOS)

    def _ensure_bucket(self, bucket: str) -> None:
        try:
            if not self.client.bucket_exists(bucket):
                self.client.make_bucket(bucket)
                logger.info("MinIO bucket 已创建: {}", bucket)
        except S3Error as e:
            logger.warning("MinIO bucket 检查失败（服务可能未就绪）: {}", e)

    def get_presigned_url(self, bucket: str, object_name: str, expires: int = 3600) -> str:
        return self.client.presigned_get_object(bucket, object_name, expires=timedelta(seconds=expires))

    def object_exists(self, bucket: str, object_name: str) -> bool:
        try:
            self.client.stat_object(bucket, object_name)
            return True
        except S3Error:
            return False

    def get_video_url(self, object_name: str, expires: int = 3600) -> str | None:
        """获取视频文件的预签名 URL。若 object_name 为空或文件不存在返回 None。"""
        if not object_name:
            return None
        try:
            return self.get_presigned_url(settings.MINIO_BUCKET_VIDEOS, object_name, expires)
        except S3Error:
            return None


@lru_cache
def get_storage_service() -> StorageService:
    return StorageService()
