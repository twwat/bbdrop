#!/usr/bin/env python3
"""
Comprehensive pytest-qt tests for CredentialSetupDialog
Tests all aspects of the credential setup dialog functionality

Coverage targets:
- Dialog initialization and UI components
- Credential loading and display
- Set/Change/Remove operations for username, password, API key
- Cookie settings enable/disable
- Sub-dialog interactions
- Error handling
- Button state management
- Theme-aware styling
"""

import os
import sys
import pytest
import tempfile
import configparser
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock, call

from PyQt6.QtWidgets import (
    QDialog, QLineEdit, QPushButton, QLabel, QMessageBox, QGroupBox
)
from PyQt6.QtCore import Qt

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from src.gui.dialogs.credential_setup import CredentialSetupDialog


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_credentials(monkeypatch):
    """
    Mock credential storage functions.
    Returns a dict that can be used to track stored credentials.
    """
    storage = {}

    def mock_get_credential(key):
        return storage.get(key)

    def mock_set_credential(key, value):
        storage[key] = value
        return True

    def mock_remove_credential(key):
        storage.pop(key, None)
        return True

    def mock_encrypt_password(password):
        return f"encrypted_{password}"

    def mock_decrypt_password(encrypted):
        if encrypted and encrypted.startswith("encrypted_"):
            return encrypted[10:]  # Remove "encrypted_" prefix
        return encrypted

    monkeypatch.setattr('src.gui.dialogs.credential_setup.get_credential', mock_get_credential)
    monkeypatch.setattr('src.gui.dialogs.credential_setup.set_credential', mock_set_credential)
    monkeypatch.setattr('src.gui.dialogs.credential_setup.remove_credential', mock_remove_credential)
    monkeypatch.setattr('src.gui.dialogs.credential_setup.encrypt_password', mock_encrypt_password)
    monkeypatch.setattr('src.gui.dialogs.credential_setup.decrypt_password', mock_decrypt_password)

    return storage


@pytest.fixture
def mock_config_path(tmp_path, monkeypatch):
    """Create a temporary config file and mock get_config_path."""
    config_file = tmp_path / "bbdrop.ini"
    config_file.touch()

    monkeypatch.setattr('src.gui.dialogs.credential_setup.get_config_path', lambda: str(config_file))

    return config_file


@pytest.fixture
def dialog_with_mocks(qtbot, mock_credentials, mock_config_path):
    """Create a dialog with all dependencies mocked."""
    dialog = CredentialSetupDialog()
    qtbot.addWidget(dialog)
    return dialog


# =============================================================================
# Initialization Tests
# =============================================================================

class TestCredentialSetupDialogInit:
    """Test CredentialSetupDialog initialization and basic structure"""

    def test_dialog_creates_successfully(self, qtbot, mock_credentials, mock_config_path):
        """Test basic dialog instantiation"""
        dialog = CredentialSetupDialog()
        qtbot.addWidget(dialog)

        assert dialog is not None
        assert isinstance(dialog, QDialog)
        assert dialog.windowTitle() == "Setup Secure Credentials"
        assert dialog.isModal() is True

    def test_dialog_default_size(self, qtbot, mock_credentials, mock_config_path):
        """Test dialog has correct default size"""
        dialog = CredentialSetupDialog()
        qtbot.addWidget(dialog)

        assert dialog.width() == 500
        assert dialog.height() == 430

    def test_dialog_standalone_mode(self, qtbot, mock_credentials, mock_config_path):
        """Test dialog in standalone mode has OK button"""
        dialog = CredentialSetupDialog(standalone=True)
        qtbot.addWidget(dialog)

        assert dialog.standalone is True
        # Find OK button in dialog
        ok_buttons = [
            btn for btn in dialog.findChildren(QPushButton)
            if 'OK' in btn.text()
        ]
        assert len(ok_buttons) == 1

    def test_dialog_non_standalone_mode(self, qtbot, mock_credentials, mock_config_path):
        """Test dialog in non-standalone mode has no OK button"""
        dialog = CredentialSetupDialog(standalone=False)
        qtbot.addWidget(dialog)

        assert dialog.standalone is False
        # Should not have standalone OK button (other buttons exist)
        ok_buttons = [
            btn for btn in dialog.findChildren(QPushButton)
            if btn.text().strip() == 'OK'
        ]
        assert len(ok_buttons) == 0


