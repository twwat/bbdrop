"""
Comprehensive pytest-qt tests for ImageStatusChecker

Tests thread-safety, state management, dialog close behavior, cancellation,
completion handling, and error handling with proper mocking.

Target: 25-40 tests covering all major functionality.
"""

import pytest
import threading
import time
from unittest.mock import Mock, MagicMock, patch, PropertyMock

from PyQt6.QtCore import pyqtSignal, QObject, Qt


class MockRenameWorker(QObject):
    """Mock rename worker with signals for testing."""

    status_check_progress = pyqtSignal(int, int)
    status_check_completed = pyqtSignal(dict)
    status_check_error = pyqtSignal(str)
    quick_count_available = pyqtSignal(int, int)  # current, total for quick count

    def __init__(self):
        super().__init__()
        self._check_cancelled = False

    def check_image_status(self, galleries_data):
        """Mock check_image_status method."""
        pass

    def cancel_status_check(self):
        """Mock cancel_status_check method."""
        self._check_cancelled = True


class MockGalleryItem:
    """Mock gallery queue item."""

    def __init__(self, path, name="Test Gallery", status="completed", db_id=1):
        self.path = path
        self.name = name
        self.status = status
        self.db_id = db_id


@pytest.fixture
def mock_queue_manager():
    """Create mock queue manager."""
    manager = Mock()
    manager.store = Mock()
    manager.store.get_image_urls_for_galleries = Mock(return_value={})
    manager.store.bulk_update_gallery_imx_status = Mock()
    return manager


@pytest.fixture
def mock_rename_worker():
    """Create mock rename worker with signals."""
    worker = MockRenameWorker()
    # Note: QObject is not a QWidget, so we don't use addWidget
    # The worker will be cleaned up by Python's garbage collection
    return worker


@pytest.fixture
def mock_gallery_table():
    """Create mock gallery table."""
    table = Mock()
    table.rowCount = Mock(return_value=0)
    table.item = Mock(return_value=None)
    table.set_online_imx_status = Mock()
    return table


@pytest.fixture
def mock_parent(qtbot):
    """Create a mock parent widget."""
    from PyQt6.QtWidgets import QWidget
    parent = QWidget()
    qtbot.addWidget(parent)
    return parent


@pytest.fixture
def status_checker(mock_parent, mock_queue_manager, mock_rename_worker, mock_gallery_table):
    """Create ImageStatusChecker instance for testing."""
    from src.gui.dialogs.image_status_checker import ImageStatusChecker

    checker = ImageStatusChecker(
        parent=mock_parent,
        queue_manager=mock_queue_manager,
        rename_worker=mock_rename_worker,
        gallery_table=mock_gallery_table
    )
    return checker


class TestImageStatusCheckerInit:
    """Test ImageStatusChecker initialization."""

    def test_init_creates_instance(self, status_checker):
        """Test basic initialization."""
        assert status_checker is not None
        assert status_checker.dialog is None
        assert status_checker._check_in_progress is False
        assert status_checker._cancelled is False

    def test_init_has_state_lock(self, status_checker):
        """Test that state lock is created."""
        assert hasattr(status_checker, '_state_lock')
        assert isinstance(status_checker._state_lock, type(threading.Lock()))

    def test_init_stores_references(self, status_checker, mock_queue_manager,
                                    mock_rename_worker, mock_gallery_table):
        """Test that references are stored correctly."""
        assert status_checker.queue_manager is mock_queue_manager
        assert status_checker.rename_worker is mock_rename_worker
        assert status_checker.gallery_table is mock_gallery_table


