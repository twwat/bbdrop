#!/usr/bin/env python3
"""
Unit tests for UploadLifecycleHandler - upload lifecycle signal handling.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from PyQt6.QtCore import QMutex

from src.gui.upload_lifecycle_handler import UploadLifecycleHandler
from src.storage.queue_manager import GalleryQueueItem


class TestUploadLifecycleHandlerConstruction:
    """Test suite for UploadLifecycleHandler construction."""

    @pytest.fixture
    def mock_main_window(self):
        """Create a mock main window with required attributes."""
        mw = Mock()
        mw.queue_manager = Mock()
        mw.queue_manager.mutex = QMutex()
        mw.queue_manager.items = {}
        return mw

    def test_construction_with_mock_main_window(self, mock_main_window):
        """Verify handler can be constructed with a mock main window."""
        handler = UploadLifecycleHandler(mock_main_window)
        assert handler._main_window is mock_main_window

    def test_handler_stores_main_window_reference(self, mock_main_window):
        """Verify handler stores reference to main window."""
        handler = UploadLifecycleHandler(mock_main_window)
        assert handler._main_window is mock_main_window


class TestOnGalleryStarted:
    """Test suite for on_gallery_started method."""

    @pytest.fixture
    def mock_main_window(self):
        """Create a mock main window with required attributes."""
        mw = Mock()
        mw.queue_manager = Mock()
        mw.queue_manager.mutex = QMutex()
        mw.queue_manager.items = {}
        mw.queue_manager.store = Mock()
        mw._get_row_for_path = Mock(return_value=None)
        mw.gallery_table = Mock()
        mw.worker_signal_handler = Mock()
        mw.progress_tracker = Mock()
        return mw

    @pytest.fixture
    def handler(self, mock_main_window):
        """Create handler with mocked main window."""
        return UploadLifecycleHandler(mock_main_window)

    @patch('src.gui.upload_lifecycle_handler.QTimer')
    def test_sets_total_images(self, mock_timer, handler, mock_main_window):
        """Verify on_gallery_started sets item.total_images."""
        item = GalleryQueueItem(path="/test/gallery")
        item.total_images = 0
        item.uploaded_images = 5
        mock_main_window.queue_manager.items = {"/test/gallery": item}

        with patch('src.gui.upload_lifecycle_handler.log'):
            handler.on_gallery_started("/test/gallery", 42)

        assert item.total_images == 42

    @patch('src.gui.upload_lifecycle_handler.QTimer')
    def test_resets_uploaded_images(self, mock_timer, handler, mock_main_window):
        """Verify on_gallery_started resets item.uploaded_images to 0."""
        item = GalleryQueueItem(path="/test/gallery")
        item.total_images = 10
        item.uploaded_images = 5
        mock_main_window.queue_manager.items = {"/test/gallery": item}

        with patch('src.gui.upload_lifecycle_handler.log'):
            handler.on_gallery_started("/test/gallery", 20)

        assert item.uploaded_images == 0

    @patch('src.gui.upload_lifecycle_handler.QTimer')
    def test_nonexistent_path_no_error(self, mock_timer, handler, mock_main_window):
        """Verify no error when path doesn't exist in queue."""
        mock_main_window.queue_manager.items = {}

        with patch('src.gui.upload_lifecycle_handler.log'):
            # Should not raise
            handler.on_gallery_started("/nonexistent/path", 10)

    @patch('src.gui.upload_lifecycle_handler.QTimer')
    def test_updates_row_when_found(self, mock_timer, handler, mock_main_window):
        """Verify table row is updated when path maps to a row."""
        item = GalleryQueueItem(path="/test/gallery")
        item.status = "uploading"
        mock_main_window.queue_manager.items = {"/test/gallery": item}
        mock_main_window._get_row_for_path.return_value = 3

        with patch('src.gui.upload_lifecycle_handler.log'):
            handler.on_gallery_started("/test/gallery", 15)

        # Should have set items on the gallery table
        mock_main_window.gallery_table.setItem.assert_called()
        mock_main_window._set_status_cell_icon.assert_called_once_with(3, "uploading")
        mock_main_window._set_status_text_cell.assert_called_once_with(3, "uploading")


