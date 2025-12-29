#!/usr/bin/env python3
"""
Unit tests for TableRowManager - specifically IMX status handling.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from src.gui.table_row_manager import TableRowManager
from src.storage.queue_manager import GalleryQueueItem


class TestUpdateImxStatusCell:
    """Test suite for _update_imx_status_cell method."""

    @pytest.fixture
    def mock_main_window(self):
        """Create a mock main window with gallery_table."""
        mw = Mock()
        mw.gallery_table = Mock()
        mw.gallery_table.set_online_imx_status = Mock()
        return mw

    @pytest.fixture
    def table_row_manager(self, mock_main_window):
        """Create TableRowManager with mocked main window."""
        return TableRowManager(mock_main_window)

    @pytest.fixture
    def sample_item_with_imx_status(self):
        """Create a sample gallery queue item with IMX status data."""
        item = GalleryQueueItem(path="/test/gallery")
        item.imx_status = "Online (87/87)"
        item.imx_status_checked = 1704067200  # 2024-01-01 00:00:00
        return item

    @pytest.fixture
    def sample_item_without_imx_status(self):
        """Create a sample gallery queue item without IMX status data."""
        item = GalleryQueueItem(path="/test/gallery")
        item.imx_status = ""
        item.imx_status_checked = None
        return item

    # =========================================================================
    # Happy Path Tests
    # =========================================================================

    def test_updates_status_with_valid_data(self, table_row_manager, mock_main_window, sample_item_with_imx_status):
        """Verify IMX status is updated when valid data exists."""
        result = table_row_manager._update_imx_status_cell(0, sample_item_with_imx_status)

        assert result is True
        mock_main_window.gallery_table.set_online_imx_status.assert_called_once()

        # Verify the call arguments
        call_args = mock_main_window.gallery_table.set_online_imx_status.call_args
        assert call_args[0][0] == 0  # row
        assert call_args[0][1] == 87  # online count
        assert call_args[0][2] == 87  # total count
        # Verify datetime format (timezone-agnostic - just check format)
        check_datetime = call_args[0][3]
        assert len(check_datetime) == 16  # "YYYY-MM-DD HH:MM"
        assert "-" in check_datetime and ":" in check_datetime

    def test_parses_different_status_formats(self, table_row_manager, mock_main_window):
        """Verify different status string formats are parsed correctly."""
        test_cases = [
            ("Online (50/100)", 50, 100),
            ("Offline (0/50)", 0, 50),
            ("Partial (25/30)", 25, 30),
            ("Online(10/10)", 10, 10),  # No space before parenthesis
            ("Status (1/1)", 1, 1),
        ]

        for status_str, expected_online, expected_total in test_cases:
            mock_main_window.gallery_table.set_online_imx_status.reset_mock()

            item = GalleryQueueItem(path="/test/gallery")
            item.imx_status = status_str
            item.imx_status_checked = 1704067200

            result = table_row_manager._update_imx_status_cell(0, item)

            assert result is True, f"Failed for status: {status_str}"
            call_args = mock_main_window.gallery_table.set_online_imx_status.call_args
            assert call_args[0][1] == expected_online, f"Wrong online count for: {status_str}"
            assert call_args[0][2] == expected_total, f"Wrong total count for: {status_str}"

    def test_formats_datetime_correctly(self, table_row_manager, mock_main_window):
        """Verify datetime is formatted as YYYY-MM-DD HH:MM."""
        item = GalleryQueueItem(path="/test/gallery")
        item.imx_status = "Online (10/10)"
        item.imx_status_checked = 1704067200  # 2024-01-01 00:00:00 UTC

        table_row_manager._update_imx_status_cell(0, item)

        call_args = mock_main_window.gallery_table.set_online_imx_status.call_args
        check_datetime = call_args[0][3]

        # Should be in format "YYYY-MM-DD HH:MM"
        assert len(check_datetime) == 16
        assert check_datetime[4] == "-"
        assert check_datetime[7] == "-"
        assert check_datetime[10] == " "
        assert check_datetime[13] == ":"

    # =========================================================================
    # Edge Case Tests
    # =========================================================================

    def test_returns_false_when_imx_status_empty(self, table_row_manager, mock_main_window):
        """Verify returns False when imx_status is empty string."""
        item = GalleryQueueItem(path="/test/gallery")
        item.imx_status = ""
        item.imx_status_checked = 1704067200

        result = table_row_manager._update_imx_status_cell(0, item)

        assert result is False
        mock_main_window.gallery_table.set_online_imx_status.assert_not_called()

    def test_returns_false_when_imx_status_checked_none(self, table_row_manager, mock_main_window):
        """Verify returns False when imx_status_checked is None."""
        item = GalleryQueueItem(path="/test/gallery")
        item.imx_status = "Online (10/10)"
        item.imx_status_checked = None

        result = table_row_manager._update_imx_status_cell(0, item)

        assert result is False
        mock_main_window.gallery_table.set_online_imx_status.assert_not_called()

    def test_returns_false_when_both_missing(self, table_row_manager, mock_main_window, sample_item_without_imx_status):
        """Verify returns False when both imx_status and imx_status_checked are missing."""
        result = table_row_manager._update_imx_status_cell(0, sample_item_without_imx_status)

        assert result is False
        mock_main_window.gallery_table.set_online_imx_status.assert_not_called()

    def test_returns_false_when_regex_doesnt_match(self, table_row_manager, mock_main_window):
        """Verify returns False when status string doesn't match expected format."""
        invalid_formats = [
            "Invalid",
            "No numbers here",
            "(10/10)",  # Missing word prefix
            "Online 10/10",  # Missing parentheses
            "Online (abc/def)",  # Non-numeric
            "",
        ]

        for invalid_status in invalid_formats:
            mock_main_window.gallery_table.set_online_imx_status.reset_mock()

            item = GalleryQueueItem(path="/test/gallery")
            item.imx_status = invalid_status
            item.imx_status_checked = 1704067200

            result = table_row_manager._update_imx_status_cell(0, item)

            # Empty string returns False early (before regex)
            # Other invalid formats should also return False
            assert result is False, f"Should return False for invalid format: '{invalid_status}'"
            mock_main_window.gallery_table.set_online_imx_status.assert_not_called()

    def test_handles_large_numbers(self, table_row_manager, mock_main_window):
        """Verify large image counts are handled correctly."""
        item = GalleryQueueItem(path="/test/gallery")
        item.imx_status = "Online (99999/100000)"
        item.imx_status_checked = 1704067200

        result = table_row_manager._update_imx_status_cell(0, item)

        assert result is True
        call_args = mock_main_window.gallery_table.set_online_imx_status.call_args
        assert call_args[0][1] == 99999
        assert call_args[0][2] == 100000

    def test_handles_zero_counts(self, table_row_manager, mock_main_window):
        """Verify zero counts are handled correctly."""
        item = GalleryQueueItem(path="/test/gallery")
        item.imx_status = "Offline (0/50)"
        item.imx_status_checked = 1704067200

        result = table_row_manager._update_imx_status_cell(0, item)

        assert result is True
        call_args = mock_main_window.gallery_table.set_online_imx_status.call_args
        assert call_args[0][1] == 0
        assert call_args[0][2] == 50

    # =========================================================================
    # Row Index Tests
    # =========================================================================

    def test_passes_correct_row_index(self, table_row_manager, mock_main_window, sample_item_with_imx_status):
        """Verify row index is passed correctly to set_online_imx_status."""
        for row in [0, 1, 5, 100]:
            mock_main_window.gallery_table.set_online_imx_status.reset_mock()

            table_row_manager._update_imx_status_cell(row, sample_item_with_imx_status)

            call_args = mock_main_window.gallery_table.set_online_imx_status.call_args
            assert call_args[0][0] == row