class TestCheckGalleries:
    """Test check_galleries method."""

    def test_check_galleries_empty_paths(self, status_checker):
        """Test check_galleries with empty paths list."""
        status_checker.check_galleries([])

        assert status_checker._check_in_progress is False
        assert status_checker.dialog is None

    def test_check_galleries_sets_check_in_progress(self, status_checker, mock_queue_manager, qtbot):
        """Test that _check_in_progress is set to True on start."""
        # Setup mock to return valid item
        mock_item = MockGalleryItem("/test/path")
        mock_queue_manager.get_item = Mock(return_value=mock_item)
        mock_queue_manager.store.get_image_urls_for_galleries = Mock(
            return_value={"/test/path": [{"url": "http://example.com/img1.jpg"}]}
        )

        with patch('src.gui.dialogs.image_status_checker.ImageStatusDialog') as mock_dialog_class:
            mock_dialog = Mock()
            mock_dialog.isVisible = Mock(return_value=False)
            mock_dialog.finished = Mock()
            mock_dialog.cancelled = Mock()
            mock_dialog_class.return_value = mock_dialog

            status_checker.check_galleries(["/test/path"])

            assert status_checker._check_in_progress is True

    def test_check_galleries_returns_if_dialog_visible(self, status_checker, mock_rename_worker, qtbot):
        """Test that check_galleries returns early if dialog is already visible."""
        mock_dialog = Mock()
        mock_dialog.isVisible = Mock(return_value=True)
        status_checker.dialog = mock_dialog

        # Mock the method so we can check if it was called
        mock_rename_worker.check_image_status = Mock()

        status_checker.check_galleries(["/test/path"])

        # Should not have started a new check
        mock_rename_worker.check_image_status.assert_not_called()

    def test_check_galleries_skips_non_completed(self, status_checker, mock_queue_manager):
        """Test that non-completed galleries are skipped."""
        mock_item = MockGalleryItem("/test/path", status="uploading")
        mock_queue_manager.get_item = Mock(return_value=mock_item)

        with patch('src.gui.dialogs.image_status_checker.QMessageBox') as mock_msgbox:
            status_checker.check_galleries(["/test/path"])

            # Should show "No Images" message
            mock_msgbox.information.assert_called_once()

    def test_check_galleries_skips_no_urls(self, status_checker, mock_queue_manager):
        """Test that galleries without URLs are skipped."""
        mock_item = MockGalleryItem("/test/path")
        mock_queue_manager.get_item = Mock(return_value=mock_item)
        mock_queue_manager.store.get_image_urls_for_galleries = Mock(return_value={"/test/path": []})

        with patch('src.gui.dialogs.image_status_checker.QMessageBox') as mock_msgbox:
            status_checker.check_galleries(["/test/path"])

            # Should show "No Images" message
            mock_msgbox.information.assert_called_once()

    def test_check_galleries_stores_galleries_data(self, status_checker, mock_queue_manager, qtbot):
        """Test that galleries data is stored for result application."""
        mock_item = MockGalleryItem("/test/path", name="Gallery Name", db_id=42)
        mock_queue_manager.get_item = Mock(return_value=mock_item)
        mock_queue_manager.store.get_image_urls_for_galleries = Mock(
            return_value={"/test/path": [{"url": "http://example.com/img1.jpg"}]}
        )

        with patch('src.gui.dialogs.image_status_checker.ImageStatusDialog') as mock_dialog_class:
            mock_dialog = Mock()
            mock_dialog.isVisible = Mock(return_value=False)
            mock_dialog.finished = Mock()
            mock_dialog.cancelled = Mock()
            mock_dialog_class.return_value = mock_dialog

            status_checker.check_galleries(["/test/path"])

            assert len(status_checker._galleries_data) == 1
            assert status_checker._galleries_data[0]['path'] == "/test/path"
            assert status_checker._galleries_data[0]['db_id'] == 42

    def test_check_galleries_starts_worker(self, status_checker, mock_queue_manager, mock_rename_worker, qtbot):
        """Test that worker check_image_status is called."""
        mock_item = MockGalleryItem("/test/path")
        mock_queue_manager.get_item = Mock(return_value=mock_item)
        mock_queue_manager.store.get_image_urls_for_galleries = Mock(
            return_value={"/test/path": [{"url": "http://example.com/img1.jpg"}]}
        )

        with patch('src.gui.dialogs.image_status_checker.ImageStatusDialog') as mock_dialog_class:
            mock_dialog = Mock()
            mock_dialog.isVisible = Mock(return_value=False)
            mock_dialog.finished = Mock()
            mock_dialog.cancelled = Mock()
            mock_dialog_class.return_value = mock_dialog

            # Use a mock that we can verify
            mock_rename_worker.check_image_status = Mock()

            status_checker.check_galleries(["/test/path"])

            mock_rename_worker.check_image_status.assert_called_once()

    def test_check_galleries_records_start_time(self, status_checker, mock_queue_manager, qtbot):
        """Test that start time is recorded for timing."""
        mock_item = MockGalleryItem("/test/path")
        mock_queue_manager.get_item = Mock(return_value=mock_item)
        mock_queue_manager.store.get_image_urls_for_galleries = Mock(
            return_value={"/test/path": [{"url": "http://example.com/img1.jpg"}]}
        )

        with patch('src.gui.dialogs.image_status_checker.ImageStatusDialog') as mock_dialog_class:
            mock_dialog = Mock()
            mock_dialog.isVisible = Mock(return_value=False)
            mock_dialog.finished = Mock()
            mock_dialog.cancelled = Mock()
            mock_dialog_class.return_value = mock_dialog

            before = time.time()
            status_checker.check_galleries(["/test/path"])
            after = time.time()

            assert before <= status_checker._start_time <= after


