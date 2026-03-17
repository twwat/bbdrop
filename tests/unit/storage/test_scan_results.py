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


class TestBulkUpsertScanResults:
    """Tests for QueueStore.bulk_upsert_scan_results()."""

    def _insert_gallery(self, store, path, name='test'):
        """Helper: insert a completed gallery, return its id."""
        conn = _connect(store.db_path)
        conn.execute(
            "INSERT INTO galleries (path, name, status, added_ts) VALUES (?, ?, ?, ?)",
            (path, name, 'completed', int(time.time()))
        )
        gal_id = conn.execute("SELECT id FROM galleries WHERE path = ?", (path,)).fetchone()[0]
        conn.close()
        return gal_id

    def test_insert_new_results(self, store):
        """Bulk upsert should insert new rows."""
        gal_id = self._insert_gallery(store, '/test/a')
        now = int(time.time())
        results = [
            (gal_id, 'image', 'turbo', 'online', 10, 10, now, None),
            (gal_id, 'file', 'rapidgator', 'online', 1, 1, now, None),
        ]
        store.bulk_upsert_scan_results(results)
        conn = _connect(store.db_path)
        count = conn.execute("SELECT COUNT(*) FROM host_scan_results WHERE gallery_fk = ?", (gal_id,)).fetchone()[0]
        conn.close()
        assert count == 2

    def test_upsert_updates_existing(self, store):
        """Bulk upsert should update status on conflict."""
        gal_id = self._insert_gallery(store, '/test/b')
        now = int(time.time())
        store.bulk_upsert_scan_results([
            (gal_id, 'image', 'turbo', 'online', 10, 10, now, None),
        ])
        store.bulk_upsert_scan_results([
            (gal_id, 'image', 'turbo', 'partial', 7, 10, now + 60, None),
        ])
        conn = _connect(store.db_path)
        row = conn.execute(
            "SELECT status, online_count, checked_ts FROM host_scan_results "
            "WHERE gallery_fk = ? AND host_id = 'turbo'", (gal_id,)
        ).fetchone()
        conn.close()
        assert row[0] == 'partial'
        assert row[1] == 7
        assert row[2] == now + 60

    def test_empty_list_is_noop(self, store):
        """Empty list should not error."""
        store.bulk_upsert_scan_results([])

    def test_detail_json_stored(self, store):
        """detail_json column should round-trip JSON data."""
        import json
        gal_id = self._insert_gallery(store, '/test/c')
        detail = json.dumps({"offline_urls": ["http://example.com/1.jpg"]})
        store.bulk_upsert_scan_results([
            (gal_id, 'image', 'turbo', 'partial', 9, 10, int(time.time()), detail),
        ])
        conn = _connect(store.db_path)
        row = conn.execute(
            "SELECT detail_json FROM host_scan_results WHERE gallery_fk = ? AND host_id = 'turbo'",
            (gal_id,)
        ).fetchone()
        conn.close()
        assert json.loads(row[0]) == {"offline_urls": ["http://example.com/1.jpg"]}


class TestGetScanStatsByHost:
    """Tests for QueueStore.get_scan_stats_by_host()."""

    def _seed_data(self, store):
        """Insert galleries and scan results for stats testing."""
        conn = _connect(store.db_path)
        now = int(time.time())
        for i, (status, online, total) in enumerate([
            ('online', 10, 10),
            ('partial', 7, 10),
            ('offline', 0, 10),
        ]):
            conn.execute(
                "INSERT INTO galleries (path, name, status, added_ts) VALUES (?, ?, ?, ?)",
                (f'/test/stats{i}', f'stats{i}', 'completed', now)
            )
            gal_id = conn.execute("SELECT id FROM galleries WHERE path = ?", (f'/test/stats{i}',)).fetchone()[0]
            conn.execute(
                "INSERT INTO host_scan_results (gallery_fk, host_type, host_id, status, online_count, total_count, checked_ts) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (gal_id, 'image', 'turbo', status, online, total, now)
            )
        conn.close()

    def test_returns_per_host_counts(self, store):
        """Stats should include per-host gallery and item counts."""
        self._seed_data(store)
        stats = store.get_scan_stats_by_host()
        turbo = stats.get(('image', 'turbo'))
        assert turbo is not None
        assert turbo['online_galleries'] == 1
        assert turbo['partial_galleries'] == 1
        assert turbo['offline_galleries'] == 1
        assert turbo['total_online'] == 17  # 10 + 7 + 0
        assert turbo['total_items'] == 30   # 10 + 10 + 10

    def test_empty_db_returns_empty_dict(self, store):
        """No scan results should return empty dict."""
        stats = store.get_scan_stats_by_host()
        assert stats == {}


