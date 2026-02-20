"""
Tests for path normalization in QueueManager.

Verifies that trailing slashes, dot segments, and other path variants
are normalized on entry so that duplicate paths are correctly detected.
"""

import os
import queue
import tempfile
import time

import pytest
from unittest.mock import Mock, patch

from src.storage.queue_manager import QueueManager


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
    store.add_file_host_upload.return_value = None
    return store


@pytest.fixture
def queue_manager(mock_store):
    """Create QueueManager instance with mocked store."""
    with patch('src.storage.queue_manager.QueueStore', return_value=mock_store):
        with patch('src.storage.queue_manager.QSettings'):
            manager = QueueManager()
            yield manager
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
            f.write(b'\xFF\xD8\xFF\xE0')
    return gallery_path


class TestPathNormalization:
    """Tests that QueueManager normalizes paths to prevent duplicates."""

    def test_trailing_slash_deduplication(self, queue_manager, gallery_dir):
        """Adding a path with and without trailing slash should deduplicate."""
        path_clean = gallery_dir               # e.g. /tmp/xyz/test_gallery
        path_slash = gallery_dir + '/'         # e.g. /tmp/xyz/test_gallery/

        first = queue_manager.add_item(path_clean, name='First')
        second = queue_manager.add_item(path_slash, name='Second')

        assert first is True
        assert second is False, (
            "Second add with trailing slash should be rejected as duplicate"
        )
        # Only one item in the dict
        assert len(queue_manager.items) == 1
        # The stored item should use the first name
        item = list(queue_manager.items.values())[0]
        assert item.name == 'First'

    def test_get_item_normalizes(self, queue_manager, gallery_dir):
        """get_item should find items regardless of trailing slash."""
        queue_manager.add_item(gallery_dir, name='MyGallery')

        # Look up with trailing slash
        item = queue_manager.get_item(gallery_dir + '/')
        assert item is not None
        assert item.name == 'MyGallery'

        # Look up without trailing slash (original)
        item2 = queue_manager.get_item(gallery_dir)
        assert item2 is not None
        assert item2.name == 'MyGallery'

    def test_remove_item_normalizes(self, queue_manager, gallery_dir):
        """remove_item should work with trailing-slash variant of the path."""
        queue_manager.add_item(gallery_dir, name='ToRemove')
        assert gallery_dir in queue_manager.items or os.path.normpath(gallery_dir) in queue_manager.items

        # Remove using trailing-slash variant
        success = queue_manager.remove_item(gallery_dir + '/')
        assert success is True
        assert len(queue_manager.items) == 0

    def test_dot_segments_normalized(self, queue_manager, gallery_dir):
        """Paths with /./ segments should be caught as duplicate."""
        parent = os.path.dirname(gallery_dir)
        basename = os.path.basename(gallery_dir)
        dot_path = os.path.join(parent, '.', basename)  # /tmp/xyz/./test_gallery

        first = queue_manager.add_item(gallery_dir, name='Original')
        second = queue_manager.add_item(dot_path, name='DotVariant')

        assert first is True
        assert second is False, (
            "Path with /./ segment should be caught as duplicate"
        )
        assert len(queue_manager.items) == 1
