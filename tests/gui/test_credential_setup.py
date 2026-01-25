#!/usr/bin/env python3
"""
pytest-qt tests for CredentialSetupDialog
Tests credential management dialog functionality
"""

import pytest
from unittest.mock import patch, Mock
from PyQt6.QtWidgets import QDialog, QLineEdit, QPushButton

from src.gui.dialogs.credential_setup import CredentialSetupDialog


class TestCredentialSetupDialogInit:
    """Test CredentialSetupDialog initialization"""

    @patch('src.gui.dialogs.credential_setup.get_credential')
    def test_credential_dialog_creates(self, mock_get_cred, qtbot, mock_bbdrop_functions):
        """Test CredentialSetupDialog instantiation"""
        mock_get_cred.return_value = None

        dialog = CredentialSetupDialog()
        qtbot.addWidget(dialog)

        assert dialog is not None
        assert isinstance(dialog, QDialog)

    @patch('src.gui.dialogs.credential_setup.get_credential')
    def test_dialog_has_api_key_section(self, mock_get_cred, qtbot, mock_bbdrop_functions):
        """Test that dialog has API key section"""
        mock_get_cred.return_value = None

        dialog = CredentialSetupDialog()
        qtbot.addWidget(dialog)

        assert hasattr(dialog, 'api_key_status_label')
        assert hasattr(dialog, 'api_key_change_btn')


class TestCredentialOperations:
    """Test credential operations"""

    @patch('src.gui.dialogs.credential_setup.get_credential')
    @patch('src.gui.dialogs.credential_setup.set_credential')
    def test_change_api_key_button_exists(self, mock_set, mock_get, qtbot, mock_bbdrop_functions):
        """Test change API key button"""
        mock_get.return_value = None

        dialog = CredentialSetupDialog()
        qtbot.addWidget(dialog)

        assert dialog.api_key_change_btn is not None
        assert isinstance(dialog.api_key_change_btn, QPushButton)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
