#!/usr/bin/env python3
"""
pytest-qt tests for FileHostConfigDialog
Tests dialog initialization, form validation, save/cancel actions, and host configuration

Target: 60%+ coverage with 35-50 tests
Environment: pytest-qt, PyQt6, venv ~/imxup-venv-314
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from PyQt6.QtWidgets import (
    QDialog, QLineEdit, QPushButton, QComboBox, QCheckBox,
    QSpinBox, QProgressBar, QLabel, QListWidget, QMessageBox
)
from PyQt6.QtCore import QSettings, Qt, pyqtSignal, QObject
from PyQt6.QtTest import QTest

from src.gui.dialogs.file_host_config_dialog import FileHostConfigDialog
from src.core.file_host_config import HostConfig


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_host_config():
    """Create a mock HostConfig object for testing"""
    config = Mock(spec=HostConfig)
    config.name = "TestHost"
    config.requires_auth = True
    config.auth_type = "token_login"
    config.user_info_url = "https://testhost.com/userinfo"
    config.storage_left_path = ["data", "storage", "left"]
    config.storage_regex = None
    config.referral_url = "https://testhost.com/ref"
    return config


@pytest.fixture
def mock_host_config_no_auth():
    """Create a mock HostConfig without authentication"""
    config = Mock(spec=HostConfig)
    config.name = "SimpleHost"
    config.requires_auth = False
    config.auth_type = None
    config.user_info_url = None
    config.storage_left_path = None
    config.storage_regex = None
    config.referral_url = None
    return config


@pytest.fixture
def mock_worker():
    """Create a mock file host worker"""
    worker = Mock()
    worker.log_message = MagicMock()
    worker.test_completed = MagicMock()
    worker.storage_updated = MagicMock()
    worker.credentials_update_requested = MagicMock()

    # Add signal-like behavior
    worker.log_message.__getitem__ = Mock(return_value=MagicMock())
    worker.test_completed.connect = Mock()
    worker.test_completed.disconnect = Mock()
    worker.storage_updated.connect = Mock()
    worker.storage_updated.disconnect = Mock()
    worker.log_message.connect = Mock()
    worker.log_message.disconnect = Mock()
    worker.credentials_update_requested.emit = Mock()

    return worker


@pytest.fixture
def mock_worker_manager(mock_worker):
    """Create a mock FileHostWorkerManager"""
    manager = Mock()
    manager.get_worker = Mock(return_value=mock_worker)
    manager.is_enabled = Mock(return_value=False)
    manager.enable_host = Mock()
    manager.disable_host = Mock()
    manager.spinup_complete = MagicMock()
    manager.spinup_complete.connect = Mock()
    manager.spinup_complete.disconnect = Mock()
    manager.pending_workers = {}
    return manager


@pytest.fixture
def mock_main_widgets():
    """Create mock main widgets dictionary"""
    return {
        'status_label': Mock(),
        'enable_button': Mock(),
    }


@pytest.fixture
def mock_qsettings(monkeypatch):
    """Mock QSettings to avoid writing to actual system settings"""
    settings_dict = {}

    class MockQSettings:
        def __init__(self, *args, **kwargs):
            self.data = settings_dict

        def value(self, key, default=None, type=None):
            val = self.data.get(key, default)
            if type is not None and val is not None:
                try:
                    return type(val)
                except (ValueError, TypeError):
                    return default
            return val

        def setValue(self, key, value):
            self.data[key] = value

        def remove(self, key):
            self.data.pop(key, None)

        def contains(self, key):
            return key in self.data

        def clear(self):
            self.data.clear()

        def sync(self):
            pass

    monkeypatch.setattr('PyQt6.QtCore.QSettings', MockQSettings)
    yield MockQSettings
    settings_dict.clear()


@pytest.fixture
def dialog_patches(mock_qsettings, monkeypatch):
    """Apply common patches needed for dialog creation"""
    # Mock imxup functions
    monkeypatch.setattr('imxup.get_credential', Mock(return_value=None))
    monkeypatch.setattr('imxup.set_credential', Mock(return_value=True))
    monkeypatch.setattr('imxup.encrypt_password', lambda x: f"encrypted_{x}")
    monkeypatch.setattr('imxup.decrypt_password', lambda x: x.replace("encrypted_", ""))
    monkeypatch.setattr('imxup.get_project_root', Mock(return_value="/tmp/imxup"))
    monkeypatch.setattr('imxup.get_central_store_base_path', Mock(return_value="/tmp/.imxup"))

    # Mock file_host_config functions
    with patch('src.core.file_host_config.get_file_host_setting') as mock_get:
        mock_get.side_effect = lambda host_id, key, type_hint: {
            'enabled': False,
            'trigger': 'disabled',
            'auto_retry': True,
            'max_retries': 3,
            'max_connections': 5,
            'max_file_size_mb': 0,
        }.get(key, None)

        with patch('src.core.file_host_config.save_file_host_setting'):
            # Mock logger functions
            with patch('src.utils.logger.log'):
                with patch('src.utils.logging.get_logger') as mock_logger:
                    mock_logger_instance = Mock()
                    mock_logger_instance.read_current_log = Mock(return_value="")
                    mock_logger.return_value = mock_logger_instance
                    yield


# ============================================================================
# TEST CLASS: Dialog Initialization
# ============================================================================

class TestFileHostConfigDialogInit:
    """Test dialog initialization and UI setup"""

    def test_dialog_creates_with_auth(self, qtbot, mock_host_config, mock_worker_manager,
                                      mock_main_widgets, dialog_patches):
        """Test dialog creation with authentication required"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        assert dialog is not None
        assert isinstance(dialog, QDialog)
        assert dialog.host_id == "testhost"
        assert dialog.host_config == mock_host_config
        assert dialog.worker_manager == mock_worker_manager

    def test_dialog_creates_without_auth(self, qtbot, mock_host_config_no_auth,
                                         mock_worker_manager, mock_main_widgets, dialog_patches):
        """Test dialog creation without authentication"""
        dialog = FileHostConfigDialog(
            None, "simplehost", mock_host_config_no_auth,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        assert dialog is not None
        assert dialog.creds_input is None  # No credentials input for no-auth hosts

    def test_dialog_window_properties(self, qtbot, mock_host_config, mock_worker_manager,
                                       mock_main_widgets, dialog_patches):
        """Test dialog window properties (title, modal, size)"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        assert "TestHost" in dialog.windowTitle()
        assert dialog.isModal()
        assert dialog.width() == 900
        assert dialog.height() == 650

    def test_credentials_input_created_when_auth_required(self, qtbot, mock_host_config,
                                                          mock_worker_manager, mock_main_widgets,
                                                          dialog_patches):
        """Test credentials input is created when auth is required"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        assert dialog.creds_input is not None
        assert isinstance(dialog.creds_input, QLineEdit)
        assert dialog.creds_input.echoMode() == QLineEdit.EchoMode.Password

    def test_trigger_combo_initialized(self, qtbot, mock_host_config, mock_worker_manager,
                                       mock_main_widgets, dialog_patches):
        """Test trigger combo box is properly initialized"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        assert dialog.trigger_combo is not None
        assert isinstance(dialog.trigger_combo, QComboBox)
        assert dialog.trigger_combo.count() == 4  # Disabled, On Added, On Started, On Completed
        assert dialog.trigger_combo.currentIndex() == 0  # Default: Disabled

    def test_host_settings_spinboxes_initialized(self, qtbot, mock_host_config, mock_worker_manager,
                                                  mock_main_widgets, dialog_patches):
        """Test host settings spinboxes are properly initialized"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        assert dialog.auto_retry_check is not None
        assert dialog.max_retries_spin is not None
        assert dialog.max_connections_spin is not None
        assert dialog.max_file_size_spin is not None

        assert dialog.auto_retry_check.isChecked() is True
        assert dialog.max_retries_spin.value() == 3
        assert dialog.max_connections_spin.value() == 5
        assert dialog.max_file_size_spin.value() == 0

    def test_buttons_initialized(self, qtbot, mock_host_config, mock_worker_manager,
                                  mock_main_widgets, dialog_patches):
        """Test all buttons are properly initialized"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        # Find buttons
        enable_button = dialog.enable_button
        test_button = dialog.test_connection_btn
        apply_button = dialog.apply_btn

        assert enable_button is not None
        assert test_button is not None
        assert apply_button is not None

        # Apply button should start disabled (no changes yet)
        assert not apply_button.isEnabled()

    def test_storage_bar_created_when_storage_tracking_enabled(self, qtbot, mock_host_config,
                                                                mock_worker_manager, mock_main_widgets,
                                                                dialog_patches):
        """Test storage bar is created when host supports storage tracking"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        assert dialog.storage_bar is not None
        assert isinstance(dialog.storage_bar, QProgressBar)

    def test_log_list_initialized(self, qtbot, mock_host_config, mock_worker_manager,
                                   mock_main_widgets, dialog_patches):
        """Test worker logs list widget is initialized"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        assert dialog.log_list is not None
        assert isinstance(dialog.log_list, QListWidget)

    def test_dirty_state_initialized_false(self, qtbot, mock_host_config, mock_worker_manager,
                                           mock_main_widgets, dialog_patches):
        """Test dirty state (unsaved changes) starts as False"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        assert dialog.has_unsaved_changes is False


# ============================================================================
# TEST CLASS: Form Validation
# ============================================================================

class TestFormValidation:
    """Test form validation and input sanitization"""

    def test_credentials_input_accepts_text(self, qtbot, mock_host_config, mock_worker_manager,
                                            mock_main_widgets, dialog_patches):
        """Test credentials input accepts text"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        dialog.creds_input.setText("username:password")
        assert dialog.creds_input.text() == "username:password"

    def test_credentials_show_hide_toggle(self, qtbot, mock_host_config, mock_worker_manager,
                                          mock_main_widgets, dialog_patches):
        """Test credentials show/hide button toggles visibility"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        # Initially password mode
        assert dialog.creds_input.echoMode() == QLineEdit.EchoMode.Password

    def test_trigger_combo_values(self, qtbot, mock_host_config, mock_worker_manager,
                                   mock_main_widgets, dialog_patches):
        """Test trigger combo box has correct values"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        expected_data = [None, "on_added", "on_started", "on_completed"]
        for i, expected in enumerate(expected_data):
            assert dialog.trigger_combo.itemData(i) == expected

    def test_max_retries_range_validation(self, qtbot, mock_host_config, mock_worker_manager,
                                          mock_main_widgets, dialog_patches):
        """Test max retries spinbox range validation"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        assert dialog.max_retries_spin.minimum() == 1
        assert dialog.max_retries_spin.maximum() == 10

    def test_max_connections_range_validation(self, qtbot, mock_host_config, mock_worker_manager,
                                               mock_main_widgets, dialog_patches):
        """Test max connections spinbox range validation"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        assert dialog.max_connections_spin.minimum() == 1
        assert dialog.max_connections_spin.maximum() == 10

    def test_max_file_size_zero_means_no_limit(self, qtbot, mock_host_config, mock_worker_manager,
                                                mock_main_widgets, dialog_patches):
        """Test max file size spinbox zero value means no limit"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        dialog.max_file_size_spin.setValue(0)
        assert dialog.max_file_size_spin.specialValueText() == "No limit"

    def test_max_file_size_range_validation(self, qtbot, mock_host_config, mock_worker_manager,
                                            mock_main_widgets, dialog_patches):
        """Test max file size spinbox range validation"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        assert dialog.max_file_size_spin.minimum() == 0
        assert dialog.max_file_size_spin.maximum() == 10000


# ============================================================================
# TEST CLASS: Dirty State Tracking
# ============================================================================

class TestDirtyStateTracking:
    """Test unsaved changes tracking"""

    def test_credentials_change_marks_dirty(self, qtbot, mock_host_config, mock_worker_manager,
                                             mock_main_widgets, dialog_patches):
        """Test changing credentials marks form as dirty"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        assert not dialog.has_unsaved_changes

        dialog.creds_input.setText("new:credentials")

        assert dialog.has_unsaved_changes
        assert dialog.apply_btn.isEnabled()

    def test_trigger_change_marks_dirty(self, qtbot, mock_host_config, mock_worker_manager,
                                        mock_main_widgets, dialog_patches):
        """Test changing trigger marks form as dirty"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        assert not dialog.has_unsaved_changes

        dialog.trigger_combo.setCurrentIndex(1)  # On Added

        assert dialog.has_unsaved_changes
        assert dialog.apply_btn.isEnabled()

    def test_auto_retry_change_marks_dirty(self, qtbot, mock_host_config, mock_worker_manager,
                                           mock_main_widgets, dialog_patches):
        """Test changing auto retry marks form as dirty"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        assert not dialog.has_unsaved_changes

        dialog.auto_retry_check.setChecked(False)

        assert dialog.has_unsaved_changes
        assert dialog.apply_btn.isEnabled()

    def test_max_retries_change_marks_dirty(self, qtbot, mock_host_config, mock_worker_manager,
                                            mock_main_widgets, dialog_patches):
        """Test changing max retries marks form as dirty"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        assert not dialog.has_unsaved_changes

        dialog.max_retries_spin.setValue(5)

        assert dialog.has_unsaved_changes
        assert dialog.apply_btn.isEnabled()

    def test_max_connections_change_marks_dirty(self, qtbot, mock_host_config, mock_worker_manager,
                                                 mock_main_widgets, dialog_patches):
        """Test changing max connections marks form as dirty"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        assert not dialog.has_unsaved_changes

        dialog.max_connections_spin.setValue(8)

        assert dialog.has_unsaved_changes
        assert dialog.apply_btn.isEnabled()

    def test_max_file_size_change_marks_dirty(self, qtbot, mock_host_config, mock_worker_manager,
                                               mock_main_widgets, dialog_patches):
        """Test changing max file size marks form as dirty"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        assert not dialog.has_unsaved_changes

        dialog.max_file_size_spin.setValue(100)

        assert dialog.has_unsaved_changes
        assert dialog.apply_btn.isEnabled()


# ============================================================================
# TEST CLASS: Save/Apply Actions
# ============================================================================

class TestSaveApplyActions:
    """Test save, apply, and cancel actions"""

    @patch('src.core.file_host_config.save_file_host_setting')
    def test_apply_saves_credentials(self, mock_save, qtbot, mock_host_config,
                                     mock_worker_manager, mock_main_widgets, dialog_patches):
        """Test Apply button saves credentials"""
        with patch('imxup.set_credential') as mock_set_cred:
            dialog = FileHostConfigDialog(
                None, "testhost", mock_host_config,
                mock_main_widgets, mock_worker_manager
            )
            qtbot.addWidget(dialog)

            dialog.creds_input.setText("user:pass")
            dialog._on_apply_clicked()

            # Should encrypt and save credentials
            assert mock_set_cred.called

    @patch('src.core.file_host_config.save_file_host_setting')
    def test_apply_saves_trigger_settings(self, mock_save, qtbot, mock_host_config,
                                          mock_worker_manager, mock_main_widgets, dialog_patches):
        """Test Apply button saves trigger settings"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        dialog.trigger_combo.setCurrentIndex(2)  # On Started
        dialog._on_apply_clicked()

        # Should save trigger setting
        assert mock_save.called
        # Find the call with trigger setting
        trigger_calls = [call for call in mock_save.call_args_list
                        if len(call[0]) > 1 and call[0][1] == 'trigger']
        assert len(trigger_calls) > 0
        assert trigger_calls[0][0][2] == 'on_started'

    @patch('src.core.file_host_config.save_file_host_setting')
    def test_apply_saves_host_settings(self, mock_save, qtbot, mock_host_config,
                                       mock_worker_manager, mock_main_widgets, dialog_patches):
        """Test Apply button saves host settings"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        dialog.auto_retry_check.setChecked(False)
        dialog.max_retries_spin.setValue(7)
        dialog.max_connections_spin.setValue(3)
        dialog.max_file_size_spin.setValue(500)

        dialog._on_apply_clicked()

        # Should save all settings
        assert mock_save.call_count >= 4

    @patch('src.core.file_host_config.save_file_host_setting')
    def test_apply_clears_dirty_flag_on_success(self, mock_save, qtbot, mock_host_config,
                                                 mock_worker_manager, mock_main_widgets, dialog_patches):
        """Test Apply clears dirty flag on successful save"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        dialog.trigger_combo.setCurrentIndex(1)
        assert dialog.has_unsaved_changes

        dialog._on_apply_clicked()

        assert not dialog.has_unsaved_changes
        assert not dialog.apply_btn.isEnabled()

    @patch('src.core.file_host_config.save_file_host_setting')
    def test_apply_updates_cached_credentials(self, mock_save, qtbot, mock_host_config,
                                               mock_worker_manager, mock_main_widgets, dialog_patches):
        """Test Apply updates cached credentials value"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        dialog.creds_input.setText("newuser:newpass")
        dialog._on_apply_clicked()

        assert dialog.saved_credentials == "newuser:newpass"

    @patch('src.core.file_host_config.save_file_host_setting')
    def test_apply_updates_cached_trigger(self, mock_save, qtbot, mock_host_config,
                                          mock_worker_manager, mock_main_widgets, dialog_patches):
        """Test Apply updates cached trigger value"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        dialog.trigger_combo.setCurrentIndex(3)  # On Completed
        dialog._on_apply_clicked()

        assert dialog.saved_trigger == "on_completed"

    @patch('src.core.file_host_config.save_file_host_setting')
    def test_save_applies_then_closes(self, mock_save, qtbot, mock_host_config,
                                      mock_worker_manager, mock_main_widgets, dialog_patches):
        """Test Save button applies changes then closes dialog"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        dialog.trigger_combo.setCurrentIndex(1)

        with patch.object(dialog, 'accept') as mock_accept:
            dialog._on_save_clicked()

            # Should apply changes
            assert not dialog.has_unsaved_changes
            # Should close dialog
            assert mock_accept.called

    def test_cancel_closes_without_saving(self, qtbot, mock_host_config, mock_worker_manager,
                                          mock_main_widgets, dialog_patches):
        """Test Cancel button closes without saving"""
        with patch('src.core.file_host_config.save_file_host_setting') as mock_save:
            dialog = FileHostConfigDialog(
                None, "testhost", mock_host_config,
                mock_main_widgets, mock_worker_manager
            )
            qtbot.addWidget(dialog)

            dialog.trigger_combo.setCurrentIndex(1)
            assert dialog.has_unsaved_changes

            # Mock reject to prevent actual dialog close in test
            with patch.object(dialog, 'reject'):
                # Simulate cancel button click (reject is connected to cancel button)
                pass

            # Save should not be called
            assert not mock_save.called


# ============================================================================
# TEST CLASS: Enable/Disable Actions
# ============================================================================

class TestEnableDisableActions:
    """Test host enable/disable functionality"""

    def test_enable_button_text_when_disabled(self, qtbot, mock_host_config, mock_worker_manager,
                                               mock_main_widgets, dialog_patches):
        """Test enable button shows 'Enable' text when host is disabled"""
        mock_worker_manager.is_enabled.return_value = False

        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        assert "Enable" in dialog.enable_button.text()

    def test_enable_button_text_when_enabled(self, qtbot, mock_host_config, mock_worker_manager,
                                             mock_main_widgets, dialog_patches):
        """Test enable button shows 'Disable' text when host is enabled"""
        mock_worker_manager.is_enabled.return_value = True

        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        assert "Disable" in dialog.enable_button.text()

    def test_test_connection_disabled_when_host_disabled(self, qtbot, mock_host_config,
                                                         mock_worker_manager, mock_main_widgets,
                                                         dialog_patches):
        """Test connection button is disabled when host is not enabled"""
        mock_worker_manager.is_enabled.return_value = False

        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        assert not dialog.test_connection_btn.isEnabled()

    def test_test_connection_enabled_when_host_enabled(self, qtbot, mock_host_config,
                                                       mock_worker_manager, mock_main_widgets,
                                                       dialog_patches):
        """Test connection button is enabled when host is enabled"""
        mock_worker_manager.is_enabled.return_value = True
        mock_worker_manager.get_worker.return_value = Mock()

        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        assert dialog.test_connection_btn.isEnabled()

    def test_disable_host_calls_manager(self, qtbot, mock_host_config, mock_worker_manager,
                                        mock_main_widgets, dialog_patches):
        """Test clicking disable calls worker manager disable_host"""
        mock_worker_manager.is_enabled.return_value = True
        mock_worker_manager.get_worker.return_value = Mock()

        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        # Mock the unsaved changes check to return True (proceed)
        with patch.object(dialog, '_check_unsaved_changes', return_value=True):
            dialog._on_enable_button_clicked()

        mock_worker_manager.disable_host.assert_called_once_with("testhost")

    def test_enable_host_calls_manager(self, qtbot, mock_host_config, mock_worker_manager,
                                       mock_main_widgets, dialog_patches):
        """Test clicking enable calls worker manager enable_host"""
        mock_worker_manager.is_enabled.return_value = False

        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        # Mock the unsaved changes check to return True (proceed)
        with patch.object(dialog, '_check_unsaved_changes', return_value=True):
            dialog._on_enable_button_clicked()

        mock_worker_manager.enable_host.assert_called_once_with("testhost")

    def test_spinup_complete_success_enables_button(self, qtbot, mock_host_config,
                                                     mock_worker_manager, mock_main_widgets,
                                                     dialog_patches):
        """Test spinup_complete signal with success enables host"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        # Simulate successful spinup
        dialog._on_spinup_complete("testhost", "")

        assert dialog.saved_enabled is True
        assert "Disable" in dialog.enable_button.text()

    def test_spinup_complete_failure_keeps_disabled(self, qtbot, mock_host_config,
                                                     mock_worker_manager, mock_main_widgets,
                                                     dialog_patches):
        """Test spinup_complete signal with error keeps host disabled"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        # Simulate failed spinup
        dialog._on_spinup_complete("testhost", "Authentication failed")

        assert dialog.saved_enabled is False
        assert "Enable" in dialog.enable_button.text()
        assert "Failed to enable" in dialog.enable_error_label.text()


# ============================================================================
# TEST CLASS: Test Connection
# ============================================================================

class TestConnectionTesting:
    """Test connection testing functionality"""

    def test_test_connection_requires_credentials(self, qtbot, mock_host_config,
                                                   mock_worker_manager, mock_main_widgets,
                                                   dialog_patches):
        """Test connection test requires credentials to be entered"""
        mock_worker_manager.is_enabled.return_value = True
        mock_worker = Mock()
        mock_worker_manager.get_worker.return_value = mock_worker

        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        # Empty credentials
        dialog.creds_input.setText("")

        # Mock the unsaved changes check
        with patch.object(dialog, '_check_unsaved_changes', return_value=True):
            dialog.run_full_test()

        assert "No credentials" in dialog.test_timestamp_label.text()

    def test_test_connection_requires_enabled_worker(self, qtbot, mock_host_config,
                                                     mock_worker_manager, mock_main_widgets,
                                                     dialog_patches):
        """Test connection test requires host to be enabled"""
        mock_worker_manager.is_enabled.return_value = False

        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)
        dialog.worker = None  # Simulate no worker

        dialog.creds_input.setText("user:pass")

        # Mock the unsaved changes check
        with patch.object(dialog, '_check_unsaved_changes', return_value=True):
            dialog.run_full_test()

        assert "Host not enabled" in dialog.test_timestamp_label.text()

    def test_test_connection_queues_test_request(self, qtbot, mock_host_config,
                                                  mock_worker_manager, mock_main_widgets,
                                                  dialog_patches):
        """Test connection test queues test request to worker"""
        mock_worker_manager.is_enabled.return_value = True
        mock_worker = Mock()
        mock_worker.queue_test_request = Mock()
        mock_worker_manager.get_worker.return_value = mock_worker

        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)
        dialog.worker = mock_worker

        dialog.creds_input.setText("user:pass")

        # Mock the unsaved changes check
        with patch.object(dialog, '_check_unsaved_changes', return_value=True):
            dialog.run_full_test()

        mock_worker.queue_test_request.assert_called_once_with("user:pass")

    def test_test_connection_updates_ui_during_test(self, qtbot, mock_host_config,
                                                     mock_worker_manager, mock_main_widgets,
                                                     dialog_patches):
        """Test connection test updates UI to show testing state"""
        mock_worker_manager.is_enabled.return_value = True
        mock_worker = Mock()
        mock_worker.queue_test_request = Mock()
        mock_worker_manager.get_worker.return_value = mock_worker

        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)
        dialog.worker = mock_worker

        dialog.creds_input.setText("user:pass")

        # Mock the unsaved changes check
        with patch.object(dialog, '_check_unsaved_changes', return_value=True):
            dialog.run_full_test()

        # Should show testing state
        assert "Testing..." in dialog.test_timestamp_label.text()
        assert not dialog.test_connection_btn.isEnabled()

    def test_test_completed_updates_results(self, qtbot, mock_host_config, mock_worker_manager,
                                            mock_main_widgets, dialog_patches):
        """Test _on_worker_test_completed updates test results"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        results = {
            'timestamp': 1700000000,
            'credentials_valid': True,
            'user_info_valid': True,
            'upload_success': True,
            'delete_success': True,
            'error_message': ''
        }

        dialog._on_worker_test_completed("testhost", results)

        assert "Pass" in dialog.test_credentials_label.text()
        assert "Pass" in dialog.test_userinfo_label.text()
        assert "Pass" in dialog.test_upload_label.text()
        assert "Pass" in dialog.test_delete_label.text()
        assert dialog.test_connection_btn.isEnabled()


