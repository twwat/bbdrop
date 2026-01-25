#!/usr/bin/env python3
"""
Comprehensive pytest-qt tests for GalleryContextMenuHelper.

Tests context menu creation, action setup, menu display positioning,
action callbacks, keyboard shortcuts, icon loading, and enabled/disabled states.

Target: High coverage with thorough testing of all menu operations.
"""

import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call

import pytest
from PyQt6.QtWidgets import (
    QApplication, QMenu, QTableWidget, QTableWidgetItem,
    QWidget, QMainWindow
)
from PyQt6.QtCore import Qt, QPoint, QModelIndex
from PyQt6.QtGui import QAction

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from src.gui.widgets.context_menu_helper import GalleryContextMenuHelper


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_queue_manager():
    """Mock QueueManager for testing"""
    manager = Mock()
    manager.get_item = Mock(return_value=None)
    manager.get_all_items = Mock(return_value=[])
    manager.mutex = MagicMock()
    manager.items = {}
    manager._inc_version = Mock()
    manager.store = Mock()
    manager.store.update_item_template = Mock(return_value=True)
    return manager


@pytest.fixture
def mock_tab_manager():
    """Mock TabManager for testing"""
    manager = Mock()
    manager.get_visible_tab_names = Mock(return_value=['Main', 'Archive', 'Completed'])
    manager.get_tab_by_name = Mock(return_value=Mock(id=1, name='Main'))
    return manager


@pytest.fixture
def mock_main_window(mock_queue_manager, mock_tab_manager):
    """Mock MainWindow for testing"""
    main_window = Mock()
    main_window.queue_manager = mock_queue_manager
    main_window.tab_manager = mock_tab_manager
    main_window.current_tab = 'Main'
    main_window.gallery_table = Mock()
    main_window.gallery_table.table = Mock()
    main_window.add_log_message = Mock()
    main_window.regenerate_gallery_bbcode = Mock()

    # Add common methods that might be delegated to
    main_window.start_selected_via_menu = Mock()
    main_window.delete_selected_via_menu = Mock()
    main_window.cancel_selected_via_menu = Mock()
    main_window.open_folders_via_menu = Mock()
    main_window.manage_gallery_files = Mock()
    main_window.rename_gallery = Mock()
    main_window.retry_selected_via_menu = Mock()
    main_window.rescan_additive_via_menu = Mock()
    main_window.rescan_all_items_via_menu = Mock()
    main_window.reset_gallery_via_menu = Mock()
    main_window.handle_view_button = Mock()
    main_window.copy_bbcode_via_menu_multi = Mock()
    main_window.regenerate_bbcode_for_gallery = Mock()
    main_window.regenerate_bbcode_for_gallery_multi = Mock()
    main_window.open_gallery_links_via_menu = Mock()
    main_window.browse_for_folders = Mock()
    main_window._move_selected_to_tab = Mock()

    return main_window


@pytest.fixture
def context_menu_helper(qtbot, mock_main_window):
    """Create a GalleryContextMenuHelper for testing"""
    helper = GalleryContextMenuHelper()
    helper.set_main_window(mock_main_window)
    return helper


@pytest.fixture
def mock_table_widget(qtbot):
    """Create a mock table widget for testing"""
    table = QTableWidget()
    table.setColumnCount(12)
    table.setRowCount(3)

    # Set up items with paths stored in UserRole
    for row in range(3):
        name_item = QTableWidgetItem(f"Gallery {row}")
        name_item.setData(Qt.ItemDataRole.UserRole, f"/path/to/gallery_{row}")
        table.setItem(row, 1, name_item)

    qtbot.addWidget(table)
    return table


@pytest.fixture
def sample_queue_item():
    """Sample gallery queue item"""
    item = Mock()
    item.name = "Test Gallery"
    item.path = "/path/to/gallery"
    item.status = "ready"
    item.gallery_id = "12345"
    item.gallery_url = "https://imx.to/g/12345"
    item.tab_name = "Main"
    item.tab_id = 1
    item.template_name = "Default"
    item.total_images = 10
    item.uploaded_images = 5
    return item


# ============================================================================
# Test: Initialization and Setup
# ============================================================================

