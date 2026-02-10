# tests/unit/storage/test_cover_scan_integration.py
"""Tests that cover detection runs during gallery scanning."""
import os
import tempfile
from contextlib import contextmanager

import pytest
from unittest.mock import patch, MagicMock

from src.storage.queue_manager import QueueManager, GalleryQueueItem


@contextmanager
def _noop_locker(mutex):
    """No-op replacement for QMutexLocker in tests."""
    yield


def _make_queue_manager():
    """Create a bare QueueManager bypassing QObject.__init__."""
    with patch('src.storage.queue_manager.QueueStore'), \
         patch('src.storage.queue_manager.QSettings'), \
         patch('src.storage.queue_manager.QObject.__init__'):
        qm = QueueManager.__new__(QueueManager)
    qm.items = {}
    qm.mutex = MagicMock()
    qm._status_counts = {}
    qm._batch_mode = False
    qm._batched_changes = set()
    qm._pending_save_timer = None
    qm._version = 0
    qm._scan_queue = MagicMock()
    qm.status_changed = MagicMock()
    qm.scan_status_changed = MagicMock()
    qm.store = MagicMock()
    qm.queue = MagicMock()
    return qm


def _create_image_files(tmpdir, names):
    """Write tiny JPEG stubs into tmpdir."""
    for name in names:
        with open(os.path.join(tmpdir, name), 'wb') as f:
            f.write(b'\xff\xd8\xff\xe0' + b'\x00' * 100)


def _run_scan(qm, tmpdir, cover_config):
    """Run _comprehensive_scan_item with standard mocks."""
    # Bind mock methods directly to avoid patch.object getattr issues with PyQt6
    qm._get_scanning_config = lambda: {'fast_scan': True, 'pil_sampling': 2}
    qm._get_cover_detection_config = lambda: cover_config
    qm._scan_images = lambda path, files: {
        'total_size': 300, 'failed_files': [],
        'avg_width': 100, 'avg_height': 100,
        'max_width': 100, 'max_height': 100,
        'min_width': 100, 'min_height': 100,
    }
    qm._schedule_debounced_save = lambda *a, **kw: None
    qm._emit_scan_status = lambda *a, **kw: None
    qm._inc_version = lambda *a, **kw: None

    with patch('src.storage.queue_manager.QMutexLocker', side_effect=_noop_locker), \
         patch('src.storage.queue_manager.load_user_defaults', return_value={}):
        qm._comprehensive_scan_item(tmpdir)


class TestCoverScanIntegration:
    """Cover detection is invoked during _comprehensive_scan_item."""

    def test_cover_detected_during_scan(self):
        """When scanning finds files matching cover pattern, cover_source_path is set."""
        qm = _make_queue_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            _create_image_files(tmpdir, ["image001.jpg", "cover.jpg", "image002.jpg"])

            item = GalleryQueueItem(path=tmpdir, name="test", status="validating")
            qm.items[tmpdir] = item

            _run_scan(qm, tmpdir, {'patterns': 'cover*', 'also_upload': False})

            assert item.cover_source_path == os.path.join(tmpdir, "cover.jpg")

    def test_no_cover_when_pattern_empty(self):
        """When cover patterns are empty, cover_source_path stays None."""
        qm = _make_queue_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            _create_image_files(tmpdir, ["image001.jpg", "cover.jpg", "image002.jpg"])

            item = GalleryQueueItem(path=tmpdir, name="test", status="validating")
            qm.items[tmpdir] = item

            _run_scan(qm, tmpdir, {'patterns': '', 'also_upload': False})

            assert item.cover_source_path is None

    def test_no_cover_when_no_match(self):
        """When no files match the cover pattern, cover_source_path stays None."""
        qm = _make_queue_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            _create_image_files(tmpdir, ["image001.jpg", "image002.jpg", "image003.jpg"])

            item = GalleryQueueItem(path=tmpdir, name="test", status="validating")
            qm.items[tmpdir] = item

            _run_scan(qm, tmpdir, {'patterns': 'cover*', 'also_upload': False})

            assert item.cover_source_path is None

    def test_cover_also_upload_false_decrements_total(self):
        """When also_upload=False, total_images is decremented by 1."""
        qm = _make_queue_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            _create_image_files(tmpdir, ["image001.jpg", "cover.jpg", "image002.jpg"])

            item = GalleryQueueItem(path=tmpdir, name="test", status="validating")
            qm.items[tmpdir] = item

            _run_scan(qm, tmpdir, {'patterns': 'cover*', 'also_upload': False})

            # 3 files found, but cover excluded from gallery => total_images = 2
            assert item.total_images == 2
            assert item.cover_source_path == os.path.join(tmpdir, "cover.jpg")

    def test_cover_also_upload_true_keeps_total(self):
        """When also_upload=True, total_images is NOT decremented."""
        qm = _make_queue_manager()

        with tempfile.TemporaryDirectory() as tmpdir:
            _create_image_files(tmpdir, ["image001.jpg", "cover.jpg", "image002.jpg"])

            item = GalleryQueueItem(path=tmpdir, name="test", status="validating")
            qm.items[tmpdir] = item

            _run_scan(qm, tmpdir, {'patterns': 'cover*', 'also_upload': True})

            # 3 files found, cover also uploaded as gallery image => total_images stays 3
            assert item.total_images == 3
            assert item.cover_source_path == os.path.join(tmpdir, "cover.jpg")