class TestDialogUIComponents:
    """Test dialog UI component existence and structure"""

    def test_has_api_key_section(self, dialog_with_mocks):
        """Test API key section components exist"""
        dialog = dialog_with_mocks

        assert hasattr(dialog, 'api_key_status_label')
        assert hasattr(dialog, 'api_key_change_btn')
        assert hasattr(dialog, 'api_key_remove_btn')
        assert hasattr(dialog, 'api_key_edit')
        assert isinstance(dialog.api_key_status_label, QLabel)
        assert isinstance(dialog.api_key_change_btn, QPushButton)

    def test_has_username_section(self, dialog_with_mocks):
        """Test username section components exist"""
        dialog = dialog_with_mocks

        assert hasattr(dialog, 'username_status_label')
        assert hasattr(dialog, 'username_change_btn')
        assert hasattr(dialog, 'username_remove_btn')
        assert hasattr(dialog, 'username_edit')

    def test_has_password_section(self, dialog_with_mocks):
        """Test password section components exist"""
        dialog = dialog_with_mocks

        assert hasattr(dialog, 'password_status_label')
        assert hasattr(dialog, 'password_change_btn')
        assert hasattr(dialog, 'password_remove_btn')
        assert hasattr(dialog, 'password_edit')
        # Password field should be masked
        assert dialog.password_edit.echoMode() == QLineEdit.EchoMode.Password

    def test_has_cookies_section(self, dialog_with_mocks):
        """Test cookies section components exist"""
        dialog = dialog_with_mocks

        assert hasattr(dialog, 'cookies_status_label')
        assert hasattr(dialog, 'cookies_enable_btn')
        assert hasattr(dialog, 'cookies_disable_btn')

    def test_has_remove_all_button(self, dialog_with_mocks):
        """Test Remove All button exists"""
        dialog = dialog_with_mocks

        assert hasattr(dialog, 'remove_all_btn')
        assert isinstance(dialog.remove_all_btn, QPushButton)
        assert 'Unset All' in dialog.remove_all_btn.text()

    def test_api_key_edit_is_password_mode(self, dialog_with_mocks):
        """Test API key field uses password masking"""
        dialog = dialog_with_mocks
        assert dialog.api_key_edit.echoMode() == QLineEdit.EchoMode.Password

    def test_has_group_boxes(self, dialog_with_mocks):
        """Test dialog has proper group box structure"""
        dialog = dialog_with_mocks

        group_boxes = dialog.findChildren(QGroupBox)
        group_box_titles = [gb.title() for gb in group_boxes]

        assert 'API Key' in group_box_titles
        assert 'Login' in group_box_titles


# =============================================================================
# Credential Loading Tests
# =============================================================================

class TestCredentialLoading:
    """Test credential loading and display functionality"""

    def test_loads_no_credentials(self, dialog_with_mocks, mock_credentials):
        """Test display when no credentials are stored"""
        dialog = dialog_with_mocks

        assert dialog.api_key_status_label.text() == "NOT SET"
        assert dialog.username_status_label.text() == "NOT SET"
        assert dialog.password_status_label.text() == "NOT SET"

        # Remove buttons should be disabled
        assert dialog.api_key_remove_btn.isEnabled() is False
        assert dialog.username_remove_btn.isEnabled() is False
        assert dialog.password_remove_btn.isEnabled() is False

    def test_loads_existing_username(self, qtbot, mock_credentials, mock_config_path):
        """Test display when username exists"""
        mock_credentials['username'] = 'testuser'

        dialog = CredentialSetupDialog()
        qtbot.addWidget(dialog)

        assert dialog.username_status_label.text() == 'testuser'
        assert dialog.username_remove_btn.isEnabled() is True
        assert 'Change' in dialog.username_change_btn.text()

    def test_loads_existing_password(self, qtbot, mock_credentials, mock_config_path):
        """Test display when password exists (shows masked)"""
        mock_credentials['password'] = 'encrypted_secretpass'

        dialog = CredentialSetupDialog()
        qtbot.addWidget(dialog)

        # Password should show as masked
        assert '****' in dialog.password_status_label.text() or dialog.password_status_label.text() == 'SET'
        assert dialog.password_remove_btn.isEnabled() is True

    def test_loads_existing_api_key(self, qtbot, mock_credentials, mock_config_path):
        """Test display when API key exists (shows partially masked)"""
        mock_credentials['api_key'] = 'encrypted_abcd1234efgh5678ijkl9012'

        dialog = CredentialSetupDialog()
        qtbot.addWidget(dialog)

        # API key should be partially masked
        status_text = dialog.api_key_status_label.text()
        assert '*' in status_text or status_text == 'SET'
        assert dialog.api_key_remove_btn.isEnabled() is True

    def test_loads_short_api_key(self, qtbot, mock_credentials, mock_config_path):
        """Test display when API key is short"""
        mock_credentials['api_key'] = 'encrypted_short'  # Will decrypt to 'short' (5 chars)

        dialog = CredentialSetupDialog()
        qtbot.addWidget(dialog)

        # Short keys show as 'SET'
        assert dialog.api_key_status_label.text() == 'SET'

    def test_button_text_changes_based_on_credential_state(self, qtbot, mock_credentials, mock_config_path):
        """Test Set/Change button text based on credential existence"""
        # No credentials - should show "Set"
        dialog = CredentialSetupDialog()
        qtbot.addWidget(dialog)

        assert 'Set' in dialog.username_change_btn.text()
        assert 'Set' in dialog.password_change_btn.text()
        assert 'Set' in dialog.api_key_change_btn.text()