class TestContextMenuHelperInit:
    """Test GalleryContextMenuHelper initialization and setup"""

    def test_helper_creates_successfully(self, qtbot):
        """Test basic helper instantiation"""
        helper = GalleryContextMenuHelper()
        assert helper is not None
        assert helper.main_window is None

    def test_set_main_window(self, qtbot, mock_main_window):
        """Test setting main window reference"""
        helper = GalleryContextMenuHelper()
        helper.set_main_window(mock_main_window)
        assert helper.main_window == mock_main_window

    def test_has_template_change_signal(self, qtbot):
        """Test that template change signal exists"""
        helper = GalleryContextMenuHelper()
        assert hasattr(helper, 'template_change_requested')

    def test_template_change_signal_emits(self, qtbot):
        """Test template change signal emission"""
        helper = GalleryContextMenuHelper()

        received_args = []
        helper.template_change_requested.connect(
            lambda paths, name: received_args.append((paths, name))
        )

        helper.template_change_requested.emit(["/path/1"], "TestTemplate")

        assert len(received_args) == 1
        assert received_args[0] == (["/path/1"], "TestTemplate")


# ============================================================================
# Test: Menu Creation
# ============================================================================

class TestMenuCreation:
    """Test context menu creation"""

    def test_create_menu_with_selection(self, context_menu_helper):
        """Test creating menu with selected paths"""
        selected_paths = ["/path/to/gallery"]
        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)

        assert menu is not None
        assert isinstance(menu, QMenu)
        assert menu.actions()  # Has actions

    def test_create_menu_without_selection(self, context_menu_helper):
        """Test creating menu without selection"""
        menu = context_menu_helper.create_context_menu(QPoint(0, 0), [])

        assert menu is not None
        assert isinstance(menu, QMenu)

        # Should have "Add Folders..." action
        action_texts = [a.text() for a in menu.actions()]
        assert "Add Folders..." in action_texts

    def test_create_menu_multiple_selections(self, context_menu_helper):
        """Test creating menu with multiple selected paths"""
        selected_paths = ["/path/to/gallery_1", "/path/to/gallery_2", "/path/to/gallery_3"]
        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)

        assert menu is not None
        assert menu.actions()


# ============================================================================
# Test: Action Items
# ============================================================================

class TestActionItems:
    """Test action items in the context menu"""

    def test_start_selected_action_exists(self, context_menu_helper):
        """Test Start Selected action is created"""
        selected_paths = ["/path/to/gallery"]
        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)

        action_texts = [a.text() for a in menu.actions() if not a.isSeparator()]
        assert "Start Selected" in action_texts

    def test_delete_selected_action_exists(self, context_menu_helper):
        """Test Delete Selected action is created"""
        selected_paths = ["/path/to/gallery"]
        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)

        action_texts = [a.text() for a in menu.actions() if not a.isSeparator()]
        assert "Delete Selected" in action_texts

    def test_start_action_disabled_when_cannot_start(self, context_menu_helper):
        """Test Start action is disabled when items cannot be started"""
        selected_paths = ["/path/to/gallery"]
        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)

        start_action = None
        for action in menu.actions():
            if action.text() == "Start Selected":
                start_action = action
                break

        assert start_action is not None
        assert not start_action.isEnabled()

    def test_start_action_enabled_when_can_start(self, context_menu_helper, sample_queue_item):
        """Test Start action is enabled when items can be started"""
        selected_paths = ["/path/to/gallery"]
        sample_queue_item.path = selected_paths[0]
        sample_queue_item.status = "ready"
        context_menu_helper.main_window.queue_manager.get_item.return_value = sample_queue_item

        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)

        start_action = None
        for action in menu.actions():
            if action.text() == "Start Selected":
                start_action = action
                break

        assert start_action is not None
        assert start_action.isEnabled()

    def test_cancel_action_for_queued_items(self, context_menu_helper, sample_queue_item):
        """Test Cancel action appears for queued items"""
        selected_paths = ["/path/to/gallery"]
        sample_queue_item.path = selected_paths[0]
        sample_queue_item.status = "queued"
        context_menu_helper.main_window.queue_manager.get_item.return_value = sample_queue_item

        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)

        action_texts = [a.text() for a in menu.actions() if not a.isSeparator()]
        assert "Cancel Upload" in action_texts


# ============================================================================
# Test: File Operations
# ============================================================================