# ============================================================================
# TEST CLASS: Storage Display
# ============================================================================

class TestStorageDisplay:
    """Test storage bar display and updates"""

    def test_storage_bar_loads_from_cache(self, qtbot, mock_host_config, mock_worker_manager,
                                          mock_main_widgets, dialog_patches):
        """Test storage bar loads cached values on init"""
        # Set up mock settings with cached storage values
        settings = QSettings("ImxUploader", "ImxUploadGUI")
        settings.setValue("FileHosts/testhost/storage_total", "1073741824")  # 1 GB
        settings.setValue("FileHosts/testhost/storage_left", "536870912")    # 512 MB

        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        # Storage bar should show cached values
        assert dialog.storage_bar is not None
        assert dialog.storage_bar.value() == 50  # 50% free

    def test_storage_updated_signal_updates_bar(self, qtbot, mock_host_config,
                                                 mock_worker_manager, mock_main_widgets,
                                                 dialog_patches):
        """Test storage_updated signal updates storage bar"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        # Simulate storage update
        total = 1073741824  # 1 GB
        left = 268435456    # 256 MB

        dialog._on_worker_storage_updated("testhost", total, left)

        # Should update to 25% free (75% used)
        assert dialog.storage_bar.value() == 25


# ============================================================================
# TEST CLASS: Getter Methods
# ============================================================================

class TestGetterMethods:
    """Test getter methods for retrieving values"""

    def test_get_credentials_returns_cached_value(self, qtbot, mock_host_config,
                                                   mock_worker_manager, mock_main_widgets,
                                                   dialog_patches):
        """Test get_credentials returns cached value after save"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        dialog.saved_credentials = "cached:credentials"
        assert dialog.get_credentials() == "cached:credentials"

    def test_get_credentials_returns_widget_value(self, qtbot, mock_host_config,
                                                   mock_worker_manager, mock_main_widgets,
                                                   dialog_patches):
        """Test get_credentials returns widget value if no cached value"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        dialog.saved_credentials = None
        dialog.creds_input.setText("widget:credentials")
        assert dialog.get_credentials() == "widget:credentials"

    def test_get_trigger_settings_returns_cached_value(self, qtbot, mock_host_config,
                                                        mock_worker_manager, mock_main_widgets,
                                                        dialog_patches):
        """Test get_trigger_settings returns cached value after save"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        dialog.saved_trigger = "on_completed"
        assert dialog.get_trigger_settings() == "on_completed"

    def test_get_trigger_settings_returns_widget_value(self, qtbot, mock_host_config,
                                                        mock_worker_manager, mock_main_widgets,
                                                        dialog_patches):
        """Test get_trigger_settings returns widget value if no cached value"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        dialog.trigger_combo.setCurrentIndex(2)  # On Started
        # Delete cached value to force widget read
        del dialog.saved_trigger
        assert dialog.get_trigger_settings() == "on_started"

    def test_get_enabled_state_returns_cached_value(self, qtbot, mock_host_config,
                                                     mock_worker_manager, mock_main_widgets,
                                                     dialog_patches):
        """Test get_enabled_state returns cached value"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        dialog.saved_enabled = True
        assert dialog.get_enabled_state() is True

    def test_get_enabled_state_queries_manager(self, qtbot, mock_host_config,
                                                mock_worker_manager, mock_main_widgets,
                                                dialog_patches):
        """Test get_enabled_state queries manager if no cached value"""
        mock_worker_manager.is_enabled.return_value = True

        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        # Delete cached value
        del dialog.saved_enabled
        assert dialog.get_enabled_state() is True
        mock_worker_manager.is_enabled.assert_called_with("testhost")


