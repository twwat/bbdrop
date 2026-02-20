"""
Tests for disk space check before database writes.

Verifies that:
- bulk_upsert logs a warning when disk space is below threshold
- bulk_upsert does NOT log a disk warning when space is sufficient
"""

import os
import tempfile
import time

import pytest
from unittest.mock import patch

from src.storage.database import QueueStore


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


class TestDiskSpaceCheck:
    """Test that bulk_upsert checks disk space before writing."""

    def test_low_disk_space_logs_warning(self, queue_store):
        """When disk space is below threshold, a warning-level log is emitted."""
        mock_usage = type('Usage', (), {
            'total': 100_000_000_000,
            'used': 99_990_000_000,
            'free': 10_000_000,
        })()

        good_item = {
            'path': '/test/disk_check_gallery',
            'status': 'ready',
            'added_time': int(time.time()),
            'tab_name': 'Main',
        }

        with patch('src.storage.database.shutil.disk_usage', return_value=mock_usage):
            with patch('src.storage.database.log') as mock_log:
                queue_store.bulk_upsert([good_item])

                warning_calls = [
                    call for call in mock_log.call_args_list
                    if call[1].get('level') == 'warning'
                    and call[1].get('category') == 'database'
                    and 'disk' in call[0][0].lower()
                ]
                assert len(warning_calls) == 1, (
                    f"Expected exactly one warning-level disk log, "
                    f"got calls: {mock_log.call_args_list}"
                )

    def test_normal_disk_space_no_warning(self, queue_store):
        """When disk space is sufficient, no disk warning is emitted."""
        mock_usage = type('Usage', (), {
            'total': 100_000_000_000,
            'used': 50_000_000_000,
            'free': 50_000_000_000,
        })()

        good_item = {
            'path': '/test/disk_check_ok_gallery',
            'status': 'ready',
            'added_time': int(time.time()),
            'tab_name': 'Main',
        }

        with patch('src.storage.database.shutil.disk_usage', return_value=mock_usage):
            with patch('src.storage.database.log') as mock_log:
                queue_store.bulk_upsert([good_item])

                warning_calls = [
                    call for call in mock_log.call_args_list
                    if call[1].get('level') == 'warning'
                    and call[1].get('category') == 'database'
                    and 'disk' in call[0][0].lower()
                ]
                assert len(warning_calls) == 0, (
                    f"Expected no disk warning log, "
                    f"got calls: {mock_log.call_args_list}"
                )