class TestOnGalleryFailed:
    """Test suite for on_gallery_failed method."""

    @pytest.fixture
    def mock_main_window(self):
        """Create a mock main window with required attributes."""
        mw = Mock()
        mw.queue_manager = Mock()
        mw.queue_manager.mutex = QMutex()
        mw.queue_manager.items = {}
        mw._update_specific_gallery_display = Mock()
        mw.progress_tracker = Mock()
        mw.notification_manager = Mock()
        return mw

    @pytest.fixture
    def handler(self, mock_main_window):
        """Create handler with mocked main window."""
        return UploadLifecycleHandler(mock_main_window)

    @patch('src.gui.upload_lifecycle_handler.QTimer')
    def test_sets_status_failed(self, mock_timer, handler, mock_main_window):
        """Verify on_gallery_failed sets item.status to 'failed'."""
        item = GalleryQueueItem(path="/test/gallery")
        item.status = "uploading"
        mock_main_window.queue_manager.items = {"/test/gallery": item}

        with patch('src.gui.upload_lifecycle_handler.log'):
            handler.on_gallery_failed("/test/gallery", "Connection timeout")

        assert item.status == "failed"

    @patch('src.gui.upload_lifecycle_handler.QTimer')
    def test_stores_error_message(self, mock_timer, handler, mock_main_window):
        """Verify on_gallery_failed stores the error_message."""
        item = GalleryQueueItem(path="/test/gallery")
        item.error_message = ""
        mock_main_window.queue_manager.items = {"/test/gallery": item}

        with patch('src.gui.upload_lifecycle_handler.log'):
            handler.on_gallery_failed("/test/gallery", "Connection timeout")

        assert item.error_message == "Connection timeout"

    @patch('src.gui.upload_lifecycle_handler.QTimer')
    def test_updates_display(self, mock_timer, handler, mock_main_window):
        """Verify on_gallery_failed triggers display update."""
        item = GalleryQueueItem(path="/test/gallery")
        mock_main_window.queue_manager.items = {"/test/gallery": item}

        with patch('src.gui.upload_lifecycle_handler.log'):
            handler.on_gallery_failed("/test/gallery", "Error")

        mock_main_window._update_specific_gallery_display.assert_called_once_with("/test/gallery")

    @patch('src.gui.upload_lifecycle_handler.QTimer')
    def test_fires_notification(self, mock_timer, handler, mock_main_window):
        """Verify on_gallery_failed fires a notification."""
        item = GalleryQueueItem(path="/test/gallery")
        mock_main_window.queue_manager.items = {"/test/gallery": item}

        with patch('src.gui.upload_lifecycle_handler.log'):
            handler.on_gallery_failed("/test/gallery", "Something broke")

        mock_main_window.notification_manager.notify.assert_called_once_with(
            'gallery_failed', detail="Something broke"
        )

    @patch('src.gui.upload_lifecycle_handler.QTimer')
    def test_nonexistent_path_no_error(self, mock_timer, handler, mock_main_window):
        """Verify no error when path doesn't exist in queue."""
        mock_main_window.queue_manager.items = {}

        with patch('src.gui.upload_lifecycle_handler.log'):
            # Should not raise
            handler.on_gallery_failed("/nonexistent/path", "Error")


class TestOnGalleryCompleted:
    """Test suite for on_gallery_completed method."""

    @pytest.fixture
    def mock_main_window(self):
        """Create a mock main window with required attributes."""
        mw = Mock()
        mw.queue_manager = Mock()
        mw.queue_manager.mutex = QMutex()
        mw.queue_manager.items = {}
        mw.queue_manager.get_item = Mock(return_value=None)
        mw._progress_batcher = Mock()
        mw.completion_worker = Mock()
        mw.archive_coordinator = Mock()
        mw._update_specific_gallery_display = Mock()
        mw._remove_gallery_from_table = Mock()
        mw.progress_tracker = Mock()
        mw.notification_manager = Mock()
        mw.worker_signal_handler = Mock()
        mw.gallery_table = Mock()
        mw._get_row_for_path = Mock(return_value=None)
        return mw

    @pytest.fixture
    def handler(self, mock_main_window):
        """Create handler with mocked main window."""
        return UploadLifecycleHandler(mock_main_window)

    @patch('src.gui.upload_lifecycle_handler.QTimer')
    def test_sets_completed_status_on_success(self, mock_timer, handler, mock_main_window):
        """Verify on_gallery_completed sets status to 'completed' when all succeed."""
        item = GalleryQueueItem(path="/test/gallery")
        item.start_time = 1000.0
        mock_main_window.queue_manager.items = {"/test/gallery": item}

        results = {
            'total_images': 10,
            'successful_count': 10,
            'images': [],
            'gallery_url': 'http://example.com/gallery',
            'gallery_id': 'abc123',
            'uploaded_size': 1024000,
        }

        with patch('src.gui.upload_lifecycle_handler.log'):
            handler.on_gallery_completed("/test/gallery", results)

        assert item.status == "completed"
        assert item.uploaded_images == 10
        assert item.gallery_url == 'http://example.com/gallery'
        assert item.gallery_id == 'abc123'

    @patch('src.gui.upload_lifecycle_handler.QTimer')
    def test_sets_failed_status_on_partial(self, mock_timer, handler, mock_main_window):
        """Verify on_gallery_completed sets status to 'failed' when partial success."""
        item = GalleryQueueItem(path="/test/gallery")
        item.start_time = 1000.0
        mock_main_window.queue_manager.items = {"/test/gallery": item}

        results = {
            'total_images': 10,
            'successful_count': 5,
            'images': [],
            'gallery_url': '',
            'gallery_id': '',
            'uploaded_size': 512000,
            'failed_count': 5,
            'failed_details': ['img1.jpg', 'img2.jpg'],
        }

        with patch('src.gui.upload_lifecycle_handler.log'):
            handler.on_gallery_completed("/test/gallery", results)

        assert item.status == "failed"
        assert item.uploaded_images == 5
        assert item.error_message == "5 of 10 images failed to upload"

    @patch('src.gui.upload_lifecycle_handler.QTimer')
    def test_delegates_to_completion_worker(self, mock_timer, handler, mock_main_window):
        """Verify on_gallery_completed delegates to completion_worker."""
        item = GalleryQueueItem(path="/test/gallery")
        item.start_time = 1000.0
        mock_main_window.queue_manager.items = {"/test/gallery": item}

        results = {'total_images': 5, 'successful_count': 5, 'images': [], 'uploaded_size': 0}

        with patch('src.gui.upload_lifecycle_handler.log'):
            handler.on_gallery_completed("/test/gallery", results)

        mock_main_window.completion_worker.process_completion.assert_called_once_with(
            "/test/gallery", results, mock_main_window
        )