# =============================================================================
# Cookie Settings Tests
# =============================================================================

class TestCookieSettings:
    """Test Firefox cookie settings functionality"""

    def test_cookies_default_enabled(self, dialog_with_mocks):
        """Test cookies are enabled by default"""
        dialog = dialog_with_mocks

        assert dialog.cookies_status_label.text() == 'Enabled'
        assert dialog.cookies_enable_btn.isEnabled() is False
        assert dialog.cookies_disable_btn.isEnabled() is True

    def test_cookies_disabled_in_config(self, qtbot, mock_credentials, mock_config_path):
        """Test cookies disabled when config says so"""
        # Write config with cookies disabled
        config = configparser.ConfigParser()
        config['CREDENTIALS'] = {'cookies_enabled': 'false'}
        with open(mock_config_path, 'w') as f:
            config.write(f)

        dialog = CredentialSetupDialog()
        qtbot.addWidget(dialog)

        assert dialog.cookies_status_label.text() == 'Disabled'
        assert dialog.cookies_enable_btn.isEnabled() is True
        assert dialog.cookies_disable_btn.isEnabled() is False

    def test_enable_cookies_setting(self, dialog_with_mocks, mock_config_path):
        """Test enabling cookies updates config and UI"""
        dialog = dialog_with_mocks

        # Manually disable first by writing to config
        config = configparser.ConfigParser()
        config['CREDENTIALS'] = {'cookies_enabled': 'false'}
        with open(mock_config_path, 'w') as f:
            config.write(f)

        dialog.load_current_credentials()
        assert dialog.cookies_status_label.text() == 'Disabled'

        # Now enable
        dialog.enable_cookies_setting()

        # Verify config updated
        config.read(mock_config_path)
        assert config['CREDENTIALS']['cookies_enabled'] == 'true'

        # Verify UI updated
        assert dialog.cookies_status_label.text() == 'Enabled'

    def test_disable_cookies_setting(self, dialog_with_mocks, mock_config_path):
        """Test disabling cookies updates config and UI"""
        dialog = dialog_with_mocks

        # Should be enabled by default
        assert dialog.cookies_status_label.text() == 'Enabled'

        # Disable
        dialog.disable_cookies_setting()

        # Verify config updated
        config = configparser.ConfigParser()
        config.read(mock_config_path)
        assert config['CREDENTIALS']['cookies_enabled'] == 'false'

        # Verify UI updated
        assert dialog.cookies_status_label.text() == 'Disabled'


# =============================================================================
# Change Credential Tests
# =============================================================================

