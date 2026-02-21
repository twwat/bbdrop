"""Tests for reserve file lifecycle."""

import os
import pytest
import tempfile
from unittest.mock import patch

from src.utils.disk_space_monitor import DiskSpaceMonitor


@pytest.fixture
def temp_dirs():
    with tempfile.TemporaryDirectory() as data_dir:
        with tempfile.TemporaryDirectory() as temp_dir:
            yield data_dir, temp_dir


@pytest.fixture
def monitor(temp_dirs):
    data_dir, temp_dir = temp_dirs
    with patch('src.utils.disk_space_monitor.QTimer'):
        mon = DiskSpaceMonitor(data_dir=data_dir, temp_dir=temp_dir)
        yield mon


class TestReserveFile:
    """Reserve file created on start, deleted on emergency."""

    def test_reserve_created_on_start(self, monitor, temp_dirs):
        data_dir, _ = temp_dirs
        reserve = os.path.join(data_dir, "disk_reserve.bin")
        assert not os.path.exists(reserve)

        monitor._ensure_reserve_file()
        assert os.path.exists(reserve)
        assert os.path.getsize(reserve) == 20 * 1024 * 1024

    def test_reserve_not_recreated_if_exists(self, monitor, temp_dirs):
        data_dir, _ = temp_dirs
        reserve = os.path.join(data_dir, "disk_reserve.bin")

        monitor._ensure_reserve_file()
        mtime1 = os.path.getmtime(reserve)

        monitor._ensure_reserve_file()
        mtime2 = os.path.getmtime(reserve)
        assert mtime1 == mtime2

    def test_request_emergency_space_deletes_reserve(self, monitor, temp_dirs):
        data_dir, _ = temp_dirs
        reserve = os.path.join(data_dir, "disk_reserve.bin")

        monitor._ensure_reserve_file()
        assert os.path.exists(reserve)

        freed = monitor.request_emergency_space()
        assert not os.path.exists(reserve)
        assert freed == 20 * 1024 * 1024

    def test_request_emergency_space_noop_if_no_reserve(self, monitor):
        freed = monitor.request_emergency_space()
        assert freed == 0

    def test_emergency_tier_auto_deletes_reserve(self, monitor, temp_dirs):
        data_dir, _ = temp_dirs
        monitor._ensure_reserve_file()
        reserve = os.path.join(data_dir, "disk_reserve.bin")
        assert os.path.exists(reserve)

        with patch('src.utils.disk_space_monitor.shutil.disk_usage') as mock_usage:
            mock_usage.return_value = type('U', (), {
                'total': 1_000_000_000, 'used': 960_000_000, 'free': 40_000_000,
            })()
            monitor._poll()  # Should trigger emergency -> delete reserve

        assert not os.path.exists(reserve)

    def test_reserve_path_follows_data_dir_on_update(self, monitor, temp_dirs):
        _, temp_dir = temp_dirs
        with tempfile.TemporaryDirectory() as new_data_dir:
            monitor.update_paths(new_data_dir, temp_dir)
            assert monitor._reserve_path == os.path.join(new_data_dir, "disk_reserve.bin")