class TestOnProgressUpdated:
    """Test suite for on_progress_updated method."""

    @pytest.fixture
    def mock_main_window(self):
        """Create a mock main window with required attributes."""
        mw = Mock()
        mw.queue_manager = Mock()
        mw.queue_manager.mutex = QMutex()
        mw.queue_manager.items = {}
        mw._progress_batcher = Mock()
        mw.worker_signal_handler = Mock()
        mw.worker_signal_handler.bandwidth_manager = Mock()
        mw.worker_signal_handler.bandwidth_manager.get_imx_bandwidth.return_value = 500.0
        return mw

    @pytest.fixture
    def handler(self, mock_main_window):
        """Create handler with mocked main window."""
        return UploadLifecycleHandler(mock_main_window)

    def test_updates_item_progress(self, handler, mock_main_window):
        """Verify on_progress_updated updates item progress fields."""
        item = GalleryQueueItem(path="/test/gallery")
        item.status = "uploading"
        mock_main_window.queue_manager.items = {"/test/gallery": item}

        handler.on_progress_updated("/test/gallery", 5, 10, 50, "image5.jpg")

        assert item.uploaded_images == 5
        assert item.total_images == 10
        assert item.progress == 50
        assert item.current_image == "image5.jpg"

    def test_updates_bandwidth_when_uploading(self, handler, mock_main_window):
        """Verify bandwidth is updated when item is uploading."""
        item = GalleryQueueItem(path="/test/gallery")
        item.status = "uploading"
        mock_main_window.queue_manager.items = {"/test/gallery": item}

        handler.on_progress_updated("/test/gallery", 5, 10, 50, "image5.jpg")

        assert item.current_kibps == 500.0

    def test_adds_to_progress_batcher(self, handler, mock_main_window):
        """Verify update is added to progress batcher."""
        item = GalleryQueueItem(path="/test/gallery")
        item.status = "uploading"
        mock_main_window.queue_manager.items = {"/test/gallery": item}

        handler.on_progress_updated("/test/gallery", 5, 10, 50, "image5.jpg")

        mock_main_window._progress_batcher.add_update.assert_called_once_with(
            "/test/gallery", 5, 10, 50, "image5.jpg"
        )


class TestOnCompletionProcessed:
    """Test suite for on_completion_processed method."""

    @pytest.fixture
    def mock_main_window(self):
        mw = Mock()
        return mw

    def test_on_completion_processed_is_noop(self, mock_main_window):
        """Verify on_completion_processed is a no-op (returns None)."""
        handler = UploadLifecycleHandler(mock_main_window)
        result = handler.on_completion_processed("/test/gallery")
        assert result is None


class TestOnGalleryRenamed:
    """Test suite for on_gallery_renamed method."""

    @pytest.fixture
    def mock_main_window(self):
        mw = Mock()
        mw.progress_tracker = Mock()
        mw.path_to_row = {}
        mw.queue_manager = Mock()
        return mw

    @patch('src.gui.upload_lifecycle_handler.QTimer')
    def test_updates_unnamed_count(self, mock_timer, mock_main_window):
        """Verify on_gallery_renamed triggers unnamed count update."""
        handler = UploadLifecycleHandler(mock_main_window)
        handler.on_gallery_renamed("gallery123")
        mock_main_window.progress_tracker._update_unnamed_count_background.assert_called_once()