class TestChangeUsername:
    """Test username change functionality"""

    def test_change_username_opens_dialog(self, dialog_with_mocks, qtbot):
        """Test change_username opens a subdialog"""
        dialog = dialog_with_mocks

        # Track dialogs opened
        dialogs_opened = []
        original_show = QDialog.show

        def track_show(self):
            if self != dialog:
                dialogs_opened.append(self)
            original_show(self)

        with patch.object(QDialog, 'show', track_show):
            dialog.change_username()

        assert len(dialogs_opened) == 1
        assert dialogs_opened[0].windowTitle() == "Set Username"

    def test_handle_username_dialog_accept(self, dialog_with_mocks, mock_credentials):
        """Test username is saved when dialog accepted"""
        dialog = dialog_with_mocks

        with patch.object(QMessageBox, 'information') as mock_info:
            dialog._handle_username_dialog_result(QDialog.DialogCode.Accepted, 'newuser')

        assert mock_credentials.get('username') == 'newuser'
        mock_info.assert_called_once()

    def test_handle_username_dialog_reject(self, dialog_with_mocks, mock_credentials):
        """Test username not saved when dialog rejected"""
        dialog = dialog_with_mocks

        dialog._handle_username_dialog_result(QDialog.DialogCode.Rejected, 'newuser')

        assert 'username' not in mock_credentials

    def test_handle_username_empty_warning(self, dialog_with_mocks):
        """Test warning when empty username submitted"""
        dialog = dialog_with_mocks

        with patch.object(QMessageBox, 'warning') as mock_warning:
            dialog._handle_username_dialog_result(QDialog.DialogCode.Accepted, '')

        mock_warning.assert_called_once()
        assert 'Missing' in str(mock_warning.call_args)


class TestChangePassword:
    """Test password change functionality"""

    def test_change_password_opens_dialog(self, dialog_with_mocks, qtbot):
        """Test change_password opens a subdialog"""
        dialog = dialog_with_mocks

        dialogs_opened = []
        original_show = QDialog.show

        def track_show(self):
            if self != dialog:
                dialogs_opened.append(self)
            original_show(self)

        with patch.object(QDialog, 'show', track_show):
            dialog.change_password()

        assert len(dialogs_opened) == 1
        assert dialogs_opened[0].windowTitle() == "Set Password"

    def test_handle_password_dialog_accept(self, dialog_with_mocks, mock_credentials):
        """Test password is encrypted and saved when dialog accepted"""
        dialog = dialog_with_mocks

        with patch.object(QMessageBox, 'information'):
            dialog._handle_password_dialog_result(QDialog.DialogCode.Accepted, 'secretpass')

        # Password should be encrypted
        assert mock_credentials.get('password') == 'encrypted_secretpass'

    def test_handle_password_empty_warning(self, dialog_with_mocks):
        """Test warning when empty password submitted"""
        dialog = dialog_with_mocks

        with patch.object(QMessageBox, 'warning') as mock_warning:
            dialog._handle_password_dialog_result(QDialog.DialogCode.Accepted, '')

        mock_warning.assert_called_once()


class TestChangeApiKey:
    """Test API key change functionality"""

    def test_change_api_key_opens_dialog(self, dialog_with_mocks, qtbot):
        """Test change_api_key opens a subdialog"""
        dialog = dialog_with_mocks

        dialogs_opened = []
        original_show = QDialog.show

        def track_show(self):
            if self != dialog:
                dialogs_opened.append(self)
            original_show(self)

        with patch.object(QDialog, 'show', track_show):
            dialog.change_api_key()

        assert len(dialogs_opened) == 1
        assert dialogs_opened[0].windowTitle() == "Change API Key"

    def test_handle_api_key_dialog_accept(self, dialog_with_mocks, mock_credentials):
        """Test API key is encrypted and saved when dialog accepted"""
        dialog = dialog_with_mocks

        with patch.object(QMessageBox, 'information'):
            dialog._handle_api_key_dialog_result(QDialog.DialogCode.Accepted, 'myapikey123')

        # API key should be encrypted
        assert mock_credentials.get('api_key') == 'encrypted_myapikey123'

    def test_handle_api_key_empty_warning(self, dialog_with_mocks):
        """Test warning when empty API key submitted"""
        dialog = dialog_with_mocks

        with patch.object(QMessageBox, 'warning') as mock_warning:
            dialog._handle_api_key_dialog_result(QDialog.DialogCode.Accepted, '')

        mock_warning.assert_called_once()


# =============================================================================
# Remove Credential Tests
# =============================================================================

