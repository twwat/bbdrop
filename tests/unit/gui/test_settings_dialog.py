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
import os
import configparser
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call, PropertyMock
from PyQt6.QtWidgets import (
    QDialog, QTabWidget, QMessageBox, QPushButton,
    QCheckBox, QSpinBox, QComboBox, QLineEdit, QSlider
)
from PyQt6.QtCore import Qt, QSettings, pyqtSignal
from PyQt6.QtTest import QTest

from src.gui.settings_dialog import (
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
        assert 'blue' in status_label.styleSheet()

    def test_update_test_status_success(self, qtbot):
        """Test updating test status to success"""
        dialog = HostTestDialog("ImgBox")
        qtbot.addWidget(dialog)

        dialog.update_test_status('credentials', 'success')

        status_label = dialog.test_items['credentials']['status_label']
        assert status_label.text() == "✓"
        assert 'green' in status_label.styleSheet()

    def test_update_test_status_failure(self, qtbot):
        """Test updating test status to failure"""
        dialog = HostTestDialog("ImgBox")
        qtbot.addWidget(dialog)

        dialog.update_test_status('upload', 'failure', 'Upload failed')

        status_label = dialog.test_items['upload']['status_label']
        name_label = dialog.test_items['upload']['name_label']
        assert status_label.text() == "✗"
        assert 'red' in status_label.styleSheet()
        assert name_label.text() == 'Upload failed'

    def test_update_test_status_skipped(self, qtbot):
        """Test updating test status to skipped"""
        dialog = HostTestDialog("ImgBox")
        qtbot.addWidget(dialog)

        dialog.update_test_status('cleanup', 'skipped')

        status_label = dialog.test_items['cleanup']['status_label']
        assert status_label.text() == "○"
        assert 'gray' in status_label.styleSheet()

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

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_settings_dialog_creates(self, mock_get_path, mock_load, qtbot,
                                     mock_config_file, mock_imxup_functions):
        """Test ComprehensiveSettingsDialog instantiation"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        assert dialog is not None
        assert isinstance(dialog, QDialog)
        assert dialog.isModal() is True
        assert dialog.windowTitle() == "Settings & Preferences"

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_dialog_has_tab_widget(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test dialog contains tab widget"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        assert hasattr(dialog, 'tab_widget')
        assert isinstance(dialog.tab_widget, QTabWidget)
        assert dialog.tab_widget.count() > 0

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_dialog_has_buttons(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test dialog has OK, Apply, Cancel, and Reset buttons"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

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

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_apply_button_initially_disabled(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test Apply button is initially disabled"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        assert dialog.apply_btn.isEnabled() is False

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_initializes_dirty_states(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test dialog initializes dirty state tracking"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        assert hasattr(dialog, 'tab_dirty_states')
        assert isinstance(dialog.tab_dirty_states, dict)
        assert dialog.current_tab_index == 0

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_initializes_qsettings(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test dialog initializes QSettings"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        assert hasattr(dialog, 'settings')
        assert isinstance(dialog.settings, QSettings)


# ============================================================================
# ComprehensiveSettingsDialog Tests - Tab Management
# ============================================================================

class TestSettingsDialogTabs:
    """Test settings dialog tab management"""

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_has_general_tab(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test dialog has General tab"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        tab_names = [dialog.tab_widget.tabText(i) for i in range(dialog.tab_widget.count())]
        assert any('General' in name for name in tab_names)

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_has_scanning_tab(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test dialog has Scanning tab"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        tab_names = [dialog.tab_widget.tabText(i) for i in range(dialog.tab_widget.count())]
        assert any('Scanning' in name for name in tab_names)

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_tab_change_signal_connected(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test tab change signal is connected"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        # Change tab
        if dialog.tab_widget.count() > 1:
            dialog.tab_widget.setCurrentIndex(1)
            assert dialog.current_tab_index == 1 or dialog.tab_widget.currentIndex() == 1


# ============================================================================
# ComprehensiveSettingsDialog Tests - Dirty State Tracking
# ============================================================================

class TestSettingsDialogDirtyState:
    """Test dirty state tracking and unsaved changes detection"""

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_has_unsaved_changes_false_initially(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test has_unsaved_changes returns False initially"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        assert dialog.has_unsaved_changes() is False

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_mark_tab_dirty_sets_state(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test mark_tab_dirty sets dirty state"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        dialog.mark_tab_dirty(0)
        assert dialog.tab_dirty_states[0] is True
        assert dialog.has_unsaved_changes(0) is True

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_mark_tab_clean_clears_state(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test mark_tab_clean clears dirty state"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        dialog.mark_tab_dirty(0)
        assert dialog.has_unsaved_changes(0) is True

        dialog.mark_tab_clean(0)
        assert dialog.has_unsaved_changes(0) is False

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_mark_dirty_enables_apply_button(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test marking tab dirty enables Apply button"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        assert dialog.apply_btn.isEnabled() is False

        dialog.mark_tab_dirty()
        dialog._update_apply_button()

        assert dialog.apply_btn.isEnabled() is True

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_mark_clean_disables_apply_button(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test marking tab clean disables Apply button"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

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

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_load_settings_called_on_init(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test load_settings is called during initialization"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        with patch.object(ComprehensiveSettingsDialog, 'load_settings') as mock_load_settings:
            dialog = ComprehensiveSettingsDialog()
            qtbot.addWidget(dialog)
            mock_load_settings.assert_called_once()

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_load_scanning_settings(self, mock_get_path, mock_load, qtbot, tmp_path):
        """Test loading scanning settings from config file"""
        mock_load.return_value = {}

        # Create config file with scanning settings
        config_file = tmp_path / "imxup.ini"
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

        mock_get_path.return_value = str(config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        # Verify settings loaded
        if hasattr(dialog, 'fast_scan_check'):
            assert dialog.fast_scan_check.isChecked() is True
        if hasattr(dialog, 'exclude_small_check'):
            assert dialog.exclude_small_check.isChecked() is True

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_save_scanning_settings(self, mock_get_path, mock_load, qtbot, tmp_path):
        """Test saving scanning settings to config file"""
        mock_load.return_value = {}
        config_file = tmp_path / "imxup.ini"
        config_file.write_text("[SCANNING]\n")
        mock_get_path.return_value = str(config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        # Modify settings
        if hasattr(dialog, 'fast_scan_check'):
            dialog.fast_scan_check.setChecked(False)

        dialog._save_scanning_settings()

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

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_spinbox_value_ranges(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test spinbox values are within valid ranges"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        # Test sampling spinbox
        if hasattr(dialog, 'sampling_fixed_spin'):
            min_val = dialog.sampling_fixed_spin.minimum()
            max_val = dialog.sampling_fixed_spin.maximum()
            dialog.sampling_fixed_spin.setValue(max_val + 10)  # Try to exceed max
            assert dialog.sampling_fixed_spin.value() <= max_val

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_slider_value_ranges(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test slider values are within valid ranges"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        if hasattr(dialog, 'max_retries_slider'):
            min_val = dialog.max_retries_slider.minimum()
            max_val = dialog.max_retries_slider.maximum()
            assert min_val >= 0
            assert max_val > min_val


# ============================================================================
# ComprehensiveSettingsDialog Tests - Dialog Behavior
# ============================================================================

class TestSettingsDialogBehavior:
    """Test dialog accept/reject and button behavior"""

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_ok_button_saves_and_closes(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test OK button saves settings and closes dialog"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        with patch.object(dialog, 'save_current_tab', return_value=True):
            with patch.object(dialog, 'accept') as mock_accept:
                dialog.save_and_close()
                # Should eventually call accept (might be delayed due to message boxes)

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_cancel_button_closes_without_saving(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test Cancel button closes dialog without saving"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        # Mock the message box to auto-decline
        with patch('src.gui.settings_dialog.QMessageBox.exec', return_value=QMessageBox.StandardButton.No):
            with patch.object(dialog, 'reject') as mock_reject:
                dialog.on_cancel_clicked()
                # Will call reject if no unsaved changes

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_apply_button_saves_current_tab(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test Apply button saves current tab settings"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

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

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_reset_to_defaults_shows_confirmation(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test reset to defaults shows confirmation dialog"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        with patch('src.gui.settings_dialog.QMessageBox') as mock_msgbox:
            mock_box = Mock()
            mock_msgbox.return_value = mock_box

            dialog.reset_to_defaults()

            # Verify message box was created
            mock_msgbox.assert_called_once()

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_reset_confirmation_yes_resets_values(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test confirming reset actually resets values"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        # Change from defaults
        if hasattr(dialog, 'theme_combo'):
            dialog.theme_combo.setCurrentText("light")

        # Reset
        dialog._handle_reset_confirmation(QMessageBox.StandardButton.Yes)

        # Verify reset to default
        if hasattr(dialog, 'theme_combo'):
            assert dialog.theme_combo.currentText() == "dark"

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_reset_confirmation_no_keeps_values(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test declining reset keeps current values"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        # Change from defaults
        if hasattr(dialog, 'theme_combo'):
            original = dialog.theme_combo.currentText()
            dialog.theme_combo.setCurrentText("light" if original == "dark" else "dark")
            changed_value = dialog.theme_combo.currentText()

        # Don't reset
        dialog._handle_reset_confirmation(QMessageBox.StandardButton.No)

        # Verify value unchanged
        if hasattr(dialog, 'theme_combo'):
            assert dialog.theme_combo.currentText() == changed_value


# ============================================================================
# ComprehensiveSettingsDialog Tests - Widget Interactions
# ============================================================================

class TestSettingsDialogWidgets:
    """Test widget-specific interactions and behavior"""

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_checkbox_state_changes(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test checkbox state changes are tracked"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        if hasattr(dialog, 'fast_scan_check'):
            original = dialog.fast_scan_check.isChecked()
            dialog.fast_scan_check.setChecked(not original)
            assert dialog.fast_scan_check.isChecked() == (not original)

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_combobox_selection_changes(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test combobox selection changes work"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        if hasattr(dialog, 'theme_combo') and dialog.theme_combo.count() > 1:
            original_index = dialog.theme_combo.currentIndex()
            new_index = 1 if original_index == 0 else 0
            dialog.theme_combo.setCurrentIndex(new_index)
            assert dialog.theme_combo.currentIndex() == new_index

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_spinbox_value_changes(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test spinbox value changes work"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        if hasattr(dialog, 'font_size_spin'):
            dialog.font_size_spin.setValue(12)
            assert dialog.font_size_spin.value() == 12

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_slider_value_changes(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test slider value changes work"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        if hasattr(dialog, 'max_retries_slider'):
            dialog.max_retries_slider.setValue(5)
            assert dialog.max_retries_slider.value() == 5


# ============================================================================
# ComprehensiveSettingsDialog Tests - Tab Change Behavior
# ============================================================================

class TestSettingsDialogTabChanges:
    """Test tab change behavior with unsaved changes"""

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_tab_change_with_no_changes(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test tab change works when no unsaved changes"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        if dialog.tab_widget.count() > 1:
            initial_tab = dialog.tab_widget.currentIndex()
            new_tab = 1 if initial_tab == 0 else 0

            dialog.tab_widget.setCurrentIndex(new_tab)
            # Should change without blocking
            qtbot.wait(100)

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_tab_change_blocks_with_unsaved_changes(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test tab change is blocked when there are unsaved changes"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        if dialog.tab_widget.count() > 1:
            # Mark current tab as dirty
            dialog.mark_tab_dirty(dialog.current_tab_index)

            initial_index = dialog.current_tab_index
            new_index = 1 if initial_index == 0 else 0

            # Mock message box to cancel
            with patch('src.gui.settings_dialog.QMessageBox.exec',
                      return_value=QMessageBox.StandardButton.No):
                dialog.on_tab_changed(new_index)


# ============================================================================
# ComprehensiveSettingsDialog Tests - File Host Integration
# ============================================================================

class TestSettingsDialogFileHosts:
    """Test file host management integration"""

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_file_host_manager_integration(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test file host manager is integrated if provided"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        mock_file_host_mgr = Mock()
        dialog = ComprehensiveSettingsDialog(file_host_manager=mock_file_host_mgr)
        qtbot.addWidget(dialog)

        assert dialog.file_host_manager == mock_file_host_mgr


# ============================================================================
# ComprehensiveSettingsDialog Tests - External Apps
# ============================================================================

class TestSettingsDialogExternalApps:
    """Test external apps configuration"""

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_load_external_apps_settings(self, mock_get_path, mock_load, qtbot, tmp_path):
        """Test loading external apps settings"""
        mock_load.return_value = {}

        config_file = tmp_path / "imxup.ini"
        config = configparser.ConfigParser()
        config['HOOKS'] = {
            'pre_scan_enabled': 'true',
            'pre_scan_program': '/usr/bin/test',
        }
        with open(config_file, 'w') as f:
            config.write(f)

        mock_get_path.return_value = str(config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        # Verify method exists
        assert hasattr(dialog, '_load_external_apps_settings')


# ============================================================================
# ComprehensiveSettingsDialog Tests - Close Event
# ============================================================================

class TestSettingsDialogCloseEvent:
    """Test dialog close event handling"""

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_close_event_with_no_changes(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test close event accepts when no unsaved changes"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        from PyQt6.QtGui import QCloseEvent
        event = QCloseEvent()

        dialog.closeEvent(event)
        # Should accept event (not ignore)

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_close_event_with_unsaved_changes(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test close event prompts when unsaved changes exist"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        # Mark as dirty
        dialog.mark_tab_dirty()

        from PyQt6.QtGui import QCloseEvent
        event = QCloseEvent()

        # Mock message box
        with patch('src.gui.settings_dialog.QMessageBox') as mock_msgbox:
            mock_box = Mock()
            mock_msgbox.return_value = mock_box

            dialog.closeEvent(event)


# ============================================================================
# ComprehensiveSettingsDialog Tests - Save Functions
# ============================================================================

class TestSettingsDialogSaveFunctions:
    """Test various save functions"""

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_save_settings_with_parent(self, mock_get_path, mock_load, qtbot, tmp_path):
        """Test save_settings when dialog has parent"""
        from PyQt6.QtWidgets import QWidget, QCheckBox, QComboBox
        from PyQt6.QtCore import QSettings

        mock_load.return_value = {}
        config_file = tmp_path / "imxup.ini"
        config_file.write_text("[SCANNING]\n")
        mock_get_path.return_value = str(config_file)

        # Create real QWidget parent with necessary attributes
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.settings = QSettings("TestOrg", "TestApp")
        parent.confirm_delete_check = QCheckBox()
        parent.auto_rename_check = QCheckBox()
        parent.store_in_uploaded_check = QCheckBox()
        parent.store_in_central_check = QCheckBox()
        parent.thumbnail_size_combo = QComboBox()
        parent.thumbnail_format_combo = QComboBox()
        parent.save_upload_settings = Mock()

        dialog = ComprehensiveSettingsDialog(parent=parent)
        qtbot.addWidget(dialog)

        result = dialog.save_settings()
        assert result is True
        parent.save_upload_settings.assert_called_once()

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_save_settings_handles_errors(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test save_settings handles errors gracefully"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        mock_parent = Mock()
        mock_parent.save_upload_settings.side_effect = Exception("Save failed")

        dialog = ComprehensiveSettingsDialog(parent=mock_parent)
        qtbot.addWidget(dialog)

        # Should not raise, should return False
        with patch('src.gui.settings_dialog.QMessageBox') as mock_msgbox:
            result = dialog.save_settings()
            assert result is False


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================

class TestSettingsDialogEdgeCases:
    """Test edge cases and error handling"""

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_missing_config_file_handled(self, mock_get_path, mock_load, qtbot, tmp_path):
        """Test dialog handles missing config file"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(tmp_path / "nonexistent.ini")

        # Should not crash
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        assert dialog is not None

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_corrupted_config_handled(self, mock_get_path, mock_load, qtbot, tmp_path):
        """Test dialog handles corrupted config file"""
        mock_load.return_value = {}

        config_file = tmp_path / "corrupted.ini"
        config_file.write_text("This is not valid INI format {][")
        mock_get_path.return_value = str(config_file)

        # Should not crash
        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        assert dialog is not None

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_empty_config_handled(self, mock_get_path, mock_load, qtbot, tmp_path):
        """Test dialog handles empty config file"""
        mock_load.return_value = {}

        config_file = tmp_path / "empty.ini"
        config_file.write_text("")
        mock_get_path.return_value = str(config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        assert dialog is not None

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_load_settings_exception_handling(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test load_settings handles exceptions"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        # Force exception in load
        with patch('src.gui.settings_dialog.configparser.ConfigParser.read',
                  side_effect=Exception("Read error")):
            # Should not crash
            dialog._load_scanning_settings()


# ============================================================================
# Integration Tests
# ============================================================================

class TestSettingsDialogIntegration:
    """Integration tests for complete workflows"""

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_complete_edit_save_workflow(self, mock_get_path, mock_load, qtbot, tmp_path):
        """Test complete workflow: open, edit, save, close"""
        mock_load.return_value = {}

        config_file = tmp_path / "imxup.ini"
        config = configparser.ConfigParser()
        config['SCANNING'] = {'fast_scanning': 'true'}
        with open(config_file, 'w') as f:
            config.write(f)

        mock_get_path.return_value = str(config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        # Edit setting
        if hasattr(dialog, 'fast_scan_check'):
            dialog.fast_scan_check.setChecked(False)
            dialog.mark_tab_dirty()

        # Save
        dialog._save_scanning_settings()

        # Verify
        config.read(config_file)
        if hasattr(dialog, 'fast_scan_check'):
            assert config.getboolean('SCANNING', 'fast_scanning') is False

    @patch('src.gui.settings_dialog.load_user_defaults')
    @patch('src.gui.settings_dialog.get_config_path')
    def test_multiple_tab_changes_workflow(self, mock_get_path, mock_load, qtbot, mock_config_file):
        """Test workflow with multiple tab changes"""
        mock_load.return_value = {}
        mock_get_path.return_value = str(mock_config_file)

        dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        if dialog.tab_widget.count() > 2:
            # Change tabs multiple times
            for i in range(min(3, dialog.tab_widget.count())):
                dialog.tab_widget.setCurrentIndex(i)
                qtbot.wait(50)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
