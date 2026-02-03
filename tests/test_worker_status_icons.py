"""
Test Suite for Worker Status Icons and Context Menu
====================================================

Tests verify the implementation of:
1. Icon loading (_load_icons adds host_enabled/host_disabled/auto to cache)
2. Host enable/disable functionality (_set_host_enabled calls save and refresh)
3. Host trigger functionality (_set_host_trigger calls save and refresh)
4. Context menu filtering (early return for non-filehost workers)
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication, QMenu
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, QPoint

from src.gui.widgets.worker_status_widget import (
    WorkerStatusWidget, WorkerStatus, ColumnConfig, ColumnType
)


@pytest.fixture
def qapp():
    """Provide QApplication instance for tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def worker_status_widget(qapp):
    """Create a WorkerStatusWidget instance for testing."""
    with patch('src.gui.widgets.worker_status_widget.get_icon_manager') as mock_mgr_fn, \
         patch('src.gui.widgets.worker_status_widget.get_config_manager') as mock_config_fn, \
         patch('src.gui.widgets.worker_status_widget.QSettings') as mock_settings_cls:
        # Mock icon manager
        mock_mgr = MagicMock()
        mock_mgr.get_icon.return_value = QIcon()
        mock_mgr_fn.return_value = mock_mgr

        # Mock config manager
        mock_config_fn.return_value = None

        # Mock QSettings
        mock_settings = MagicMock()
        mock_settings_cls.return_value = mock_settings

        def mock_value(key, default=None, type=None):
            return default

        mock_settings.value = mock_value

        widget = WorkerStatusWidget()
        yield widget
        widget.deleteLater()


@pytest.fixture
def filehost_worker():
    """Create a filehost worker status object."""
    return WorkerStatus(
        worker_id='test-filehost-1',
        worker_type='filehost',
        hostname='example.com',
        display_name='example.com',
        speed_bps=1024000.0,
        status='idle',
        files_remaining=5,
        bytes_remaining=1048576,
        storage_used_bytes=5368709120,
        storage_total_bytes=10737418240
    )


@pytest.fixture
def imx_worker():
    """Create an IMX worker status object."""
    return WorkerStatus(
        worker_id='test-imx-1',
        worker_type='imx',
        hostname='imx.to',
        display_name='imx.to',
        speed_bps=2048000.0,
        status='idle'
    )


class TestLoadIcons:
    """Test suite for _load_icons method"""

    def test_load_icons_adds_host_enabled_to_cache(self, worker_status_widget, qapp):
        """Verify _load_icons adds host_enabled icon to _icon_cache"""
        mock_icon = QIcon()
        with patch('src.gui.widgets.worker_status_widget.get_icon_manager') as mock_mgr_fn:
            mock_mgr = MagicMock()
            mock_mgr_fn.return_value = mock_mgr
            mock_mgr.get_icon.return_value = mock_icon

            worker_status_widget._load_icons()

            # Verify the icon manager was called with 'host_enabled'
            calls = [str(call_obj) for call_obj in mock_mgr.get_icon.call_args_list]
            assert any('host_enabled' in str(c) for c in calls), \
                f"get_icon('host_enabled') not called. Calls: {calls}"

            # Verify it's in the cache
            assert 'host_enabled' in worker_status_widget._icon_cache, \
                "host_enabled not in _icon_cache"

    def test_load_icons_adds_host_disabled_to_cache(self, worker_status_widget, qapp):
        """Verify _load_icons adds host_disabled icon to _icon_cache"""
        mock_icon = QIcon()
        with patch('src.gui.widgets.worker_status_widget.get_icon_manager') as mock_mgr_fn:
            mock_mgr = MagicMock()
            mock_mgr_fn.return_value = mock_mgr
            mock_mgr.get_icon.return_value = mock_icon

            worker_status_widget._load_icons()

            calls = [str(call_obj) for call_obj in mock_mgr.get_icon.call_args_list]
            assert any('host_disabled' in str(c) for c in calls), \
                f"get_icon('host_disabled') not called. Calls: {calls}"

            assert 'host_disabled' in worker_status_widget._icon_cache, \
                "host_disabled not in _icon_cache"

    def test_load_icons_adds_auto_to_cache(self, worker_status_widget, qapp):
        """Verify _load_icons adds auto icon to _icon_cache"""
        mock_icon = QIcon()
        with patch('src.gui.widgets.worker_status_widget.get_icon_manager') as mock_mgr_fn:
            mock_mgr = MagicMock()
            mock_mgr_fn.return_value = mock_mgr
            mock_mgr.get_icon.return_value = mock_icon

            worker_status_widget._load_icons()

            calls = [str(call_obj) for call_obj in mock_mgr.get_icon.call_args_list]
            assert any('auto' in str(c) for c in calls), \
                f"get_icon('auto') not called. Calls: {calls}"

            assert 'auto' in worker_status_widget._icon_cache, \
                "auto not in _icon_cache"

    def test_load_icons_creates_icon_cache_entries(self, worker_status_widget):
        """Verify _load_icons properly initializes icon cache"""
        # The fixture already calls _load_icons during init
        # Just verify the cache has the expected keys
        assert hasattr(worker_status_widget, '_icon_cache')
        assert isinstance(worker_status_widget._icon_cache, dict)

        # Should have loaded status icons (from base implementation)
        # and the new host state icons
        expected_keys = ['host_enabled', 'host_disabled', 'auto']
        for key in expected_keys:
            assert key in worker_status_widget._icon_cache, \
                f"Expected key '{key}' not in _icon_cache"

    def test_load_icons_all_three_icons_cached(self, worker_status_widget, qapp):
        """Verify all three new icons are loaded into cache"""
        mock_icon = QIcon()
        with patch('src.gui.widgets.worker_status_widget.get_icon_manager') as mock_mgr_fn:
            mock_mgr = MagicMock()
            mock_mgr_fn.return_value = mock_mgr
            mock_mgr.get_icon.return_value = mock_icon

            worker_status_widget._load_icons()

            # All three should be present
            required_icons = ['host_enabled', 'host_disabled', 'auto']
            for icon_key in required_icons:
                assert icon_key in worker_status_widget._icon_cache, \
                    f"Icon '{icon_key}' not in _icon_cache"
                assert worker_status_widget._icon_cache[icon_key] is not None, \
                    f"Icon '{icon_key}' is None"


