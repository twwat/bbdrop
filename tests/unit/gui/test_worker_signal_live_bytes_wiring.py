"""Unit tests for WorkerSignalHandler forwarding live file host bytes.

The worker emits upload_progress at ~4 Hz with the bytes sent so far. Two
display surfaces need that number while the transfer is still running:
ProgressTracker (the byte-weighted percent) and the worker status table's
"uploaded" columns. Both are cleared when the transfer lands or fails, so a
finished file is never counted twice.
"""

import os

from unittest.mock import MagicMock

from src.gui.worker_signal_handler import WorkerSignalHandler


GALLERY = os.path.normpath("C:/media/gallery one")


def _handler():
    mw = MagicMock()
    mw._get_current_tab_items.return_value = []
    mw.queue_manager.store.get_file_host_uploads_for_paths.return_value = {}
    mw.file_host_controller._db_id_to_path = {}
    return WorkerSignalHandler(mw), mw


class TestProgressTrackerOverlay:
    def test_progress_forwards_live_bytes(self):
        h, mw = _handler()

        h.on_file_host_upload_progress(
            7, "rapidgator", 40_000_000, 100_000_000, 0.0, GALLERY
        )

        mw.progress_tracker.set_file_host_live_bytes.assert_called_once_with(
            GALLERY, "rapidgator", 40_000_000
        )

    def test_completion_clears_live_bytes(self):
        h, mw = _handler()

        h.on_file_host_upload_completed(7, "rapidgator", {}, GALLERY)

        mw.progress_tracker.clear_file_host_live_bytes.assert_called_once_with(
            GALLERY, "rapidgator"
        )

    def test_failure_clears_live_bytes(self):
        h, mw = _handler()

        h.on_file_host_upload_failed(7, "rapidgator", "boom", GALLERY)

        mw.progress_tracker.clear_file_host_live_bytes.assert_called_once_with(
            GALLERY, "rapidgator"
        )


class TestRetryLeavesNoStaleBytes:
    """A retryable error puts the row back to 'pending' without emitting
    upload_failed and without calling record_transfer, so neither of the
    usual clear paths fires. The next attempt re-emits upload_started, so
    clearing there is what keeps the aborted attempt's bytes from lingering.
    """

    def test_start_clears_stale_live_bytes(self):
        h, mw = _handler()

        h.on_file_host_upload_started(7, "rapidgator", GALLERY)

        mw.progress_tracker.clear_file_host_live_bytes.assert_called_once_with(
            GALLERY, "rapidgator"
        )

    def test_start_clears_stale_inflight_bytes(self):
        """Widget overlay lifecycle lives with its siblings in the
        _on_filehost_worker_* handlers; both are wired to upload_started."""
        h, mw = _handler()

        h._on_filehost_worker_started(7, "rapidgator", GALLERY)

        mw.worker_status_widget.clear_inflight_bytes.assert_called_once_with(
            "rapidgator"
        )

    def test_start_survives_deleted_window(self):
        h, mw = _handler()
        mw.objectName.side_effect = RuntimeError("wrapped C/C++ object deleted")

        h.on_file_host_upload_started(7, "rapidgator", GALLERY)


class TestMainWindowGone:
    """The _mw property returns None once the C++ window is deleted; the
    overlay calls must not turn that into a crash on a late signal."""

    @staticmethod
    def _dead_handler():
        h, mw = _handler()
        mw.objectName.side_effect = RuntimeError("wrapped C/C++ object deleted")
        return h

    def test_progress_survives_deleted_window(self):
        self._dead_handler().on_file_host_upload_progress(
            7, "rapidgator", 40_000_000, 100_000_000, 0.0, GALLERY
        )

    def test_completion_survives_deleted_window(self):
        self._dead_handler().on_file_host_upload_completed(
            7, "rapidgator", {}, GALLERY
        )

    def test_dedup_completion_survives_deleted_window(self):
        """The dedup branch resolves a gallery name and writes to the status
        bar, both of which dereference the window. A plain {} result never
        reaches it, so that path needs its own case."""
        self._dead_handler().on_file_host_upload_completed(
            7, "rapidgator", {'deduplication': True}, GALLERY
        )

    def test_failure_survives_deleted_window(self):
        self._dead_handler().on_file_host_upload_failed(
            7, "rapidgator", "boom", GALLERY
        )


class TestWorkerStatusOverlay:
    def test_progress_forwards_inflight_bytes(self):
        h, mw = _handler()

        h._on_filehost_worker_progress(
            7, "rapidgator", 40_000_000, 100_000_000, 0.0, GALLERY
        )

        mw.worker_status_widget.set_inflight_bytes.assert_called_once_with(
            "rapidgator", 40_000_000
        )

    def test_completion_clears_inflight_bytes(self):
        h, mw = _handler()

        h._on_filehost_worker_completed(7, "rapidgator", {}, GALLERY)

        mw.worker_status_widget.clear_inflight_bytes.assert_called_once_with(
            "rapidgator"
        )

    def test_failure_clears_inflight_bytes(self):
        h, mw = _handler()

        h._on_filehost_worker_failed(7, "rapidgator", "boom", GALLERY)

        mw.worker_status_widget.clear_inflight_bytes.assert_called_once_with(
            "rapidgator"
        )
