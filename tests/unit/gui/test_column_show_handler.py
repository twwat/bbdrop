#!/usr/bin/env python3
"""
Unit tests for column show handler - verifies data appears when hidden columns are enabled
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from PyQt6.QtWidgets import QApplication, QTableWidgetItem
from PyQt6.QtCore import Qt

from src.gui.main_window import BBDropGUI
from src.gui.widgets.gallery_table import GalleryTableWidget
from src.storage.queue_manager import GalleryQueueItem


class TestColumnShowHandler:
    """Test suite for column visibility change handler"""

    @pytest.fixture
    def main_window(self, qtbot):
        """Create main window instance for testing"""
        with patch('src.gui.main_window.get_config_path'), \
             patch('src.gui.main_window.load_user_defaults'), \
             patch('src.gui.main_window.get_file_host_setting'), \
             patch('src.gui.main_window.get_config_manager'):
            window = BBDropGUI()
            qtbot.addWidget(window)
            yield window

    @pytest.fixture
    def sample_item(self):
        """Create a sample gallery queue item"""
        item = GalleryQueueItem(path="/test/gallery")
        item.db_id = 123
        item.name = "Test Gallery"
        item.status = "completed"
        item.added_time = 1234567890.0
        item.finished_time = 1234567950.0
        item.total_images = 50
        item.uploaded_images = 50
        item.total_size = 1024000
        item.current_kibps = 0.0
        item.final_kibps = 512.5
        item.template_name = "Test Template"
        item.gallery_id = "12345"
        item.custom1 = "Custom1 Data"
        item.custom2 = "Custom2 Data"
        item.custom3 = "Custom3 Data"
        item.custom4 = "Custom4 Data"
        item.ext1 = "Ext1 Data"
        item.ext2 = "Ext2 Data"
        item.ext3 = "Ext3 Data"
        item.ext4 = "Ext4 Data"
        return item

    def test_column_show_populates_status_text(self, main_window, sample_item, qtbot):
        """Verify STATUS_TEXT column (5) gets populated when shown"""
        # Add item to table
        main_window.gallery_table.setRowCount(1)
        main_window.row_to_path[0] = sample_item.path
        main_window.path_to_row[sample_item.path] = 0

        # Mock queue manager
        main_window.queue_manager.get_item = Mock(return_value=sample_item)

        # Initially hide STATUS_TEXT column
        main_window.gallery_table.setColumnHidden(GalleryTableWidget.COL_STATUS_TEXT, True)

        # Verify column is hidden and no item exists
        assert main_window.gallery_table.isColumnHidden(GalleryTableWidget.COL_STATUS_TEXT)
        assert main_window.gallery_table.item(0, GalleryTableWidget.COL_STATUS_TEXT) is None

        # Show the column (trigger handler)
        main_window._set_column_visibility(GalleryTableWidget.COL_STATUS_TEXT, True)

        # Verify column is now visible and item exists
        assert not main_window.gallery_table.isColumnHidden(GalleryTableWidget.COL_STATUS_TEXT)
        item = main_window.gallery_table.item(0, GalleryTableWidget.COL_STATUS_TEXT)
        assert item is not None
        assert "Completed" in item.text()

    def test_column_show_populates_transfer(self, main_window, sample_item, qtbot):
        """Verify TRANSFER column (10) gets populated when shown"""
        # Add item to table
        main_window.gallery_table.setRowCount(1)
        main_window.row_to_path[0] = sample_item.path
        main_window.path_to_row[sample_item.path] = 0

        # Mock queue manager
        main_window.queue_manager.get_item = Mock(return_value=sample_item)

        # Initially hide TRANSFER column
        main_window.gallery_table.setColumnHidden(GalleryTableWidget.COL_TRANSFER, True)

        # Verify column is hidden and no item exists
        assert main_window.gallery_table.isColumnHidden(GalleryTableWidget.COL_TRANSFER)
        assert main_window.gallery_table.item(0, GalleryTableWidget.COL_TRANSFER) is None

        # Show the column (trigger handler)
        main_window._set_column_visibility(GalleryTableWidget.COL_TRANSFER, True)

        # Verify column is now visible and item exists with transfer rate
        assert not main_window.gallery_table.isColumnHidden(GalleryTableWidget.COL_TRANSFER)
        item = main_window.gallery_table.item(0, GalleryTableWidget.COL_TRANSFER)
        assert item is not None
        # Should contain formatted rate (512.5 KiB/s)
        assert len(item.text()) > 0

    def test_column_show_populates_gallery_id(self, main_window, sample_item, qtbot):
        """Verify GALLERY_ID column (13) gets populated when shown"""
        # Add item to table
        main_window.gallery_table.setRowCount(1)
        main_window.row_to_path[0] = sample_item.path
        main_window.path_to_row[sample_item.path] = 0

        # Mock queue manager
        main_window.queue_manager.get_item = Mock(return_value=sample_item)

        # Initially hide GALLERY_ID column
        main_window.gallery_table.setColumnHidden(GalleryTableWidget.COL_GALLERY_ID, True)

        # Get actual table for checking items
        actual_table = getattr(main_window.gallery_table, 'table', main_window.gallery_table)

        # Verify column is hidden and no item exists
        assert main_window.gallery_table.isColumnHidden(GalleryTableWidget.COL_GALLERY_ID)
        assert actual_table.item(0, GalleryTableWidget.COL_GALLERY_ID) is None

        # Show the column (trigger handler)
        main_window._set_column_visibility(GalleryTableWidget.COL_GALLERY_ID, True)

        # Verify column is now visible and item exists with gallery ID
        assert not main_window.gallery_table.isColumnHidden(GalleryTableWidget.COL_GALLERY_ID)
        item = actual_table.item(0, GalleryTableWidget.COL_GALLERY_ID)
        assert item is not None
        assert item.text() == "12345"

    def test_column_show_populates_custom_columns(self, main_window, sample_item, qtbot):
        """Verify CUSTOM1-4 columns (14-17) get populated when shown"""
        # Add item to table
        main_window.gallery_table.setRowCount(1)
        main_window.row_to_path[0] = sample_item.path
        main_window.path_to_row[sample_item.path] = 0

        # Mock queue manager
        main_window.queue_manager.get_item = Mock(return_value=sample_item)

        # Get actual table for checking items
        actual_table = getattr(main_window.gallery_table, 'table', main_window.gallery_table)

        # Test each custom column
        for col_idx, expected_text in [
            (GalleryTableWidget.COL_CUSTOM1, "Custom1 Data"),
            (GalleryTableWidget.COL_CUSTOM2, "Custom2 Data"),
            (GalleryTableWidget.COL_CUSTOM3, "Custom3 Data"),
            (GalleryTableWidget.COL_CUSTOM4, "Custom4 Data"),
        ]:
            # Initially hide column
            main_window.gallery_table.setColumnHidden(col_idx, True)

            # Verify column is hidden and no item exists
            assert main_window.gallery_table.isColumnHidden(col_idx)
            assert actual_table.item(0, col_idx) is None

            # Show the column (trigger handler)
            main_window._set_column_visibility(col_idx, True)

            # Verify column is now visible and item exists with correct data
            assert not main_window.gallery_table.isColumnHidden(col_idx)
            item = actual_table.item(0, col_idx)
            assert item is not None
            assert item.text() == expected_text
            # Verify it's editable
            assert item.flags() & Qt.ItemFlag.ItemIsEditable

    def test_column_show_populates_ext_columns(self, main_window, sample_item, qtbot):
        """Verify EXT1-4 columns (18-21) get populated when shown"""
        # Add item to table
        main_window.gallery_table.setRowCount(1)
        main_window.row_to_path[0] = sample_item.path
        main_window.path_to_row[sample_item.path] = 0

        # Mock queue manager
        main_window.queue_manager.get_item = Mock(return_value=sample_item)

        # Get actual table for checking items
        actual_table = getattr(main_window.gallery_table, 'table', main_window.gallery_table)

        # Test each ext column
        for col_idx, expected_text in [
            (GalleryTableWidget.COL_EXT1, "Ext1 Data"),
            (GalleryTableWidget.COL_EXT2, "Ext2 Data"),
            (GalleryTableWidget.COL_EXT3, "Ext3 Data"),
            (GalleryTableWidget.COL_EXT4, "Ext4 Data"),
        ]:
            # Initially hide column
            main_window.gallery_table.setColumnHidden(col_idx, True)

            # Verify column is hidden and no item exists
            assert main_window.gallery_table.isColumnHidden(col_idx)
            assert actual_table.item(0, col_idx) is None

            # Show the column (trigger handler)
            main_window._set_column_visibility(col_idx, True)

            # Verify column is now visible and item exists with correct data
            assert not main_window.gallery_table.isColumnHidden(col_idx)
            item = actual_table.item(0, col_idx)
            assert item is not None
            assert item.text() == expected_text
            # Verify it's editable
            assert item.flags() & Qt.ItemFlag.ItemIsEditable

    def test_column_show_handles_multiple_rows(self, main_window, qtbot):
        """Verify handler populates all rows when column is shown"""
        # Create multiple items
        items = []
        for i in range(5):
            item = GalleryQueueItem(path=f"/test/gallery{i}")
            item.gallery_id = f"ID-{i}"
            item.custom1 = f"Custom1-{i}"
            items.append(item)

        # Add items to table
        main_window.gallery_table.setRowCount(5)
        for row, item in enumerate(items):
            main_window.row_to_path[row] = item.path
            main_window.path_to_row[item.path] = row

        # Mock queue manager to return correct items
        def get_item_mock(path):
            for item in items:
                if item.path == path:
                    return item
            return None

        main_window.queue_manager.get_item = Mock(side_effect=get_item_mock)

        # Get actual table
        actual_table = getattr(main_window.gallery_table, 'table', main_window.gallery_table)

        # Initially hide CUSTOM1 column
        main_window.gallery_table.setColumnHidden(GalleryTableWidget.COL_CUSTOM1, True)

        # Show the column (trigger handler)
        main_window._set_column_visibility(GalleryTableWidget.COL_CUSTOM1, True)

        # Verify all rows have data
        for row in range(5):
            item = actual_table.item(row, GalleryTableWidget.COL_CUSTOM1)
            assert item is not None
            assert item.text() == f"Custom1-{row}"

    def test_column_hide_doesnt_populate(self, main_window, sample_item, qtbot):
        """Verify hiding a column doesn't trigger population (only showing does)"""
        # Add item to table
        main_window.gallery_table.setRowCount(1)
        main_window.row_to_path[0] = sample_item.path
        main_window.path_to_row[sample_item.path] = 0

        # Mock populate method to track if it's called
        main_window._populate_column_data = Mock()

        # Column starts visible
        main_window.gallery_table.setColumnHidden(GalleryTableWidget.COL_CUSTOM1, False)

        # Hide the column
        main_window._set_column_visibility(GalleryTableWidget.COL_CUSTOM1, False)

        # Verify populate was NOT called
        main_window._populate_column_data.assert_not_called()

    def test_already_visible_column_doesnt_repopulate(self, main_window, sample_item, qtbot):
        """Verify showing an already-visible column doesn't unnecessarily repopulate"""
        # Add item to table
        main_window.gallery_table.setRowCount(1)
        main_window.row_to_path[0] = sample_item.path
        main_window.path_to_row[sample_item.path] = 0

        # Mock populate method to track if it's called
        original_populate = main_window._populate_column_data
        main_window._populate_column_data = Mock(side_effect=original_populate)

        # Column starts visible
        main_window.gallery_table.setColumnHidden(GalleryTableWidget.COL_CUSTOM1, False)

        # "Show" the already-visible column
        main_window._set_column_visibility(GalleryTableWidget.COL_CUSTOM1, True)

        # Verify populate was NOT called (column was already visible)
        main_window._populate_column_data.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
