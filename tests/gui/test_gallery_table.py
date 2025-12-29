#!/usr/bin/env python3
"""
pytest-qt tests for GalleryTableWidget
Tests gallery queue table functionality
"""

import pytest
from unittest.mock import Mock, patch
from PyQt6.QtWidgets import QTableWidget
from PyQt6.QtCore import Qt

from src.gui.widgets.gallery_table import GalleryTableWidget, NumericColumnDelegate


class TestGalleryTableWidgetInit:
    """Test GalleryTableWidget initialization"""

    def test_gallery_table_creates(self, qtbot, mock_queue_manager):
        """Test GalleryTableWidget instantiation"""
        table = GalleryTableWidget()
        table.queue_manager = mock_queue_manager
        qtbot.addWidget(table)

        assert table is not None
        assert isinstance(table, QTableWidget)

    def test_table_has_columns(self, qtbot, mock_queue_manager):
        """Test that table has defined columns"""
        table = GalleryTableWidget()
        table.queue_manager = mock_queue_manager
        qtbot.addWidget(table)

        assert hasattr(table, 'COLUMNS')
        assert len(table.COLUMNS) > 0


class TestNumericColumnDelegate:
    """Test NumericColumnDelegate"""

    def test_delegate_creates(self, qtbot):
        """Test NumericColumnDelegate instantiation"""
        delegate = NumericColumnDelegate()

        assert delegate is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