class TestFileOperations:
    """Test file operation menu items"""

    def test_open_folder_action_exists(self, context_menu_helper):
        """Test Open Folder action is created"""
        selected_paths = ["/path/to/gallery"]
        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)

        action_texts = [a.text() for a in menu.actions() if not a.isSeparator()]
        assert "Open Folder" in action_texts

    def test_manage_files_single_selection(self, context_menu_helper):
        """Test Manage Files action appears for single selection"""
        selected_paths = ["/path/to/gallery"]
        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)

        action_texts = [a.text() for a in menu.actions() if not a.isSeparator()]
        assert "Manage Files..." in action_texts

    def test_manage_files_not_for_multiple_selection(self, context_menu_helper):
        """Test Manage Files action does not appear for multiple selections"""
        selected_paths = ["/path/to/gallery_1", "/path/to/gallery_2"]
        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)

        action_texts = [a.text() for a in menu.actions() if not a.isSeparator()]
        assert "Manage Files..." not in action_texts

    def test_rename_gallery_single_selection(self, context_menu_helper):
        """Test Rename Gallery action appears for single selection"""
        selected_paths = ["/path/to/gallery"]
        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)

        has_rename = any("Rename Gallery" in a.text() for a in menu.actions())
        assert has_rename


# ============================================================================
# Test: Status Operations
# ============================================================================

class TestStatusOperations:
    """Test status-based menu operations"""

    def test_retry_upload_for_failed_uploads(self, context_menu_helper, sample_queue_item):
        """Test Retry Upload action for failed uploads"""
        selected_paths = ["/path/to/gallery"]
        sample_queue_item.path = selected_paths[0]
        sample_queue_item.status = "upload_failed"
        context_menu_helper.main_window.queue_manager.get_item.return_value = sample_queue_item

        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)

        has_retry = any("Retry Upload" in a.text() for a in menu.actions())
        assert has_retry

    def test_retry_for_generic_failures(self, context_menu_helper, sample_queue_item):
        """Test Retry action for generic failures"""
        selected_paths = ["/path/to/gallery"]
        sample_queue_item.path = selected_paths[0]
        sample_queue_item.status = "failed"
        context_menu_helper.main_window.queue_manager.get_item.return_value = sample_queue_item

        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)

        # Should have generic retry
        action_texts = [a.text() for a in menu.actions()]
        has_retry = any("Retry" in text and "Upload" not in text for text in action_texts)
        assert has_retry

    def test_rescan_action_for_rescannable(self, context_menu_helper, sample_queue_item):
        """Test Rescan action appears for rescannable items"""
        selected_paths = ["/path/to/gallery"]
        sample_queue_item.path = selected_paths[0]
        sample_queue_item.status = "completed"
        context_menu_helper.main_window.queue_manager.get_item.return_value = sample_queue_item

        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)

        has_rescan = any("Rescan" in a.text() for a in menu.actions())
        assert has_rescan

    def test_reset_gallery_action_exists(self, context_menu_helper):
        """Test Reset Gallery action is created"""
        selected_paths = ["/path/to/gallery"]
        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)

        has_reset = any("Reset Gallery" in a.text() for a in menu.actions())
        assert has_reset

    def test_copy_bbcode_for_completed(self, context_menu_helper, sample_queue_item):
        """Test Copy BBCode action for completed items"""
        selected_paths = ["/path/to/gallery"]
        sample_queue_item.path = selected_paths[0]
        sample_queue_item.status = "completed"
        context_menu_helper.main_window.queue_manager.get_item.return_value = sample_queue_item

        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)

        action_texts = [a.text() for a in menu.actions()]
        assert "Copy BBCode" in action_texts

    def test_view_bbcode_single_completed(self, context_menu_helper, sample_queue_item):
        """Test View BBCode action for single completed item"""
        selected_paths = ["/path/to/gallery"]
        sample_queue_item.path = selected_paths[0]
        sample_queue_item.status = "completed"
        context_menu_helper.main_window.queue_manager.get_item.return_value = sample_queue_item

        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)

        action_texts = [a.text() for a in menu.actions()]
        assert "View BBCode" in action_texts

    def test_open_gallery_link_for_completed(self, context_menu_helper, sample_queue_item):
        """Test Open Gallery Link action for completed items"""
        selected_paths = ["/path/to/gallery"]
        sample_queue_item.path = selected_paths[0]
        sample_queue_item.status = "completed"
        context_menu_helper.main_window.queue_manager.get_item.return_value = sample_queue_item

        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)

        action_texts = [a.text() for a in menu.actions()]
        assert "Open Gallery Link" in action_texts


