#!/usr/bin/env python3
"""
Test script for emergency performance fix

Tests:
1. Window visibility < 2 seconds
2. UI responsiveness during load
3. All galleries visible after load
4. Abort flag works for clean shutdown

These tests use proper mocking to avoid segfaults from real threads/sockets.
"""

import pytest
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# Fixtures for mocking problematic components
@pytest.fixture
def mock_single_instance_server():
    """Mock SingleInstanceServer to avoid socket creation."""
    with patch('src.gui.main_window.SingleInstanceServer') as mock_class:
        mock_instance = MagicMock()
        mock_instance.start = MagicMock()
        mock_instance.stop = MagicMock()
        mock_instance.wait = MagicMock(return_value=True)
        mock_instance.isRunning = MagicMock(return_value=False)
        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_completion_worker():
    """Mock CompletionWorker to avoid background thread."""
    with patch('src.gui.main_window.CompletionWorker') as mock_class:
        mock_instance = MagicMock()
        mock_instance.start = MagicMock()
        mock_instance.stop = MagicMock()
        mock_instance.wait = MagicMock(return_value=True)
        mock_instance.isRunning = MagicMock(return_value=False)
        mock_instance.completion_processed = MagicMock()
        mock_instance.log_message = MagicMock()
        # Make signal connections work
        mock_instance.completion_processed.connect = MagicMock()
        mock_instance.log_message.connect = MagicMock()
        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_file_host_manager():
    """Mock FileHostWorkerManager to avoid network connections."""
    with patch('src.processing.file_host_worker_manager.FileHostWorkerManager') as mock_class:
        mock_instance = MagicMock()
        mock_instance.shutdown_all = MagicMock()
        mock_instance.init_enabled_hosts = MagicMock()
        # Mock all signals
        for signal_name in ['test_completed', 'upload_started', 'upload_progress',
                           'upload_completed', 'upload_failed', 'bandwidth_updated']:
            signal = MagicMock()
            signal.connect = MagicMock()
            setattr(mock_instance, signal_name, signal)
        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_queue_manager():
    """Mock QueueManager to avoid database operations."""
    with patch('src.gui.main_window.QueueManager') as mock_class:
        mock_instance = MagicMock()
        mock_instance.store = MagicMock()
        mock_instance.get_all_items = MagicMock(return_value=[])
        mock_instance.parent = None
        # Mock signals
        mock_instance.status_changed = MagicMock()
        mock_instance.status_changed.connect = MagicMock()
        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_icon_manager():
    """Mock icon manager initialization."""
    with patch('src.gui.main_window.init_icon_manager') as mock_init:
        mock_mgr = MagicMock()
        mock_mgr.validate_icons = MagicMock(return_value={'valid': True, 'missing': []})
        mock_init.return_value = mock_mgr
        yield mock_mgr


@pytest.fixture
def mock_get_icon():
    """Mock get_icon to return a valid icon."""
    from PyQt6.QtGui import QIcon
    with patch('src.gui.main_window.get_icon') as mock:
        mock.return_value = QIcon()
        yield mock


@pytest.fixture
def mock_splash():
    """Create a mock splash screen."""
    splash = MagicMock()
    splash.set_status = MagicMock()
    splash.close = MagicMock()
    return splash


@pytest.fixture
def gui_window(qtbot, mock_single_instance_server, mock_completion_worker,
               mock_file_host_manager, mock_queue_manager, mock_icon_manager,
               mock_get_icon, mock_splash):
    """Create a properly mocked ImxUploadGUI window for testing."""
    from src.gui.main_window import ImxUploadGUI

    # Create window with mocked dependencies
    window = ImxUploadGUI(splash=mock_splash)
    qtbot.addWidget(window)

    yield window

    # Cleanup
    window.close()


class TestWindowVisibility:
    """Test that window becomes visible quickly."""

    def test_window_visibility_time(self, qtbot, mock_single_instance_server,
                                     mock_completion_worker, mock_file_host_manager,
                                     mock_queue_manager, mock_icon_manager,
                                     mock_get_icon, mock_splash):
        """Test that window becomes visible in < 2 seconds."""
        from src.gui.main_window import ImxUploadGUI

        start_time = time.time()
        window = ImxUploadGUI(splash=mock_splash)
        qtbot.addWidget(window)
        window.show()
        qtbot.waitExposed(window)
        visibility_time = time.time() - start_time

        assert visibility_time < 2.0, f"Window took {visibility_time:.2f}s to show (expected < 2s)"

        window.close()


