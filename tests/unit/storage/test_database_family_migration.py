"""Tests for schema v14 migration (K2S family dedup columns + blocked status)."""
import sqlite3
import tempfile
from pathlib import Path

import pytest

from src.storage.database import QueueStore, _ensure_schema


@pytest.fixture
def tmp_db_path():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d) / "test.db"


def _table_info(conn: sqlite3.Connection, table: str) -> dict[str, dict]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1]: {"type": r[2], "notnull": r[3], "dflt": r[4]} for r in rows}


def _insert_raw(conn, gallery_path, host, status, **kwargs):
    """Insert a file_host_uploads row using raw SQL, bypassing add_file_host_upload signature."""
    gallery_row = conn.execute("SELECT id FROM galleries WHERE path = ?", (gallery_path,)).fetchone()
    if gallery_row is None:
        gallery_id = conn.execute(
            "INSERT INTO galleries (path, name, status, added_ts) VALUES (?, ?, ?, strftime('%s', 'now'))",
            (gallery_path, Path(gallery_path).name or "test", "ready"),
        ).lastrowid
    else:
        gallery_id = gallery_row[0]
    cursor = conn.execute(
        "INSERT INTO file_host_uploads (gallery_fk, host_name, status) VALUES (?, ?, ?)",
        (gallery_id, host, status),
    )
    return cursor.lastrowid


class TestFamilyMigration:
    def test_blocked_by_upload_id_column_exists(self, tmp_db_path):
        store = QueueStore(str(tmp_db_path))
        with sqlite3.connect(str(tmp_db_path)) as conn:
            info = _table_info(conn, "file_host_uploads")
            assert "blocked_by_upload_id" in info

    def test_dedup_only_column_exists_with_default_zero(self, tmp_db_path):
        store = QueueStore(str(tmp_db_path))
        with sqlite3.connect(str(tmp_db_path)) as conn:
            info = _table_info(conn, "file_host_uploads")
            assert "dedup_only" in info
            # Default of 0 is represented as "0" in the dflt column
            assert info["dedup_only"]["dflt"] in ("0", 0)

    def test_blocked_status_is_accepted(self, tmp_db_path):
        store = QueueStore(str(tmp_db_path))
        with sqlite3.connect(str(tmp_db_path)) as conn:
            upload_id = _insert_raw(conn, "/tmp/test_gallery", "fileboom", "blocked")
            conn.commit()
        assert upload_id is not None
        with sqlite3.connect(str(tmp_db_path)) as conn:
            row = conn.execute(
                "SELECT status FROM file_host_uploads WHERE id = ?", (upload_id,)
            ).fetchone()
            assert row[0] == "blocked"

    def test_existing_statuses_still_accepted(self, tmp_db_path):
        store = QueueStore(str(tmp_db_path))
        with sqlite3.connect(str(tmp_db_path)) as conn:
            for status in ("pending", "uploading", "completed", "failed", "cancelled"):
                upload_id = _insert_raw(
                    conn, f"/tmp/test_gallery_{status}", "rapidgator", status
                )
                conn.commit()
                assert upload_id is not None, f"status={status} was rejected"

    def test_invalid_status_rejected(self, tmp_db_path):
        store = QueueStore(str(tmp_db_path))
        with sqlite3.connect(str(tmp_db_path)) as conn:
            try:
                _insert_raw(conn, "/tmp/test_gallery_invalid", "rapidgator", "totally_not_valid")
                conn.commit()
                inserted = True
            except sqlite3.IntegrityError:
                inserted = False
        assert not inserted, "Invalid status should be rejected by CHECK constraint"

    def test_existing_rows_preserved_after_migration(self, tmp_db_path):
        # Simulate a legacy DB: seed a row, then re-open (schema init is idempotent)
        store1 = QueueStore(str(tmp_db_path))
        legacy_id = store1.add_file_host_upload(
            gallery_path="/tmp/legacy_gallery",
            host_name="rapidgator",
            status="completed",
        )
        assert legacy_id is not None
        # Re-open — schema init should be idempotent and preserve the row
        store2 = QueueStore(str(tmp_db_path))
        with sqlite3.connect(str(tmp_db_path)) as conn:
            row = conn.execute(
                "SELECT status, blocked_by_upload_id, dedup_only FROM file_host_uploads WHERE id = ?",
                (legacy_id,),
            ).fetchone()
            assert row[0] == "completed"
            assert row[1] is None  # new NULL column
            assert row[2] == 0  # new default column
