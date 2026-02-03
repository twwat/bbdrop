#!/usr/bin/env python3
"""
Comprehensive pytest-qt tests for TabbedGalleryWidget and DropEnabledTabBar

Tests cover:
- Tab creation, management, and deletion
- Signal emission
- Context menus and actions
- Tab switching and navigation
- Data filtering and display
- Drag-and-drop functionality
- Keyboard shortcuts
- Cache invalidation
- Performance metrics
"""

import pytest
import time
from unittest.mock import Mock, MagicMock, patch, call
from PyQt6.QtCore import Qt, QMimeData, QPoint, QSettings
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QWidget, QMessageBox, QInputDialog, QTableWidgetItem
from PyQt6.QtTest import QSignalSpy

from src.gui.widgets.tabbed_gallery import (
    TabbedGalleryWidget,
    DropEnabledTabBar,
    GalleryTableWidget
)


class TestDropEnabledTabBar:
    """Tests for DropEnabledTabBar custom tab bar"""

    @pytest.fixture
    def tab_bar(self, qtbot):
        """Create a DropEnabledTabBar instance"""
        bar = DropEnabledTabBar()
        qtbot.addWidget(bar)
        return bar

    def test_initialization(self, tab_bar):
        """Test tab bar initializes with correct defaults"""
        assert tab_bar.acceptDrops()
        assert tab_bar._drag_highlight_index == -1

    def test_add_tab(self, tab_bar):
        """Test adding tabs to bar"""
        tab_bar.addTab("Tab1")
        assert tab_bar.count() == 1
        assert tab_bar.tabText(0) == "Tab1"

    def test_drag_enter_event_with_gallery_mime(self, tab_bar, qtbot):
        """Test drag enter accepts gallery mime type"""
        tab_bar.addTab("Test Tab")

        event = MagicMock()
        event.mimeData().hasFormat.return_value = True
        event.position().toPoint.return_value = QPoint(10, 10)

        tab_bar.dragEnterEvent(event)
        event.acceptProposedAction.assert_called_once()

    def test_drag_enter_event_without_gallery_mime(self, tab_bar, qtbot):
        """Test drag enter rejects non-gallery mime types"""
        # Test the core logic by patching the parent class to avoid type checking
        event = MagicMock()
        mime_data = MagicMock()
        mime_data.hasFormat.return_value = False
        event.mimeData.return_value = mime_data

        # Call the parent handler directly to bypass type checking
        with patch('PyQt6.QtWidgets.QTabBar.dragEnterEvent') as mock_parent:
            tab_bar.dragEnterEvent(event)
            # When mime data doesn't have gallery format, should call parent (default behavior)
            mock_parent.assert_called_once_with(event)

    def test_drag_move_event(self, tab_bar):
        """Test drag move updates highlight"""
        tab_bar.addTab("Tab1")

        event = MagicMock()
        event.mimeData().hasFormat.return_value = True
        event.position().toPoint.return_value = QPoint(5, 5)

        tab_bar.dragMoveEvent(event)
        event.acceptProposedAction.assert_called_once()

    def test_drag_leave_event(self, tab_bar):
        """Test drag leave clears highlight"""
        tab_bar._drag_highlight_index = 0
        event = MagicMock()

        # Call with parent class patched to avoid type checking
        with patch('PyQt6.QtWidgets.QTabBar.dragLeaveEvent'):
            tab_bar.dragLeaveEvent(event)
        assert tab_bar._drag_highlight_index == -1

    def test_drop_event_with_valid_gallery(self, tab_bar):
        """Test drop event processes gallery mime data"""
        tab_bar.addTab("Target Tab")

        mime_data = QMimeData()
        mime_data.setData("application/x-bbdrop-galleries", b"/path/to/gallery1\n/path/to/gallery2")

        event = MagicMock()
        event.mimeData.return_value = mime_data
        event.position().toPoint.return_value = QPoint(5, 5)

        spy = QSignalSpy(tab_bar.galleries_dropped)
        tab_bar.dropEvent(event)

        assert len(spy) == 1
        args = spy[0]
        assert args[0] == "Target Tab"
        assert len(args[1]) == 2

    def test_drop_event_with_invalid_position(self, tab_bar):
        """Test drop on invalid position is ignored"""
        mime_data = QMimeData()
        mime_data.setData("application/x-bbdrop-galleries", b"/path/to/gallery")

        event = MagicMock()
        event.mimeData.return_value = mime_data
        event.position().toPoint.return_value = QPoint(9999, 9999)

        spy = QSignalSpy(tab_bar.galleries_dropped)
        tab_bar.dropEvent(event)

        assert len(spy) == 0

    def test_on_tab_moved_all_tabs_stays_at_zero(self, tab_bar):
        """Test 'All Tabs' is enforced at position 0"""
        tab_bar.addTab("All Tabs")
        tab_bar.addTab("Tab1")
        tab_bar.addTab("Tab2")

        spy = QSignalSpy(tab_bar.tab_order_changed)

        tab_bar._on_tab_moved(0, 1)

        assert tab_bar.tabText(0) == "All Tabs"
        assert len(spy) == 1

    def test_update_drag_highlight(self, tab_bar):
        """Test drag highlight updates on position change"""
        tab_bar.addTab("Tab1")
        tab_bar.addTab("Tab2")

        tab_bar._update_drag_highlight(QPoint(5, 5))
        assert tab_bar._drag_highlight_index >= 0

    def test_clear_drag_highlight(self, tab_bar):
        """Test clearing drag highlight"""
        tab_bar._drag_highlight_index = 0
        tab_bar._clear_drag_highlight()
        assert tab_bar._drag_highlight_index == -1

    def test_paint_event_with_highlight(self, tab_bar, qtbot):
        """Test paint event handles drag highlight"""
        tab_bar.addTab("Tab1")
        tab_bar._drag_highlight_index = 0

        tab_bar.update()
        qtbot.wait(50)


