#!/usr/bin/env python3
"""
Unit tests for FileHostController - file host upload operations.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from PyQt6.QtCore import QMutex, Qt

from src.gui.file_host_controller import FileHostController
from src.storage.queue_manager import GalleryQueueItem


class TestFileHostControllerConstruction:
    """Test suite for FileHostController construction."""

    @pytest.fixture
    def mock_main_window(self):
        """Create a mock main window with required attributes."""
        mw = Mock()
        mw.queue_manager = Mock()
        mw.queue_manager.mutex = QMutex()
        mw.queue_manager.items = {}
        mw.queue_manager.store = Mock()
        mw.gallery_table = Mock()
        mw.path_to_row = {}
        mw.row_to_path = {}
        mw.worker_signal_handler = Mock()
        mw._file_host_startup_complete = False
        mw._scan_status_cache = {}
        mw._file_host_uploads_cache = {}
        mw.gallery_queue_controller = Mock()
        return mw

    def test_construction_with_mock_main_window(self, mock_main_window):
        """Verify controller can be constructed with a mock main window."""
        controller = FileHostController(mock_main_window)
        assert controller._main_window is mock_main_window

    def test_controller_initializes_db_id_to_path_cache(self, mock_main_window):
        """Verify controller initializes an empty _db_id_to_path cache."""
        controller = FileHostController(mock_main_window)
        assert controller._db_id_to_path == {}


class TestStartUploadForItem:
    """Test suite for start_upload_for_item method."""

    @pytest.fixture
    def mock_main_window(self):
        """Create a mock main window with required attributes."""
        mw = Mock()
        mw.queue_manager = Mock()
        mw.queue_manager.mutex = QMutex()
        mw.queue_manager.items = {}
        mw.queue_manager.store = Mock()
        mw._update_specific_gallery_display = Mock()
        return mw

    @pytest.fixture
    def controller(self, mock_main_window):
        """Create controller with mocked main window."""
        return FileHostController(mock_main_window)

    def test_starts_ready_item(self, controller, mock_main_window):
        """Verify start_upload_for_item starts a ready item and returns True."""
        item = GalleryQueueItem(path="/test/gallery")
        item.status = "ready"
        mock_main_window.queue_manager.get_item.return_value = item
        mock_main_window.queue_manager.start_item.return_value = True

        with patch('src.gui.file_host_controller.log'):
            result = controller.start_upload_for_item("/test/gallery")

        assert result is True
        mock_main_window.queue_manager.start_item.assert_called_once_with("/test/gallery")
        mock_main_window._update_specific_gallery_display.assert_called_once_with("/test/gallery")

    def test_starts_paused_item(self, controller, mock_main_window):
        """Verify start_upload_for_item starts a paused item."""
        item = GalleryQueueItem(path="/test/gallery")
        item.status = "paused"
        mock_main_window.queue_manager.get_item.return_value = item
        mock_main_window.queue_manager.start_item.return_value = True

        with patch('src.gui.file_host_controller.log'):
            result = controller.start_upload_for_item("/test/gallery")

        assert result is True

    def test_starts_incomplete_item(self, controller, mock_main_window):
        """Verify start_upload_for_item starts an incomplete item."""
        item = GalleryQueueItem(path="/test/gallery")
        item.status = "incomplete"
        mock_main_window.queue_manager.get_item.return_value = item
        mock_main_window.queue_manager.start_item.return_value = True

        with patch('src.gui.file_host_controller.log'):
            result = controller.start_upload_for_item("/test/gallery")

        assert result is True

    def test_starts_upload_failed_item(self, controller, mock_main_window):
        """Verify start_upload_for_item starts an upload_failed item."""
        item = GalleryQueueItem(path="/test/gallery")
        item.status = "upload_failed"
        mock_main_window.queue_manager.get_item.return_value = item
        mock_main_window.queue_manager.start_item.return_value = True

        with patch('src.gui.file_host_controller.log'):
            result = controller.start_upload_for_item("/test/gallery")

        assert result is True

    def test_rejects_uploading_item(self, controller, mock_main_window):
        """Verify start_upload_for_item rejects an uploading item."""
        item = GalleryQueueItem(path="/test/gallery")
        item.status = "uploading"
        mock_main_window.queue_manager.get_item.return_value = item

        with patch('src.gui.file_host_controller.log'):
            result = controller.start_upload_for_item("/test/gallery")

        assert result is False
        mock_main_window.queue_manager.start_item.assert_not_called()

    def test_rejects_completed_item(self, controller, mock_main_window):
        """Verify start_upload_for_item rejects a completed item."""
        item = GalleryQueueItem(path="/test/gallery")
        item.status = "completed"
        mock_main_window.queue_manager.get_item.return_value = item

        with patch('src.gui.file_host_controller.log'):
            result = controller.start_upload_for_item("/test/gallery")

        assert result is False

    def test_returns_false_for_missing_item(self, controller, mock_main_window):
        """Verify start_upload_for_item returns False for non-existent item."""
        mock_main_window.queue_manager.get_item.return_value = None

        with patch('src.gui.file_host_controller.log'):
            result = controller.start_upload_for_item("/nonexistent/gallery")

        assert result is False

    def test_returns_false_when_start_fails(self, controller, mock_main_window):
        """Verify start_upload_for_item returns False when queue_manager.start_item fails."""
        item = GalleryQueueItem(path="/test/gallery")
        item.status = "ready"
        mock_main_window.queue_manager.get_item.return_value = item
        mock_main_window.queue_manager.start_item.return_value = False

        with patch('src.gui.file_host_controller.log'):
            result = controller.start_upload_for_item("/test/gallery")

        assert result is False

    def test_handles_exception_gracefully(self, controller, mock_main_window):
        """Verify start_upload_for_item handles exceptions and returns False."""
        mock_main_window.queue_manager.get_item.side_effect = Exception("DB error")

        with patch('src.gui.file_host_controller.log'):
            result = controller.start_upload_for_item("/test/gallery")

        assert result is False


class TestRefreshFileHostWidgetsForDbId:
    """Test suite for _refresh_file_host_widgets_for_db_id method."""

    @pytest.fixture
    def mock_main_window(self):
        """Create a mock main window with required attributes."""
        mw = Mock()
        mw.queue_manager = Mock()
        mw.queue_manager.mutex = QMutex()
        mw.queue_manager.items = {}
        mw.queue_manager.store = Mock()
        mw.gallery_table = Mock()
        mw.path_to_row = {}
        mw.row_to_path = {}
        mw._file_host_uploads_cache = {}
        return mw

    @pytest.fixture
    def controller(self, mock_main_window):
        """Create controller with mocked main window."""
        return FileHostController(mock_main_window)

    def test_skips_unknown_db_id_without_crashing(self, controller, mock_main_window):
        """Verify _refresh_file_host_widgets_for_db_id handles unknown db_id gracefully."""
        mock_main_window.queue_manager.get_all_items.return_value = []

        with patch('src.gui.file_host_controller.log'):
            # Should not raise
            controller._refresh_file_host_widgets_for_db_id(99999)

    def test_skips_when_path_not_in_table(self, controller, mock_main_window):
        """Verify method exits when path has no corresponding table row."""
        # Cache a path for the db_id
        controller._db_id_to_path[42] = "/test/gallery"
        mock_main_window.path_to_row = {}  # No row mapping

        with patch('src.gui.file_host_controller.log'):
            controller._refresh_file_host_widgets_for_db_id(42)

        # Should not crash, should not call get_file_host_uploads
        mock_main_window.queue_manager.store.get_file_host_uploads.assert_not_called()

    def test_uses_cached_path(self, controller, mock_main_window):
        """Verify method uses cached db_id -> path mapping."""
        controller._db_id_to_path[10] = "/cached/gallery"
        mock_main_window.path_to_row = {"/cached/gallery": 0}

        # Mock table item
        mock_item = Mock()
        mock_main_window.gallery_table.table.item.return_value = mock_item
        mock_main_window.queue_manager.store.get_file_host_uploads.return_value = []

        with patch('src.gui.file_host_controller.log'):
            controller._refresh_file_host_widgets_for_db_id(10)

        mock_main_window.queue_manager.store.get_file_host_uploads.assert_called_once_with("/cached/gallery")

    def test_falls_back_to_queue_search_on_cache_miss(self, controller, mock_main_window):
        """Verify method searches queue items when db_id not in cache."""
        item = GalleryQueueItem(path="/found/gallery")
        item.db_id = 7
        mock_main_window.queue_manager.get_all_items.return_value = [item]
        mock_main_window.path_to_row = {"/found/gallery": 1}

        mock_table_item = Mock()
        mock_main_window.gallery_table.table.item.return_value = mock_table_item
        mock_main_window.queue_manager.store.get_file_host_uploads.return_value = []

        with patch('src.gui.file_host_controller.log'):
            controller._refresh_file_host_widgets_for_db_id(7)

        # Should have cached the path
        assert controller._db_id_to_path[7] == "/found/gallery"


class TestHandleActionButton:
    """Test suite for _handle_action_button method."""

    @pytest.fixture
    def mock_main_window(self):
        """Create a mock main window with required attributes."""
        mw = Mock()
        mw.start_single_item = Mock()
        mw.gallery_queue_controller = Mock()
        mw.view_bbcode_files = Mock()
        mw._show_error_details = Mock()
        return mw

    @pytest.fixture
    def controller(self, mock_main_window):
        """Create controller with mocked main window."""
        return FileHostController(mock_main_window)

    def test_start_action(self, controller, mock_main_window):
        """Verify 'start' action delegates to start_single_item."""
        controller._handle_action_button("/test", "start")
        mock_main_window.start_single_item.assert_called_once_with("/test")

    def test_stop_action(self, controller, mock_main_window):
        """Verify 'stop' action delegates to gallery_queue_controller.stop_gallery."""
        controller._handle_action_button("/test", "stop")
        mock_main_window.gallery_queue_controller.stop_gallery.assert_called_once_with("/test")

    def test_cancel_action(self, controller, mock_main_window):
        """Verify 'cancel' action delegates to gallery_queue_controller.cancel_gallery."""
        controller._handle_action_button("/test", "cancel")
        mock_main_window.gallery_queue_controller.cancel_gallery.assert_called_once_with("/test")

    def test_view_action(self, controller, mock_main_window):
        """Verify 'view' action delegates to view_bbcode_files."""
        controller._handle_action_button("/test", "view")
        mock_main_window.view_bbcode_files.assert_called_once_with("/test")

    def test_view_error_action(self, controller, mock_main_window):
        """Verify 'view_error' action delegates to _show_error_details."""
        controller._handle_action_button("/test", "view_error")
        mock_main_window._show_error_details.assert_called_once_with("/test")


class TestOnFileHostsEnabledChanged:
    """Test suite for _on_file_hosts_enabled_changed method."""

    @pytest.fixture
    def mock_main_window(self):
        mw = Mock()
        mw.queue_manager = Mock()
        mw.queue_manager.mutex = QMutex()
        mw.queue_manager.items = {}
        mw.queue_manager.store = Mock()
        mw.gallery_table = Mock()
        mw.gallery_table.table = Mock()
        mw.path_to_row = {}
        mw.row_to_path = {}
        mw.worker_signal_handler = Mock()
        mw._file_host_startup_complete = False
        return mw

    @pytest.fixture
    def controller(self, mock_main_window):
        return FileHostController(mock_main_window)

    def test_skips_during_startup(self, controller, mock_main_window):
        """Verify _on_file_hosts_enabled_changed skips when startup not complete."""
        mock_main_window._file_host_startup_complete = False

        with patch('src.gui.file_host_controller.log'):
            controller._on_file_hosts_enabled_changed(["host1", "host2"])

        # Should not touch queue_manager or gallery_table since startup not complete
        mock_main_window.queue_manager.get_all_items.assert_not_called()

    def test_refreshes_after_startup(self, controller, mock_main_window):
        """Verify _on_file_hosts_enabled_changed refreshes widgets after startup."""
        mock_main_window._file_host_startup_complete = True
        mock_main_window.queue_manager.get_all_items.return_value = []
        mock_main_window.gallery_table.rowCount.return_value = 0

        with patch('src.gui.file_host_controller.log'):
            controller._on_file_hosts_enabled_changed(["host1"])

        mock_main_window.worker_signal_handler._on_enabled_workers_changed.assert_called_once_with(["host1"])
        mock_main_window.queue_manager.get_all_items.assert_called_once()


class TestQueueFileHostUpload:
    """Test suite for _queue_file_host_upload method."""

    @pytest.fixture
    def mock_main_window(self):
        mw = Mock()
        mw.queue_manager = Mock()
        mw.queue_manager.store = Mock()
        mw.queue_manager.store.add_file_host_upload.return_value = 42
        mw._update_specific_gallery_display = Mock()
        return mw

    @pytest.fixture
    def controller(self, mock_main_window):
        return FileHostController(mock_main_window)

    @patch('os.path.isdir', return_value=True)
    def test_calls_store_add_file_host_upload(self, mock_isdir, controller, mock_main_window):
        """Verify _queue_file_host_upload calls store.add_file_host_upload."""
        mock_config = Mock()
        mock_config.get_host.return_value = Mock()

        with patch('src.gui.file_host_controller.log'), \
             patch('src.core.file_host_config.get_config_manager', return_value=mock_config), \
             patch('PyQt6.QtWidgets.QMessageBox'):
            controller._queue_file_host_upload("/test/gallery", "filedot", "Filedot")

        mock_main_window.queue_manager.store.add_file_host_upload.assert_called_once_with(
            gallery_path="/test/gallery",
            host_name="filedot",
            status='pending'
        )
        mock_main_window._update_specific_gallery_display.assert_called_once_with("/test/gallery")

    @patch('os.path.isdir', return_value=True)
    def test_skips_when_host_config_not_found(self, mock_isdir, controller, mock_main_window):
        """Verify _queue_file_host_upload shows warning when host config not found."""
        mock_config = Mock()
        mock_config.get_host.return_value = None

        with patch('src.gui.file_host_controller.log'), \
             patch('src.core.file_host_config.get_config_manager', return_value=mock_config), \
             patch('PyQt6.QtWidgets.QMessageBox') as MockMsgBox:
            controller._queue_file_host_upload("/test/gallery", "unknown_host", "Unknown")

        MockMsgBox.warning.assert_called_once()
        mock_main_window.queue_manager.store.add_file_host_upload.assert_not_called()
