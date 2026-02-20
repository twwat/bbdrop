"""
Tests for immediate synchronous save on critical status transitions.

When a gallery reaches 'completed', 'failed', or 'upload_failed' status,
QueueManager must persist that state immediately via bulk_upsert (synchronous)
rather than the debounced path, to prevent data loss on crash/close.
"""

import os
import queue
import tempfile
import time

import pytest
from unittest.mock import Mock, patch

from src.storage.queue_manager import QueueManager
from src.core.constants import (
    QUEUE_STATE_READY,
    QUEUE_STATE_QUEUED,
    QUEUE_STATE_UPLOADING,
    QUEUE_STATE_COMPLETED,
    QUEUE_STATE_FAILED,
    QUEUE_STATE_UPLOAD_FAILED,
)


@pytest.fixture
def temp_dir():
    """Create temporary directory for test galleries."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_store():
    """Mock QueueStore."""
    store = Mock()
    store.load_all_items.return_value = []
    store.bulk_upsert.return_value = None
    store.bulk_upsert_async.return_value = None
    store.delete_by_paths.return_value = 1
    store.update_item_custom_field.return_value = True
    return store


@pytest.fixture
def queue_manager(mock_store):
    """Create QueueManager instance with mocked store."""
    with patch('src.storage.queue_manager.QueueStore', return_value=mock_store):
        with patch('src.storage.queue_manager.QSettings'):
            manager = QueueManager()
            yield manager
            # Cleanup
            manager._scan_worker_running = False
            try:
                manager._scan_queue.put(None, timeout=0.1)
            except (queue.Full, AttributeError):
                pass
            if manager._scan_worker and manager._scan_worker.is_alive():
                manager._scan_worker.join(timeout=3.0)
            import gc
            gc.collect()
            time.sleep(0.1)


@pytest.fixture
def gallery_dir(temp_dir):
    """Create a test gallery directory with images."""
    gallery_path = os.path.join(temp_dir, 'test_gallery')
    os.makedirs(gallery_path)
    for i in range(3):
        img_path = os.path.join(gallery_path, f'image{i}.jpg')
        with open(img_path, 'wb') as f:
            f.write(b'\xFF\xD8\xFF\xE0')  # JPEG header
    return gallery_path


class TestCompletionImmediateSave:
    """Test that critical status transitions trigger immediate synchronous save."""

    def test_completed_triggers_immediate_save(
        self, queue_manager, gallery_dir, mock_store
    ):
        """Setting status to 'completed' must call store.bulk_upsert
        synchronously, not the debounced async path."""
        queue_manager.add_item(gallery_dir)
        queue_manager.items[gallery_dir].status = QUEUE_STATE_UPLOADING

        # Reset mock call history so add_item's saves don't interfere
        mock_store.bulk_upsert.reset_mock()
        mock_store.bulk_upsert_async.reset_mock()

        queue_manager.update_item_status(gallery_dir, QUEUE_STATE_COMPLETED)

        # Synchronous bulk_upsert must have been called
        assert mock_store.bulk_upsert.called, (
            "Expected synchronous bulk_upsert for 'completed' transition"
        )

    def test_failed_triggers_immediate_save(
        self, queue_manager, gallery_dir, mock_store
    ):
        """Setting status to 'failed' must call store.bulk_upsert
        synchronously."""
        queue_manager.add_item(gallery_dir)
        queue_manager.items[gallery_dir].status = QUEUE_STATE_UPLOADING

        mock_store.bulk_upsert.reset_mock()
        mock_store.bulk_upsert_async.reset_mock()

        queue_manager.update_item_status(gallery_dir, QUEUE_STATE_FAILED)

        assert mock_store.bulk_upsert.called, (
            "Expected synchronous bulk_upsert for 'failed' transition"
        )

    def test_upload_failed_triggers_immediate_save(
        self, queue_manager, gallery_dir, mock_store
    ):
        """Setting status to 'upload_failed' must call store.bulk_upsert
        synchronously."""
        queue_manager.add_item(gallery_dir)
        queue_manager.items[gallery_dir].status = QUEUE_STATE_UPLOADING

        mock_store.bulk_upsert.reset_mock()
        mock_store.bulk_upsert_async.reset_mock()

        queue_manager.update_item_status(gallery_dir, QUEUE_STATE_UPLOAD_FAILED)

        assert mock_store.bulk_upsert.called, (
            "Expected synchronous bulk_upsert for 'upload_failed' transition"
        )

    def test_non_critical_status_uses_debounced_save(
        self, queue_manager, gallery_dir, mock_store
    ):
        """Setting a non-critical status (e.g. 'ready') must NOT call
        synchronous bulk_upsert; only the debounced path should be used."""
        queue_manager.add_item(gallery_dir)
        queue_manager.items[gallery_dir].status = QUEUE_STATE_QUEUED

        mock_store.bulk_upsert.reset_mock()
        mock_store.bulk_upsert_async.reset_mock()

        queue_manager.update_item_status(gallery_dir, QUEUE_STATE_READY)

        assert not mock_store.bulk_upsert.called, (
            "Synchronous bulk_upsert should NOT be called for non-critical "
            "status 'ready'"
        )

    def test_completed_save_includes_correct_item_data(
        self, queue_manager, gallery_dir, mock_store
    ):
        """The immediate save for 'completed' must pass the correct item
        dict with status='completed' and progress=100."""
        queue_manager.add_item(gallery_dir)
        queue_manager.items[gallery_dir].status = QUEUE_STATE_UPLOADING
        queue_manager.items[gallery_dir].progress = 75

        mock_store.bulk_upsert.reset_mock()

        queue_manager.update_item_status(gallery_dir, QUEUE_STATE_COMPLETED)

        assert mock_store.bulk_upsert.called
        saved_items = mock_store.bulk_upsert.call_args[0][0]
        assert len(saved_items) == 1
        assert saved_items[0]['status'] == QUEUE_STATE_COMPLETED
        assert saved_items[0]['progress'] == 100
        assert saved_items[0]['path'] == gallery_dir

    def test_critical_save_failure_is_logged_not_raised(
        self, queue_manager, gallery_dir, mock_store
    ):
        """If the synchronous save fails, the exception must be caught
        and logged, not propagated to the caller."""
        queue_manager.add_item(gallery_dir)
        queue_manager.items[gallery_dir].status = QUEUE_STATE_UPLOADING

        mock_store.bulk_upsert.side_effect = Exception("DB write error")

        # Must not raise
        queue_manager.update_item_status(gallery_dir, QUEUE_STATE_COMPLETED)

        # Status should still be updated in memory
        assert queue_manager.items[gallery_dir].status == QUEUE_STATE_COMPLETED

    def test_critical_status_in_batch_mode_still_saves_immediately(
        self, queue_manager, gallery_dir, mock_store
    ):
        """Even in batch mode, critical transitions must save immediately
        rather than being deferred to the batch flush."""
        queue_manager.add_item(gallery_dir)
        queue_manager.items[gallery_dir].status = QUEUE_STATE_UPLOADING

        mock_store.bulk_upsert.reset_mock()

        # Enter batch mode manually
        queue_manager._batch_mode = True

        queue_manager.update_item_status(gallery_dir, QUEUE_STATE_COMPLETED)

        assert mock_store.bulk_upsert.called, (
            "Critical transitions must save immediately even in batch mode"
        )

        queue_manager._batch_mode = False
