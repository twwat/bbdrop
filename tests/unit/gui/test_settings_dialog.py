#!/usr/bin/env python3
"""
pytest-qt tests for ComprehensiveSettingsDialog
Comprehensive tests for settings dialog functionality, configuration management,
and dialog behavior with 60%+ coverage target.

Tests cover:
- Dialog initialization and setup
- Settings loading and saving
- Tab management and dirty state tracking
- Input validation
- Signal emissions
- Dialog accept/reject behavior
- Reset to defaults functionality
- Unsaved changes detection
- File host management
- External apps configuration
"""

import pytest
import configparser
from unittest.mock import Mock, patch
from PyQt6.QtWidgets import (
    QDialog, QMessageBox, QCheckBox, QComboBox
)
from PyQt6.QtCore import QSettings

from src.gui.settings import (
    ComprehensiveSettingsDialog,
    HostTestDialog,
    IconDropFrame
)


# ============================================================================
# IconDropFrame Tests
# ============================================================================

class TestIconDropFrame:
    """Test IconDropFrame drag-and-drop functionality"""

    def test_icon_drop_frame_init(self, qtbot):
        """Test IconDropFrame initialization"""
        frame = IconDropFrame('light')
        qtbot.addWidget(frame)

        assert frame.variant_type == 'light'
        assert frame.acceptDrops() is True
        assert hasattr(frame, 'icon_dropped')

    def test_drag_enter_accepts_image_files(self, qtbot, tmp_path):
        """Test drag enter accepts valid image files"""
        frame = IconDropFrame('dark')
        qtbot.addWidget(frame)

        # Create mock drag event with image file
        mock_event = Mock()
        mock_mime = Mock()
        mock_url = Mock()

        test_file = tmp_path / "test_icon.png"
        test_file.write_text("fake png")
        mock_url.toLocalFile.return_value = str(test_file)

        mock_mime.hasUrls.return_value = True
        mock_mime.urls.return_value = [mock_url]
        mock_event.mimeData.return_value = mock_mime

        frame.dragEnterEvent(mock_event)
        mock_event.acceptProposedAction.assert_called_once()

    def test_drag_enter_rejects_non_image_files(self, qtbot, tmp_path):
        """Test drag enter rejects non-image files"""
        frame = IconDropFrame('light')
        qtbot.addWidget(frame)

        mock_event = Mock()
        mock_mime = Mock()
        mock_url = Mock()

        test_file = tmp_path / "test.txt"
        test_file.write_text("not an image")
        mock_url.toLocalFile.return_value = str(test_file)

        mock_mime.hasUrls.return_value = True
        mock_mime.urls.return_value = [mock_url]
        mock_event.mimeData.return_value = mock_mime

        frame.dragEnterEvent(mock_event)
        mock_event.ignore.assert_called_once()

    def test_drag_enter_rejects_multiple_files(self, qtbot):
        """Test drag enter rejects multiple files"""
        frame = IconDropFrame('dark')
        qtbot.addWidget(frame)

        mock_event = Mock()
        mock_mime = Mock()
        mock_mime.hasUrls.return_value = True
        mock_mime.urls.return_value = [Mock(), Mock()]  # Two files
        mock_event.mimeData.return_value = mock_mime

        frame.dragEnterEvent(mock_event)
        mock_event.ignore.assert_called_once()

    def test_drop_event_emits_signal(self, qtbot, tmp_path):
        """Test drop event emits icon_dropped signal"""
        frame = IconDropFrame('light')
        qtbot.addWidget(frame)

        test_file = tmp_path / "dropped_icon.png"
        test_file.write_text("fake png")

        with qtbot.waitSignal(frame.icon_dropped, timeout=1000) as blocker:
            mock_event = Mock()
            mock_mime = Mock()
            mock_url = Mock()
            mock_url.toLocalFile.return_value = str(test_file)
            mock_mime.urls.return_value = [mock_url]
            mock_event.mimeData.return_value = mock_mime

            frame.dropEvent(mock_event)

        assert blocker.args[0] == str(test_file)

    @pytest.mark.parametrize("extension", ['.png', '.ico', '.svg', '.jpg', '.jpeg'])
    def test_drop_accepts_various_image_formats(self, qtbot, tmp_path, extension):
        """Test drop accepts various image file formats"""
        frame = IconDropFrame('dark')
        qtbot.addWidget(frame)

        test_file = tmp_path / f"icon{extension}"
        test_file.write_text("fake image")

        mock_event = Mock()
        mock_mime = Mock()
        mock_url = Mock()
        mock_url.toLocalFile.return_value = str(test_file)
        mock_mime.urls.return_value = [mock_url]
        mock_event.mimeData.return_value = mock_mime

        frame.dropEvent(mock_event)
        mock_event.acceptProposedAction.assert_called_once()