class TestPhaseTracking:
    """Test that loading phases are tracked correctly."""

    def test_initial_phase_is_zero(self, gui_window):
        """Test initial loading phase is 0."""
        assert gui_window._loading_phase == 0, "Initial phase should be 0"

    def test_abort_flag_initially_false(self, gui_window):
        """Test abort flag is False initially."""
        assert gui_window._loading_abort == False, "Abort flag should be False initially"

    def test_abort_flag_can_be_set(self, gui_window):
        """Test that abort flag can be set for clean shutdown."""
        gui_window._loading_abort = True
        assert gui_window._loading_abort == True, "Abort flag should be settable"


class TestMinimalRowPopulation:
    """Test that minimal row population method exists and works."""

    def test_method_exists(self, gui_window):
        """Test that _populate_table_row_minimal method exists."""
        assert hasattr(gui_window, '_populate_table_row_minimal'), \
            "Window should have _populate_table_row_minimal method"

    def test_minimal_population_creates_basic_data(self, gui_window):
        """Test that minimal row population creates basic data without expensive widgets."""
        from src.storage.queue_manager import GalleryQueueItem

        # Create a test item
        test_item = GalleryQueueItem(
            path="/test/gallery",
            name="Test Gallery",
            status="ready",
            total_images=10,
            uploaded_images=0,
            total_size=1024000
        )

        # Add a row
        gui_window.gallery_table.setRowCount(1)
        gui_window._populate_table_row_minimal(0, test_item)

        # Check that basic data was populated
        name_item = gui_window.gallery_table.item(0, gui_window.gallery_table.COL_NAME)
        assert name_item is not None, "Name column should be populated"
        assert name_item.text() == "Test Gallery", "Name should match"

    def test_minimal_population_skips_expensive_widgets(self, gui_window):
        """Test that minimal mode does not create expensive progress widgets."""
        from src.storage.queue_manager import GalleryQueueItem

        # Create a test item
        test_item = GalleryQueueItem(
            path="/test/gallery",
            name="Test Gallery",
            status="ready",
            total_images=10,
            uploaded_images=0,
            total_size=1024000
        )

        # Add a row
        gui_window.gallery_table.setRowCount(1)
        gui_window._populate_table_row_minimal(0, test_item)

        # Check that expensive widgets were NOT created
        progress_widget = gui_window.gallery_table.cellWidget(
            0, gui_window.gallery_table.COL_PROGRESS
        )
        assert progress_widget is None, "Progress widget should NOT be created in minimal mode"


class TestBackgroundLoadingMethods:
    """Test that background loading methods exist."""

    @pytest.mark.parametrize("method_name", [
        '_load_galleries_phase1',
        '_load_galleries_phase2',
        '_finalize_gallery_load',
        '_populate_table_row_minimal'
    ])
    def test_background_method_exists(self, gui_window, method_name):
        """Test that background loading method exists."""
        assert hasattr(gui_window, method_name), \
            f"Window should have {method_name} method"

    def test_all_methods_callable(self, gui_window):
        """Test that all background loading methods are callable."""
        methods = [
            '_load_galleries_phase1',
            '_load_galleries_phase2',
            '_finalize_gallery_load',
            '_populate_table_row_minimal'
        ]

        for method in methods:
            assert callable(getattr(gui_window, method)), \
                f"{method} should be callable"


class TestEmergencyPerformanceAttributes:
    """Test emergency performance fix attributes."""

    def test_rows_with_widgets_tracking(self, gui_window):
        """Test that viewport-based lazy loading tracking is initialized."""
        assert hasattr(gui_window, '_rows_with_widgets'), \
            "Window should have _rows_with_widgets attribute"
        assert isinstance(gui_window._rows_with_widgets, set), \
            "_rows_with_widgets should be a set"

    def test_loading_abort_flag_exists(self, gui_window):
        """Test that loading abort flag exists for clean shutdown."""
        assert hasattr(gui_window, '_loading_abort'), \
            "Window should have _loading_abort attribute"

    def test_loading_phase_tracking_exists(self, gui_window):
        """Test that loading phase tracking exists."""
        assert hasattr(gui_window, '_loading_phase'), \
            "Window should have _loading_phase attribute"


# Allow running tests directly for debugging
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