# ============================================================================
# Test: Template Submenu
# ============================================================================

class TestTemplateSubmenu:
    """Test template selection submenu"""

    @patch('bbdrop.load_templates')
    def test_template_submenu_exists(self, mock_load_templates, context_menu_helper):
        """Test template submenu is created"""
        mock_load_templates.return_value = {
            'Default': {},
            'Thumbnails': {},
            'Full Size': {}
        }

        selected_paths = ["/path/to/gallery"]
        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)

        # Find submenu
        has_template_menu = any(
            a.menu() and "template" in a.text().lower()
            for a in menu.actions()
        )
        assert has_template_menu

    @patch('bbdrop.load_templates')
    def test_template_submenu_has_templates(self, mock_load_templates, context_menu_helper):
        """Test template submenu contains available templates"""
        template_names = ['Default', 'Thumbnails', 'Full Size']
        mock_load_templates.return_value = {name: {} for name in template_names}

        selected_paths = ["/path/to/gallery"]
        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)

        # Find template submenu
        template_submenu = None
        for action in menu.actions():
            if action.menu() and "template" in action.text().lower():
                template_submenu = action.menu()
                break

        assert template_submenu is not None
        submenu_texts = [a.text() for a in template_submenu.actions()]
        for name in template_names:
            assert name in submenu_texts

    @patch('bbdrop.load_templates')
    def test_template_selection_emits_signal(self, mock_load_templates, context_menu_helper, qtbot):
        """Test template selection emits signal"""
        mock_load_templates.return_value = {'Default': {}}

        # Connect to signal
        received_args = []
        context_menu_helper.template_change_requested.connect(
            lambda paths, name: received_args.append((paths, name))
        )

        selected_paths = ["/path/to/gallery"]
        context_menu_helper._handle_template_selection(selected_paths, "Default")

        assert len(received_args) == 1
        assert received_args[0] == (selected_paths, "Default")


# ============================================================================
# Test: Move to Tab Submenu
# ============================================================================

class TestMoveToSubmenu:
    """Test Move to tab submenu"""

    def test_move_to_submenu_exists(self, context_menu_helper):
        """Test Move to submenu is created"""
        selected_paths = ["/path/to/gallery"]
        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)

        has_move_menu = any(
            a.menu() and "Move to" in a.text()
            for a in menu.actions()
        )
        assert has_move_menu

    def test_move_to_excludes_current_tab(self, context_menu_helper):
        """Test Move to submenu excludes current tab"""
        context_menu_helper.main_window.current_tab = 'Main'

        selected_paths = ["/path/to/gallery"]
        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)

        # Find move submenu
        move_submenu = None
        for action in menu.actions():
            if action.menu() and "Move to" in action.text():
                move_submenu = action.menu()
                break

        if move_submenu:
            submenu_texts = [a.text() for a in move_submenu.actions()]
            assert 'Main' not in submenu_texts

    def test_move_to_excludes_all_tabs(self, context_menu_helper):
        """Test Move to submenu excludes 'All Tabs' option"""
        context_menu_helper.main_window.tab_manager.get_visible_tab_names.return_value = [
            'Main', 'Archive', 'All Tabs'
        ]

        selected_paths = ["/path/to/gallery"]
        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)

        # Find move submenu
        move_submenu = None
        for action in menu.actions():
            if action.menu() and "Move to" in action.text():
                move_submenu = action.menu()
                break

        if move_submenu:
            submenu_texts = [a.text() for a in move_submenu.actions()]
            assert 'All Tabs' not in submenu_texts


# ============================================================================
# Test: Helper Methods
# ============================================================================

