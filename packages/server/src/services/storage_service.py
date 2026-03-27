"""MinIO 存储服务"""

from minio import Minio
from src.core.config import settings


class StorageService:

    def __init__(self) -> None:
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            settings.MINIO_ACCESS_KEY,
            settings.MINIO_SECRET_KEY,
            secure=False,
        )

    def get_presigned_url(self, bucket: str, object_name: str, expires: int = 3600) -> str:
        from datetime import timedelta
        return self.client.presigned_get_object(bucket, object_name, expires=timedelta(seconds=expires))
