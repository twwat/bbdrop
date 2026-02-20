"""
Tests for _next_db_id collision prevention.

When load_persistent_queue skips orphaned rows (non-completed items whose
paths no longer exist on disk), _next_db_id must still account for their IDs.
Otherwise new items may collide with orphan IDs on INSERT, causing a UNIQUE
constraint violation on the `id` column (which is NOT caught by
ON CONFLICT(path)).

Tests cover:
- QueueManager._next_db_id accounts for orphaned DB rows
- Only valid items are loaded into the in-memory queue
- QueueStore.get_max_gallery_id returns the correct maximum
"""

import os
import tempfile
import time

import pytest
from unittest.mock import Mock, patch

from src.storage.queue_manager import QueueManager
from src.storage.database import QueueStore
from src.core.constants import QUEUE_STATE_READY


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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
def queue_store(temp_db):
    """Create a QueueStore instance with temporary database."""
    store = QueueStore(db_path=temp_db)
    yield store
    if hasattr(store, '_executor'):
        store._executor.shutdown(wait=True)


@pytest.fixture
def existing_dir(tmp_path):
    """Create a real directory that os.path.exists will find."""
    d = tmp_path / "existing_gallery"
    d.mkdir()
    return str(d)


@pytest.fixture
def mock_store(existing_dir):
    """Mock QueueStore returning data that simulates orphaned rows.

    Row layout:
      id=5  path=/gone/orphan   status=ready   <- path does NOT exist (orphan)
      id=3  path=<existing_dir> status=ready   <- path exists (loaded)

    get_max_gallery_id returns 5 (the highest id in the DB).
    """
    store = Mock()
    store.load_all_items.return_value = [
        {
            'db_id': 5,
            'path': '/gone/orphan_gallery',
            'name': 'Orphan',
            'status': QUEUE_STATE_READY,
            'added_time': int(time.time()),
            'tab_name': 'Main',
            'insertion_order': 2,
        },
        {
            'db_id': 3,
            'path': existing_dir,
            'name': 'Valid',
            'status': QUEUE_STATE_READY,
            'added_time': int(time.time()),
            'tab_name': 'Main',
            'insertion_order': 1,
        },
    ]
    store.get_max_gallery_id.return_value = 5
    store.bulk_upsert.return_value = None
    store.bulk_upsert_async.return_value = None
    store.delete_by_paths.return_value = 1
    store.update_item_custom_field.return_value = True
    store.migrate_from_qsettings_if_needed.return_value = None
    return store


@pytest.fixture
def queue_manager(mock_store):
    """Create QueueManager with the mock_store wired in."""
    import queue as _q

    with patch('src.storage.queue_manager.QueueStore', return_value=mock_store):
        with patch('src.storage.queue_manager.QSettings'):
            manager = QueueManager()
            yield manager
            # Cleanup
            manager._scan_worker_running = False
            try:
                manager._scan_queue.put(None, timeout=0.1)
            except (_q.Full, AttributeError):
                pass
            if manager._scan_worker and manager._scan_worker.is_alive():
                manager._scan_worker.join(timeout=3.0)


# ---------------------------------------------------------------------------
# QueueManager tests
# ---------------------------------------------------------------------------

class TestNextDbIdOrphanCollision:
    """Verify _next_db_id skips over orphaned row IDs."""

    def test_next_db_id_skips_orphan_ids(self, queue_manager):
        """_next_db_id must be >= 6 because the DB contains id=5 (orphan)."""
        assert queue_manager._next_db_id >= 6

    def test_loaded_item_has_correct_id(self, queue_manager, existing_dir):
        """Only the non-orphan item (id=3) should be loaded into memory."""
        assert len(queue_manager.items) == 1
        loaded_item = queue_manager.items[existing_dir]
        assert loaded_item.db_id == 3


# ---------------------------------------------------------------------------
# QueueStore.get_max_gallery_id — real database test
# ---------------------------------------------------------------------------

class TestGetMaxGalleryId:
    """Test QueueStore.get_max_gallery_id with a real temp database."""

    def test_empty_database_returns_zero(self, queue_store):
        """An empty galleries table should return 0."""
        assert queue_store.get_max_gallery_id() == 0

    def test_returns_highest_id(self, queue_store):
        """Should return the maximum id across all rows."""
        items = [
            {
                'path': '/test/gallery_a',
                'status': 'ready',
                'added_time': int(time.time()),
                'tab_name': 'Main',
            },
            {
                'path': '/test/gallery_b',
                'status': 'ready',
                'added_time': int(time.time()),
                'tab_name': 'Main',
            },
        ]
        queue_store.bulk_upsert(items)

        max_id = queue_store.get_max_gallery_id()
        # Both rows inserted; max id should be >= 2
        assert max_id >= 2

    def test_returns_max_after_deletion(self, queue_store):
        """After deleting the highest-id row, max should reflect the gap."""
        items = [
            {
                'path': '/test/gallery_a',
                'status': 'ready',
                'added_time': int(time.time()),
                'tab_name': 'Main',
            },
            {
                'path': '/test/gallery_b',
                'status': 'ready',
                'added_time': int(time.time()),
                'tab_name': 'Main',
            },
        ]
        queue_store.bulk_upsert(items)

        # Record the max before deletion
        max_before = queue_store.get_max_gallery_id()
        assert max_before >= 2

        # Delete second row — the one with the higher id
        queue_store.delete_by_paths(['/test/gallery_b'])

        max_after = queue_store.get_max_gallery_id()
        # After deletion, max should be less than before
        assert max_after < max_before
        assert max_after >= 1