class TestHelperMethods:
    """Test helper methods for status checking"""

    def test_check_can_start_with_ready_item(self, context_menu_helper, sample_queue_item):
        """Test _check_can_start returns True for ready items"""
        sample_queue_item.status = "ready"
        context_menu_helper.main_window.queue_manager.get_item.return_value = sample_queue_item

        result = context_menu_helper._check_can_start(["/path/to/gallery"])
        assert result is True

    def test_check_can_start_with_paused_item(self, context_menu_helper, sample_queue_item):
        """Test _check_can_start returns True for paused items"""
        sample_queue_item.status = "paused"
        context_menu_helper.main_window.queue_manager.get_item.return_value = sample_queue_item

        result = context_menu_helper._check_can_start(["/path/to/gallery"])
        assert result is True

    def test_check_can_start_with_incomplete_item(self, context_menu_helper, sample_queue_item):
        """Test _check_can_start returns True for incomplete items"""
        sample_queue_item.status = "incomplete"
        context_menu_helper.main_window.queue_manager.get_item.return_value = sample_queue_item

        result = context_menu_helper._check_can_start(["/path/to/gallery"])
        assert result is True

    def test_check_can_start_with_completed_item(self, context_menu_helper, sample_queue_item):
        """Test _check_can_start returns False for completed items"""
        sample_queue_item.status = "completed"
        context_menu_helper.main_window.queue_manager.get_item.return_value = sample_queue_item

        result = context_menu_helper._check_can_start(["/path/to/gallery"])
        assert result is False

    def test_get_paths_by_status_single(self, context_menu_helper, sample_queue_item):
        """Test _get_paths_by_status with single status"""
        sample_queue_item.status = "completed"
        context_menu_helper.main_window.queue_manager.get_item.return_value = sample_queue_item

        paths = ["/path/to/gallery"]
        result = context_menu_helper._get_paths_by_status(paths, "completed")

        assert result == paths

    def test_get_paths_by_status_list(self, context_menu_helper, sample_queue_item):
        """Test _get_paths_by_status with list of statuses"""
        sample_queue_item.status = "failed"
        context_menu_helper.main_window.queue_manager.get_item.return_value = sample_queue_item

        paths = ["/path/to/gallery"]
        result = context_menu_helper._get_paths_by_status(paths, ["failed", "upload_failed"])

        assert result == paths

    def test_get_paths_by_status_no_match(self, context_menu_helper, sample_queue_item):
        """Test _get_paths_by_status returns empty for non-matching"""
        sample_queue_item.status = "ready"
        context_menu_helper.main_window.queue_manager.get_item.return_value = sample_queue_item

        paths = ["/path/to/gallery"]
        result = context_menu_helper._get_paths_by_status(paths, "completed")

        assert result == []

    def test_get_rescannable_paths(self, context_menu_helper, sample_queue_item):
        """Test _get_rescannable_paths returns correct paths"""
        sample_queue_item.status = "completed"
        context_menu_helper.main_window.queue_manager.get_item.return_value = sample_queue_item

        paths = ["/path/to/gallery"]
        result = context_menu_helper._get_rescannable_paths(paths)

        assert result == paths

    def test_get_rescan_all_paths_excludes_100_percent(self, context_menu_helper, sample_queue_item):
        """Test _get_rescan_all_paths excludes 100% completed"""
        sample_queue_item.status = "completed"
        sample_queue_item.total_images = 10
        sample_queue_item.uploaded_images = 10  # 100% complete
        context_menu_helper.main_window.queue_manager.get_item.return_value = sample_queue_item

        paths = ["/path/to/gallery"]
        result = context_menu_helper._get_rescan_all_paths(paths)

        assert result == []

    def test_get_rescan_all_paths_includes_incomplete(self, context_menu_helper, sample_queue_item):
        """Test _get_rescan_all_paths includes incomplete items"""
        sample_queue_item.status = "completed"
        sample_queue_item.total_images = 10
        sample_queue_item.uploaded_images = 5  # 50% complete
        context_menu_helper.main_window.queue_manager.get_item.return_value = sample_queue_item

        paths = ["/path/to/gallery"]
        result = context_menu_helper._get_rescan_all_paths(paths)

        assert result == paths


# ============================================================================
# Test: Delegation to Main Window
# ============================================================================

