"""MinIO 上传 + 离线补传队列（P0-P3 优先级）"""

from __future__ import annotations

import heapq
import io
import json
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any, Callable

from loguru import logger
from minio import Minio


class MinIOUploader:

    def __init__(self, endpoint: str = "localhost:9000", access_key: str = "minioadmin",
                 secret_key: str = "changeme", bucket: str = "sop-videos", secure: bool = False) -> None:
        self.client = Minio(endpoint, access_key, secret_key, secure=secure)
        self.bucket = bucket
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)
            logger.info("MinIO bucket 已创建: {}", self.bucket)

    def upload_file(self, local_path: str, object_name: str | None = None) -> str:
        p = Path(local_path)
        if not object_name:
            object_name = p.name
        content_type = "video/mp4" if p.suffix == ".mp4" else "image/jpeg"
        self.client.fput_object(self.bucket, object_name, str(p), content_type=content_type)
        url = f"{self.bucket}/{object_name}"
        logger.info("已上传: {}", url)
        return url

    def upload_bytes(self, data: bytes, object_name: str, content_type: str = "image/jpeg") -> str:
        self.client.put_object(self.bucket, object_name, io.BytesIO(data), len(data), content_type=content_type)
        return f"{self.bucket}/{object_name}"


class Priority(IntEnum):
    P0 = 0
    P1 = 1
    P2 = 2
    P3 = 3


@dataclass(order=True)
class SyncTask:
    priority: int
    seq: int
    payload: dict[str, Any] = field(compare=False)


class OfflineDataSync:

    def __init__(self, sender: Callable[[dict[str, Any]], None]) -> None:
        self._sender = sender
        self._queue: list[SyncTask] = []
        self._lock = threading.Lock()
        self._seq = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def enqueue(self, priority: Priority, payload: dict[str, Any]) -> None:
        with self._lock:
            self._seq += 1
            heapq.heappush(self._queue, SyncTask(priority=int(priority), seq=self._seq, payload=payload))
        logger.debug("入队补传任务 priority={} payload_keys={}", priority.name, list(payload))

    def start_worker(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop_worker(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            task = self._pop_task()
            if task is None:
                time.sleep(0.05)
                continue
            try:
                if task.priority == Priority.P3:
                    time.sleep(0.05)
                self._sender(task.payload)
            except Exception as e:
                logger.exception("补传发送失败，重新入队: {}", e)
                with self._lock:
                    heapq.heappush(self._queue, task)

    def _pop_task(self) -> SyncTask | None:
        with self._lock:
            if not self._queue:
                return None
            return heapq.heappop(self._queue)