class TestCancelledFlagPreventsResultProcessing:
    """Test that cancelled flag prevents result processing."""

    def test_cancelled_flag_prevents_result_processing(self, status_checker, qtbot):
        """Test that results are discarded when cancelled is True."""
        # Set up initial state
        with status_checker._state_lock:
            status_checker._check_in_progress = True
            status_checker._cancelled = True
            status_checker._start_time = time.time()

        results = {"/test/path": {"online": 5, "total": 10}}

        # Process completion
        status_checker._on_completed(results)

        # Should NOT have updated database
        status_checker.queue_manager.store.bulk_update_gallery_imx_status.assert_not_called()

        # Check state was reset
        assert status_checker._check_in_progress is False

    def test_not_cancelled_processes_results(self, status_checker, mock_gallery_table, qtbot):
        """Test that results are processed when not cancelled."""
        # Set up initial state
        with status_checker._state_lock:
            status_checker._check_in_progress = True
            status_checker._cancelled = False
            status_checker._start_time = time.time() - 1.0  # 1 second ago

        mock_gallery_table.rowCount = Mock(return_value=0)

        results = {"/test/path": {"online": 5, "total": 10}}

        # Process completion
        status_checker._on_completed(results)

        # Should have updated database via bulk update
        status_checker.queue_manager.store.bulk_update_gallery_imx_status.assert_called_once()

        # Verify the call arguments
        call_args = status_checker.queue_manager.store.bulk_update_gallery_imx_status.call_args[0][0]
        assert len(call_args) == 1  # One gallery updated
        assert call_args[0][0] == '/test/path'  # path
        assert 'Partial' in call_args[0][1]  # status_text


class TestDialogCloseDuringCheck:
    """Test dialog close behavior during active check."""

    def test_dialog_close_during_check_continues_background(self, status_checker, qtbot):
        """Test that closing dialog during check allows background processing."""
        # Set check in progress
        with status_checker._state_lock:
            status_checker._check_in_progress = True

        mock_dialog = Mock()
        status_checker.dialog = mock_dialog

        # Simulate dialog closed (finished signal)
        status_checker._on_dialog_finished(0)

        # Dialog should be cleared but signals not disconnected yet
        assert status_checker.dialog is None

    def test_dialog_close_when_idle_cleans_up(self, status_checker, qtbot):
        """Test that closing dialog when idle cleans up signals."""
        # Set check NOT in progress
        with status_checker._state_lock:
            status_checker._check_in_progress = False

        mock_dialog = Mock()
        status_checker.dialog = mock_dialog

        # Track cleanup
        cleanup_called = []

        def mock_cleanup():
            cleanup_called.append(True)

        status_checker._cleanup_connections = mock_cleanup

        # Simulate dialog closed
        status_checker._on_dialog_finished(0)

        assert status_checker.dialog is None
        assert len(cleanup_called) == 1


