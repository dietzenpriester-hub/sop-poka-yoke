"""SQLite 离线存储单元测试"""

import json

import pytest

from src.storage.sqlite_store import SQLiteStore


@pytest.fixture
def store(tmp_path):
    """临时数据库文件，测试结束自动清理。"""
    db = tmp_path / "edge_test.db"
    s = SQLiteStore(str(db))
    yield s
    s.close()


def test_save_and_get_step_record(store: SQLiteStore):
    """保存步骤记录后可通过未同步列表查询到。"""
    rid = store.save_step_record(
        "WO001", 0, "步骤A", "OK", 0.92, snapshot_url="s.jpg", video_url="v.mp4"
    )
    assert rid > 0
    rows = store.get_unsynced_records()
    assert len(rows) == 1
    row = rows[0]
    assert row["work_order_sn"] == "WO001"
    assert row["step_index"] == 0
    assert row["step_name"] == "步骤A"
    assert row["result"] == "OK"
    assert abs(row["confidence"] - 0.92) < 1e-6
    assert row["synced"] == 0


def test_get_unsynced_records(store: SQLiteStore):
    """仅返回 synced=0 的记录，并受 limit 限制。"""
    for i in range(3):
        store.save_step_record(f"WO{i}", 0, "s", "OK", 0.9)
    rows = store.get_unsynced_records(limit=2)
    assert len(rows) == 2


def test_mark_synced(store: SQLiteStore):
    """标记已同步后不再出现在未同步列表。"""
    r1 = store.save_step_record("WOX", 0, "s", "OK", 0.9)
    r2 = store.save_step_record("WOX", 1, "s2", "OK", 0.8)
    store.mark_synced([r1])
    pending = store.get_unsynced_records()
    ids = {r["id"] for r in pending}
    assert r1 not in ids
    assert r2 in ids


def test_save_sync_dead_letter(store: SQLiteStore):
    """死信写入 sync_queue，payload 含标记字段。"""
    payload = {"local_path": "/tmp/a.jpg", "kind": "snapshot"}
    did = store.save_sync_dead_letter(2, payload, last_error="conn reset", object_path="obj/a.jpg")
    assert did > 0
    rows = store.list_dead_letters()
    assert any(r["id"] == did for r in rows)
    row = next(r for r in rows if r["id"] == did)
    data = json.loads(row["payload"])
    assert data["_dead_letter"] is True
    assert "conn reset" in data["_last_sync_error"]


def test_list_dead_letters(store: SQLiteStore):
    """列出 sync_queue 记录（含死信）。"""
    store.save_sync_dead_letter(1, {"x": 1}, last_error="e1")
    store.save_sync_dead_letter(0, {"x": 2}, last_error="e2")
    rows = store.list_dead_letters(limit=10)
    assert len(rows) >= 2


def test_count_dead_letters(store: SQLiteStore):
    """仅统计 status=dead_letter 的条数。"""
    assert store.count_dead_letters() == 0
    store.save_sync_dead_letter(1, {"a": 1}, last_error="err")
    assert store.count_dead_letters() == 1
    store.save_sync_dead_letter(1, {"b": 2}, last_error="err")
    assert store.count_dead_letters() == 2


def test_delete_dead_letter(store: SQLiteStore):
    """按 id 删除 sync_queue 记录。"""
    did = store.save_sync_dead_letter(1, {"k": "v"}, last_error="e")
    assert store.delete_dead_letter(did) is True
    assert store.delete_dead_letter(did) is False
    rows = store.get_sync_queue_rows_by_ids([did])
    assert rows == []


def test_retry_dead_letters(store: SQLiteStore):
    """将死信标记为 pending，供后续重放。"""
    d1 = store.save_sync_dead_letter(1, {"p": 1}, last_error="e")
    d2 = store.save_sync_dead_letter(1, {"p": 2}, last_error="e")
    n = store.retry_dead_letters([d1, d2, 99999])
    assert n == 2
    rows = store.get_sync_queue_rows_by_ids([d1, d2])
    for r in rows:
        assert r["status"] == "pending"
