"""Tests for host_scan_results table schema and query methods."""

import pytest
import sqlite3
import os
import tempfile
import time

from src.storage.database import QueueStore, _connect, _ensure_schema


@pytest.fixture
def temp_db():
    """Create a temporary test database."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def store(temp_db):
    """Create a QueueStore with temporary database."""
    return QueueStore(db_path=temp_db)


class TestHostScanResultsSchema:
    """Verify host_scan_results table is created by migration."""

    def test_table_exists_after_init(self, store):
        """host_scan_results table should exist after QueueStore init."""
        conn = _connect(store.db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='host_scan_results'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_table_columns(self, store):
        """Table should have all expected columns."""
        conn = _connect(store.db_path)
        cursor = conn.execute("PRAGMA table_info(host_scan_results)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()
        expected = {
            'id', 'gallery_fk', 'host_type', 'host_id',
            'status', 'online_count', 'total_count',
            'checked_ts', 'detail_json'
        }
        assert expected.issubset(columns)

    def test_unique_constraint(self, store):
        """UNIQUE(gallery_fk, host_type, host_id) prevents duplicates."""
        conn = _connect(store.db_path)
        conn.execute(
            "INSERT INTO galleries (path, name, status, added_ts) VALUES (?, ?, ?, ?)",
            ('/test/gal1', 'gal1', 'completed', int(time.time()))
        )
        gal_id = conn.execute("SELECT id FROM galleries WHERE path = '/test/gal1'").fetchone()[0]
        conn.execute(
            "INSERT INTO host_scan_results (gallery_fk, host_type, host_id, status, online_count, total_count, checked_ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (gal_id, 'image', 'turbo', 'online', 10, 10, int(time.time()))
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO host_scan_results (gallery_fk, host_type, host_id, status, online_count, total_count, checked_ts) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (gal_id, 'image', 'turbo', 'offline', 0, 10, int(time.time()))
            )
        conn.close()

    def test_upsert_replaces_on_conflict(self, store):
        """INSERT OR REPLACE should update existing row on conflict."""
        conn = _connect(store.db_path)
        conn.execute(
            "INSERT INTO galleries (path, name, status, added_ts) VALUES (?, ?, ?, ?)",
            ('/test/gal2', 'gal2', 'completed', int(time.time()))
        )
        gal_id = conn.execute("SELECT id FROM galleries WHERE path = '/test/gal2'").fetchone()[0]
        now = int(time.time())
        conn.execute(
            "INSERT OR REPLACE INTO host_scan_results (gallery_fk, host_type, host_id, status, online_count, total_count, checked_ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (gal_id, 'file', 'rapidgator', 'online', 1, 1, now)
        )
        conn.execute(
            "INSERT OR REPLACE INTO host_scan_results (gallery_fk, host_type, host_id, status, online_count, total_count, checked_ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (gal_id, 'file', 'rapidgator', 'offline', 0, 1, now + 100)
        )
        row = conn.execute(
            "SELECT status, checked_ts FROM host_scan_results WHERE gallery_fk = ? AND host_id = ?",
            (gal_id, 'rapidgator')
        ).fetchone()
        assert row[0] == 'offline'
        assert row[1] == now + 100
        conn.close()

    def test_cascade_delete(self, store):
        """Deleting a gallery should cascade-delete its scan results."""
        conn = _connect(store.db_path)
        conn.execute(
            "INSERT INTO galleries (path, name, status, added_ts) VALUES (?, ?, ?, ?)",
            ('/test/gal3', 'gal3', 'completed', int(time.time()))
        )
        gal_id = conn.execute("SELECT id FROM galleries WHERE path = '/test/gal3'").fetchone()[0]
        conn.execute(
            "INSERT INTO host_scan_results (gallery_fk, host_type, host_id, status, online_count, total_count, checked_ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (gal_id, 'image', 'imx', 'online', 5, 5, int(time.time()))
        )
        conn.execute("DELETE FROM galleries WHERE id = ?", (gal_id,))
        count = conn.execute("SELECT COUNT(*) FROM host_scan_results WHERE gallery_fk = ?", (gal_id,)).fetchone()[0]
        assert count == 0
        conn.close()
