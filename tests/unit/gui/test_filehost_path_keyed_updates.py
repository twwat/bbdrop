#!/usr/bin/env python3
"""File host GUI updates must be keyed by gallery_path, not resolved from db_id.

Regression tests for the stale-row bug: in-memory item.db_id is a *predicted*
id that can diverge from the real galleries.id carried in worker signals
(gallery_fk). When that happens, every db_id-keyed lookup silently no-ops:
host logo refresh, per-row file host progress, the final bar/status refresh,
and BBCode auto-regeneration. The fix carries gallery_path (which the worker
already has) through the upload_* signals so no resolution is needed.
"""

import pytest
from unittest.mock import Mock, patch

from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_mock_main_window():
    mw = Mock()
    mw.file_host_controller = Mock()
    mw.file_host_controller._db_id_to_path = {}
    mw.queue_manager = Mock()
    return mw


@pytest.fixture
def handler(qapp):
    from src.gui.worker_signal_handler import WorkerSignalHandler
    mw = _make_mock_main_window()
    h = WorkerSignalHandler(mw)
    # Not under test; touch unrelated Mock plumbing that would explode.
    h._update_filehost_queue_for_host = Mock()
    h._maybe_notify_queue_finished = Mock()
    return h


class TestWorkerSignalsCarryGalleryPath:
    """The worker's upload_* signals must include gallery_path."""

    @pytest.fixture
    def worker(self):
        with patch('src.processing.file_host_workers.get_config_manager') as cfg, \
             patch('src.processing.file_host_workers.get_coordinator'), \
             patch('src.processing.file_host_workers.get_archive_manager'), \
             patch('src.processing.file_host_workers.QSettings'), \
             patch('src.processing.file_host_workers.get_credential', return_value=None):
            mock_config = Mock()
            mock_config.name = "TestHost"
            cfg.return_value.get_host.return_value = mock_config
            from src.processing.file_host_workers import FileHostWorker
            yield FileHostWorker("testhost", Mock())

    def test_upload_started_carries_path(self, qapp, worker):
        received = []
        worker.upload_started.connect(lambda *a: received.append(a))
        worker.upload_started.emit(7, 'testhost', '/gal/a')
        assert received == [(7, 'testhost', '/gal/a')]

    def test_upload_progress_carries_path(self, qapp, worker):
        received = []
        worker.upload_progress.connect(lambda *a: received.append(a))
        worker.upload_progress.emit(7, 'testhost', 50, 100, 1000.0, '/gal/a')
        assert received == [(7, 'testhost', 50, 100, 1000.0, '/gal/a')]

    def test_upload_completed_carries_path(self, qapp, worker):
        received = []
        worker.upload_completed.connect(lambda *a: received.append(a))
        worker.upload_completed.emit(7, 'testhost', {'status': 'success'}, '/gal/a')
        assert received == [(7, 'testhost', {'status': 'success'}, '/gal/a')]

    def test_upload_failed_carries_path(self, qapp, worker):
        received = []
        worker.upload_failed.connect(lambda *a: received.append(a))
        worker.upload_failed.emit(7, 'testhost', 'boom', '/gal/a')
        assert received == [(7, 'testhost', 'boom', '/gal/a')]

    def test_manager_relay_signals_carry_path(self, qapp):
        """Manager relay signals must match the worker signatures."""
        from src.processing.file_host_worker_manager import FileHostWorkerManager
        received = []
        with patch.object(FileHostWorkerManager, '__init__', lambda self, *a, **k: super(FileHostWorkerManager, self).__init__()):
            manager = FileHostWorkerManager(Mock())
        manager.upload_completed.connect(lambda *a: received.append(a))
        manager.upload_completed.emit(7, 'testhost', {}, '/gal/a')
        assert received == [(7, 'testhost', {}, '/gal/a')]