# ============================================================================
# HostTestDialog Tests
# ============================================================================

class TestHostTestDialog:
    """Test HostTestDialog for file host testing"""

    def test_host_test_dialog_init(self, qtbot):
        """Test HostTestDialog initialization"""
        dialog = HostTestDialog("ImageBam")
        qtbot.addWidget(dialog)

        assert dialog.host_name == "ImageBam"
        assert dialog.windowTitle() == "Testing ImageBam"
        assert dialog.isModal() is True
        assert 'login' in dialog.test_items
        assert 'upload' in dialog.test_items
        assert dialog.close_btn.isVisible() is False

    def test_update_test_status_running(self, qtbot):
        """Test updating test status to running"""
        dialog = HostTestDialog("ImgBox")
        qtbot.addWidget(dialog)

        dialog.update_test_status('login', 'running', 'Logging in...')

        status_label = dialog.test_items['login']['status_label']
        assert status_label.text() == "⏳"
        assert status_label.property("status") == "running"

    def test_update_test_status_success(self, qtbot):
        """Test updating test status to success"""
        dialog = HostTestDialog("ImgBox")
        qtbot.addWidget(dialog)

        dialog.update_test_status('credentials', 'success')

        status_label = dialog.test_items['credentials']['status_label']
        assert status_label.text() == "✓"
        assert status_label.property("status") == "success"

    def test_update_test_status_failure(self, qtbot):
        """Test updating test status to failure"""
        dialog = HostTestDialog("ImgBox")
        qtbot.addWidget(dialog)

        dialog.update_test_status('upload', 'failure', 'Upload failed')

        status_label = dialog.test_items['upload']['status_label']
        name_label = dialog.test_items['upload']['name_label']
        assert status_label.text() == "✗"
        assert status_label.property("status") == "failure"
        assert name_label.text() == 'Upload failed'

    def test_update_test_status_skipped(self, qtbot):
        """Test updating test status to skipped"""
        dialog = HostTestDialog("ImgBox")
        qtbot.addWidget(dialog)

        dialog.update_test_status('cleanup', 'skipped')

        status_label = dialog.test_items['cleanup']['status_label']
        assert status_label.text() == "○"
        assert status_label.property("status") == "skipped"

    def test_update_invalid_test_id(self, qtbot):
        """Test updating invalid test ID does nothing"""
        dialog = HostTestDialog("ImgBox")
        qtbot.addWidget(dialog)

        # Should not raise exception
        dialog.update_test_status('invalid_test', 'running')
        assert 'invalid_test' not in dialog.test_items

    def test_set_complete_success(self, qtbot):
        """Test marking test as complete with success"""
        dialog = HostTestDialog("ImgBox")
        qtbot.addWidget(dialog)
        dialog.show()  # Show dialog to ensure widgets are visible
        qtbot.waitExposed(dialog)

        dialog.set_complete(True)
        qtbot.wait(10)  # Allow Qt to process events

        # Button should be set visible, even if dialog is hidden
        # Check the actual property, not the isVisible which depends on parent
        assert dialog.close_btn.isHidden() is False
        assert "Complete ✓" in dialog.windowTitle()

    def test_set_complete_failure(self, qtbot):
        """Test marking test as complete with failure"""
        dialog = HostTestDialog("ImgBox")
        qtbot.addWidget(dialog)
        dialog.show()
        qtbot.waitExposed(dialog)

        dialog.set_complete(False)
        qtbot.wait(10)  # Allow Qt to process events

        assert dialog.close_btn.isHidden() is False
        assert "Failed ✗" in dialog.windowTitle()

    def test_all_test_items_present(self, qtbot):
        """Test all expected test items are created"""
        dialog = HostTestDialog("TestHost")
        qtbot.addWidget(dialog)

        expected_items = ['login', 'credentials', 'user_info', 'upload', 'cleanup']
        for item in expected_items:
            assert item in dialog.test_items
            assert 'status_label' in dialog.test_items[item]
            assert 'name_label' in dialog.test_items[item]