class TestResultsAppliedWithoutDialog:
    """Test that database/table updated even when dialog is None."""

    def test_results_applied_even_without_dialog(self, status_checker, mock_gallery_table, qtbot):
        """Test that database and table get updated when dialog is None."""
        # Set up state
        with status_checker._state_lock:
            status_checker._check_in_progress = True
            status_checker._cancelled = False
            status_checker._start_time = time.time() - 1.0

        status_checker.dialog = None  # Dialog was closed
        mock_gallery_table.rowCount = Mock(return_value=0)

        results = {"/test/path": {"online": 5, "total": 10}}

        # Process completion
        status_checker._on_completed(results)

        # Should still update database via bulk update
        status_checker.queue_manager.store.bulk_update_gallery_imx_status.assert_called_once()

        # Verify the call arguments
        call_args = status_checker.queue_manager.store.bulk_update_gallery_imx_status.call_args[0][0]
        assert len(call_args) == 1  # One gallery updated
        assert call_args[0][0] == '/test/path'  # path


class TestCancellation:
    """Test cancellation behavior."""

    def test_on_cancel_sets_cancelled_flag(self, status_checker, qtbot):
        """Test that _on_cancel sets the cancelled flag."""
        status_checker._on_cancel()

        with status_checker._state_lock:
            assert status_checker._cancelled is True

    def test_on_cancel_resets_check_in_progress(self, status_checker, qtbot):
        """Test that _on_cancel resets check_in_progress."""
        with status_checker._state_lock:
            status_checker._check_in_progress = True

        status_checker._on_cancel()

        with status_checker._state_lock:
            assert status_checker._check_in_progress is False

    def test_on_cancel_calls_worker_cancel(self, status_checker, mock_rename_worker, qtbot):
        """Test that _on_cancel calls worker's cancel_status_check."""
        mock_rename_worker.cancel_status_check = Mock()

        status_checker._on_cancel()

        mock_rename_worker.cancel_status_check.assert_called_once()

    def test_cleanup_called_on_cancel(self, status_checker, qtbot):
        """Test that signals are disconnected on cancel."""
        cleanup_called = []

        def mock_cleanup():
            cleanup_called.append(True)

        status_checker._cleanup_connections = mock_cleanup

        status_checker._on_cancel()

        assert len(cleanup_called) == 1


class TestCompletion:
    """Test completion behavior."""

    def test_on_completed_updates_database(self, status_checker, mock_queue_manager, mock_gallery_table, qtbot):
        """Test that _on_completed updates the database via bulk update."""
        # Set up state
        with status_checker._state_lock:
            status_checker._check_in_progress = True
            status_checker._cancelled = False
            status_checker._start_time = time.time() - 1.0

        # Set up table to find the row
        mock_name_item = Mock()
        mock_name_item.data = Mock(return_value="/test/path")
        mock_gallery_table.rowCount = Mock(return_value=1)
        mock_gallery_table.item = Mock(return_value=mock_name_item)

        results = {"/test/path": {"online": 8, "total": 10}}

        status_checker._on_completed(results)

        # Should update database with status via bulk update
        mock_queue_manager.store.bulk_update_gallery_imx_status.assert_called_once()

        # Verify the call arguments
        call_args = mock_queue_manager.store.bulk_update_gallery_imx_status.call_args[0][0]
        assert len(call_args) == 1  # One gallery updated
        assert call_args[0][0] == "/test/path"  # path
        assert "Partial" in call_args[0][1]  # status_text contains "Partial"

    def test_on_completed_updates_table(self, status_checker, mock_gallery_table, qtbot):
        """Test that _on_completed updates the table display via O(1) path lookup."""
        from src.gui.widgets.gallery_table import GalleryTableWidget

        # Set up state
        with status_checker._state_lock:
            status_checker._check_in_progress = True
            status_checker._cancelled = False
            status_checker._start_time = time.time() - 1.0

        # Set up table mock with path-to-row mapping support
        mock_name_item = Mock()
        mock_name_item.data = Mock(return_value="/test/path")
        mock_gallery_table.rowCount = Mock(return_value=1)
        mock_gallery_table.item = Mock(return_value=mock_name_item)

        # Patch the constant
        with patch.object(GalleryTableWidget, 'COL_NAME', 1):
            results = {"/test/path": {"online": 10, "total": 10}}

            status_checker._on_completed(results)

            # Should update table display
            mock_gallery_table.set_online_imx_status.assert_called_once()

    def test_on_completed_resets_check_in_progress(self, status_checker, mock_gallery_table, qtbot):
        """Test that _on_completed resets check_in_progress to False."""
        # Set up state
        with status_checker._state_lock:
            status_checker._check_in_progress = True
            status_checker._cancelled = False
            status_checker._start_time = time.time() - 1.0

        mock_gallery_table.rowCount = Mock(return_value=0)

        status_checker._on_completed({})

        with status_checker._state_lock:
            assert status_checker._check_in_progress is False

    def test_on_completed_clears_dialog_reference(self, status_checker, mock_gallery_table, qtbot):
        """Test that _on_completed clears dialog reference."""
        # Set up state
        with status_checker._state_lock:
            status_checker._check_in_progress = True
            status_checker._cancelled = False
            status_checker._start_time = time.time() - 1.0

        mock_gallery_table.rowCount = Mock(return_value=0)
        status_checker.dialog = Mock()

        status_checker._on_completed({})

        assert status_checker.dialog is None

    def test_on_completed_logs_statistics(self, status_checker, mock_gallery_table, qtbot):
        """Test that _on_completed logs proper statistics with timing."""
        # Set up state
        with status_checker._state_lock:
            status_checker._check_in_progress = True
            status_checker._cancelled = False
            status_checker._start_time = time.time() - 2.0  # 2 seconds ago

        mock_gallery_table.rowCount = Mock(return_value=0)

        with patch('src.gui.dialogs.image_status_checker.log') as mock_log:
            results = {"/test/path": {"online": 5, "total": 10}}

            status_checker._on_completed(results)

            # Should log with timing info - find the statistics log message
            # (contains "Found online" and "sec") among all the DEBUG TIMING logs
            mock_log.assert_called()
            stats_message = None
            for call in mock_log.call_args_list:
                msg = call[0][0]
                if "Found online" in msg:
                    stats_message = msg
                    break
            assert stats_message is not None, "Statistics log message not found"
            assert "sec" in stats_message.lower()  # Elapsed time