class TestHandlersUseGalleryPathFromSignal:
    """GUI handlers must act on the signal's gallery_path even when no queue
    item has a matching db_id (the predicted-id divergence case)."""

    def test_completed_refreshes_row_via_signal_path(self, handler):
        mw = handler._main_window
        # No cache entry, no item with this db_id anywhere:
        mw.file_host_controller._db_id_to_path = {}
        handler.on_file_host_upload_completed(
            999, 'filedot', {'status': 'success'}, '/gal/stuck')
        mw.upload_lifecycle_handler.maybe_notify_gallery_done.assert_called_once_with('/gal/stuck')
        # Assert on the positional path only: the coalesced refresh pass also
        # passes pre-fetched file_host_rows=, which is an implementation
        # detail of the batching. What matters here is WHICH path was used.
        assert mw.progress_tracker.refresh_row_display.call_count == 1
        assert mw.progress_tracker.refresh_row_display.call_args[0][0] == '/gal/stuck'

    def test_completed_seeds_db_id_cache(self, handler):
        mw = handler._main_window
        handler.on_file_host_upload_completed(
            999, 'filedot', {'status': 'success'}, '/gal/stuck')
        assert mw.file_host_controller._db_id_to_path[999] == '/gal/stuck'

    def test_progress_queues_row_refresh_via_signal_path(self, handler):
        mw = handler._main_window
        mw.file_host_controller._db_id_to_path = {}
        handler.on_file_host_upload_progress(999, 'filedot', 50, 100, 1000.0, '/gal/stuck')
        # The refresh coalescer is leading-edge: the first event after idle
        # drains _rows_needing_refresh synchronously, so the set is empty by
        # now. Assert the path actually reached the row refresh instead.
        assert mw.progress_tracker.refresh_row_display.call_args[0][0] == '/gal/stuck'

    def test_started_seeds_db_id_cache(self, handler):
        mw = handler._main_window
        handler.on_file_host_upload_started(999, 'filedot', '/gal/stuck')
        assert mw.file_host_controller._db_id_to_path[999] == '/gal/stuck'

    def test_failed_refreshes_row_via_signal_path(self, handler):
        mw = handler._main_window
        mw.file_host_controller._db_id_to_path = {}
        with patch('src.gui.worker_signal_handler.get_file_host_setting', create=True):
            handler.on_file_host_upload_failed(999, 'filedot', 'boom', '/gal/stuck')
        assert mw.progress_tracker.refresh_row_display.call_count == 1
        assert mw.progress_tracker.refresh_row_display.call_args[0][0] == '/gal/stuck'


class TestControllerRefreshAcceptsExplicitPath:
    """_refresh_file_host_widgets_for_db_id must prefer a caller-supplied path
    over db_id resolution, and seed its cache from it."""

    @pytest.fixture
    def controller(self):
        from src.gui.file_host_controller import FileHostController
        mw = Mock()
        mw.queue_manager = Mock()
        mw.queue_manager.store = Mock()
        mw.gallery_table = Mock()
        mw.path_to_row = {'/given/path': 3}
        mw._file_host_uploads_cache = {}
        return FileHostController(mw)

    def test_uses_explicit_path_without_scanning_queue(self, controller):
        mw = controller._main_window
        mw.gallery_table.table.item.return_value = Mock()
        mw.queue_manager.store.get_file_host_uploads.return_value = []
        with patch('src.gui.file_host_controller.log'):
            controller._refresh_file_host_widgets_for_db_id(42, gallery_path='/given/path')
        mw.queue_manager.get_all_items.assert_not_called()
        mw.queue_manager.store.get_file_host_uploads.assert_called_once_with('/given/path')
        assert controller._db_id_to_path[42] == '/given/path'


class TestAutoRegenAcceptsExplicitPath:
    """BBCode auto-regen must work from the signal path even when no queue
    item carries the real db_id."""

    def test_background_regen_uses_explicit_path(self, qapp):
        from src.processing.artifact_handler import ArtifactHandler
        qm = Mock()
        qm.get_all_items.return_value = []  # no item matches the db_id
        handler = ArtifactHandler(qm, {}, parent_widget=None)
        try:
            handler.should_auto_regenerate_bbcode = Mock(return_value=True)
            handler.regenerate_bbcode_for_gallery = Mock()
            handler._auto_regen_background(999, '/gal/stuck')
            handler.regenerate_bbcode_for_gallery.assert_called_once_with('/gal/stuck', force=False)
        finally:
            handler.shutdown()
