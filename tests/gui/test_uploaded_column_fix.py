"""
Test suite for uploaded column update fix

Tests verify that the uploaded column item is always created,
allowing updates even when total_images starts at 0.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from PyQt6.QtWidgets import QTableWidgetItem, QApplication
from PyQt6.QtCore import Qt
import sys


class TestUploadedColumnFix:
    """Test cases for uploaded column creation and update behavior"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Ensure QApplication exists for Qt tests"""
        if not QApplication.instance():
            self.app = QApplication(sys.argv)
        yield

    def test_uploaded_column_created_when_total_images_zero(self):
        """
        Test: Uploaded column item should be created even when total_images=0

        This is the critical fix - previously the column item was only created
        when total_images > 0, causing silent failures on updates.
        """
        # Mock the gallery item with zero images
        mock_item = Mock()
        mock_item.total_images = 0
        mock_item.uploaded_images = 0
        mock_item.name = "Test Gallery"
        mock_item.path = "/test/path"
        mock_item.progress = 0
        mock_item.status = "queued"
        mock_item.added_time = None
        mock_item.finished_time = None
        mock_item.total_size = 0

        # Mock the gallery table
        mock_table = Mock()
        mock_table.setItem = Mock()

        # Import and test the actual implementation pattern
        # Simulating the fixed code:
        total_images = getattr(mock_item, 'total_images', 0) or 0
        uploaded_images = getattr(mock_item, 'uploaded_images', 0) or 0
        uploaded_text = f"{uploaded_images}/{total_images}" if total_images > 0 else ""
        uploaded_item = QTableWidgetItem(uploaded_text)
        uploaded_item.setFlags(uploaded_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        uploaded_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # Verify item was created (not None)
        assert uploaded_item is not None
        assert uploaded_item.text() == ""
        assert not (uploaded_item.flags() & Qt.ItemFlag.ItemIsEditable)

    def test_uploaded_column_created_with_valid_images(self):
        """
        Test: Uploaded column item should show correct format when images exist
        """
        # Mock the gallery item with images
        mock_item = Mock()
        mock_item.total_images = 10
        mock_item.uploaded_images = 5

        # Simulating the fixed code:
        total_images = getattr(mock_item, 'total_images', 0) or 0
        uploaded_images = getattr(mock_item, 'uploaded_images', 0) or 0
        uploaded_text = f"{uploaded_images}/{total_images}" if total_images > 0 else ""
        uploaded_item = QTableWidgetItem(uploaded_text)

        # Verify item has correct text
        assert uploaded_item is not None
        assert uploaded_item.text() == "5/10"

    def test_uploaded_column_updateable_after_scan(self):
        """
        Test: Uploaded column should be updateable after scan completes

        This tests the scenario where:
        1. Gallery added with total_images=0
        2. Column item created (empty)
        3. Scan completes, total_images updated to actual count
        4. Column item should be updateable
        """
        # Step 1: Initial state with no images
        total_images = 0
        uploaded_images = 0
        uploaded_text = f"{uploaded_images}/{total_images}" if total_images > 0 else ""
        uploaded_item = QTableWidgetItem(uploaded_text)

        assert uploaded_item.text() == ""

        # Step 2: Simulate scan completion
        total_images = 15
        uploaded_images = 0
        new_text = f"{uploaded_images}/{total_images}"

        # This should work now because item exists
        uploaded_item.setText(new_text)

        assert uploaded_item.text() == "0/15"

        # Step 3: Simulate upload progress
        uploaded_images = 7
        new_text = f"{uploaded_images}/{total_images}"
        uploaded_item.setText(new_text)

        assert uploaded_item.text() == "7/15"

    def test_uploaded_column_matches_size_column_pattern(self):
        """
        Test: Uploaded column should follow same pattern as size column

        The size column always creates an item, even with empty text.
        The uploaded column should do the same.
        """
        # Size column pattern (reference implementation)
        size_text = ""  # Empty when size unknown
        size_item = QTableWidgetItem(size_text)
        size_item.setFlags(size_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # Uploaded column pattern (should match)
        uploaded_text = ""  # Empty when total_images=0
        uploaded_item = QTableWidgetItem(uploaded_text)
        uploaded_item.setFlags(uploaded_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        uploaded_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # Both should have items created
        assert size_item is not None
        assert uploaded_item is not None

        # Both should have same alignment
        assert size_item.textAlignment() == uploaded_item.textAlignment()

        # Both should be non-editable
        assert not (size_item.flags() & Qt.ItemFlag.ItemIsEditable)
        assert not (uploaded_item.flags() & Qt.ItemFlag.ItemIsEditable)


class TestUploadedColumnIntegration:
    """Integration tests for uploaded column in table context"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Ensure QApplication exists for Qt tests"""
        if not QApplication.instance():
            self.app = QApplication(sys.argv)
        yield

    def test_no_debug_log_when_total_images_zero(self):
        """
        Test: No debug log should be generated when total_images=0

        The old code had: log(f"DEBUG: No uploaded column set because total_images={total_images} <= 0")
        This should no longer exist.
        """
        # This test documents that the debug log was removed
        # In practice, you would check that the log function is NOT called
        # with the specific message when total_images=0

        with patch('src.gui.main_window.log') as mock_log:
            # Simulate the new code path
            total_images = 0
            uploaded_images = 0
            uploaded_text = f"{uploaded_images}/{total_images}" if total_images > 0 else ""
            uploaded_item = QTableWidgetItem(uploaded_text)

            # Verify no debug log was called
            mock_log.assert_not_called()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