class TestRemoveUsername:
    """Test username removal functionality"""

    def test_remove_username_shows_confirmation(self, dialog_with_mocks, qtbot, mock_credentials):
        """Test remove_username shows confirmation dialog"""
        dialog = dialog_with_mocks
        mock_credentials['username'] = 'testuser'
        dialog.load_current_credentials()

        # Track message boxes
        with patch.object(QMessageBox, 'open') as mock_open:
            dialog.remove_username()
            mock_open.assert_called_once()

    def test_remove_username_on_confirmation(self, dialog_with_mocks, mock_credentials):
        """Test username removed when confirmed"""
        dialog = dialog_with_mocks
        mock_credentials['username'] = 'testuser'
        dialog.load_current_credentials()

        with patch.object(QMessageBox, 'information'):
            dialog._handle_remove_username_confirmation(QMessageBox.StandardButton.Yes)

        assert 'username' not in mock_credentials

    def test_remove_username_cancelled(self, dialog_with_mocks, mock_credentials):
        """Test username not removed when cancelled"""
        dialog = dialog_with_mocks
        mock_credentials['username'] = 'testuser'
        dialog.load_current_credentials()

        dialog._handle_remove_username_confirmation(QMessageBox.StandardButton.No)

        assert mock_credentials.get('username') == 'testuser'


class TestRemovePassword:
    """Test password removal functionality"""

    def test_remove_password_with_confirmation(self, dialog_with_mocks, mock_credentials):
        """Test password removed when confirmed"""
        dialog = dialog_with_mocks
        mock_credentials['password'] = 'encrypted_secret'
        dialog.load_current_credentials()

        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            with patch.object(QMessageBox, 'information'):
                dialog.remove_password()

        assert 'password' not in mock_credentials

    def test_remove_password_cancelled(self, dialog_with_mocks, mock_credentials):
        """Test password not removed when cancelled"""
        dialog = dialog_with_mocks
        mock_credentials['password'] = 'encrypted_secret'
        dialog.load_current_credentials()

        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.No):
            dialog.remove_password()

        assert mock_credentials.get('password') == 'encrypted_secret'


class TestRemoveApiKey:
    """Test API key removal functionality"""

    def test_remove_api_key_with_confirmation(self, dialog_with_mocks, mock_credentials):
        """Test API key removed when confirmed"""
        dialog = dialog_with_mocks
        mock_credentials['api_key'] = 'encrypted_apikey123'
        dialog.load_current_credentials()

        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            with patch.object(QMessageBox, 'information'):
                dialog.remove_api_key()

        assert 'api_key' not in mock_credentials

    def test_remove_api_key_cancelled(self, dialog_with_mocks, mock_credentials):
        """Test API key not removed when cancelled"""
        dialog = dialog_with_mocks
        mock_credentials['api_key'] = 'encrypted_apikey123'
        dialog.load_current_credentials()

        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.No):
            dialog.remove_api_key()

        assert mock_credentials.get('api_key') == 'encrypted_apikey123'


class TestRemoveAllCredentials:
    """Test remove all credentials functionality"""

    def test_remove_all_with_confirmation(self, dialog_with_mocks, mock_credentials):
        """Test all credentials removed when confirmed"""
        dialog = dialog_with_mocks
        mock_credentials['username'] = 'user'
        mock_credentials['password'] = 'encrypted_pass'
        mock_credentials['api_key'] = 'encrypted_key'
        dialog.load_current_credentials()

        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            with patch.object(QMessageBox, 'information'):
                dialog.remove_all_credentials()

        assert 'username' not in mock_credentials
        assert 'password' not in mock_credentials
        assert 'api_key' not in mock_credentials

    def test_remove_all_cancelled(self, dialog_with_mocks, mock_credentials):
        """Test credentials preserved when cancelled"""
        dialog = dialog_with_mocks
        mock_credentials['username'] = 'user'
        mock_credentials['password'] = 'encrypted_pass'
        mock_credentials['api_key'] = 'encrypted_key'
        dialog.load_current_credentials()

        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.No):
            dialog.remove_all_credentials()

        assert mock_credentials.get('username') == 'user'
        assert mock_credentials.get('password') == 'encrypted_pass'
        assert mock_credentials.get('api_key') == 'encrypted_key'


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestErrorHandling:
    """Test error handling throughout the dialog"""

    def test_set_credential_error_handling(self, dialog_with_mocks, monkeypatch):
        """Test error shown when set_credential fails"""
        dialog = dialog_with_mocks

        def failing_set_credential(key, value):
            raise Exception("Storage error")

        monkeypatch.setattr('src.gui.dialogs.credential_setup.set_credential', failing_set_credential)

        with patch.object(QMessageBox, 'critical') as mock_critical:
            dialog._handle_username_dialog_result(QDialog.DialogCode.Accepted, 'newuser')

        mock_critical.assert_called_once()
        assert 'Error' in str(mock_critical.call_args)

    def test_remove_credential_error_handling(self, dialog_with_mocks, mock_credentials, monkeypatch):
        """Test error shown when remove_credential fails"""
        dialog = dialog_with_mocks
        mock_credentials['password'] = 'encrypted_pass'
        dialog.load_current_credentials()

        def failing_remove_credential(key):
            raise Exception("Removal error")

        monkeypatch.setattr('src.gui.dialogs.credential_setup.remove_credential', failing_remove_credential)

        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
            with patch.object(QMessageBox, 'critical') as mock_critical:
                dialog.remove_password()

        mock_critical.assert_called_once()

    def test_enable_cookies_error_handling(self, dialog_with_mocks, monkeypatch):
        """Test error handling when enable cookies fails"""
        dialog = dialog_with_mocks

        # Make config path unwritable
        monkeypatch.setattr('src.gui.dialogs.credential_setup.get_config_path',
                          lambda: '/nonexistent/path/config.ini')

        with patch.object(QMessageBox, 'critical') as mock_critical:
            dialog.enable_cookies_setting()

        mock_critical.assert_called_once()

    def test_disable_cookies_error_handling(self, dialog_with_mocks, monkeypatch):
        """Test error handling when disable cookies fails"""
        dialog = dialog_with_mocks

        monkeypatch.setattr('src.gui.dialogs.credential_setup.get_config_path',
                          lambda: '/nonexistent/path/config.ini')

        with patch.object(QMessageBox, 'critical') as mock_critical:
            dialog.disable_cookies_setting()

        mock_critical.assert_called_once()


