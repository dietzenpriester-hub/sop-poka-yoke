"""SQLite 离线数据暂存"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from loguru import logger


class SQLiteStore:

    def __init__(self, db_path: str = "./data/edge_local.db") -> None:
        p = Path(db_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()
        logger.info("SQLite 已初始化: {}", db_path)

    def _init_tables(self) -> None:
        with self._lock:
            self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS step_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                work_order_sn TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                step_name TEXT,
                result TEXT NOT NULL,
                confidence REAL DEFAULT 0,
                snapshot_url TEXT DEFAULT '',
                video_url TEXT DEFAULT '',
                synced INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS sync_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                priority INTEGER NOT NULL,
                payload TEXT NOT NULL,
                object_path TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
            self._ensure_sync_queue_status_column()
            self._conn.commit()

    def _ensure_sync_queue_status_column(self) -> None:
        """旧库可能没有 status 列，用于区分 pending / dead_letter / retried / archived。"""
        rows = self._conn.execute("PRAGMA table_info(sync_queue)").fetchall()
        col_names = {r[1] for r in rows}
        if "status" not in col_names:
            self._conn.execute(
                "ALTER TABLE sync_queue ADD COLUMN status TEXT DEFAULT 'pending'"
            )

    def save_step_record(self, sn: str, step_index: int, step_name: str,
                         result: str, confidence: float, snapshot_url: str = "", video_url: str = "") -> int:
        with self._lock:
            cursor = self._conn.execute(
                "INSERT INTO step_records (work_order_sn, step_index, step_name, result, confidence, snapshot_url, video_url) VALUES (?,?,?,?,?,?,?)",
                (sn, step_index, step_name, result, confidence, snapshot_url, video_url),
            )
            self._conn.commit()
            return cursor.lastrowid

    def get_unsynced_records(self, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM step_records WHERE synced=0 ORDER BY id LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def mark_synced(self, record_ids: list[int]) -> None:
        if not record_ids:
            return
        placeholders = ",".join("?" * len(record_ids))
        with self._lock:
            self._conn.execute(f"UPDATE step_records SET synced=1 WHERE id IN ({placeholders})", record_ids)
            self._conn.commit()

    def list_dead_letters(self, limit: int = 100) -> list[dict]:
        """列出 sync_queue 中的记录（含死信与待重试等）。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM sync_queue ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def count_dead_letters(self) -> int:
        """统计 status=dead_letter 的死信条数。"""
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM sync_queue WHERE COALESCE(status, '') = 'dead_letter'",
            ).fetchone()
            return int(row[0]) if row else 0

    def delete_dead_letter(self, id: int) -> bool:
        """删除一条 sync_queue 记录。"""
        with self._lock:
            cur = self._conn.execute("DELETE FROM sync_queue WHERE id = ?", (id,))
            self._conn.commit()
            return cur.rowcount > 0

    def retry_dead_letters(self, ids: list[int]) -> int:
        """将指定死信/归档记录标记为待重试（status=pending），供后续重新入队到 data_sync。"""
        if not ids:
            return 0
        placeholders = ",".join("?" * len(ids))
        with self._lock:
            cur = self._conn.execute(
                f"""
                UPDATE sync_queue SET status = 'pending'
                WHERE id IN ({placeholders})
                  AND COALESCE(status, '') IN ('dead_letter', 'archived', 'retried')
                """,
                ids,
            )
            self._conn.commit()
            return int(cur.rowcount or 0)

    def get_sync_queue_rows_by_ids(self, ids: list[int]) -> list[dict]:
        """按 id 批量读取 sync_queue（供重放时解析 payload）。"""
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM sync_queue WHERE id IN ({placeholders}) ORDER BY id",
                ids,
            ).fetchall()
            return [dict(r) for r in rows]

    def mark_sync_queue_status(self, id: int, status: str) -> bool:
        """更新单条 sync_queue 的 status（如 retried / archived）。"""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE sync_queue SET status = ? WHERE id = ?",
                (status, id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def save_sync_dead_letter(
        self, priority: int, payload: dict, *, last_error: str = "", object_path: str | None = None
    ) -> int:
        """补传多次失败后的死信：写入 sync_queue，避免静默丢失。"""
        merged = dict(payload)
        merged["_dead_letter"] = True
        merged["_last_sync_error"] = last_error
        op = object_path if object_path is not None else merged.get("local_path")
        blob = json.dumps(merged, ensure_ascii=False)
        with self._lock:
            cursor = self._conn.execute(
                "INSERT INTO sync_queue (priority, payload, object_path, status) VALUES (?,?,?,?)",
                (priority, blob, op, "dead_letter"),
            )
            self._conn.commit()
            return int(cursor.lastrowid or 0)

    def close(self) -> None:
        with self._lock:
            self._conn.close()