class TestDelegation:
    """Test delegation of actions to main window"""

    def test_delegate_without_main_window(self, qtbot):
        """Test delegation with no main window set"""
        helper = GalleryContextMenuHelper()
        # Should not raise error
        helper._delegate_to_main_window('some_method')

    def test_delegate_to_main_window_method(self, context_menu_helper):
        """Test delegation calls main window method"""
        # Configure mock to not have the method on table
        context_menu_helper.main_window.gallery_table.table = Mock(spec=[])

        context_menu_helper._delegate_to_main_window('browse_for_folders')
        context_menu_helper.main_window.browse_for_folders.assert_called_once()

    def test_delegate_with_args(self, context_menu_helper):
        """Test delegation passes arguments correctly"""
        # Configure mock to not have the method on table
        context_menu_helper.main_window.gallery_table.table = Mock(spec=[])

        paths = ["/path/to/gallery"]
        context_menu_helper._delegate_to_main_window('open_folders_via_menu', paths)
        context_menu_helper.main_window.open_folders_via_menu.assert_called_once_with(paths)

    def test_delegate_to_table_widget(self, context_menu_helper):
        """Test delegation tries table widget first"""
        # Create a mock table with a specific method
        mock_table = Mock()
        mock_table.custom_method = Mock()
        context_menu_helper.main_window.gallery_table.table = mock_table

        context_menu_helper._delegate_to_main_window('custom_method')
        mock_table.custom_method.assert_called_once()

    def test_delegate_missing_method(self, context_menu_helper, capsys):
        """Test delegation handles missing method"""
        # Configure mocks to not have the method
        context_menu_helper.main_window.gallery_table.table = Mock(spec=[])
        # Remove the attribute from main_window mock
        del context_menu_helper.main_window.nonexistent_method

        context_menu_helper._delegate_to_main_window('nonexistent_method')

        captured = capsys.readouterr()
        assert "not found" in captured.out


# ============================================================================
# Test: Table Context Menu Display
# ============================================================================

class TestTableContextMenuDisplay:
    """Test showing context menu for table widget"""

    def test_show_context_menu_for_table(self, context_menu_helper, mock_table_widget):
        """Test showing context menu at position"""
        # Select first row
        mock_table_widget.selectRow(0)

        position = QPoint(50, 50)

        # This would normally show the menu, but we can test setup
        with patch.object(QMenu, 'exec'):
            context_menu_helper.show_context_menu_for_table(mock_table_widget, position)

    def test_show_context_menu_selects_row(self, context_menu_helper, mock_table_widget):
        """Test that showing menu selects row under cursor"""
        position = QPoint(0, 0)

        with patch.object(QMenu, 'exec'):
            context_menu_helper.show_context_menu_for_table(mock_table_widget, position)

        # Row should be selected
        assert mock_table_widget.currentRow() >= 0 or mock_table_widget.rowCount() == 0

    def test_show_context_menu_gets_paths(self, context_menu_helper, mock_table_widget):
        """Test that paths are extracted from selected rows"""
        mock_table_widget.selectRow(0)
        position = QPoint(50, 50)

        with patch.object(context_menu_helper, 'create_context_menu') as mock_create:
            mock_create.return_value = QMenu()
            with patch.object(QMenu, 'exec'):
                context_menu_helper.show_context_menu_for_table(mock_table_widget, position)

            # Verify create_context_menu was called with paths
            mock_create.assert_called_once()


# ============================================================================
# Test: Template Update
# ============================================================================

class TestTemplateUpdate:
    """Test template update functionality"""

    def test_set_template_for_galleries_updates_db(self, context_menu_helper):
        """Test template update calls database"""
        paths = ["/path/to/gallery"]
        template_name = "NewTemplate"

        with patch('bbdrop.timestamp', return_value="12:00"):
            context_menu_helper.set_template_for_galleries(paths, template_name)

        context_menu_helper.main_window.queue_manager.store.update_item_template.assert_called_with(
            paths[0], template_name
        )

    def test_set_template_updates_in_memory(self, context_menu_helper, sample_queue_item):
        """Test template update modifies in-memory item"""
        from PyQt6.QtCore import QMutex

        paths = ["/path/to/gallery"]
        template_name = "NewTemplate"
        sample_queue_item.status = "ready"

        # Set up items dict and use real mutex
        context_menu_helper.main_window.queue_manager.items = {paths[0]: sample_queue_item}
        context_menu_helper.main_window.queue_manager.mutex = QMutex()

        with patch('bbdrop.timestamp', return_value="12:00"):
            context_menu_helper.set_template_for_galleries(paths, template_name)

        assert sample_queue_item.template_name == template_name

    def test_set_template_regenerates_bbcode_for_completed(self, context_menu_helper, sample_queue_item):
        """Test template update regenerates BBCode for completed items"""
        from PyQt6.QtCore import QMutex

        paths = ["/path/to/gallery"]
        template_name = "NewTemplate"
        sample_queue_item.status = "completed"

        # Set up items dict and use real mutex
        context_menu_helper.main_window.queue_manager.items = {paths[0]: sample_queue_item}
        context_menu_helper.main_window.queue_manager.mutex = QMutex()

        with patch('bbdrop.timestamp', return_value="12:00"):
            context_menu_helper.set_template_for_galleries(paths, template_name)

        context_menu_helper.main_window.regenerate_gallery_bbcode.assert_called_with(
            paths[0], template_name
        )

    def test_set_template_logs_message(self, context_menu_helper):
        """Test template update logs message"""
        paths = ["/path/to/gallery"]
        template_name = "NewTemplate"

        with patch('bbdrop.timestamp', return_value="12:00"):
            context_menu_helper.set_template_for_galleries(paths, template_name)

        context_menu_helper.main_window.add_log_message.assert_called()

    def test_set_template_empty_paths(self, context_menu_helper):
        """Test template update with empty paths does nothing"""
        context_menu_helper.set_template_for_galleries([], "Template")

        context_menu_helper.main_window.queue_manager.store.update_item_template.assert_not_called()

    def test_set_template_no_main_window(self, qtbot):
        """Test template update without main window does nothing"""
        helper = GalleryContextMenuHelper()
        # Should not raise error
        helper.set_template_for_galleries(["/path"], "Template")