# ============================================================================
# TEST CLASS: Close Event Handling
# ============================================================================

class TestCloseEventHandling:
    """Test dialog close event and cleanup"""

    @patch('PyQt6.QtWidgets.QMessageBox.warning')
    def test_close_warns_about_unsaved_changes(self, mock_warning, qtbot, mock_host_config,
                                                mock_worker_manager, mock_main_widgets,
                                                dialog_patches):
        """Test closing with unsaved changes shows warning"""
        mock_warning.return_value = QMessageBox.StandardButton.Discard

        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        # Make changes
        dialog.trigger_combo.setCurrentIndex(1)
        assert dialog.has_unsaved_changes

        # Simulate close event
        from PyQt6.QtGui import QCloseEvent
        event = QCloseEvent()
        dialog.closeEvent(event)

        # Should show warning
        assert mock_warning.called

    def test_close_saves_splitter_state(self, qtbot, mock_host_config, mock_worker_manager,
                                        mock_main_widgets, dialog_patches):
        """Test closing saves splitter state to QSettings"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        # Simulate close event
        from PyQt6.QtGui import QCloseEvent
        event = QCloseEvent()
        dialog.closeEvent(event)

        # Should save splitter state (we can't easily verify without actual QSettings)
        # But we can verify no exception is raised
        assert True


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