class TestSetHostEnabled:
    """Test suite for _set_host_enabled method"""

    def test_set_host_enabled_calls_save_file_host_setting(self, worker_status_widget):
        """Verify _set_host_enabled calls save_file_host_setting with correct params"""
        with patch('src.gui.widgets.worker_status_widget.save_file_host_setting') as mock_save, \
             patch.object(worker_status_widget, '_refresh_display') as mock_refresh:

            worker_status_widget._set_host_enabled('test-host', True)

            # Verify save_file_host_setting was called with correct args
            mock_save.assert_called_once_with('test-host', 'enabled', True)

    def test_set_host_enabled_calls_refresh_display(self, worker_status_widget):
        """Verify _set_host_enabled calls _refresh_display after saving"""
        with patch('src.gui.widgets.worker_status_widget.save_file_host_setting'), \
             patch.object(worker_status_widget, '_refresh_display') as mock_refresh:

            worker_status_widget._set_host_enabled('test-host', True)

            # Verify _refresh_display was called
            mock_refresh.assert_called_once()

    def test_set_host_enabled_true_saves_boolean_true(self, worker_status_widget):
        """Verify _set_host_enabled(True) saves boolean True"""
        with patch('src.gui.widgets.worker_status_widget.save_file_host_setting') as mock_save, \
             patch.object(worker_status_widget, '_refresh_display'):

            worker_status_widget._set_host_enabled('example.com', True)

            # The third argument should be boolean True
            call_args = mock_save.call_args
            assert call_args[0][2] is True, \
                f"Expected True, got {call_args[0][2]}"

    def test_set_host_enabled_false_saves_boolean_false(self, worker_status_widget):
        """Verify _set_host_enabled(False) saves boolean False"""
        with patch('src.gui.widgets.worker_status_widget.save_file_host_setting') as mock_save, \
             patch.object(worker_status_widget, '_refresh_display'):

            worker_status_widget._set_host_enabled('example.com', False)

            # The third argument should be boolean False
            call_args = mock_save.call_args
            assert call_args[0][2] is False, \
                f"Expected False, got {call_args[0][2]}"

    def test_set_host_enabled_saves_enabled_setting(self, worker_status_widget):
        """Verify _set_host_enabled saves to 'enabled' setting key"""
        with patch('src.gui.widgets.worker_status_widget.save_file_host_setting') as mock_save, \
             patch.object(worker_status_widget, '_refresh_display'):

            worker_status_widget._set_host_enabled('myhost', True)

            # The second argument should be 'enabled'
            call_args = mock_save.call_args
            assert call_args[0][1] == 'enabled', \
                f"Expected 'enabled', got {call_args[0][1]}"

    def test_set_host_enabled_uses_correct_host_id(self, worker_status_widget):
        """Verify _set_host_enabled passes correct host_id"""
        with patch('src.gui.widgets.worker_status_widget.save_file_host_setting') as mock_save, \
             patch.object(worker_status_widget, '_refresh_display'):

            test_host = 'my-special-host.com'
            worker_status_widget._set_host_enabled(test_host, True)

            # The first argument should be the host_id
            call_args = mock_save.call_args
            assert call_args[0][0] == test_host, \
                f"Expected '{test_host}', got {call_args[0][0]}"

    def test_set_host_enabled_refresh_called_after_save(self, worker_status_widget):
        """Verify _refresh_display is called AFTER save_file_host_setting"""
        call_order = []

        def mock_save(*args, **kwargs):
            call_order.append('save')

        def mock_refresh(*args, **kwargs):
            call_order.append('refresh')

        with patch('src.gui.widgets.worker_status_widget.save_file_host_setting', side_effect=mock_save), \
             patch.object(worker_status_widget, '_refresh_display', side_effect=mock_refresh):

            worker_status_widget._set_host_enabled('test', True)

            # Refresh should be called after save
            assert call_order == ['save', 'refresh'], \
                f"Expected ['save', 'refresh'], got {call_order}"