class TestErrorHandling:
    """Test error handling."""

    def test_on_error_resets_state(self, status_checker, qtbot):
        """Test that _on_error resets _check_in_progress to False."""
        with status_checker._state_lock:
            status_checker._check_in_progress = True

        status_checker._on_error("Test error")

        with status_checker._state_lock:
            assert status_checker._check_in_progress is False

    def test_on_error_shows_message_box_with_dialog(self, status_checker, mock_parent, qtbot):
        """Test that _on_error shows error message if dialog exists."""
        mock_dialog = Mock()
        status_checker.dialog = mock_dialog

        with patch('src.gui.dialogs.image_status_checker.QMessageBox') as mock_msgbox:
            status_checker._on_error("Test error message")

            mock_msgbox.critical.assert_called_once()
            call_args = mock_msgbox.critical.call_args
            assert "Test error message" in str(call_args)

    def test_on_error_hides_progress(self, status_checker, qtbot):
        """Test that _on_error hides progress on dialog."""
        mock_dialog = Mock()
        status_checker.dialog = mock_dialog

        with patch('src.gui.dialogs.image_status_checker.QMessageBox'):
            status_checker._on_error("Error")

            mock_dialog.show_progress.assert_called_with(False)

    def test_cleanup_called_on_error(self, status_checker, qtbot):
        """Test that signals are disconnected on error."""
        cleanup_called = []

        def mock_cleanup():
            cleanup_called.append(True)

        status_checker._cleanup_connections = mock_cleanup

        status_checker._on_error("Test error")

        assert len(cleanup_called) == 1

    def test_on_error_clears_dialog(self, status_checker, qtbot):
        """Test that _on_error clears dialog reference."""
        status_checker.dialog = Mock()

        with patch('src.gui.dialogs.image_status_checker.QMessageBox'):
            status_checker._on_error("Error")

            assert status_checker.dialog is None

    def test_on_error_logs_message(self, status_checker, qtbot):
        """Test that _on_error logs the error message."""
        with patch('src.gui.dialogs.image_status_checker.log') as mock_log:
            status_checker._on_error("Test error message")

            mock_log.assert_called()
            log_args = str(mock_log.call_args)
            assert "Test error message" in log_args