class TestGetHostsWithUploads:
    """Tests for QueueStore.get_hosts_with_uploads()."""

    def test_empty_db(self, store):
        """No uploads should return empty dict."""
        assert store.get_hosts_with_uploads() == {}

    def test_image_hosts_from_galleries(self, store):
        """Completed galleries with image_host_id should appear with counts."""
        conn = _connect(store.db_path)
        now = int(time.time())
        conn.execute(
            "INSERT INTO galleries (path, name, status, added_ts, image_host_id, total_images) VALUES (?, ?, ?, ?, ?, ?)",
            ('/test/a', 'a', 'completed', now, 'imx', 15)
        )
        conn.execute(
            "INSERT INTO galleries (path, name, status, added_ts, image_host_id, total_images) VALUES (?, ?, ?, ?, ?, ?)",
            ('/test/b', 'b', 'completed', now, 'imx', 25)
        )
        conn.execute(
            "INSERT INTO galleries (path, name, status, added_ts, image_host_id, total_images) VALUES (?, ?, ?, ?, ?, ?)",
            ('/test/c', 'c', 'completed', now, 'turbo', 10)
        )
        conn.close()
        result = store.get_hosts_with_uploads()
        assert result[('image', 'imx')]['gallery_count'] == 2
        assert result[('image', 'imx')]['image_count'] == 40
        assert result[('image', 'turbo')]['gallery_count'] == 1
        assert result[('image', 'turbo')]['image_count'] == 10

    def test_excludes_non_completed(self, store):
        """Only completed galleries should be counted."""
        conn = _connect(store.db_path)
        now = int(time.time())
        conn.execute(
            "INSERT INTO galleries (path, name, status, added_ts, image_host_id) VALUES (?, ?, ?, ?, ?)",
            ('/test/d', 'd', 'uploading', now, 'imx')
        )
        conn.execute(
            "INSERT INTO galleries (path, name, status, added_ts, image_host_id) VALUES (?, ?, ?, ?, ?)",
            ('/test/e', 'e', 'completed', now, 'imx')
        )
        conn.close()
        result = store.get_hosts_with_uploads()
        assert result[('image', 'imx')]['gallery_count'] == 1

    def test_file_hosts_from_file_host_uploads(self, store):
        """Completed file_host_uploads should appear as file hosts."""
        conn = _connect(store.db_path)
        now = int(time.time())
        conn.execute(
            "INSERT INTO galleries (path, name, status, added_ts) VALUES (?, ?, ?, ?)",
            ('/test/f', 'f', 'completed', now)
        )
        gal_id = conn.execute("SELECT id FROM galleries WHERE path = '/test/f'").fetchone()[0]
        conn.execute(
            "INSERT INTO file_host_uploads (gallery_fk, host_name, status) VALUES (?, ?, ?)",
            (gal_id, 'rapidgator', 'completed')
        )
        conn.execute(
            "INSERT INTO file_host_uploads (gallery_fk, host_name, status) VALUES (?, ?, ?)",
            (gal_id, 'keep2share', 'completed')
        )
        conn.close()
        result = store.get_hosts_with_uploads()
        assert result[('file', 'rapidgator')]['gallery_count'] == 1
        assert result[('file', 'rapidgator')]['image_count'] == 1  # 1 file upload
        assert result[('file', 'keep2share')]['gallery_count'] == 1

    def test_mixed_image_and_file_hosts(self, store):
        """Both image and file hosts should appear together."""
        conn = _connect(store.db_path)
        now = int(time.time())
        conn.execute(
            "INSERT INTO galleries (path, name, status, added_ts, image_host_id) VALUES (?, ?, ?, ?, ?)",
            ('/test/g', 'g', 'completed', now, 'turbo')
        )
        gal_id = conn.execute("SELECT id FROM galleries WHERE path = '/test/g'").fetchone()[0]
        conn.execute(
            "INSERT INTO file_host_uploads (gallery_fk, host_name, status) VALUES (?, ?, ?)",
            (gal_id, 'rapidgator', 'completed')
        )
        conn.close()
        result = store.get_hosts_with_uploads()
        assert ('image', 'turbo') in result
        assert ('file', 'rapidgator') in result


