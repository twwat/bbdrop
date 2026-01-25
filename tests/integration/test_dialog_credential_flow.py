#!/usr/bin/env python3
"""Integration test for dialog credential flow - minimal mocking."""

import pytest
from unittest.mock import Mock, patch
from PyQt6.QtWidgets import QApplication, QLineEdit
from PyQt6.QtGui import QIcon

from bbdrop import get_credential, set_credential, encrypt_password, decrypt_password, remove_credential
from src.gui.dialogs.file_host_config_dialog import FileHostConfigDialog, AsteriskPasswordEdit
from src.core.file_host_config import HostConfig


class TestAsteriskPasswordEdit:
    """Test the AsteriskPasswordEdit widget behavior."""

    @pytest.fixture
    def widget(self, qtbot):
        w = AsteriskPasswordEdit()
        qtbot.addWidget(w)
        return w

    def test_initial_state(self, widget):
        """Widget starts masked with empty text."""
        assert widget.echoMode() == QLineEdit.EchoMode.Password
        assert widget.text() == ""

    def test_set_text_while_masked(self, widget):
        """setText works while masked - text() returns actual value."""
        widget.setText("password123")
        assert widget.text() == "password123"
        assert widget.echoMode() == QLineEdit.EchoMode.Password

    def test_unmask_shows_actual_text(self, widget):
        """Unmasking shows the actual password."""
        widget.setText("password123")
        widget.set_masked(False)
        assert widget.echoMode() == QLineEdit.EchoMode.Normal
        assert widget.text() == "password123"

    def test_type_while_masked_works(self, widget, qtbot):
        """Typing while masked updates text properly."""
        # User can type while masked (unlike the old broken implementation)
        widget.clear()
        widget.insert("new_pass")
        assert widget.text() == "new_pass"

    def test_remask_after_edit_preserves_value(self, widget, qtbot):
        """Re-masking after edit preserves the value."""
        widget.set_masked(False)
        widget.clear()
        widget.insert("new_pass")
        widget.set_masked(True)
        # Value preserved after re-masking
        assert widget.text() == "new_pass"
        assert widget.echoMode() == QLineEdit.EchoMode.Password


class TestDialogCredentialFlow:
    """Test the full dialog credential flow with real storage."""

    TEST_KEY = "file_host_DIALOG_TEST_credentials"

    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Clean up test credentials."""
        remove_credential(self.TEST_KEY)
        yield
        remove_credential(self.TEST_KEY)

    @pytest.fixture
    def mock_host_config(self):
        config = Mock(spec=HostConfig)
        config.name = "TestHost"
        config.requires_auth = True
        config.auth_type = "token_login"
        config.user_info_url = None
        config.storage_left_path = None
        config.storage_regex = None
        config.referral_url = None
        config.inactivity_timeout = 300
        config.upload_timeout = None
        return config

    @pytest.fixture
    def mock_worker_manager(self):
        manager = Mock()
        manager.is_enabled.return_value = False
        manager.get_worker.return_value = None
        return manager

    def test_get_credentials_returns_widget_values(self, qtbot, mock_host_config, mock_worker_manager, monkeypatch):
        """Test that get_credentials returns values from widgets, not cached."""
        # Mock icon manager
        mock_icon_manager = Mock()
        mock_icon_manager.get_icon = Mock(return_value=QIcon())
        monkeypatch.setattr('src.gui.icon_manager.get_icon_manager', lambda: mock_icon_manager)
        monkeypatch.setattr('bbdrop.get_project_root', Mock(return_value="/tmp"))
        monkeypatch.setattr('bbdrop.get_credential', Mock(return_value=None))

        # Create dialog with no stored credentials
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config, {}, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        # User types credentials (can type directly, no need to unmask)
        dialog.creds_username_input.setText("testuser")
        dialog.creds_password_input.setText("testpass")

        # get_credentials should return what user typed
        creds = dialog.get_credentials()
        assert creds == "testuser:testpass", f"get_credentials returned '{creds}', expected 'testuser:testpass'"

    def test_get_credentials_after_edit_not_cached(self, qtbot, mock_host_config, mock_worker_manager, monkeypatch):
        """Test that editing credentials updates get_credentials return value."""
        mock_icon_manager = Mock()
        mock_icon_manager.get_icon = Mock(return_value=QIcon())
        monkeypatch.setattr('src.gui.icon_manager.get_icon_manager', lambda: mock_icon_manager)
        monkeypatch.setattr('bbdrop.get_project_root', Mock(return_value="/tmp"))
        # Return old encrypted credentials
        monkeypatch.setattr('bbdrop.get_credential', Mock(return_value=encrypt_password("olduser:oldpass")))

        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config, {}, mock_worker_manager
        )
        qtbot.addWidget(dialog)

        # Dialog loads old credentials into saved_credentials cache
        assert dialog.saved_credentials == "olduser:oldpass"

        # User edits (can type directly now)
        dialog.creds_username_input.clear()
        dialog.creds_username_input.insert("newuser")
        dialog.creds_password_input.clear()
        dialog.creds_password_input.insert("newpass")

        # get_credentials should return NEW values, not cached
        creds = dialog.get_credentials()
        assert creds == "newuser:newpass", f"get_credentials returned '{creds}', expected 'newuser:newpass' (cached was 'olduser:oldpass')"