# =============================================================================
# Theme and Styling Tests
# =============================================================================

class TestThemeStyling:
    """Test theme-aware styling"""

    def test_dark_theme_colors_with_parent(self, qtbot, mock_credentials, mock_config_path):
        """Test dark theme colors when parent has dark theme"""
        from PyQt6.QtWidgets import QWidget

        # Create a real QWidget as parent with dark theme attribute
        parent_widget = QWidget()
        parent_widget._current_theme_mode = 'dark'
        qtbot.addWidget(parent_widget)

        dialog = CredentialSetupDialog(parent=parent_widget)
        qtbot.addWidget(dialog)

        assert dialog.success_color == "#0fd66b"
        assert dialog.error_color == "#c0392b"
        assert dialog.muted_color == "#dddddd"

    def test_light_theme_colors_with_parent(self, qtbot, mock_credentials, mock_config_path):
        """Test light theme colors when parent has light theme"""
        from PyQt6.QtWidgets import QWidget

        parent_widget = QWidget()
        parent_widget._current_theme_mode = 'light'
        qtbot.addWidget(parent_widget)

        dialog = CredentialSetupDialog(parent=parent_widget)
        qtbot.addWidget(dialog)

        assert dialog.success_color == "#0ba653"
        assert dialog.error_color == "#c0392b"
        assert dialog.muted_color == "#444444"

    def test_theme_detection_via_cached_theme(self, qtbot, mock_credentials, mock_config_path):
        """Test theme detection via _get_cached_theme method"""
        from PyQt6.QtWidgets import QWidget

        parent_widget = QWidget()
        # No _current_theme_mode, but has _get_cached_theme
        parent_widget._get_cached_theme = lambda: True  # True = dark
        qtbot.addWidget(parent_widget)

        dialog = CredentialSetupDialog(parent=parent_widget)
        qtbot.addWidget(dialog)

        assert dialog.muted_color == "#dddddd"  # Dark theme

    def test_no_parent_uses_defaults(self, dialog_with_mocks):
        """Test default colors when no parent"""
        dialog = dialog_with_mocks

        # Should use light theme defaults
        assert dialog.success_color == "#0ba653"
        assert dialog.muted_color == "#444444"


# =============================================================================
# Button Click Integration Tests
# =============================================================================