class TestGetGalleriesForScanAgeMode:
    """Test age_mode parameter for upload-age vs last-scan filtering."""

    @pytest.fixture
    def store_with_data(self, tmp_path):
        """Store with galleries that have different upload times and scan times."""
        store = QueueStore(db_path=str(tmp_path / "test.db"))
        conn = _connect(store.db_path)
        _ensure_schema(conn)
        now = int(time.time())
        # Gallery 1: uploaded 60 days ago, scanned 5 days ago
        conn.execute(
            "INSERT INTO galleries (id, path, name, status, added_ts, image_host_id, finished_ts) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1, '/old_upload_recent_scan', 'OldUpload', 'completed', now - 60 * 86400, 'turbo', now - 60 * 86400)
        )
        conn.execute(
            "INSERT INTO images (gallery_fk, filename, thumb_url) VALUES (?, ?, ?)",
            (1, 'img1.jpg', 'https://t.turbo.to/thumb/abc.jpg')
        )
        conn.execute(
            "INSERT INTO host_scan_results (gallery_fk, host_type, host_id, status, online_count, total_count, checked_ts) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1, 'image', 'turbo', 'online', 1, 1, now - 5 * 86400)
        )
        # Gallery 2: uploaded 5 days ago, scanned 60 days ago
        conn.execute(
            "INSERT INTO galleries (id, path, name, status, added_ts, image_host_id, finished_ts) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (2, '/new_upload_old_scan', 'NewUpload', 'completed', now - 5 * 86400, 'turbo', now - 5 * 86400)
        )
        conn.execute(
            "INSERT INTO images (gallery_fk, filename, thumb_url) VALUES (?, ?, ?)",
            (2, 'img2.jpg', 'https://t.turbo.to/thumb/def.jpg')
        )
        conn.execute(
            "INSERT INTO host_scan_results (gallery_fk, host_type, host_id, status, online_count, total_count, checked_ts) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (2, 'image', 'turbo', 'online', 1, 1, now - 60 * 86400)
        )
        conn.close()
        return store

    def test_last_scan_mode_filters_by_checked_ts(self, store_with_data):
        """age_mode='last_scan' should return gallery scanned 60 days ago, not the one scanned 5 days ago."""
        result = store_with_data.get_galleries_for_scan(30, '', 'age', age_mode='last_scan')
        db_ids = [g['db_id'] for g in result['image_galleries']]
        assert 2 in db_ids  # scanned 60 days ago
        assert 1 not in db_ids  # scanned 5 days ago

    def test_upload_mode_filters_by_finished_ts(self, store_with_data):
        """age_mode='upload' should return gallery uploaded 60 days ago, not the one uploaded 5 days ago."""
        result = store_with_data.get_galleries_for_scan(30, '', 'age', age_mode='upload')
        db_ids = [g['db_id'] for g in result['image_galleries']]
        assert 1 in db_ids  # uploaded 60 days ago
        assert 2 not in db_ids  # uploaded 5 days ago

    def test_default_age_mode_is_last_scan(self, store_with_data):
        """Omitting age_mode should default to last_scan behavior."""
        result = store_with_data.get_galleries_for_scan(30, '', 'age')
        db_ids = [g['db_id'] for g in result['image_galleries']]
        assert 2 in db_ids
        assert 1 not in db_ids

    def test_age_zero_returns_all(self, store_with_data):
        """age_days=0 ('All') should return all galleries regardless of age."""
        result = store_with_data.get_galleries_for_scan(0, '', 'age', age_mode='last_scan')
        db_ids = [g['db_id'] for g in result['image_galleries']]
        assert 1 in db_ids
        assert 2 in db_ids