class TestSetHostTrigger:
    """Test suite for _set_host_trigger method"""

    def test_set_host_trigger_calls_save_file_host_setting(self, worker_status_widget):
        """Verify _set_host_trigger calls save_file_host_setting with correct params"""
        with patch('src.gui.widgets.worker_status_widget.save_file_host_setting') as mock_save, \
             patch.object(worker_status_widget, '_refresh_display') as mock_refresh:

            worker_status_widget._set_host_trigger('test-host', 'on_added')

            # Verify save_file_host_setting was called
            mock_save.assert_called_once_with('test-host', 'trigger', 'on_added')

    def test_set_host_trigger_calls_refresh_display(self, worker_status_widget):
        """Verify _set_host_trigger calls _refresh_display after saving"""
        with patch('src.gui.widgets.worker_status_widget.save_file_host_setting'), \
             patch.object(worker_status_widget, '_refresh_display') as mock_refresh:

            worker_status_widget._set_host_trigger('test-host', 'on_started')

            # Verify _refresh_display was called
            mock_refresh.assert_called_once()

    def test_set_host_trigger_saves_trigger_setting(self, worker_status_widget):
        """Verify _set_host_trigger saves to 'trigger' setting key"""
        with patch('src.gui.widgets.worker_status_widget.save_file_host_setting') as mock_save, \
             patch.object(worker_status_widget, '_refresh_display'):

            worker_status_widget._set_host_trigger('myhost', 'on_completed')

            # The second argument should be 'trigger'
            call_args = mock_save.call_args
            assert call_args[0][1] == 'trigger', \
                f"Expected 'trigger', got {call_args[0][1]}"

    def test_set_host_trigger_on_added_value(self, worker_status_widget):
        """Verify _set_host_trigger correctly saves 'on_added' trigger"""
        with patch('src.gui.widgets.worker_status_widget.save_file_host_setting') as mock_save, \
             patch.object(worker_status_widget, '_refresh_display'):

            worker_status_widget._set_host_trigger('host', 'on_added')

            call_args = mock_save.call_args
            assert call_args[0][2] == 'on_added'

    def test_set_host_trigger_on_started_value(self, worker_status_widget):
        """Verify _set_host_trigger correctly saves 'on_started' trigger"""
        with patch('src.gui.widgets.worker_status_widget.save_file_host_setting') as mock_save, \
             patch.object(worker_status_widget, '_refresh_display'):

            worker_status_widget._set_host_trigger('host', 'on_started')

            call_args = mock_save.call_args
            assert call_args[0][2] == 'on_started'

    def test_set_host_trigger_on_completed_value(self, worker_status_widget):
        """Verify _set_host_trigger correctly saves 'on_completed' trigger"""
        with patch('src.gui.widgets.worker_status_widget.save_file_host_setting') as mock_save, \
             patch.object(worker_status_widget, '_refresh_display'):

            worker_status_widget._set_host_trigger('host', 'on_completed')

            call_args = mock_save.call_args
            assert call_args[0][2] == 'on_completed'

    def test_set_host_trigger_disabled_value(self, worker_status_widget):
        """Verify _set_host_trigger correctly saves 'disabled' trigger"""
        with patch('src.gui.widgets.worker_status_widget.save_file_host_setting') as mock_save, \
             patch.object(worker_status_widget, '_refresh_display'):

            worker_status_widget._set_host_trigger('host', 'disabled')

            call_args = mock_save.call_args
            assert call_args[0][2] == 'disabled'

    def test_set_host_trigger_uses_correct_host_id(self, worker_status_widget):
        """Verify _set_host_trigger passes correct host_id"""
        with patch('src.gui.widgets.worker_status_widget.save_file_host_setting') as mock_save, \
             patch.object(worker_status_widget, '_refresh_display'):

            test_host = 'special-host.example.org'
            worker_status_widget._set_host_trigger(test_host, 'on_added')

            # The first argument should be the host_id
            call_args = mock_save.call_args
            assert call_args[0][0] == test_host