class TestProgressUpdates:
    """Test progress update handling."""

    def test_on_progress_updates_dialog(self, status_checker, qtbot):
        """Test that _on_progress updates the dialog."""
        mock_dialog = Mock()
        status_checker.dialog = mock_dialog

        status_checker._on_progress(5, 10)

        mock_dialog.update_progress.assert_called_once_with(5, 10)

    def test_on_progress_does_nothing_without_dialog(self, status_checker, qtbot):
        """Test that _on_progress does nothing when dialog is None."""
        status_checker.dialog = None

        # Should not raise
        status_checker._on_progress(5, 10)


class TestInlineTableUpdate:
    """Test inline table update logic in _on_completed (replaces TestTableDisplayUpdate)."""

    def test_inline_update_finds_row_via_path_index(self, status_checker, mock_gallery_table, qtbot):
        """Test that _on_completed finds the correct row via O(1) path lookup."""
        from src.gui.widgets.gallery_table import GalleryTableWidget

        # Set up state
        with status_checker._state_lock:
            status_checker._check_in_progress = True
            status_checker._cancelled = False
            status_checker._start_time = time.time() - 1.0

        # Set up mock - path-to-row index is built from table items
        mock_name_item = Mock()
        mock_name_item.data = Mock(return_value="/test/path")
        mock_gallery_table.rowCount = Mock(return_value=1)
        mock_gallery_table.item = Mock(return_value=mock_name_item)

        with patch.object(GalleryTableWidget, 'COL_NAME', 1):
            results = {"/test/path": {"online": 5, "total": 10}}

            status_checker._on_completed(results)

            # Should call set_online_imx_status with row 0
            mock_gallery_table.set_online_imx_status.assert_called_once()
            call_args = mock_gallery_table.set_online_imx_status.call_args
            assert call_args[0][0] == 0  # row
            assert call_args[0][1] == 5  # online
            assert call_args[0][2] == 10  # total

    def test_inline_update_skips_wrong_path(self, status_checker, mock_gallery_table, qtbot):
        """Test that _on_completed skips rows with wrong path."""
        from src.gui.widgets.gallery_table import GalleryTableWidget

        # Set up state
        with status_checker._state_lock:
            status_checker._check_in_progress = True
            status_checker._cancelled = False
            status_checker._start_time = time.time() - 1.0

        # Set up mock to return different path
        mock_name_item = Mock()
        mock_name_item.data = Mock(return_value="/other/path")
        mock_gallery_table.rowCount = Mock(return_value=1)
        mock_gallery_table.item = Mock(return_value=mock_name_item)

        with patch.object(GalleryTableWidget, 'COL_NAME', 1):
            results = {"/test/path": {"online": 5, "total": 10}}

            status_checker._on_completed(results)

            # Should not call set_online_imx_status for wrong path
            mock_gallery_table.set_online_imx_status.assert_not_called()

    def test_inline_update_handles_multiple_galleries(self, status_checker, mock_gallery_table, qtbot):
        """Test that _on_completed handles multiple galleries efficiently."""
        from src.gui.widgets.gallery_table import GalleryTableWidget

        # Set up state
        with status_checker._state_lock:
            status_checker._check_in_progress = True
            status_checker._cancelled = False
            status_checker._start_time = time.time() - 1.0

        # Set up mock with multiple rows
        def item_side_effect(row, col):
            mock_item = Mock()
            paths = ["/path/gallery1", "/path/gallery2", "/path/gallery3"]
            mock_item.data = Mock(return_value=paths[row] if row < len(paths) else None)
            return mock_item

        mock_gallery_table.rowCount = Mock(return_value=3)
        mock_gallery_table.item = Mock(side_effect=item_side_effect)

        with patch.object(GalleryTableWidget, 'COL_NAME', 1):
            results = {
                "/path/gallery1": {"online": 10, "total": 10},
                "/path/gallery2": {"online": 5, "total": 10},
                "/path/gallery3": {"online": 0, "total": 10},
            }

            status_checker._on_completed(results)

            # Should call set_online_imx_status for each found row
            assert mock_gallery_table.set_online_imx_status.call_count == 3


