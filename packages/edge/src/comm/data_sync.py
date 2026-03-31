"""MinIO 上传 + 离线补传队列（P0-P3 优先级）"""

from __future__ import annotations

import heapq
import io
import json
import os
import threading
import time
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from loguru import logger
from minio import Minio

if TYPE_CHECKING:
    from src.storage.sqlite_store import SQLiteStore

MAX_SEND_RETRIES = 5


class MinIOUploader:

    def __init__(
        self,
        endpoint: str = "localhost:9000",
        access_key: str | None = None,
        secret_key: str | None = None,
        bucket: str = "sop-videos",
        secure: bool = False,
    ) -> None:
        access_key = access_key if access_key is not None else os.environ.get("SOP_MINIO_ACCESS_KEY")
        secret_key = secret_key if secret_key is not None else os.environ.get("SOP_MINIO_SECRET_KEY")
        if not access_key or not secret_key:
            logger.error(
                "MinIO 凭证未配置：请设置环境变量 SOP_MINIO_ACCESS_KEY 与 SOP_MINIO_SECRET_KEY（无默认密钥）"
            )
            raise ValueError("SOP_MINIO_ACCESS_KEY and SOP_MINIO_SECRET_KEY must be set")
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
        if ".." in object_name or object_name.startswith("/"):
            raise ValueError(f"不安全的 object_name: {object_name}")
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

    def __init__(
        self,
        sender: Callable[[dict[str, Any]], None],
        *,
        dead_letter_store: SQLiteStore | None = None,
        dead_letter_jsonl: Path | None = None,
        data_dir: Path | None = None,
    ) -> None:
        self._sender = sender
        self._dead_letter_store = dead_letter_store
        self._dead_letter_jsonl = dead_letter_jsonl
        self._data_dir = data_dir or (dead_letter_jsonl.parent if dead_letter_jsonl else Path("."))
        self._queue: list[SyncTask] = []
        self._lock = threading.Lock()
        self._seq = 0
        self._stop = threading.Event()
        self._has_data = threading.Event()
        self._thread: threading.Thread | None = None

    def enqueue(self, priority: Priority, payload: dict[str, Any]) -> None:
        with self._lock:
            self._seq += 1
            heapq.heappush(self._queue, SyncTask(priority=int(priority), seq=self._seq, payload=payload))
        self._has_data.set()
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
                self._has_data.wait(timeout=2.0)
                self._has_data.clear()
                continue
            try:
                if task.priority == Priority.P3:
                    time.sleep(0.05)
                self._sender(task.payload)
            except Exception as e:
                retries = getattr(task, "_retries", 0) + 1
                if retries >= MAX_SEND_RETRIES:
                    self._persist_dead_letter(task, e)
                    continue
                task._retries = retries
                logger.warning(
                    "补传发送失败 ({}/{}），重新入队: {}",
                    retries,
                    MAX_SEND_RETRIES,
                    e,
                )
                with self._lock:
                    heapq.heappush(self._queue, task)

    def enqueue_dead_letter_retries(self, store: "SQLiteStore", ids: list[int]) -> int:
        """将死信标记为 pending 后，按记录重新入队到内存补传队列，并标记为 retried。"""
        store.retry_dead_letters(ids)
        rows = store.get_sync_queue_rows_by_ids(ids)
        n = 0
        for row in rows:
            if (row.get("status") or "") != "pending":
                continue
            try:
                payload = json.loads(row["payload"])
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning("死信 payload 解析失败 id={}: {}", row.get("id"), e)
                continue
            self.enqueue(Priority(int(row["priority"])), payload)
            store.mark_sync_queue_status(int(row["id"]), "retried")
            n += 1
        return n

    def _persist_dead_letter(self, task: SyncTask, err: Exception) -> None:
        """超过重试次数后写入 SQLite 或 JSONL，禁止静默丢弃。"""
        logger.error("补传任务超过最大重试次数，已写入死信队列: {}", err)
        if self._dead_letter_store:
            try:
                self._dead_letter_store.save_sync_dead_letter(
                    task.priority, task.payload, last_error=str(err), object_path=task.payload.get("local_path")
                )
            except Exception as ex:
                logger.critical("死信写入 SQLite 失败: {}", ex)
                try:
                    task_dict = {
                        "priority": task.priority,
                        "seq": task.seq,
                        "payload": task.payload,
                        "error": str(err),
                        "sqlite_error": str(ex),
                        "ts": time.time(),
                    }
                    fallback_path = self._data_dir / "dead_letter_fallback.log"
                    with open(fallback_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(task_dict, ensure_ascii=False) + "\n")
                except Exception as fb:
                    logger.critical("死信 fallback 日志写入失败: {}", fb)
        if self._dead_letter_jsonl:
            try:
                line = json.dumps(
                    {
                        "priority": task.priority,
                        "payload": task.payload,
                        "error": str(err),
                        "ts": time.time(),
                    },
                    ensure_ascii=False,
                )
                self._dead_letter_jsonl.parent.mkdir(parents=True, exist_ok=True)
                with open(self._dead_letter_jsonl, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception as ex:
                logger.critical("死信写入 JSONL 失败: {}", ex)
                try:
                    task_dict = {
                        "priority": task.priority,
                        "seq": task.seq,
                        "payload": task.payload,
                        "error": str(err),
                        "jsonl_error": str(ex),
                        "ts": time.time(),
                    }
                    fallback_path = self._data_dir / "dead_letter_fallback.log"
                    with open(fallback_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(task_dict, ensure_ascii=False) + "\n")
                except Exception as fb:
                    logger.critical("死信 fallback 日志写入失败: {}", fb)

    def _pop_task(self) -> SyncTask | None:
        with self._lock:
            if not self._queue:
                return None
            return heapq.heappop(self._queue)