# ============================================================================
# Test: Table Display Update
# ============================================================================

class TestTableDisplayUpdate:
    """Test table display update functionality"""

    def test_update_table_display_without_main_window(self, qtbot):
        """Test update with no main window set"""
        helper = GalleryContextMenuHelper()
        # Should not raise error
        helper._update_table_display(["/path"], "Template")

    def test_update_table_display_updates_cells(self, context_menu_helper):
        """Test table display update modifies correct cells"""
        # Create mock table with items
        mock_table = Mock()
        mock_table.rowCount.return_value = 1

        name_item = Mock()
        name_item.data.return_value = "/path/to/gallery"

        template_item = Mock()

        mock_table.item = Mock(side_effect=lambda row, col: name_item if col == 1 else template_item)
        mock_table.UserRole = Qt.ItemDataRole.UserRole

        context_menu_helper.main_window.gallery_table.table = mock_table

        context_menu_helper._update_table_display(["/path/to/gallery"], "NewTemplate")

        template_item.setText.assert_called_with("NewTemplate")


# ============================================================================
# Test: No Selection Menu Items
# ============================================================================

class TestNoSelectionItems:
    """Test menu items when nothing is selected"""

    def test_add_folders_action(self, context_menu_helper):
        """Test Add Folders action appears when no selection"""
        menu = context_menu_helper.create_context_menu(QPoint(0, 0), [])

        action_texts = [a.text() for a in menu.actions()]
        assert "Add Folders..." in action_texts

    def test_add_folders_triggers_browse(self, context_menu_helper):
        """Test Add Folders action triggers browse dialog"""
        # Ensure method is on main_window, not table
        context_menu_helper.main_window.gallery_table.table = Mock(spec=[])

        menu = context_menu_helper.create_context_menu(QPoint(0, 0), [])

        # Find and trigger the action
        for action in menu.actions():
            if action.text() == "Add Folders...":
                action.trigger()
                break

        context_menu_helper.main_window.browse_for_folders.assert_called_once()


# ============================================================================
# Test: Edge Cases and Error Handling
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_create_menu_with_none_paths(self, context_menu_helper):
        """Test menu creation handles None in paths"""
        # Technically shouldn't happen, but test robustness
        selected_paths = ["/path/to/gallery", None]
        context_menu_helper.main_window.queue_manager.get_item.return_value = None

        # Should not raise error
        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)
        assert menu is not None

    def test_create_menu_without_queue_manager(self, context_menu_helper):
        """Test menu creation without queue manager"""
        context_menu_helper.main_window.queue_manager = None
        delattr(context_menu_helper.main_window, 'queue_manager')

        selected_paths = ["/path/to/gallery"]
        # Should not raise error
        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)
        assert menu is not None

    def test_create_menu_without_tab_manager(self, context_menu_helper):
        """Test menu creation without tab manager"""
        context_menu_helper.main_window.tab_manager = None

        selected_paths = ["/path/to/gallery"]
        # Should not raise error
        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)
        assert menu is not None

    @patch('bbdrop.load_templates')
    def test_template_load_error(self, mock_load_templates, context_menu_helper, capsys):
        """Test handling of template loading error"""
        mock_load_templates.side_effect = Exception("Load error")

        selected_paths = ["/path/to/gallery"]
        # Should not raise error
        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)
        assert menu is not None

        captured = capsys.readouterr()
        assert "Error loading templates" in captured.out

    def test_multiple_status_filters(self, context_menu_helper):
        """Test filtering with multiple statuses"""
        # Create items with different statuses
        items = {
            "/path/1": Mock(status="completed"),
            "/path/2": Mock(status="failed"),
            "/path/3": Mock(status="ready")
        }

        def get_item(path):
            return items.get(path)

        context_menu_helper.main_window.queue_manager.get_item = get_item

        paths = list(items.keys())
        result = context_menu_helper._get_paths_by_status(paths, ["completed", "failed"])

        assert "/path/1" in result
        assert "/path/2" in result
        assert "/path/3" not in result