class TestCleanupConnections:
    """Test _cleanup_connections method."""

    def test_cleanup_disconnects_signals(self, status_checker, mock_rename_worker, qtbot):
        """Test that cleanup disconnects all signals."""
        # First connect signals
        mock_rename_worker.status_check_progress.connect(status_checker._on_progress)
        mock_rename_worker.status_check_completed.connect(status_checker._on_completed)
        mock_rename_worker.status_check_error.connect(status_checker._on_error)

        # Then cleanup
        status_checker._cleanup_connections()

        # Signals should be disconnected (no error on second disconnect)
        # Calling cleanup again should not raise
        status_checker._cleanup_connections()

    def test_cleanup_handles_already_disconnected(self, status_checker, qtbot):
        """Test that cleanup handles already disconnected signals gracefully."""
        # Should not raise even if signals were never connected
        status_checker._cleanup_connections()


class TestThreadSafety:
    """Test thread-safety of state management."""

    def test_state_lock_protects_check_in_progress(self, status_checker, qtbot):
        """Test that state lock protects _check_in_progress access."""
        results = []

        def reader():
            for _ in range(100):
                with status_checker._state_lock:
                    results.append(status_checker._check_in_progress)

        def writer():
            for _ in range(100):
                with status_checker._state_lock:
                    status_checker._check_in_progress = not status_checker._check_in_progress

        threads = [
            threading.Thread(target=reader),
            threading.Thread(target=reader),
            threading.Thread(target=writer),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All operations should complete without error
        assert len(results) == 200

    def test_concurrent_cancel_and_complete(self, status_checker, mock_gallery_table, qtbot):
        """Test concurrent cancel and completion handling."""
        # Set up initial state
        with status_checker._state_lock:
            status_checker._check_in_progress = True
            status_checker._cancelled = False
            status_checker._start_time = time.time()

        mock_gallery_table.rowCount = Mock(return_value=0)

        def cancel_thread():
            time.sleep(0.001)  # Small delay
            status_checker._on_cancel()

        def complete_thread():
            status_checker._on_completed({"/test": {"online": 1, "total": 1}})

        t1 = threading.Thread(target=cancel_thread)
        t2 = threading.Thread(target=complete_thread)

        t1.start()
        t2.start()

        t1.join()
        t2.join()

        # State should be consistent
        with status_checker._state_lock:
            assert status_checker._check_in_progress is False


class TestStatusTextGeneration:
    """Test status text generation in _on_completed."""

    def test_online_status_text(self, status_checker, mock_gallery_table, qtbot):
        """Test status text for fully online galleries."""
        # Set up state
        with status_checker._state_lock:
            status_checker._check_in_progress = True
            status_checker._cancelled = False
            status_checker._start_time = time.time()

        mock_gallery_table.rowCount = Mock(return_value=0)

        results = {"/test/path": {"online": 10, "total": 10}}

        status_checker._on_completed(results)

        # Check the status text passed to database via bulk update
        status_checker.queue_manager.store.bulk_update_gallery_imx_status.assert_called_once()
        call_args = status_checker.queue_manager.store.bulk_update_gallery_imx_status.call_args[0][0]
        status_text = call_args[0][1]  # First tuple's status_text
        assert "Online" in status_text
        assert "10/10" in status_text

    def test_offline_status_text(self, status_checker, mock_gallery_table, qtbot):
        """Test status text for fully offline galleries."""
        with status_checker._state_lock:
            status_checker._check_in_progress = True
            status_checker._cancelled = False
            status_checker._start_time = time.time()

        mock_gallery_table.rowCount = Mock(return_value=0)

        results = {"/test/path": {"online": 0, "total": 10}}

        status_checker._on_completed(results)

        status_checker.queue_manager.store.bulk_update_gallery_imx_status.assert_called_once()
        call_args = status_checker.queue_manager.store.bulk_update_gallery_imx_status.call_args[0][0]
        status_text = call_args[0][1]
        assert "Offline" in status_text
        assert "0/10" in status_text

    def test_partial_status_text(self, status_checker, mock_gallery_table, qtbot):
        """Test status text for partially online galleries."""
        with status_checker._state_lock:
            status_checker._check_in_progress = True
            status_checker._cancelled = False
            status_checker._start_time = time.time()

        mock_gallery_table.rowCount = Mock(return_value=0)

        results = {"/test/path": {"online": 5, "total": 10}}

        status_checker._on_completed(results)

        status_checker.queue_manager.store.bulk_update_gallery_imx_status.assert_called_once()
        call_args = status_checker.queue_manager.store.bulk_update_gallery_imx_status.call_args[0][0]
        status_text = call_args[0][1]
        assert "Partial" in status_text
        assert "5/10" in status_text

    def test_empty_gallery_status_text(self, status_checker, mock_gallery_table, qtbot):
        """Test status text for galleries with no images."""
        with status_checker._state_lock:
            status_checker._check_in_progress = True
            status_checker._cancelled = False
            status_checker._start_time = time.time()

        mock_gallery_table.rowCount = Mock(return_value=0)

        results = {"/test/path": {"online": 0, "total": 0}}

        status_checker._on_completed(results)

        status_checker.queue_manager.store.bulk_update_gallery_imx_status.assert_called_once()
        call_args = status_checker.queue_manager.store.bulk_update_gallery_imx_status.call_args[0][0]
        status_text = call_args[0][1]
        # Empty status text for galleries with 0 total
        assert status_text == ""


class TestDatabaseUpdateFailure:
    """Test handling of database update failures."""

    def test_database_update_exception_logged(self, status_checker, mock_queue_manager, mock_gallery_table, qtbot):
        """Test that database update exceptions are logged."""
        with status_checker._state_lock:
            status_checker._check_in_progress = True
            status_checker._cancelled = False
            status_checker._start_time = time.time()

        mock_gallery_table.rowCount = Mock(return_value=0)
        mock_queue_manager.store.bulk_update_gallery_imx_status = Mock(side_effect=Exception("DB Error"))

        with patch('src.gui.dialogs.image_status_checker.log') as mock_log:
            results = {"/test/path": {"online": 5, "total": 10}}

            # Should not raise
            status_checker._on_completed(results)

            # Error should be logged
            error_logged = any("error" in str(call).lower() for call in mock_log.call_args_list)
            assert error_logged


class TestBatchDatabaseUpdate:
    """Test batch database update functionality."""

    def test_batch_update_called_with_all_galleries(self, status_checker, mock_gallery_table, qtbot):
        """Test that bulk_update_gallery_imx_status is called with all galleries."""
        with status_checker._state_lock:
            status_checker._check_in_progress = True
            status_checker._cancelled = False
            status_checker._start_time = time.time()

        mock_gallery_table.rowCount = Mock(return_value=0)

        results = {
            "/path/gallery1": {"online": 10, "total": 10},
            "/path/gallery2": {"online": 5, "total": 10},
            "/path/gallery3": {"online": 0, "total": 10},
        }

        status_checker._on_completed(results)

        # Should call bulk update once with all galleries
        status_checker.queue_manager.store.bulk_update_gallery_imx_status.assert_called_once()

        call_args = status_checker.queue_manager.store.bulk_update_gallery_imx_status.call_args[0][0]
        assert len(call_args) == 3  # All three galleries

        # Verify each tuple structure (path, status_text, timestamp)
        paths = {item[0] for item in call_args}
        assert paths == {"/path/gallery1", "/path/gallery2", "/path/gallery3"}

    def test_batch_update_includes_timestamp(self, status_checker, mock_gallery_table, qtbot):
        """Test that batch update includes timestamp for each gallery."""
        with status_checker._state_lock:
            status_checker._check_in_progress = True
            status_checker._cancelled = False
            status_checker._start_time = time.time()

        mock_gallery_table.rowCount = Mock(return_value=0)

        results = {"/test/path": {"online": 5, "total": 10}}

        status_checker._on_completed(results)

        call_args = status_checker.queue_manager.store.bulk_update_gallery_imx_status.call_args[0][0]
        assert len(call_args) == 1
        assert len(call_args[0]) == 3  # (path, status_text, timestamp)
        assert isinstance(call_args[0][2], int)  # timestamp is int

    def test_batch_update_not_called_for_empty_results(self, status_checker, mock_gallery_table, qtbot):
        """Test that bulk_update_gallery_imx_status is not called for empty results."""
        with status_checker._state_lock:
            status_checker._check_in_progress = True
            status_checker._cancelled = False
            status_checker._start_time = time.time()

        mock_gallery_table.rowCount = Mock(return_value=0)

        results = {}  # Empty results

        status_checker._on_completed(results)

        # Should not call bulk update for empty results
        status_checker.queue_manager.store.bulk_update_gallery_imx_status.assert_not_called()
