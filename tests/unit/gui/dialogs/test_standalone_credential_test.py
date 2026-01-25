#!/usr/bin/env python3
"""
pytest-qt tests for standalone credential testing in FileHostConfigDialog

Tests for the test button fix that allows testing credentials without requiring
a running worker. This enables users to test credentials before enabling the host.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from PyQt6.QtWidgets import QLineEdit
from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QIcon

from src.gui.dialogs.file_host_config_dialog import FileHostConfigDialog
from src.core.file_host_config import HostConfig


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
    config.inactivity_timeout = 300
    config.upload_timeout = None
    return config


@pytest.fixture
def mock_host_config_api_key():
    """Create a mock HostConfig with API key authentication"""
    config = Mock(spec=HostConfig)
    config.name = "ApiKeyHost"
    config.requires_auth = True
    config.auth_type = "api_key"
    config.user_info_url = "https://apihost.com/userinfo"
    config.storage_left_path = None
    config.storage_regex = None
    config.referral_url = None
    config.inactivity_timeout = 300
    config.upload_timeout = None
    return config


@pytest.fixture
def mock_worker_manager_no_worker():
    """Create a mock FileHostWorkerManager with NO worker (host not enabled)."""
    manager = Mock()
    manager.get_worker = Mock(return_value=None)
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
def dialog_patches(monkeypatch):
    """Apply common patches needed for dialog creation"""
    monkeypatch.setattr('bbdrop.get_credential', Mock(return_value=None))
    monkeypatch.setattr('bbdrop.set_credential', Mock(return_value=True))
    monkeypatch.setattr('bbdrop.encrypt_password', lambda x: f"encrypted_{x}")
    monkeypatch.setattr('bbdrop.decrypt_password', lambda x: x.replace("encrypted_", ""))
    monkeypatch.setattr('bbdrop.get_project_root', Mock(return_value="/tmp/bbdrop"))

    mock_icon_manager = Mock()
    mock_icon_manager.get_icon = Mock(return_value=QIcon())

    with patch('src.gui.icon_manager.get_icon_manager', return_value=mock_icon_manager):
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
                with patch('src.utils.logger.log'):
                    with patch('src.utils.logging.get_logger') as mock_logger:
                        mock_logger_instance = Mock()
                        mock_logger_instance.read_current_log = Mock(return_value="")
                        mock_logger.return_value = mock_logger_instance
                        yield


class TestButtonEnabledWithoutWorker:
    """Test that test button is enabled even when worker is None"""

    def test_button_enabled_without_worker(
        self, qtbot, mock_host_config, mock_worker_manager_no_worker,
        mock_main_widgets, dialog_patches
    ):
        """Test that the Test Connection button is enabled even when worker is None."""
        assert mock_worker_manager_no_worker.get_worker.return_value is None

        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager_no_worker
        )
        qtbot.addWidget(dialog)

        assert dialog.test_connection_btn.isEnabled(), \
            "Test button should be enabled for standalone testing even without worker"

    def test_button_state_independent_of_enable_state(
        self, qtbot, mock_host_config, mock_worker_manager_no_worker,
        mock_main_widgets, dialog_patches
    ):
        """Test button enabled state is independent of host enable state"""
        mock_worker_manager_no_worker.is_enabled.return_value = False

        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager_no_worker
        )
        qtbot.addWidget(dialog)

        assert "Enable" in dialog.enable_button.text()
        assert dialog.test_connection_btn.isEnabled()


class TestRunStandaloneTestExists:
    """Test that _run_standalone_test method exists"""

    def test_standalone_test_method_exists(
        self, qtbot, mock_host_config, mock_worker_manager_no_worker,
        mock_main_widgets, dialog_patches
    ):
        """Test that _run_standalone_test method exists on dialog."""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager_no_worker
        )
        qtbot.addWidget(dialog)

        assert hasattr(dialog, '_run_standalone_test'), \
            "_run_standalone_test method should exist"
        assert callable(dialog._run_standalone_test), \
            "_run_standalone_test should be callable"


class TestRunFullTestUsesStandaloneWhenNoWorker:
    """Test that run_full_test calls standalone test when worker is missing"""

    def test_run_full_test_uses_standalone_when_no_worker(
        self, qtbot, mock_host_config, mock_worker_manager_no_worker,
        mock_main_widgets, dialog_patches
    ):
        """Test that run_full_test calls _run_standalone_test when no worker."""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager_no_worker
        )
        qtbot.addWidget(dialog)

        assert dialog.worker is None

        dialog.creds_username_input.setText("testuser")
        dialog.creds_password_input.setText("testpass")

        with patch.object(dialog, '_check_unsaved_changes', return_value=True):
            with patch.object(dialog, '_run_standalone_test') as mock_standalone:
                dialog.run_full_test()
                mock_standalone.assert_called_once()
                assert "Host not enabled" not in dialog.test_timestamp_label.text()

    def test_run_full_test_no_error_without_worker(
        self, qtbot, mock_host_config, mock_worker_manager_no_worker,
        mock_main_widgets, dialog_patches
    ):
        """Test that run_full_test doesn't show 'Host not enabled' error."""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager_no_worker
        )
        qtbot.addWidget(dialog)

        dialog.creds_username_input.setText("user")
        dialog.creds_password_input.setText("pass")

        with patch.object(dialog, '_check_unsaved_changes', return_value=True):
            with patch.object(dialog, '_run_standalone_test'):
                dialog.run_full_test()
                # Should NOT show the old error message
                assert "Error: Host not enabled" not in dialog.test_timestamp_label.text()


class TestStandaloneTestEdgeCases:
    """Test edge cases for standalone credential testing"""

    def test_standalone_test_with_empty_credentials(
        self, qtbot, mock_host_config, mock_worker_manager_no_worker,
        mock_main_widgets, dialog_patches
    ):
        """Test standalone test handles empty credentials gracefully"""
        dialog = FileHostConfigDialog(
            None, "testhost", mock_host_config,
            mock_main_widgets, mock_worker_manager_no_worker
        )
        qtbot.addWidget(dialog)

        dialog.creds_username_input.setText("")
        dialog.creds_password_input.setText("")

        with patch.object(dialog, '_check_unsaved_changes', return_value=True):
            dialog.run_full_test()
            assert "No credentials" in dialog.test_timestamp_label.text()

    def test_standalone_test_with_api_key_auth(
        self, qtbot, mock_host_config_api_key, mock_worker_manager_no_worker,
        mock_main_widgets, dialog_patches
    ):
        """Test standalone test works with API key authentication"""
        dialog = FileHostConfigDialog(
            None, "apikeyhost", mock_host_config_api_key,
            mock_main_widgets, mock_worker_manager_no_worker
        )
        qtbot.addWidget(dialog)

        if dialog.creds_api_key_input:
            dialog.creds_api_key_input.setText("test_api_key_12345")

            with patch.object(dialog, '_check_unsaved_changes', return_value=True):
                with patch.object(dialog, '_run_standalone_test') as mock_standalone:
                    dialog.run_full_test()
                    mock_standalone.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
