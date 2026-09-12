"""Tests for FileHostWorker._cleanup_archive_if_settled.

`release_archive` deliberately parks the archive at ref 0 so an auto-retry
can reuse it without re-zipping. Nothing ever reclaimed it after the retry
window closed, so every finished gallery leaked its archive into %TEMP%
(921 MB observed in one session). This hook is the missing terminal delete.
"""

import pytest
from unittest.mock import MagicMock

from src.processing.file_host_workers import FileHostWorker


def _worker(rows):
    w = FileHostWorker.__new__(FileHostWorker)
    w.queue_store = MagicMock()
    w.queue_store.get_file_host_uploads.return_value = rows
    w.archive_manager = MagicMock()
    w._log = MagicMock()
    return w


class TestCleanupArchiveIfSettled:
    @pytest.mark.unit
    def test_deletes_when_all_rows_terminal(self):
        w = _worker([{"status": "completed"}, {"status": "completed"}])
        w._cleanup_archive_if_settled(7, "/g")
        w.archive_manager.cleanup_gallery.assert_called_once_with(7)

    @pytest.mark.unit
    def test_deletes_when_rows_failed(self):
        """A permanently failed row means no retry is coming."""
        w = _worker([{"status": "failed"}])
        w._cleanup_archive_if_settled(7, "/g")
        w.archive_manager.cleanup_gallery.assert_called_once_with(7)

    @pytest.mark.unit
    @pytest.mark.parametrize("status", ["pending", "uploading", "blocked"])
    def test_retains_while_another_attempt_could_use_it(self, status):
        """Retry / second host / family-blocked rows keep the archive."""
        w = _worker([{"status": "completed"}, {"status": status}])
        w._cleanup_archive_if_settled(7, "/g")
        w.archive_manager.cleanup_gallery.assert_not_called()

    @pytest.mark.unit
    def test_no_rows_deletes(self):
        w = _worker([])
        w._cleanup_archive_if_settled(7, "/g")
        w.archive_manager.cleanup_gallery.assert_called_once_with(7)

    @pytest.mark.unit
    def test_db_error_leaves_archive_for_the_startup_sweep(self):
        w = _worker([])
        w.queue_store.get_file_host_uploads.side_effect = RuntimeError("db")
        w._cleanup_archive_if_settled(7, "/g")
        w.archive_manager.cleanup_gallery.assert_not_called()

    @pytest.mark.unit
    def test_cleanup_failure_is_swallowed(self):
        """A locked file must not break the upload's finally block."""
        w = _worker([{"status": "completed"}])
        w.archive_manager.cleanup_gallery.side_effect = PermissionError("locked")
        w._cleanup_archive_if_settled(7, "/g")  # must not raise
