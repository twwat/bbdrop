"""Tests for K2S sibling host status message logic."""
import time
from unittest.mock import MagicMock, patch


# ── DB helper tests ──────────────────────────────────────────────────────────

def test_has_blocked_uploads_for_host_returns_false_when_empty(tmp_path):
    from src.storage.database import QueueStore
    db = QueueStore(tmp_path / "test.db")
    assert db.has_blocked_uploads_for_host("keep2share") is False


def test_has_blocked_uploads_for_host_returns_true_when_blocked_row_exists(tmp_path):
    """Insert a blocked row directly and verify the helper sees it."""
    import sqlite3
    db_path = tmp_path / "test.db"
    from src.storage.database import QueueStore, _ensure_schema
    store = QueueStore(db_path)

    with sqlite3.connect(db_path) as conn:
        _ensure_schema(conn)
        conn.execute(
            """INSERT INTO galleries (path, name, status, added_ts)
               VALUES ('x', 'x', 'ready', 0)"""
        )
        gal_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            """INSERT INTO file_host_uploads
               (gallery_fk, host_name, status, part_number)
               VALUES (?, 'fileboom', 'blocked', 0)""",
            (gal_id,),
        )

    assert store.has_blocked_uploads_for_host("fileboom") is True
    assert store.has_blocked_uploads_for_host("keep2share") is False
