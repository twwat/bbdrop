# tests/unit/storage/test_scan_file_metadata.py
"""Tests that _scan_images() populates file_sizes and file_dimensions."""
import os
import tempfile

import pytest
from PIL import Image
from unittest.mock import patch, MagicMock

from src.storage.queue_manager import QueueManager


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


def _create_real_images(tmpdir, specs):
    """Create real image files with specified dimensions.

    Args:
        tmpdir: Directory to create images in.
        specs: List of (filename, width, height) tuples.
    """
    for name, w, h in specs:
        img = Image.new('RGB', (w, h), color='red')
        img.save(os.path.join(tmpdir, name))


@pytest.mark.unit
class TestScanFileSizes:
    """_scan_images() populates file_sizes with per-file byte counts."""

    def test_file_sizes_populated(self):
        """Each valid file's size appears in file_sizes."""
        qm = _make_queue_manager()
        qm._get_scanning_config = lambda: {'fast_scan': True, 'pil_sampling': 2}

        with tempfile.TemporaryDirectory() as tmpdir:
            specs = [
                ('img001.jpg', 100, 100),
                ('img002.jpg', 200, 150),
                ('img003.jpg', 50, 50),
            ]
            _create_real_images(tmpdir, specs)
            files = sorted(os.listdir(tmpdir))

            with patch('src.storage.queue_manager.QSettings'):
                result = qm._scan_images(tmpdir, files)

            assert 'file_sizes' in result
            assert len(result['file_sizes']) == 3
            for name, _, _ in specs:
                assert name in result['file_sizes']
                expected_size = os.path.getsize(os.path.join(tmpdir, name))
                assert result['file_sizes'][name] == expected_size

    def test_file_sizes_sum_equals_total_size(self):
        """Sum of all file_sizes entries equals total_size."""
        qm = _make_queue_manager()
        qm._get_scanning_config = lambda: {'fast_scan': True, 'pil_sampling': 2}

        with tempfile.TemporaryDirectory() as tmpdir:
            specs = [
                ('a.jpg', 80, 60),
                ('b.jpg', 120, 90),
            ]
            _create_real_images(tmpdir, specs)
            files = sorted(os.listdir(tmpdir))

            with patch('src.storage.queue_manager.QSettings'):
                result = qm._scan_images(tmpdir, files)

            assert sum(result['file_sizes'].values()) == result['total_size']

    def test_file_sizes_empty_when_no_files(self):
        """file_sizes is empty dict when files list is empty."""
        qm = _make_queue_manager()
        qm._get_scanning_config = lambda: {'fast_scan': True, 'pil_sampling': 2}

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('src.storage.queue_manager.QSettings'):
                result = qm._scan_images(tmpdir, [])

            assert result['file_sizes'] == {}


@pytest.mark.unit
class TestScanFileDimensions:
    """_scan_images() populates file_dimensions with per-file (width, height)."""

    def test_file_dimensions_populated(self):
        """Each valid file's dimensions appear in file_dimensions."""
        qm = _make_queue_manager()
        qm._get_scanning_config = lambda: {'fast_scan': True, 'pil_sampling': 2}

        with tempfile.TemporaryDirectory() as tmpdir:
            specs = [
                ('img001.jpg', 100, 200),
                ('img002.jpg', 300, 400),
                ('img003.jpg', 50, 75),
            ]
            _create_real_images(tmpdir, specs)
            files = sorted(os.listdir(tmpdir))

            with patch('src.storage.queue_manager.QSettings'):
                result = qm._scan_images(tmpdir, files)

            assert 'file_dimensions' in result
            assert len(result['file_dimensions']) == 3
            for name, w, h in specs:
                assert name in result['file_dimensions']
                assert result['file_dimensions'][name] == (w, h)

    def test_file_dimensions_correct_values(self):
        """Dimensions match the actual image sizes created."""
        qm = _make_queue_manager()
        qm._get_scanning_config = lambda: {'fast_scan': True, 'pil_sampling': 2}

        with tempfile.TemporaryDirectory() as tmpdir:
            _create_real_images(tmpdir, [
                ('wide.jpg', 800, 100),
                ('tall.jpg', 100, 800),
                ('square.jpg', 500, 500),
            ])
            files = sorted(os.listdir(tmpdir))

            with patch('src.storage.queue_manager.QSettings'):
                result = qm._scan_images(tmpdir, files)

            assert result['file_dimensions']['square.jpg'] == (500, 500)
            assert result['file_dimensions']['tall.jpg'] == (100, 800)
            assert result['file_dimensions']['wide.jpg'] == (800, 100)

    def test_file_dimensions_empty_when_failed_files(self):
        """file_dimensions stays empty when validation fails."""
        qm = _make_queue_manager()
        qm._get_scanning_config = lambda: {'fast_scan': True, 'pil_sampling': 2}

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create one valid and one corrupt file
            _create_real_images(tmpdir, [('good.jpg', 100, 100)])
            corrupt_path = os.path.join(tmpdir, 'bad.jpg')
            with open(corrupt_path, 'wb') as f:
                f.write(b'\x00\x00\x00\x00')  # Not a valid image

            files = sorted(os.listdir(tmpdir))

            with patch('src.storage.queue_manager.QSettings'):
                result = qm._scan_images(tmpdir, files)

            # Validation should fail for corrupt file
            assert len(result['failed_files']) > 0
            # file_dimensions should be empty since we skip dim collection on failures
            assert result['file_dimensions'] == {}

    def test_file_dimensions_empty_when_no_files(self):
        """file_dimensions is empty dict when files list is empty."""
        qm = _make_queue_manager()
        qm._get_scanning_config = lambda: {'fast_scan': True, 'pil_sampling': 2}

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('src.storage.queue_manager.QSettings'):
                result = qm._scan_images(tmpdir, [])

            assert result['file_dimensions'] == {}


@pytest.mark.unit
class TestScanResultKeys:
    """_scan_images() result dict always contains the expected keys."""

    def test_result_has_all_expected_keys(self):
        """Result dict contains both legacy and new metadata keys."""
        qm = _make_queue_manager()
        qm._get_scanning_config = lambda: {'fast_scan': True, 'pil_sampling': 2}

        with tempfile.TemporaryDirectory() as tmpdir:
            _create_real_images(tmpdir, [('test.jpg', 100, 100)])
            files = ['test.jpg']

            with patch('src.storage.queue_manager.QSettings'):
                result = qm._scan_images(tmpdir, files)

            expected_keys = {
                'total_size', 'failed_files',
                'avg_width', 'avg_height',
                'max_width', 'max_height',
                'min_width', 'min_height',
                'file_sizes', 'file_dimensions',
            }
            assert expected_keys.issubset(result.keys())