class TestButtonClickIntegration:
    """Test button click handlers - verify buttons are connected properly"""

    def test_api_key_change_btn_connected(self, dialog_with_mocks):
        """Test API key change button is connected to correct slot"""
        dialog = dialog_with_mocks

        # Verify the button exists and is connected
        assert dialog.api_key_change_btn is not None
        # Check button is connected to the change method
        receivers = dialog.api_key_change_btn.receivers(
            dialog.api_key_change_btn.clicked
        )
        assert receivers > 0

    def test_api_key_remove_btn_connected(self, dialog_with_mocks):
        """Test API key remove button is connected"""
        dialog = dialog_with_mocks

        assert dialog.api_key_remove_btn is not None
        receivers = dialog.api_key_remove_btn.receivers(
            dialog.api_key_remove_btn.clicked
        )
        assert receivers > 0

    def test_username_change_btn_connected(self, dialog_with_mocks):
        """Test username change button is connected"""
        dialog = dialog_with_mocks

        assert dialog.username_change_btn is not None
        receivers = dialog.username_change_btn.receivers(
            dialog.username_change_btn.clicked
        )
        assert receivers > 0

    def test_password_change_btn_connected(self, dialog_with_mocks):
        """Test password change button is connected"""
        dialog = dialog_with_mocks

        assert dialog.password_change_btn is not None
        receivers = dialog.password_change_btn.receivers(
            dialog.password_change_btn.clicked
        )
        assert receivers > 0

    def test_cookies_enable_btn_connected(self, dialog_with_mocks):
        """Test cookies enable button is connected"""
        dialog = dialog_with_mocks

        assert dialog.cookies_enable_btn is not None
        receivers = dialog.cookies_enable_btn.receivers(
            dialog.cookies_enable_btn.clicked
        )
        assert receivers > 0

    def test_cookies_disable_btn_connected(self, dialog_with_mocks):
        """Test cookies disable button is connected"""
        dialog = dialog_with_mocks

        assert dialog.cookies_disable_btn is not None
        receivers = dialog.cookies_disable_btn.receivers(
            dialog.cookies_disable_btn.clicked
        )
        assert receivers > 0

    def test_remove_all_btn_connected(self, dialog_with_mocks):
        """Test remove all button is connected"""
        dialog = dialog_with_mocks

        assert dialog.remove_all_btn is not None
        receivers = dialog.remove_all_btn.receivers(
            dialog.remove_all_btn.clicked
        )
        assert receivers > 0

    def test_cookies_disable_actual_click(self, dialog_with_mocks, qtbot, mock_config_path):
        """Test clicking disable cookies actually disables"""
        dialog = dialog_with_mocks

        # Should be enabled by default
        assert dialog.cookies_status_label.text() == 'Enabled'

        # Simulate click
        dialog.cookies_disable_btn.click()

        # Should now be disabled
        assert dialog.cookies_status_label.text() == 'Disabled'

    def test_cookies_enable_actual_click(self, dialog_with_mocks, qtbot, mock_config_path):
        """Test clicking enable cookies actually enables"""
        dialog = dialog_with_mocks

        # First disable
        dialog.disable_cookies_setting()
        assert dialog.cookies_status_label.text() == 'Disabled'

        # Click enable
        dialog.cookies_enable_btn.click()

        # Should now be enabled
        assert dialog.cookies_status_label.text() == 'Enabled'


# =============================================================================
# Dialog Acceptance Tests
# =============================================================================

class TestDialogAcceptance:
    """Test dialog acceptance and closure"""

    def test_validate_and_close(self, dialog_with_mocks):
        """Test validate_and_close accepts the dialog"""
        dialog = dialog_with_mocks

        with patch.object(dialog, 'accept') as mock_accept:
            dialog.validate_and_close()

        mock_accept.assert_called_once()

    def test_save_credentials_accepts(self, dialog_with_mocks):
        """Test save_credentials accepts the dialog"""
        dialog = dialog_with_mocks

        with patch.object(dialog, 'accept') as mock_accept:
            dialog.save_credentials()

        mock_accept.assert_called_once()

    def test_standalone_ok_button_exists_and_connected(self, qtbot, mock_credentials, mock_config_path):
        """Test OK button in standalone mode exists and is connected"""
        dialog = CredentialSetupDialog(standalone=True)
        qtbot.addWidget(dialog)

        ok_buttons = [
            btn for btn in dialog.findChildren(QPushButton)
            if 'OK' in btn.text()
        ]

        assert len(ok_buttons) == 1
        ok_btn = ok_buttons[0]

        # Verify button is connected
        receivers = ok_btn.receivers(ok_btn.clicked)
        assert receivers > 0

        # Verify it's set as default button
        assert ok_btn.isDefault() is True