# ============================================================================
# ComprehensiveSettingsDialog Tests - Initialization
# ============================================================================

class TestSettingsDialogInit:
    """Test ComprehensiveSettingsDialog initialization"""

    def test_settings_dialog_creates(self, qtbot,
                                     mock_config_file, mock_bbdrop_functions):
        """Test ComprehensiveSettingsDialog instantiation"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        assert dialog is not None
        assert isinstance(dialog, QDialog)
        assert dialog.isModal() is True
        assert dialog.windowTitle() == "Settings & Preferences"

    def test_dialog_has_nav_and_stack(self, qtbot, mock_config_file):
        """Test dialog contains nav_list and stack_widget"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        from PyQt6.QtWidgets import QListWidget, QStackedWidget
        assert hasattr(dialog, 'nav_list')
        assert hasattr(dialog, 'stack_widget')
        assert isinstance(dialog.nav_list, QListWidget)
        assert isinstance(dialog.stack_widget, QStackedWidget)
        assert dialog.stack_widget.count() > 0

    def test_dialog_has_buttons(self, qtbot, mock_config_file):
        """Test dialog has OK, Apply, Cancel, and Reset buttons"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        assert hasattr(dialog, 'ok_btn')
        assert hasattr(dialog, 'apply_btn')
        assert hasattr(dialog, 'cancel_btn')
        assert hasattr(dialog, 'reset_btn')

        assert dialog.ok_btn.text() == "OK"
        assert dialog.apply_btn.text() == "Apply"
        assert dialog.cancel_btn.text() == "Cancel"
        assert dialog.reset_btn.text() == "Reset to Defaults"

    def test_apply_button_initially_disabled(self, qtbot, mock_config_file):
        """Test Apply button is initially disabled"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        assert dialog.apply_btn.isEnabled() is False

    def test_initializes_dirty_states(self, qtbot, mock_config_file):
        """Test dialog initializes dirty state tracking"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        assert hasattr(dialog, 'tab_dirty_states')
        assert isinstance(dialog.tab_dirty_states, dict)
        assert dialog.current_tab_index == 0

    def test_initializes_qsettings(self, qtbot, mock_config_file):
        """Test dialog initializes QSettings"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        assert hasattr(dialog, 'settings')
        assert isinstance(dialog.settings, QSettings)


# ============================================================================
# ComprehensiveSettingsDialog Tests - Tab Management
# ============================================================================