class TestTabbedGalleryWidget:
    """Tests for main TabbedGalleryWidget"""

    @pytest.fixture
    def widget(self, qtbot):
        """Create a TabbedGalleryWidget instance"""
        w = TabbedGalleryWidget()
        qtbot.addWidget(w)
        return w

    @pytest.fixture
    def mock_tab_manager(self):
        """Create a mock TabManager"""
        manager = MagicMock()
        manager.get_visible_tab_names.return_value = ["Main", "Tab1", "Tab2"]
        manager.last_active_tab = "Main"
        manager.load_tab_galleries.return_value = []
        return manager

    @pytest.fixture
    def mock_queue_manager(self):
        """Create a mock QueueManager"""
        return MagicMock()

    def test_initialization(self, widget):
        """Test widget initializes correctly"""
        assert widget.tab_bar is not None
        assert widget.table is not None
        assert widget.new_tab_btn is not None
        assert widget.current_tab == "Main"
        assert not widget._restoring_tabs

    def test_cache_initialization(self, widget):
        """Test cache structures are initialized"""
        assert isinstance(widget._filter_cache, dict)
        assert isinstance(widget._filter_cache_timestamps, dict)
        assert isinstance(widget._path_to_tab_cache, dict)
        assert widget._cache_version == 0
        assert widget._cache_ttl == 10.0

    def test_performance_metrics_initialization(self, widget):
        """Test performance metrics are initialized"""
        assert widget._perf_metrics['tab_switches'] == 0
        assert widget._perf_metrics['filter_cache_hits'] == 0
        assert widget._perf_metrics['filter_cache_misses'] == 0
        assert isinstance(widget._perf_metrics['filter_times'], list)

    def test_set_tab_manager(self, widget, mock_tab_manager):
        """Test setting tab manager"""
        widget.set_tab_manager(mock_tab_manager)
        assert widget.tab_manager == mock_tab_manager

    def test_refresh_tabs_with_manager(self, widget, mock_tab_manager):
        """Test refreshing tabs from manager"""
        widget.set_tab_manager(mock_tab_manager)

        assert widget.tab_bar.count() >= 1
        # All Tabs tab now includes count: "All Tabs (N)"
        assert widget.tab_bar.tabText(0).startswith("All Tabs")

    def test_refresh_tabs_without_manager(self, widget, qtbot):
        """Test refresh tabs when no manager is set - returns early without adding tabs"""
        widget._refresh_tabs()
        # Now returns early when tab_manager is not set
        assert widget.tab_bar.count() == 0

    def test_add_new_tab(self, widget, mock_tab_manager):
        """Test adding a new tab"""
        widget.set_tab_manager(mock_tab_manager)
        initial_count = widget.tab_bar.count()

        spy = QSignalSpy(widget.tab_created)

        with patch.object(QInputDialog, 'getText', return_value=("NewTab", True)):
            widget._add_new_tab()

        assert widget.tab_bar.count() == initial_count + 1
        assert len(spy) == 1
        mock_tab_manager.create_tab.assert_called_once_with("NewTab")

    def test_add_new_tab_empty_name(self, widget):
        """Test adding tab with empty name is rejected"""
        initial_count = widget.tab_bar.count()

        with patch.object(QInputDialog, 'getText', return_value=("", True)):
            widget._add_new_tab()

        assert widget.tab_bar.count() == initial_count

    def test_add_new_tab_duplicate_name(self, widget, mock_tab_manager):
        """Test adding tab with duplicate name is rejected"""
        widget.set_tab_manager(mock_tab_manager)
        initial_count = widget.tab_bar.count()

        with patch.object(QInputDialog, 'getText', return_value=("Main", True)):
            widget._add_new_tab()

        assert widget.tab_bar.count() == initial_count

    def test_rename_tab(self, widget, mock_tab_manager):
        """Test renaming a tab"""
        widget.set_tab_manager(mock_tab_manager)

        spy = QSignalSpy(widget.tab_renamed)
        widget._rename_tab(1, "Tab1", "NewName")

        assert len(spy) == 1
        assert spy[0][0] == "Tab1"
        assert spy[0][1] == "NewName"
        mock_tab_manager.rename_tab.assert_called_once_with("Tab1", "NewName")

    def test_rename_tab_updates_current(self, widget, mock_tab_manager):
        """Test renaming current tab updates current_tab"""
        widget.set_tab_manager(mock_tab_manager)
        widget.current_tab = "Tab1"

        widget._rename_tab(1, "Tab1", "NewName")
        assert widget.current_tab == "NewName"

    def test_delete_tab_with_confirmation(self, widget, mock_tab_manager):
        """Test deleting a tab with confirmation"""
        widget.set_tab_manager(mock_tab_manager)

        spy = QSignalSpy(widget.tab_deleted)
        initial_count = widget.tab_bar.count()

        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            widget._delete_tab_with_confirmation(1, "Tab1", 0)

        assert len(spy) == 1
        assert widget.tab_bar.count() < initial_count

    def test_delete_tab_cancelled(self, widget, mock_tab_manager):
        """Test cancelling tab deletion"""
        widget.set_tab_manager(mock_tab_manager)
        initial_count = widget.tab_bar.count()

        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.No):
            widget._delete_tab_with_confirmation(1, "Tab1", 0)

        assert widget.tab_bar.count() == initial_count

    def test_delete_tab_without_confirmation(self, widget, mock_tab_manager):
        """Test direct tab deletion"""
        widget.set_tab_manager(mock_tab_manager)

        spy = QSignalSpy(widget.tab_deleted)
        widget._delete_tab_without_confirmation(1, "Tab1")

        assert len(spy) == 1
        mock_tab_manager.delete_tab.assert_called_once_with("Tab1")

    def test_delete_tab_moves_galleries_to_main(self, widget, mock_tab_manager):
        """Test deleting tab moves galleries to Main"""
        widget.set_tab_manager(mock_tab_manager)
        gallery = {"path": "/path/to/gallery"}
        mock_tab_manager.load_tab_galleries.return_value = [gallery]

        widget._delete_tab_without_confirmation(1, "Tab1")

        mock_tab_manager.move_galleries_to_tab.assert_called()

    def test_on_tab_changed(self, widget, mock_tab_manager):
        """Test tab change signal is emitted"""
        widget.set_tab_manager(mock_tab_manager)

        spy = QSignalSpy(widget.tab_changed)
        widget._on_tab_changed(1)

        assert len(spy) == 1

    def test_switch_to_tab(self, widget, mock_tab_manager):
        """Test switching to specific tab"""
        widget.set_tab_manager(mock_tab_manager)

        widget.switch_to_tab("Tab1")
        assert widget.current_tab == "Tab1" or widget.tab_bar.currentIndex() > 0

    def test_get_current_tab(self, widget, mock_tab_manager):
        """Test getting current tab name"""
        widget.set_tab_manager(mock_tab_manager)
        widget.current_tab = "Tab1"

        assert widget.get_current_tab() == "Tab1"

    def test_next_tab(self, widget, mock_tab_manager):
        """Test navigating to next tab"""
        widget.set_tab_manager(mock_tab_manager)
        initial_index = widget.tab_bar.currentIndex()

        widget._next_tab()
        next_index = widget.tab_bar.currentIndex()

        expected = (initial_index + 1) % widget.tab_bar.count()
        assert next_index == expected

    def test_prev_tab(self, widget, mock_tab_manager):
        """Test navigating to previous tab"""
        widget.set_tab_manager(mock_tab_manager)
        initial_index = widget.tab_bar.currentIndex()

        widget._prev_tab()
        prev_index = widget.tab_bar.currentIndex()

        expected = (initial_index - 1) % widget.tab_bar.count()
        assert prev_index == expected

    def test_apply_filter_all_tabs(self, widget, mock_tab_manager):
        """Test filtering with 'All Tabs' shows all rows"""
        widget.set_tab_manager(mock_tab_manager)
        widget.table.setRowCount(5)

        # Populate rows with minimal data so filter doesn't hide them
        for row in range(5):
            name_item = QTableWidgetItem(f"Gallery {row}")
            name_item.setData(Qt.ItemDataRole.UserRole, f"/tmp/gallery{row}")
            widget.table.setItem(row, GalleryTableWidget.COL_NAME, name_item)

        widget._apply_filter("All Tabs")

        for row in range(5):
            assert not widget.table.isRowHidden(row)

    def test_apply_filter_no_manager(self, widget, qtbot):
        """Test filtering without tab manager shows all rows"""
        widget.table.setRowCount(3)

        widget._apply_filter("Main")

        for row in range(3):
            assert not widget.table.isRowHidden(row)

    def test_cache_hit_on_repeated_filter(self, widget, mock_tab_manager):
        """Test filter caching improves performance"""
        widget.set_tab_manager(mock_tab_manager)
        widget.table.setRowCount(10)

        widget._apply_filter("Tab1")
        misses_before = widget._perf_metrics['filter_cache_misses']

        widget._apply_filter("Tab1")
        hits_after = widget._perf_metrics['filter_cache_hits']

        assert hits_after > 0 or misses_before > 0

    def test_invalidate_filter_cache_all(self, widget):
        """Test invalidating entire filter cache"""
        widget._filter_cache = {"key1": {}, "key2": {}}
        widget._filter_cache_timestamps = {"tab1": time.time(), "tab2": time.time()}

        widget.invalidate_filter_cache()

        assert len(widget._filter_cache) == 0
        assert len(widget._filter_cache_timestamps) == 0

    def test_invalidate_filter_cache_specific_tab(self, widget):
        """Test invalidating cache for specific tab"""
        widget._filter_cache = {
            "tab1_10_0": {},
            "tab2_10_0": {}
        }
        widget._filter_cache_timestamps = {"tab1": time.time(), "tab2": time.time()}

        widget.invalidate_filter_cache("tab1")

        assert "tab1_10_0" not in widget._filter_cache

    def test_refresh_filter(self, widget, mock_tab_manager):
        """Test refreshing current filter"""
        widget.set_tab_manager(mock_tab_manager)
        widget.table.setRowCount(5)

        widget.refresh_filter()

    def test_cleanup_filter_cache(self, widget):
        """Test cleanup of expired cache entries"""
        widget._cache_ttl = 0.001
        widget._filter_cache = {
            "tab1_10_0": {},
            "tab2_10_0": {}
        }
        widget._filter_cache_timestamps = {
            "tab1": time.time() - 1,
            "tab2": time.time()
        }

        time.sleep(0.002)
        widget._cleanup_filter_cache()

        expired_keys = [k for k in widget._filter_cache if k.startswith("tab1_")]
        assert len(expired_keys) == 0

    def test_on_galleries_dropped(self, widget, mock_tab_manager):
        """Test galleries being dropped on tab"""
        widget.set_tab_manager(mock_tab_manager)
        mock_tab_manager.move_galleries_to_tab.return_value = 2

        spy = QSignalSpy(widget.galleries_dropped)
        gallery_paths = ["/path/1", "/path/2"]

        widget._on_galleries_dropped("Tab1", gallery_paths)

        assert len(spy) == 1
        mock_tab_manager.move_galleries_to_tab.assert_called_once()

    def test_on_galleries_dropped_no_paths(self, widget, mock_tab_manager):
        """Test dropping with no gallery paths"""
        widget.set_tab_manager(mock_tab_manager)

        spy = QSignalSpy(widget.galleries_dropped)
        widget._on_galleries_dropped("Tab1", [])

        assert len(spy) == 0

    def test_on_galleries_dropped_no_manager(self, widget):
        """Test dropping when no tab manager"""
        spy = QSignalSpy(widget.galleries_dropped)
        widget._on_galleries_dropped("Tab1", ["/path"])

        assert len(spy) == 0

    def test_assign_gallery_to_current_tab(self, widget, mock_tab_manager, mock_queue_manager):
        """Test assigning gallery to current tab"""
        widget.set_tab_manager(mock_tab_manager)
        widget.queue_manager = mock_queue_manager
        mock_tab_manager.move_galleries_to_tab.return_value = 1
        mock_queue_manager.get_item.return_value = MagicMock(tab_name="Main")

        widget.current_tab = "Tab1"
        widget.assign_gallery_to_current_tab("/path/gallery")

        mock_tab_manager.move_galleries_to_tab.assert_called_once()

    def test_assign_gallery_to_all_tabs(self, widget, mock_tab_manager):
        """Test that assigning to 'All Tabs' does nothing"""
        widget.set_tab_manager(mock_tab_manager)
        widget.current_tab = "All Tabs"

        widget.assign_gallery_to_current_tab("/path")

        mock_tab_manager.move_galleries_to_tab.assert_not_called()

    def test_is_valid_tab_name_valid(self, widget):
        """Test validation of valid tab name"""
        assert widget._is_valid_tab_name("NewTab")
        assert widget._is_valid_tab_name("Tab-1")
        assert widget._is_valid_tab_name("My Tab")

    def test_is_valid_tab_name_empty(self, widget):
        """Test empty tab name is invalid"""
        assert not widget._is_valid_tab_name("")
        assert not widget._is_valid_tab_name("   ")

    def test_is_valid_tab_name_duplicate(self, widget, mock_tab_manager):
        """Test duplicate tab name is invalid"""
        widget.set_tab_manager(mock_tab_manager)

        assert not widget._is_valid_tab_name("Main")

    def test_find_tab_index(self, widget, mock_tab_manager):
        """Test finding tab by name"""
        widget.set_tab_manager(mock_tab_manager)

        idx = widget._find_tab_index("All Tabs")
        assert idx == 0

    def test_find_tab_index_not_found(self, widget):
        """Test finding non-existent tab"""
        idx = widget._find_tab_index("NonExistent")
        assert idx == -1

    def test_get_performance_metrics(self, widget):
        """Test retrieving performance metrics"""
        widget._perf_metrics['tab_switches'] = 10
        widget._perf_metrics['filter_cache_hits'] = 5
        widget._perf_metrics['filter_cache_misses'] = 5

        metrics = widget.get_performance_metrics()

        assert metrics['tab_switches_total'] == 10
        assert metrics['cache_hit_rate'] == 0.5
        assert 'uptime_seconds' in metrics

    def test_performance_metrics_includes_averages(self, widget):
        """Test performance metrics include time averages"""
        widget._perf_metrics['tab_switch_times'] = [10.0, 20.0, 30.0]
        widget._perf_metrics['filter_times'] = [5.0, 10.0]

        metrics = widget.get_performance_metrics()

        assert metrics['avg_tab_switch_ms'] == 20.0
        assert metrics['max_tab_switch_ms'] == 30.0
        assert metrics['avg_filter_ms'] == 7.5

    def test_log_performance_summary(self, widget, capsys):
        """Test logging performance summary"""
        widget.log_performance_summary()

        captured = capsys.readouterr()
        assert "Performance Summary" in captured.out
        assert "Tab switches" in captured.out

    def test_update_theme(self, widget):
        """Test theme update"""
        widget.update_theme()

    def test_all_signals_exist(self, widget):
        """Test that all expected signals are defined"""
        assert hasattr(widget.tab_changed, 'emit')
        assert hasattr(widget.tab_renamed, 'emit')
        assert hasattr(widget.tab_deleted, 'emit')
        assert hasattr(widget.tab_created, 'emit')
        assert hasattr(widget.galleries_dropped, 'emit')

    def test_tab_bar_signal_exists(self):
        """Test that tab bar signals exist"""
        bar = DropEnabledTabBar()
        assert hasattr(bar.galleries_dropped, 'emit')
        assert hasattr(bar.tab_order_changed, 'emit')

    def test_apply_filter_with_no_rows(self, widget, mock_tab_manager):
        """Test filtering when table has no rows"""
        widget.set_tab_manager(mock_tab_manager)
        widget.table.setRowCount(0)

        widget._apply_filter("Tab1")

    def test_tab_count_extraction_from_text(self, widget, mock_tab_manager):
        """Test extracting base tab name from text with count"""
        widget.set_tab_manager(mock_tab_manager)
        widget.tab_bar.setTabText(0, "All Tabs (5)")

        text = widget.tab_bar.tabText(0)
        base_name = text.split(' (')[0] if ' (' in text else text
        assert base_name == "All Tabs"

    def test_tab_manager_required_for_operations(self, widget):
        """Test graceful handling when tab manager not available"""
        widget._apply_filter("Main")
        widget._update_tab_tooltips()

    def test_setup_connections(self, widget):
        """Test signal connections are established"""
        assert widget.tab_bar.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu

    def test_setup_discoverability_hints(self, widget):
        """Test setup of user discoverability hints"""
        widget._setup_discoverability_hints()

        whats_this = widget.tab_bar.whatsThis()
        assert len(whats_this) > 0

    def test_getattr_delegates_to_table(self, widget):
        """Test __getattr__ delegates to table"""
        if hasattr(widget.table, 'rowCount'):
            assert callable(widget.rowCount)

    def test_getattr_raises_for_unknown(self, widget):
        """Test __getattr__ raises AttributeError for unknown attributes"""
        with pytest.raises(AttributeError):
            _ = widget.nonexistent_attribute


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