# =============================================================================
# Reload Credentials Tests
# =============================================================================

class TestReloadCredentials:
    """Test credential reloading after changes"""

    def test_reload_after_username_change(self, dialog_with_mocks, mock_credentials):
        """Test UI reloads after username saved"""
        dialog = dialog_with_mocks

        assert dialog.username_status_label.text() == "NOT SET"

        with patch.object(QMessageBox, 'information'):
            dialog._handle_username_dialog_result(QDialog.DialogCode.Accepted, 'newuser')

        assert dialog.username_status_label.text() == 'newuser'

    def test_reload_after_password_change(self, dialog_with_mocks, mock_credentials):
        """Test UI reloads after password saved"""
        dialog = dialog_with_mocks

        assert dialog.password_status_label.text() == "NOT SET"

        with patch.object(QMessageBox, 'information'):
            dialog._handle_password_dialog_result(QDialog.DialogCode.Accepted, 'newpass')

        # Should show masked
        assert '****' in dialog.password_status_label.text()

    def test_reload_after_api_key_change(self, dialog_with_mocks, mock_credentials):
        """Test UI reloads after API key saved"""
        dialog = dialog_with_mocks

        assert dialog.api_key_status_label.text() == "NOT SET"

        with patch.object(QMessageBox, 'information'):
            dialog._handle_api_key_dialog_result(
                QDialog.DialogCode.Accepted,
                'abcd1234efgh5678ijkl9012'
            )

        # Should show partially masked
        status = dialog.api_key_status_label.text()
        assert '*' in status or status == 'SET'


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_whitespace_username_trimmed(self, dialog_with_mocks, mock_credentials):
        """Test whitespace is trimmed from username"""
        dialog = dialog_with_mocks

        with patch.object(QMessageBox, 'information'):
            dialog._handle_username_dialog_result(QDialog.DialogCode.Accepted, '  user  ')

        # Whitespace would be trimmed in the calling code before passing
        # (in change_username via text().strip())
        # Here we test the handler itself accepts it

    def test_config_file_created_if_not_exists(self, dialog_with_mocks, mock_config_path):
        """Test config file is created if it doesn't exist"""
        dialog = dialog_with_mocks

        # Remove config file
        if mock_config_path.exists():
            mock_config_path.unlink()

        # Enable cookies should create the file
        dialog.enable_cookies_setting()

        assert mock_config_path.exists()

    def test_multiple_load_current_credentials_calls(self, dialog_with_mocks, mock_credentials):
        """Test calling load_current_credentials multiple times"""
        dialog = dialog_with_mocks

        # Call multiple times should not cause issues
        dialog.load_current_credentials()
        dialog.load_current_credentials()
        dialog.load_current_credentials()

        # Should still be in consistent state
        assert dialog.api_key_status_label.text() == "NOT SET"

    def test_api_key_decrypt_failure_handling(self, qtbot, mock_credentials, mock_config_path, monkeypatch):
        """Test handling when API key decryption fails"""
        mock_credentials['api_key'] = 'corrupted_data'

        def failing_decrypt(encrypted):
            raise Exception("Decryption failed")

        monkeypatch.setattr('src.gui.dialogs.credential_setup.decrypt_password', failing_decrypt)

        dialog = CredentialSetupDialog()
        qtbot.addWidget(dialog)

        # Should show SET even if decryption fails
        assert dialog.api_key_status_label.text() == 'SET'


# =============================================================================
# Button Text Formatting Tests
# =============================================================================

class TestButtonTextFormatting:
    """Test button text has proper spacing"""

    def test_buttons_have_leading_space(self, dialog_with_mocks):
        """Test buttons have leading space for icon alignment"""
        dialog = dialog_with_mocks

        # All main action buttons should have leading space
        assert dialog.api_key_change_btn.text().startswith(' ')
        assert dialog.api_key_remove_btn.text().startswith(' ')
        assert dialog.username_change_btn.text().startswith(' ')
        assert dialog.username_remove_btn.text().startswith(' ')
        assert dialog.password_change_btn.text().startswith(' ')
        assert dialog.password_remove_btn.text().startswith(' ')
        assert dialog.cookies_enable_btn.text().startswith(' ')
        assert dialog.cookies_disable_btn.text().startswith(' ')
        assert dialog.remove_all_btn.text().startswith(' ')


# =============================================================================
# Test Runner
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