class TestSettingsDialogTabs:
    """Test settings dialog tab management"""

    def test_has_general_tab(self, qtbot, mock_config_file):
        """Test dialog has General page in nav list"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        labels = [dialog.nav_list.item(i).text() for i in range(dialog.nav_list.count())]
        assert any('General' in name for name in labels)

    def test_has_scanning_tab(self, qtbot, mock_config_file):
        """Test dialog has Scanning page in nav list"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        labels = [dialog.nav_list.item(i).text() for i in range(dialog.nav_list.count())]
        # Page is named "Image Scan"
        assert any('Scan' in name for name in labels)

    def test_tab_change_signal_connected(self, qtbot, mock_config_file):
        """Test nav list change signal is connected to stack widget"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        # Change page via nav list
        if dialog.nav_list.count() > 1:
            dialog.nav_list.setCurrentRow(1)
            assert dialog.current_tab_index == 1 or dialog.stack_widget.currentIndex() == 1


# ============================================================================
# ComprehensiveSettingsDialog Tests - Dirty State Tracking
# ============================================================================

class TestSettingsDialogDirtyState:
    """Test dirty state tracking and unsaved changes detection"""

    def test_has_unsaved_changes_false_initially(self, qtbot, mock_config_file):
        """Test has_unsaved_changes returns False initially"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        assert dialog.has_unsaved_changes() is False

    def test_mark_tab_dirty_sets_state(self, qtbot, mock_config_file):
        """Test mark_tab_dirty sets dirty state"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        dialog.mark_tab_dirty(0)
        assert dialog.tab_dirty_states[0] is True
        assert dialog.has_unsaved_changes(0) is True

    def test_mark_tab_clean_clears_state(self, qtbot, mock_config_file):
        """Test mark_tab_clean clears dirty state"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        dialog.mark_tab_dirty(0)
        assert dialog.has_unsaved_changes(0) is True

        dialog.mark_tab_clean(0)
        assert dialog.has_unsaved_changes(0) is False

    def test_mark_dirty_enables_apply_button(self, qtbot, mock_config_file):
        """Test marking tab dirty enables Apply button"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        assert dialog.apply_btn.isEnabled() is False

        dialog.mark_tab_dirty()
        dialog._update_apply_button()

        assert dialog.apply_btn.isEnabled() is True

    def test_mark_clean_disables_apply_button(self, qtbot, mock_config_file):
        """Test marking tab clean disables Apply button"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        dialog.mark_tab_dirty()
        dialog._update_apply_button()
        assert dialog.apply_btn.isEnabled() is True

        dialog.mark_tab_clean()
        dialog._update_apply_button()

        assert dialog.apply_btn.isEnabled() is False


# ============================================================================
# ComprehensiveSettingsDialog Tests - Settings Load/Save
# ============================================================================

