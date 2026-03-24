#!/usr/bin/env python3
"""
Unit tests for GalleryTableController - gallery table operations.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, PropertyMock

from PyQt6.QtCore import QMutex, Qt
from PyQt6.QtWidgets import QTableWidgetItem

from src.gui.gallery_table_controller import GalleryTableController
from src.storage.queue_manager import GalleryQueueItem


class TestGalleryTableControllerConstruction:
    """Test suite for GalleryTableController construction."""

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
        mw._path_mapping_mutex = QMutex()
        mw._last_scan_states = {}
        mw._table_update_queue = None
        mw._in_item_changed_handler = False
        mw._current_theme_mode = 'dark'
        return mw

    def test_construction_with_mock_main_window(self, mock_main_window):
        """Verify controller can be constructed with a mock main window."""
        controller = GalleryTableController(mock_main_window)
        assert controller._main_window is mock_main_window


class TestAddGalleryToTable:
    """Test suite for _add_gallery_to_table method."""

    @pytest.fixture
    def mock_main_window(self):
        """Create a mock main window with required attributes."""
        mw = Mock()
        mw.queue_manager = Mock()
        mw.queue_manager.mutex = QMutex()
        mw.queue_manager.items = {}
        mw.gallery_table = Mock()
        mw.gallery_table.rowCount.return_value = 0
        mw.gallery_table.current_tab = "All Tabs"
        mw.path_to_row = {}
        mw.row_to_path = {}
        mw._last_scan_states = {}
        mw._table_update_queue = None
        mw._populate_table_row = Mock()
        return mw

    @pytest.fixture
    def controller(self, mock_main_window):
        """Create controller with mocked main window."""
        return GalleryTableController(mock_main_window)

    def test_inserts_row_and_updates_mappings(self, controller, mock_main_window):
        """Verify _add_gallery_to_table inserts a row and updates path_to_row/row_to_path."""
        item = GalleryQueueItem(path="/test/gallery1")
        item.tab_name = "Tab1"
        item.scan_complete = False
        item.status = "ready"

        with patch('src.gui.gallery_table_controller.log'):
            controller._add_gallery_to_table(item)

        assert mock_main_window.path_to_row["/test/gallery1"] == 0
        assert mock_main_window.row_to_path[0] == "/test/gallery1"
        mock_main_window.gallery_table.setRowCount.assert_called_once_with(1)
        mock_main_window._populate_table_row.assert_called_once_with(0, item)

    def test_skips_duplicate_path(self, controller, mock_main_window):
        """Verify _add_gallery_to_table skips duplicate and updates existing row instead."""
        mock_main_window.path_to_row = {"/test/gallery1": 2}
        item = GalleryQueueItem(path="/test/gallery1")
        item.tab_name = "Tab1"
        item.scan_complete = False
        item.status = "ready"

        with patch('src.gui.gallery_table_controller.log'):
            controller._add_gallery_to_table(item)

        # Should update existing, not add new
        mock_main_window.gallery_table.setRowCount.assert_not_called()
        mock_main_window._populate_table_row.assert_called_once_with(2, item)

    def test_initializes_scan_state_tracking(self, controller, mock_main_window):
        """Verify _add_gallery_to_table initializes _last_scan_states for the item."""
        item = GalleryQueueItem(path="/test/gallery1")
        item.tab_name = "Tab1"
        item.scan_complete = True
        item.status = "ready"

        with patch('src.gui.gallery_table_controller.log'):
            controller._add_gallery_to_table(item)

        assert mock_main_window._last_scan_states["/test/gallery1"] is True

    def test_invalidates_visibility_cache(self, controller, mock_main_window):
        """Verify _add_gallery_to_table invalidates table update queue visibility cache."""
        mock_main_window._table_update_queue = Mock()
        item = GalleryQueueItem(path="/test/gallery1")
        item.tab_name = "Tab1"
        item.scan_complete = False
        item.status = "ready"

        with patch('src.gui.gallery_table_controller.log'):
            controller._add_gallery_to_table(item)

        mock_main_window._table_update_queue.invalidate_visibility_cache.assert_called_once()


class TestRemoveGalleryFromTable:
    """Test suite for _remove_gallery_from_table method."""

    @pytest.fixture
    def mock_main_window(self):
        """Create a mock main window with required attributes."""
        mw = Mock()
        mw.gallery_table = Mock()
        mw.gallery_table.table = Mock()
        mw.path_to_row = {
            "/test/gallery1": 0,
            "/test/gallery2": 1,
            "/test/gallery3": 2,
        }
        mw.row_to_path = {
            0: "/test/gallery1",
            1: "/test/gallery2",
            2: "/test/gallery3",
        }
        mw._last_scan_states = {"/test/gallery1": False, "/test/gallery2": True}
        return mw

    @pytest.fixture
    def controller(self, mock_main_window):
        """Create controller with mocked main window."""
        return GalleryTableController(mock_main_window)

    def test_removes_row_and_shifts_mappings(self, controller, mock_main_window):
        """Verify _remove_gallery_from_table removes row and shifts subsequent mappings down."""
        with patch('src.gui.gallery_table_controller.log'):
            controller._remove_gallery_from_table("/test/gallery1")

        # Row 0 removed, rows 1 and 2 should shift down
        assert "/test/gallery1" not in mock_main_window.path_to_row
        assert mock_main_window.path_to_row["/test/gallery2"] == 0
        assert mock_main_window.path_to_row["/test/gallery3"] == 1
        assert mock_main_window.row_to_path[0] == "/test/gallery2"
        assert mock_main_window.row_to_path[1] == "/test/gallery3"

    def test_removes_middle_row(self, controller, mock_main_window):
        """Verify removing a middle row shifts only subsequent rows."""
        with patch('src.gui.gallery_table_controller.log'):
            controller._remove_gallery_from_table("/test/gallery2")

        assert mock_main_window.path_to_row["/test/gallery1"] == 0
        assert "/test/gallery2" not in mock_main_window.path_to_row
        assert mock_main_window.path_to_row["/test/gallery3"] == 1

    def test_does_nothing_for_unknown_path(self, controller, mock_main_window):
        """Verify _remove_gallery_from_table does nothing for unknown path."""
        with patch('src.gui.gallery_table_controller.log'):
            controller._remove_gallery_from_table("/nonexistent/path")

        # Mappings unchanged
        assert len(mock_main_window.path_to_row) == 3
        mock_main_window.gallery_table.table.removeRow.assert_not_called()

    def test_cleans_up_scan_state(self, controller, mock_main_window):
        """Verify _remove_gallery_from_table cleans up _last_scan_states."""
        with patch('src.gui.gallery_table_controller.log'):
            controller._remove_gallery_from_table("/test/gallery1")

        assert "/test/gallery1" not in mock_main_window._last_scan_states


class TestGetRowForPath:
    """Test suite for _get_row_for_path method."""

    @pytest.fixture
    def mock_main_window(self):
        """Create a mock main window with required attributes."""
        mw = Mock()
        mw.path_to_row = {"/test/gallery1": 3, "/test/gallery2": 7}
        mw._path_mapping_mutex = QMutex()
        return mw

    @pytest.fixture
    def controller(self, mock_main_window):
        """Create controller with mocked main window."""
        return GalleryTableController(mock_main_window)

    def test_returns_correct_row_for_known_path(self, controller):
        """Verify _get_row_for_path returns correct row for known path."""
        result = controller._get_row_for_path("/test/gallery1")
        assert result == 3

    def test_returns_none_for_unknown_path(self, controller):
        """Verify _get_row_for_path returns None for unknown path."""
        result = controller._get_row_for_path("/unknown/path")
        assert result is None


class TestSetPathRowMapping:
    """Test suite for _set_path_row_mapping method."""

    @pytest.fixture
    def mock_main_window(self):
        """Create a mock main window with required attributes."""
        mw = Mock()
        mw.path_to_row = {}
        mw.row_to_path = {}
        mw._path_mapping_mutex = QMutex()
        return mw

    @pytest.fixture
    def controller(self, mock_main_window):
        """Create controller with mocked main window."""
        return GalleryTableController(mock_main_window)

    def test_sets_both_dicts(self, controller, mock_main_window):
        """Verify _set_path_row_mapping sets both path_to_row and row_to_path."""
        controller._set_path_row_mapping("/test/gallery1", 5)

        assert mock_main_window.path_to_row["/test/gallery1"] == 5
        assert mock_main_window.row_to_path[5] == "/test/gallery1"


class TestRebuildPathMappings:
    """Test suite for _rebuild_path_mappings method."""

    @pytest.fixture
    def mock_main_window(self):
        """Create a mock main window with required attributes."""
        mw = Mock()
        mw.path_to_row = {"old": 0}
        mw.row_to_path = {0: "old"}
        mw._path_mapping_mutex = QMutex()
        mw.gallery_table = Mock()
        mw.gallery_table.rowCount.return_value = 2

        # Create mock items for each row
        def make_name_item(path):
            item = Mock()
            item.data.return_value = path
            return item

        item0 = make_name_item("/test/gallery_a")
        item1 = make_name_item("/test/gallery_b")

        from src.gui.widgets.gallery_table import GalleryTableWidget

        def mock_item(row, col):
            if col == GalleryTableWidget.COL_NAME:
                return [item0, item1][row]
            return None

        mw.gallery_table.item = mock_item
        return mw

    @pytest.fixture
    def controller(self, mock_main_window):
        """Create controller with mocked main window."""
        return GalleryTableController(mock_main_window)

    def test_rebuilds_from_table_state(self, controller, mock_main_window):
        """Verify _rebuild_path_mappings rebuilds from table state."""
        with patch('src.gui.gallery_table_controller.log'):
            controller._rebuild_path_mappings()

        assert mock_main_window.path_to_row == {
            "/test/gallery_a": 0,
            "/test/gallery_b": 1,
        }
        assert mock_main_window.row_to_path == {
            0: "/test/gallery_a",
            1: "/test/gallery_b",
        }


class TestUpdateSpecificGalleryDisplay:
    """Test suite for _update_specific_gallery_display method."""

    @pytest.fixture
    def mock_main_window(self):
        """Create a mock main window with required attributes."""
        mw = Mock()
        mw.queue_manager = Mock()
        mw.gallery_table = Mock()
        mw.gallery_table.rowCount.return_value = 5
        mw.path_to_row = {"/test/gallery1": 2}
        mw._table_update_queue = Mock()
        mw._populate_table_row = Mock()
        return mw

    @pytest.fixture
    def controller(self, mock_main_window):
        """Create controller with mocked main window."""
        return GalleryTableController(mock_main_window)

    def test_queues_update_for_known_path(self, controller, mock_main_window):
        """Verify _update_specific_gallery_display queues update when path is in table."""
        item = GalleryQueueItem(path="/test/gallery1")
        mock_main_window.queue_manager.get_item.return_value = item

        with patch('src.gui.gallery_table_controller.log'):
            controller._update_specific_gallery_display("/test/gallery1")

        mock_main_window._table_update_queue.queue_update.assert_called_once_with(
            "/test/gallery1", item, 'full'
        )

    def test_returns_early_for_missing_item(self, controller, mock_main_window):
        """Verify _update_specific_gallery_display returns early when item not in queue."""
        mock_main_window.queue_manager.get_item.return_value = None

        with patch('src.gui.gallery_table_controller.log'):
            controller._update_specific_gallery_display("/test/gallery1")

        mock_main_window._table_update_queue.queue_update.assert_not_called()

    @patch('src.gui.gallery_table_controller.QTimer')
    def test_retries_when_path_not_in_table(self, mock_timer, controller, mock_main_window):
        """Verify _update_specific_gallery_display schedules retry when path not yet in table."""
        item = GalleryQueueItem(path="/test/new_gallery")
        mock_main_window.queue_manager.get_item.return_value = item
        mock_main_window.path_to_row = {}  # Path not in table

        with patch('src.gui.gallery_table_controller.log'):
            controller._update_specific_gallery_display("/test/new_gallery", _retry_count=0)

        mock_timer.singleShot.assert_called_once()


class TestUpdatePathMappingsAfterRemoval:
    """Test suite for _update_path_mappings_after_removal method."""

    @pytest.fixture
    def mock_main_window(self):
        """Create a mock main window with required attributes."""
        mw = Mock()
        mw.path_to_row = {
            "/test/a": 0,
            "/test/b": 1,
            "/test/c": 2,
        }
        mw.row_to_path = {
            0: "/test/a",
            1: "/test/b",
            2: "/test/c",
        }
        return mw

    @pytest.fixture
    def controller(self, mock_main_window):
        """Create controller with mocked main window."""
        return GalleryTableController(mock_main_window)

    def test_shifts_rows_after_removal(self, controller, mock_main_window):
        """Verify _update_path_mappings_after_removal shifts subsequent rows down."""
        controller._update_path_mappings_after_removal(1)

        # Row 0 unchanged, row 1 removed, row 2 shifted to 1
        assert mock_main_window.path_to_row == {"/test/a": 0, "/test/c": 1}
        assert mock_main_window.row_to_path == {0: "/test/a", 1: "/test/c"}


class TestPopulateColumnData:
    """Test suite for _populate_column_data method."""

    @pytest.fixture
    def mock_main_window(self):
        """Create a mock main window with required attributes."""
        mw = Mock()
        mw.queue_manager = Mock()
        mw.gallery_table = Mock()
        mw.gallery_table.rowCount.return_value = 1
        mw.gallery_table.table = Mock()
        mw.row_to_path = {0: "/test/gallery1"}
        mw._current_theme_mode = 'dark'
        mw._set_status_text_cell = Mock()
        mw._format_rate_consistent = Mock(return_value="1.23 KiB/s")
        return mw

    @pytest.fixture
    def controller(self, mock_main_window):
        """Create controller with mocked main window."""
        return GalleryTableController(mock_main_window)

    def test_populates_status_text_column(self, controller, mock_main_window):
        """Verify _populate_column_data populates status text column."""
        item = GalleryQueueItem(path="/test/gallery1")
        item.status = "uploading"
        mock_main_window.queue_manager.get_item.return_value = item

        from src.gui.widgets.gallery_table import GalleryTableWidget

        with patch('src.gui.gallery_table_controller.log'):
            controller._populate_column_data(GalleryTableWidget.COL_STATUS_TEXT)

        mock_main_window._set_status_text_cell.assert_called_once_with(0, "uploading")

    def test_skips_row_with_no_path(self, controller, mock_main_window):
        """Verify _populate_column_data skips rows without a mapped path."""
        mock_main_window.row_to_path = {}

        from src.gui.widgets.gallery_table import GalleryTableWidget

        with patch('src.gui.gallery_table_controller.log'):
            controller._populate_column_data(GalleryTableWidget.COL_STATUS_TEXT)

        mock_main_window._set_status_text_cell.assert_not_called()


class TestSetImageHostForGalleries:
    """Test suite for set_image_host_for_galleries method."""

    @pytest.fixture
    def mock_main_window(self):
        """Create a mock main window with required attributes."""
        mw = Mock()
        mw.queue_manager = Mock()
        mw.queue_manager.mutex = QMutex()
        mw.queue_manager.items = {}
        mw.queue_manager.store = Mock()
        mw.gallery_table = Mock()
        mw.gallery_table.table = Mock()
        mw.add_log_message = Mock()
        return mw

    @pytest.fixture
    def controller(self, mock_main_window):
        """Create controller with mocked main window."""
        return GalleryTableController(mock_main_window)

    def test_returns_early_for_empty_paths(self, controller, mock_main_window):
        """Verify set_image_host_for_galleries returns early for empty paths list."""
        with patch('src.gui.gallery_table_controller.log'):
            controller.set_image_host_for_galleries([], "turbo")

        mock_main_window.queue_manager.store.update_item_image_host.assert_not_called()

    def test_returns_early_for_empty_host_id(self, controller, mock_main_window):
        """Verify set_image_host_for_galleries returns early for empty host_id."""
        with patch('src.gui.gallery_table_controller.log'):
            controller.set_image_host_for_galleries(["/test/gallery"], "")

        mock_main_window.queue_manager.store.update_item_image_host.assert_not_called()

    def test_skips_uploading_gallery(self, controller, mock_main_window):
        """Verify set_image_host_for_galleries skips galleries that are uploading."""
        item = GalleryQueueItem(path="/test/gallery")
        item.status = "uploading"
        mock_main_window.queue_manager.get_item.return_value = item

        with patch('src.gui.gallery_table_controller.log'), \
             patch('src.core.image_host_config.get_image_host_config_manager'):
            controller.set_image_host_for_galleries(["/test/gallery"], "turbo")

        mock_main_window.queue_manager.store.update_item_image_host.assert_not_called()

    def test_updates_ready_gallery(self, controller, mock_main_window):
        """Verify set_image_host_for_galleries updates a ready gallery."""
        item = GalleryQueueItem(path="/test/gallery")
        item.status = "ready"
        item.image_host_id = "imx"
        mock_main_window.queue_manager.get_item.return_value = item
        mock_main_window.queue_manager.items = {"/test/gallery": item}
        mock_main_window.queue_manager.store.update_item_image_host.return_value = True

        # Mock table with no rows to avoid iteration issues
        mock_table = Mock()
        mock_table.rowCount.return_value = 0
        mock_main_window.gallery_table.table = mock_table

        mock_config_mgr = Mock()
        mock_host_cfg = Mock()
        mock_host_cfg.name = "TurboImageHost"
        mock_config_mgr.get_host.return_value = mock_host_cfg

        with patch('src.gui.gallery_table_controller.log'), \
             patch('src.core.image_host_config.get_image_host_config_manager', return_value=mock_config_mgr), \
             patch('src.utils.format_utils.timestamp', return_value="[12:00:00]"):
            controller.set_image_host_for_galleries(["/test/gallery"], "turbo")

        mock_main_window.queue_manager.store.update_item_image_host.assert_called_once_with("/test/gallery", "turbo")


class TestOnTableItemChanged:
    """Test suite for _on_table_item_changed method."""

    @pytest.fixture
    def mock_main_window(self):
        """Create a mock main window with required attributes."""
        mw = Mock()
        mw.queue_manager = Mock()
        mw.queue_manager.mutex = QMutex()
        mw.queue_manager.items = {}
        mw.queue_manager.store = Mock()
        mw._in_item_changed_handler = False
        return mw

    @pytest.fixture
    def controller(self, mock_main_window):
        """Create controller with mocked main window."""
        return GalleryTableController(mock_main_window)

    def test_skips_when_handler_already_running(self, controller, mock_main_window):
        """Verify _on_table_item_changed skips when recursion guard is set."""
        mock_main_window._in_item_changed_handler = True
        mock_item = Mock()

        with patch('src.gui.gallery_table_controller.log'):
            controller._on_table_item_changed(mock_item)

        # Should not try to get column since we returned early
        mock_item.column.assert_not_called()

    def test_skips_non_custom_column(self, controller, mock_main_window):
        """Verify _on_table_item_changed skips non-custom/ext columns."""
        mock_item = Mock()
        mock_item.column.return_value = 0  # COL_NAME, not custom

        with patch('src.gui.gallery_table_controller.log'):
            controller._on_table_item_changed(mock_item)

        # Should not try to access tableWidget
        mock_item.tableWidget.assert_not_called()
        # Flag should be reset
        assert mock_main_window._in_item_changed_handler is False