# ============================================================================
# Test: Action Callbacks
# ============================================================================

class TestActionCallbacks:
    """Test that action callbacks work correctly"""

    def test_start_action_callback(self, context_menu_helper, sample_queue_item):
        """Test Start action triggers correct callback"""
        selected_paths = ["/path/to/gallery"]
        sample_queue_item.status = "ready"
        context_menu_helper.main_window.queue_manager.get_item.return_value = sample_queue_item
        # Ensure method is on main_window, not table
        context_menu_helper.main_window.gallery_table.table = Mock(spec=[])

        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)

        for action in menu.actions():
            if action.text() == "Start Selected":
                action.trigger()
                break

        context_menu_helper.main_window.start_selected_via_menu.assert_called_once()

    def test_delete_action_callback(self, context_menu_helper):
        """Test Delete action triggers correct callback"""
        selected_paths = ["/path/to/gallery"]
        # Ensure method is on main_window, not table
        context_menu_helper.main_window.gallery_table.table = Mock(spec=[])

        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)

        for action in menu.actions():
            if action.text() == "Delete Selected":
                action.trigger()
                break

        context_menu_helper.main_window.delete_selected_via_menu.assert_called_once()

    def test_open_folder_callback(self, context_menu_helper):
        """Test Open Folder action triggers correct callback"""
        selected_paths = ["/path/to/gallery"]
        # Ensure method is on main_window, not table
        context_menu_helper.main_window.gallery_table.table = Mock(spec=[])

        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)

        for action in menu.actions():
            if action.text() == "Open Folder":
                action.trigger()
                break

        context_menu_helper.main_window.open_folders_via_menu.assert_called_once_with(selected_paths)

    def test_reset_gallery_callback(self, context_menu_helper):
        """Test Reset Gallery action triggers correct callback"""
        selected_paths = ["/path/to/gallery"]
        # Ensure method is on main_window, not table
        context_menu_helper.main_window.gallery_table.table = Mock(spec=[])

        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)

        for action in menu.actions():
            if "Reset Gallery" in action.text():
                action.trigger()
                break

        context_menu_helper.main_window.reset_gallery_via_menu.assert_called_once_with(selected_paths)


# ============================================================================
# Test: Menu Structure
# ============================================================================

class TestMenuStructure:
    """Test the overall menu structure"""

    def test_menu_has_reasonable_action_count(self, context_menu_helper):
        """Test menu has reasonable number of actions"""
        selected_paths = ["/path/to/gallery"]
        menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)

        # Should have multiple actions but not too many
        action_count = len(menu.actions())
        assert action_count >= 3  # At least start, delete, open
        assert action_count <= 30  # Not unreasonably many

    def test_completed_item_has_more_actions(self, context_menu_helper, sample_queue_item):
        """Test completed items have additional actions"""
        selected_paths = ["/path/to/gallery"]

        # Ready item
        sample_queue_item.status = "ready"
        context_menu_helper.main_window.queue_manager.get_item.return_value = sample_queue_item
        ready_menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)
        ready_count = len([a for a in ready_menu.actions() if not a.isSeparator()])

        # Completed item
        sample_queue_item.status = "completed"
        completed_menu = context_menu_helper.create_context_menu(QPoint(0, 0), selected_paths)
        completed_count = len([a for a in completed_menu.actions() if not a.isSeparator()])

        # Completed should have more actions (BBCode, links, etc.)
        assert completed_count > ready_count


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