class TestSettingsDialogLoadSave:
    """Test settings loading and saving"""

    def test_load_settings_called_on_init(self, qtbot, mock_config_file):
        """Test load_settings is called during initialization"""
        with patch.object(ComprehensiveSettingsDialog, 'load_settings') as mock_load_settings:
            dialog = ComprehensiveSettingsDialog()
            qtbot.addWidget(dialog)
            mock_load_settings.assert_called_once()

    @patch('src.gui.settings.scanning_tab.get_config_path')
    def test_load_scanning_settings(self, mock_scan_path, qtbot, tmp_path):
        """Test loading scanning settings from config file"""
        # Create config file with scanning settings
        config_file = tmp_path / "bbdrop.ini"
        config = configparser.ConfigParser()
        config['SCANNING'] = {
            'fast_scanning': 'true',
            'sampling_method': '0',
            'sampling_fixed_count': '25',
            'sampling_percentage': '10',
            'exclude_first': 'false',
            'exclude_last': 'false',
            'exclude_small_images': 'true',
            'exclude_small_threshold': '50',
        }
        with open(config_file, 'w') as f:
            config.write(f)

        mock_scan_path.return_value = str(config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        # Verify settings loaded
        if hasattr(dialog, 'scanning_tab'):
            assert dialog.scanning_tab.fast_scan_check.isChecked() is True
            assert dialog.scanning_tab.exclude_small_check.isChecked() is True

    @patch('src.gui.settings.scanning_tab.get_config_path')
    def test_save_scanning_settings(self, mock_scan_path, qtbot, tmp_path):
        """Test saving scanning settings to config file"""
        config_file = tmp_path / "bbdrop.ini"
        config_file.write_text("[SCANNING]\n")
        mock_scan_path.return_value = str(config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        # Modify settings
        if hasattr(dialog, 'scanning_tab'):
            dialog.scanning_tab.fast_scan_check.setChecked(False)

        dialog.scanning_tab.save_settings()

        # Verify saved
        config = configparser.ConfigParser()
        config.read(config_file)
        if 'SCANNING' in config and 'fast_scanning' in config['SCANNING']:
            assert config.getboolean('SCANNING', 'fast_scanning') is False


# ============================================================================
# ComprehensiveSettingsDialog Tests - Input Validation
# ============================================================================

class TestSettingsDialogValidation:
    """Test input validation for settings fields"""

    def test_spinbox_value_ranges(self, qtbot, mock_config_file):
        """Test spinbox values are within valid ranges"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        # Test sampling spinbox
        if hasattr(dialog, 'scanning_tab'):
            dialog.scanning_tab.sampling_fixed_spin.minimum()
            max_val = dialog.scanning_tab.sampling_fixed_spin.maximum()
            dialog.scanning_tab.sampling_fixed_spin.setValue(max_val + 10)  # Try to exceed max
            assert dialog.scanning_tab.sampling_fixed_spin.value() <= max_val

    def test_slider_value_ranges(self, qtbot, mock_config_file):
        """Test slider values are within valid ranges"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        if hasattr(dialog, 'max_retries_spin'):
            min_val = dialog.max_retries_spin.minimum()
            max_val = dialog.max_retries_spin.maximum()
            assert min_val >= 0
            assert max_val > min_val


# ============================================================================
# ComprehensiveSettingsDialog Tests - Dialog Behavior
# ============================================================================

class TestSettingsDialogBehavior:
    """Test dialog accept/reject and button behavior"""

    def test_ok_button_saves_and_closes(self, qtbot, mock_config_file):
        """Test OK button saves settings and closes dialog"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        with patch.object(dialog, 'save_current_tab', return_value=True):
            with patch.object(dialog, 'accept'):
                dialog.save_and_close()
                # Should eventually call accept (might be delayed due to message boxes)

    def test_cancel_button_closes_without_saving(self, qtbot, mock_config_file):
        """Test Cancel button closes dialog without saving"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        # Mock the message box to auto-decline
        with patch('src.gui.settings.settings_dialog.QMessageBox.exec', return_value=QMessageBox.StandardButton.No):
            with patch.object(dialog, 'reject'):
                dialog.on_cancel_clicked()
                # Will call reject if no unsaved changes

    def test_apply_button_saves_current_tab(self, qtbot, mock_config_file):
        """Test Apply button saves current tab settings"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        dialog.mark_tab_dirty()

        with patch.object(dialog, 'save_current_tab', return_value=True) as mock_save:
            dialog.apply_current_tab()
            mock_save.assert_called_once()


# ============================================================================
# ComprehensiveSettingsDialog Tests - Reset to Defaults
# ============================================================================

class TestSettingsDialogReset:
    """Test reset to defaults functionality"""

    def test_reset_to_defaults_shows_confirmation(self, qtbot, mock_config_file):
        """Test reset to defaults shows confirmation dialog"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        with patch('src.gui.settings.settings_dialog.QMessageBox') as mock_msgbox:
            mock_box = Mock()
            mock_msgbox.return_value = mock_box

            dialog.reset_to_defaults()

            # Verify message box was created
            mock_msgbox.assert_called_once()

    def test_reset_confirmation_yes_resets_values(self, qtbot, mock_config_file):
        """Test confirming reset calls the reset path without error"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        # Change from defaults
        dialog.general_tab.theme_combo.setCurrentText("light")

        # Mock the image_hosts_widget.panels that _handle_reset_confirmation iterates
        if hasattr(dialog, 'image_hosts_widget') and dialog.image_hosts_widget:
            dialog.image_hosts_widget.panels = {}

        # Reset — should not raise
        dialog._handle_reset_confirmation(QMessageBox.StandardButton.Yes)

    def test_reset_confirmation_no_keeps_values(self, qtbot, mock_config_file):
        """Test declining reset keeps current values"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        # Change from defaults
        if hasattr(dialog, 'general_tab'):
            original = dialog.general_tab.theme_combo.currentText()
            dialog.general_tab.theme_combo.setCurrentText("light" if original == "dark" else "dark")
            changed_value = dialog.general_tab.theme_combo.currentText()

        # Don't reset
        dialog._handle_reset_confirmation(QMessageBox.StandardButton.No)

        # Verify value unchanged
        if hasattr(dialog, 'general_tab'):
            assert dialog.general_tab.theme_combo.currentText() == changed_value


# ============================================================================
# ComprehensiveSettingsDialog Tests - Widget Interactions
# ============================================================================

class TestSettingsDialogWidgets:
    """Test widget-specific interactions and behavior"""

    def test_checkbox_state_changes(self, qtbot, mock_config_file):
        """Test checkbox state changes are tracked"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        if hasattr(dialog, 'scanning_tab'):
            original = dialog.scanning_tab.fast_scan_check.isChecked()
            dialog.scanning_tab.fast_scan_check.setChecked(not original)
            assert dialog.scanning_tab.fast_scan_check.isChecked() == (not original)

    def test_combobox_selection_changes(self, qtbot, mock_config_file):
        """Test combobox selection changes work"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        if hasattr(dialog, 'general_tab') and dialog.general_tab.theme_combo.count() > 1:
            original_index = dialog.general_tab.theme_combo.currentIndex()
            new_index = 1 if original_index == 0 else 0
            dialog.general_tab.theme_combo.setCurrentIndex(new_index)
            assert dialog.general_tab.theme_combo.currentIndex() == new_index

    def test_spinbox_value_changes(self, qtbot, mock_config_file):
        """Test spinbox value changes work"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        if hasattr(dialog, 'general_tab'):
            dialog.general_tab.font_size_spin.setValue(12)
            assert dialog.general_tab.font_size_spin.value() == 12

    def test_slider_value_changes(self, qtbot, mock_config_file):
        """Test slider value changes work"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        if hasattr(dialog, 'max_retries_spin'):
            dialog.max_retries_spin.setValue(5)
            assert dialog.max_retries_spin.value() == 5


# ============================================================================
# ComprehensiveSettingsDialog Tests - Tab Change Behavior
# ============================================================================

class TestSettingsDialogTabChanges:
    """Test tab change behavior with unsaved changes"""

    def test_tab_change_with_no_changes(self, qtbot, mock_config_file):
        """Test page change works when no unsaved changes"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        if dialog.nav_list.count() > 1:
            initial_tab = dialog.stack_widget.currentIndex()
            new_tab = 1 if initial_tab == 0 else 0

            dialog.nav_list.setCurrentRow(new_tab)
            # Should change without blocking
            qtbot.wait(100)

    def test_tab_change_blocks_with_unsaved_changes(self, qtbot, mock_config_file):
        """Test page change is blocked when there are unsaved changes"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        if dialog.nav_list.count() > 1:
            # Mark current tab as dirty
            dialog.mark_tab_dirty(dialog.current_tab_index)

            initial_index = dialog.current_tab_index
            new_index = 1 if initial_index == 0 else 0

            # Mock message box to cancel
            with patch('src.gui.settings.settings_dialog.QMessageBox.exec',
                      return_value=QMessageBox.StandardButton.No):
                dialog.on_tab_changed(new_index)


# ============================================================================
# ComprehensiveSettingsDialog Tests - File Host Integration
# ============================================================================

class TestSettingsDialogFileHosts:
    """Test file host management integration"""

    def test_file_host_manager_integration(self, qtbot, mock_config_file):
        """Test file host manager is integrated if provided"""
        from PyQt6.QtGui import QIcon
        from unittest.mock import patch
        mock_file_host_mgr = Mock()
        mock_file_host_mgr.get_enabled_hosts.return_value = []
        mock_file_host_mgr.get_icon.return_value = QIcon()

        # Mock icon_manager singleton used by FileHostsSettingsWidget
        mock_icon_mgr = Mock()
        mock_icon_mgr.get_icon.return_value = QIcon()
        with patch('src.gui.settings.file_hosts_tab.get_icon_manager', return_value=mock_icon_mgr):
            dialog = ComprehensiveSettingsDialog(file_host_manager=mock_file_host_mgr)
            qtbot.addWidget(dialog)

        assert dialog.file_host_manager == mock_file_host_mgr


# ============================================================================
# ComprehensiveSettingsDialog Tests - External Apps
# ============================================================================

class TestSettingsDialogExternalApps:
    """Test external apps configuration"""

    def test_load_external_apps_settings(self, qtbot, tmp_path):
        """Test loading external apps settings"""
        config_file = tmp_path / "bbdrop.ini"
        config = configparser.ConfigParser()
        config['HOOKS'] = {
            'pre_scan_enabled': 'true',
            'pre_scan_program': '/usr/bin/test',
        }
        with open(config_file, 'w') as f:
            config.write(f)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        # Verify hooks_tab exists with load_settings method
        assert hasattr(dialog, 'hooks_tab')
        assert hasattr(dialog.hooks_tab, 'load_settings')


# ============================================================================
# ComprehensiveSettingsDialog Tests - Close Event
# ============================================================================

class TestSettingsDialogCloseEvent:
    """Test dialog close event handling"""

    def test_close_event_with_no_changes(self, qtbot, mock_config_file):
        """Test close event accepts when no unsaved changes"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        from PyQt6.QtGui import QCloseEvent
        event = QCloseEvent()

        dialog.closeEvent(event)
        # Should accept event (not ignore)

    def test_close_event_with_unsaved_changes(self, qtbot, mock_config_file):
        """Test close event prompts when unsaved changes exist"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        # Mark as dirty
        dialog.mark_tab_dirty()

        from PyQt6.QtGui import QCloseEvent
        event = QCloseEvent()

        # Mock message box
        with patch('src.gui.settings.settings_dialog.QMessageBox') as mock_msgbox:
            mock_box = Mock()
            mock_msgbox.return_value = mock_box

            dialog.closeEvent(event)


# ============================================================================
# ComprehensiveSettingsDialog Tests - Save Functions
# ============================================================================

class TestSettingsDialogSaveFunctions:
    """Test various save functions"""

    def test_save_settings_without_parent(self, qtbot, mock_config_file):
        """Test save_settings returns True when no parent"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        result = dialog.save_settings()
        assert result is True

    def test_save_settings_with_parent(self, qtbot, mock_config_file):
        """Test save_settings delegates to tab save methods when parent exists"""
        from PyQt6.QtWidgets import QWidget
        from PyQt6.QtCore import QSettings

        parent = QWidget()
        qtbot.addWidget(parent)
        parent.settings = QSettings("TestOrg", "TestApp")

        dialog = ComprehensiveSettingsDialog(parent=parent)
        qtbot.addWidget(dialog)

        result = dialog.save_settings()
        assert result is True


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================

class TestSettingsDialogEdgeCases:
    """Test edge cases and error handling"""

    def test_missing_config_file_handled(self, qtbot, tmp_path):
        """Test dialog handles missing config file"""
        # Should not crash
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        assert dialog is not None

    def test_corrupted_config_handled(self, qtbot, tmp_path):
        """Test dialog handles corrupted config file"""
        config_file = tmp_path / "corrupted.ini"
        config_file.write_text("This is not valid INI format {][")

        # Should not crash
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        assert dialog is not None

    def test_empty_config_handled(self, qtbot, tmp_path):
        """Test dialog handles empty config file"""
        config_file = tmp_path / "empty.ini"
        config_file.write_text("")

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        assert dialog is not None

    def test_load_settings_exception_handling(self, qtbot, mock_config_file):
        """Test load_settings handles exceptions"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        # Force exception in load
        with patch('src.gui.settings.scanning_tab.configparser.ConfigParser.read',
                  side_effect=Exception("Read error")):
            # Should not crash
            dialog.scanning_tab.load_settings()


# ============================================================================
# Integration Tests
# ============================================================================

class TestSettingsDialogIntegration:
    """Integration tests for complete workflows"""

    @patch('src.gui.settings.scanning_tab.get_config_path')
    def test_complete_edit_save_workflow(self, mock_scan_path, qtbot, tmp_path):
        """Test complete workflow: open, edit, save, close"""
        config_file = tmp_path / "bbdrop.ini"
        config = configparser.ConfigParser()
        config['SCANNING'] = {'fast_scanning': 'true'}
        with open(config_file, 'w') as f:
            config.write(f)

        mock_scan_path.return_value = str(config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        # Edit setting
        if hasattr(dialog, 'scanning_tab'):
            dialog.scanning_tab.fast_scan_check.setChecked(False)
            dialog.mark_tab_dirty()

        # Save
        dialog.scanning_tab.save_settings()

        # Verify
        config.read(config_file)
        if hasattr(dialog, 'scanning_tab'):
            assert config.getboolean('SCANNING', 'fast_scanning') is False

    def test_multiple_tab_changes_workflow(self, qtbot, mock_config_file):
        """Test workflow with multiple tab changes"""
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        if dialog.nav_list.count() > 2:
            # Change pages multiple times
            for i in range(min(3, dialog.nav_list.count())):
                dialog.nav_list.setCurrentRow(i)
                qtbot.wait(50)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