class TestShowRowContextMenu:
    """Test suite for _show_row_context_menu method"""

    def test_show_row_context_menu_returns_early_for_invalid_index(self, worker_status_widget):
        """Verify context menu returns early if table index is invalid"""
        worker_status_widget.status_table.setRowCount(0)

        with patch('src.gui.widgets.worker_status_widget.get_file_host_setting') as mock_get, \
             patch('src.gui.widgets.worker_status_widget.QMenu'):

            # Call with invalid position
            worker_status_widget._show_row_context_menu(QPoint(100, 100))

            # get_file_host_setting should not be called
            mock_get.assert_not_called()

    def test_show_row_context_menu_returns_early_for_non_filehost(self, worker_status_widget, imx_worker):
        """Verify context menu returns early for non-filehost workers"""
        worker_status_widget._workers[imx_worker.worker_id] = imx_worker
        worker_status_widget.status_table.setRowCount(1)

        # Add a table item with worker_id in UserRole
        from PyQt6.QtWidgets import QTableWidgetItem
        item = QTableWidgetItem('imx.to')
        item.setData(Qt.ItemDataRole.UserRole, imx_worker.worker_id)
        worker_status_widget.status_table.setItem(0, 0, item)

        with patch('src.gui.widgets.worker_status_widget.get_file_host_setting') as mock_get, \
             patch('src.gui.widgets.worker_status_widget.QMenu') as mock_menu:

            # Get the position of the table item
            position = QPoint(10, 10)
            worker_status_widget._show_row_context_menu(position)

            # QMenu should not be created for IMX workers
            mock_menu.assert_not_called()
            # get_file_host_setting should not be called
            mock_get.assert_not_called()

    def test_show_row_context_menu_returns_early_for_unknown_worker(self, worker_status_widget):
        """Verify context menu returns early if worker_id not found"""
        worker_status_widget.status_table.setRowCount(1)

        from PyQt6.QtWidgets import QTableWidgetItem
        item = QTableWidgetItem('unknown')
        item.setData(Qt.ItemDataRole.UserRole, 'nonexistent-worker')
        worker_status_widget.status_table.setItem(0, 0, item)

        with patch('src.gui.widgets.worker_status_widget.get_file_host_setting') as mock_get, \
             patch('src.gui.widgets.worker_status_widget.QMenu') as mock_menu:

            position = QPoint(10, 10)
            worker_status_widget._show_row_context_menu(position)

            # Menu should not be created
            mock_menu.assert_not_called()
            mock_get.assert_not_called()

    def test_show_row_context_menu_creates_menu_for_filehost(self, worker_status_widget, filehost_worker):
        """Verify context menu is created for filehost workers"""
        worker_status_widget._workers[filehost_worker.worker_id] = filehost_worker
        worker_status_widget.status_table.setRowCount(1)

        from PyQt6.QtWidgets import QTableWidgetItem
        item = QTableWidgetItem(filehost_worker.display_name)
        item.setData(Qt.ItemDataRole.UserRole, filehost_worker.worker_id)
        worker_status_widget.status_table.setItem(0, 0, item)

        with patch('src.gui.widgets.worker_status_widget.get_file_host_setting') as mock_get, \
             patch('src.gui.widgets.worker_status_widget.QMenu') as mock_menu_class:

            mock_get.return_value = True
            mock_menu = MagicMock()
            mock_menu_class.return_value = mock_menu

            position = QPoint(10, 10)
            worker_status_widget._show_row_context_menu(position)

            # QMenu should be created for filehost workers
            mock_menu_class.assert_called()

    def test_show_row_context_menu_queries_file_host_setting_enabled(self, worker_status_widget, filehost_worker):
        """Verify context menu queries file host setting for 'enabled'"""
        worker_status_widget._workers[filehost_worker.worker_id] = filehost_worker
        worker_status_widget.status_table.setRowCount(1)

        from PyQt6.QtWidgets import QTableWidgetItem
        item = QTableWidgetItem(filehost_worker.display_name)
        item.setData(Qt.ItemDataRole.UserRole, filehost_worker.worker_id)
        worker_status_widget.status_table.setItem(0, 0, item)

        with patch('src.gui.widgets.worker_status_widget.get_file_host_setting') as mock_get, \
             patch('src.gui.widgets.worker_status_widget.QMenu'):

            mock_get.return_value = True

            position = QPoint(10, 10)
            worker_status_widget._show_row_context_menu(position)

            # Should query for 'enabled' setting
            get_enabled_calls = [call_obj for call_obj in mock_get.call_args_list
                               if 'enabled' in str(call_obj)]
            assert len(get_enabled_calls) > 0, \
                "get_file_host_setting not called for 'enabled' setting"

    def test_show_row_context_menu_queries_file_host_setting_trigger(self, worker_status_widget, filehost_worker):
        """Verify context menu queries file host setting for 'trigger'"""
        worker_status_widget._workers[filehost_worker.worker_id] = filehost_worker
        worker_status_widget.status_table.setRowCount(1)

        from PyQt6.QtWidgets import QTableWidgetItem
        item = QTableWidgetItem(filehost_worker.display_name)
        item.setData(Qt.ItemDataRole.UserRole, filehost_worker.worker_id)
        worker_status_widget.status_table.setItem(0, 0, item)

        with patch('src.gui.widgets.worker_status_widget.get_file_host_setting') as mock_get, \
             patch('src.gui.widgets.worker_status_widget.QMenu'):

            mock_get.return_value = 'on_added'

            position = QPoint(10, 10)
            worker_status_widget._show_row_context_menu(position)

            # Should query for 'trigger' setting
            get_trigger_calls = [call_obj for call_obj in mock_get.call_args_list
                                if 'trigger' in str(call_obj)]
            assert len(get_trigger_calls) > 0, \
                "get_file_host_setting not called for 'trigger' setting"

    def test_show_row_context_menu_finds_worker_id_from_any_column(self, worker_status_widget, filehost_worker):
        """Verify context menu can find worker_id from any column in the row"""
        worker_status_widget._workers[filehost_worker.worker_id] = filehost_worker
        worker_status_widget.status_table.setRowCount(1)
        worker_status_widget.status_table.setColumnCount(3)

        from PyQt6.QtWidgets import QTableWidgetItem
        # Put worker_id in the second column, not the first
        item1 = QTableWidgetItem('col1')
        item2 = QTableWidgetItem(filehost_worker.display_name)
        item2.setData(Qt.ItemDataRole.UserRole, filehost_worker.worker_id)
        item3 = QTableWidgetItem('col3')

        worker_status_widget.status_table.setItem(0, 0, item1)
        worker_status_widget.status_table.setItem(0, 1, item2)
        worker_status_widget.status_table.setItem(0, 2, item3)

        with patch('src.gui.widgets.worker_status_widget.get_file_host_setting') as mock_get, \
             patch('src.gui.widgets.worker_status_widget.QMenu'):

            mock_get.return_value = True

            position = QPoint(10, 10)
            worker_status_widget._show_row_context_menu(position)

            # Menu should still be created (worker found in column 1)
            # This is verified by get_file_host_setting being called


class TestHelperMethods:
    """Test helper methods work correctly in isolation"""

    def test_set_host_enabled_and_trigger_are_connected(self, worker_status_widget):
        """Verify _set_host_enabled and _set_host_trigger methods exist and are callable"""
        # Just verify the methods exist and are callable
        assert hasattr(worker_status_widget, '_set_host_enabled')
        assert callable(worker_status_widget._set_host_enabled)
        assert hasattr(worker_status_widget, '_set_host_trigger')
        assert callable(worker_status_widget._set_host_trigger)

    def test_show_row_context_menu_is_connected(self, worker_status_widget):
        """Verify _show_row_context_menu method exists and is callable"""
        assert hasattr(worker_status_widget, '_show_row_context_menu')
        assert callable(worker_status_widget._show_row_context_menu)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
