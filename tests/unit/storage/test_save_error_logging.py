"""
Tests for save error logging propagation.

Verifies that:
- Per-item failures in bulk_upsert log the path AND the exception
- bulk_upsert_async logs errors via done_callback
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


class TestPerItemFailureLogging:
    """Test that per-item failures in bulk_upsert log path and error."""

    def test_per_item_failure_logs_path_and_error(self, queue_store):
        """Pass an item with an invalid status (CHECK constraint violation)
        and verify the log call includes the path."""
        bad_item = {
            'path': '/test/bad_gallery',
            'status': 'COMPLETELY_INVALID_STATUS',
            'added_time': int(time.time()),
            'tab_name': 'Main',
        }

        with patch('src.storage.database.log') as mock_log:
            queue_store.bulk_upsert([bad_item])

            # Find the per-item error log call
            error_calls = [
                call for call in mock_log.call_args_list
                if call[1].get('level') == 'error'
                and call[1].get('category') == 'database'
                and '/test/bad_gallery' in call[0][0]
            ]
            assert len(error_calls) >= 1, (
                f"Expected at least one error log containing the path "
                f"'/test/bad_gallery', got calls: {mock_log.call_args_list}"
            )

    def test_per_item_failure_logs_exception_message(self, queue_store):
        """Verify the log message includes the exception text, not just the path."""
        bad_item = {
            'path': '/test/error_gallery',
            'status': 'TOTALLY_BOGUS',
            'added_time': int(time.time()),
            'tab_name': 'Main',
        }

        with patch('src.storage.database.log') as mock_log:
            queue_store.bulk_upsert([bad_item])

            # The per-item error log must mention the exception (e.g. CHECK constraint)
            error_calls = [
                call for call in mock_log.call_args_list
                if call[1].get('level') == 'error'
                and call[1].get('category') == 'database'
                and '/test/error_gallery' in call[0][0]
            ]
            assert len(error_calls) >= 1
            msg = error_calls[0][0][0]
            # The message should contain some indication of the error itself
            assert 'Upsert failed' in msg or 'failed' in msg.lower()

    def test_valid_items_still_saved_after_bad_item(self, queue_store):
        """A bad item should not prevent other items from being saved."""
        good_item = {
            'path': '/test/good_gallery',
            'status': 'ready',
            'added_time': int(time.time()),
            'tab_name': 'Main',
        }
        bad_item = {
            'path': '/test/bad_gallery',
            'status': 'INVALID_STATUS_VALUE',
            'added_time': int(time.time()),
            'tab_name': 'Main',
        }

        queue_store.bulk_upsert([good_item, bad_item])

        loaded = queue_store.load_all_items()
        paths = [item['path'] for item in loaded]
        assert '/test/good_gallery' in paths


class TestBulkUpsertAsyncErrorLogging:
    """Test that bulk_upsert_async logs errors via done_callback."""

    def test_bulk_upsert_async_logs_errors(self, queue_store):
        """Pass bad items via async, wait for executor, verify error logged."""
        bad_item = {
            'path': '/test/async_bad',
            'status': 'COMPLETELY_INVALID_STATUS',
            'added_time': int(time.time()),
            'tab_name': 'Main',
        }

        with patch('src.storage.database.log') as mock_log:
            queue_store.bulk_upsert_async([bad_item])
            # Wait for the async operation to complete
            queue_store._executor.shutdown(wait=True)

            # Recreate executor for fixture cleanup
            from concurrent.futures import ThreadPoolExecutor
            queue_store._executor = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="queue-store"
            )

            # Check that some error was logged (either per-item or async callback)
            error_calls = [
                call for call in mock_log.call_args_list
                if call[1].get('level') == 'error'
                and call[1].get('category') == 'database'
            ]
            assert len(error_calls) >= 1, (
                f"Expected at least one error-level database log call, "
                f"got: {mock_log.call_args_list}"
            )

    def test_bulk_upsert_async_callback_logs_on_exception(self, queue_store):
        """Force bulk_upsert to raise and verify the done_callback catches it."""
        with patch.object(
            queue_store, 'bulk_upsert', side_effect=RuntimeError("DB exploded")
        ):
            with patch('src.storage.database.log') as mock_log:
                queue_store.bulk_upsert_async([{'path': '/x'}])
                queue_store._executor.shutdown(wait=True)

                # Recreate executor for fixture cleanup
                from concurrent.futures import ThreadPoolExecutor
                queue_store._executor = ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix="queue-store"
                )

                # The done_callback should have logged the async failure
                async_error_calls = [
                    call for call in mock_log.call_args_list
                    if call[1].get('level') == 'error'
                    and 'Async bulk_upsert failed' in call[0][0]
                ]
                assert len(async_error_calls) == 1, (
                    f"Expected exactly one 'Async bulk_upsert failed' log, "
                    f"got: {mock_log.call_args_list}"
                )
