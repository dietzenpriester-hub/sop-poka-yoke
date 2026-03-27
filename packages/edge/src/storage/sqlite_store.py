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
            self._conn.commit()

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

    def close(self) -> None:
        with self._lock:
            self._conn.close()
