"""MinIO 存储服务"""

import re
from datetime import timedelta
from functools import lru_cache

from loguru import logger
from minio import Minio
from minio.error import S3Error

from src.core.config import settings

# 与 S3 桶名规则大致一致；首段含点号时视为对象键（如 xxx.mp4/...），不当作桶名。
_BUCKET_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")


def bucket_like_segment(segment: str) -> bool:
    if not segment or len(segment) < 3 or len(segment) > 63:
        return False
    if "." in segment:
        return False
    return bool(_BUCKET_NAME_RE.match(segment))


def resolve_minio_bucket_and_object(stored_path: str, default_bucket: str) -> tuple[str, str]:
    """若路径为 bucket/object/... 且首段像桶名，则解析桶与对象键；否则使用默认桶。"""
    if "/" not in stored_path:
        return default_bucket, stored_path
    first, rest = stored_path.split("/", 1)
    if rest and bucket_like_segment(first):
        return first, rest
    return default_bucket, stored_path


class StorageService:

    def __init__(self) -> None:
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            settings.MINIO_ACCESS_KEY,
            settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
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
        bucket, key = resolve_minio_bucket_and_object(object_name, settings.MINIO_BUCKET_VIDEOS)
        try:
            return self.get_presigned_url(bucket, key, expires)
        except S3Error:
            return None


@lru_cache
def get_storage_service() -> StorageService:
    return StorageService()
