"""Tests that cover settings are greyed out when credentials missing."""
import pytest
from unittest.mock import patch, MagicMock


# Sensible defaults for get_image_host_setting calls during panel construction
_SETTING_DEFAULTS = {
    'max_retries': 3,
    'parallel_batch_size': 3,
    'upload_connect_timeout': 30,
    'upload_read_timeout': 120,
    'thumbnail_size': None,
    'thumbnail_format': None,
    'content_type': None,
    'cover_thumbnail_format': None,
    'cover_gallery': None,
    'auto_rename': False,
}


def _fake_setting(host_id, key, type_hint=None):
    """Return sane defaults so sliders don't get None."""
    return _SETTING_DEFAULTS.get(key)


class TestCoverSettingsGreyed:
    """Per-host cover settings disabled when no session credentials."""

    @patch('src.gui.widgets.image_host_config_panel.get_credential')
    @patch('src.gui.widgets.image_host_config_panel.get_image_host_setting',
           side_effect=_fake_setting)
    def test_cover_group_disabled_no_credentials(self, mock_setting, mock_cred):
        """Cover group is disabled when username credential is not set."""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        mock_config = MagicMock()
        mock_config.name = "IMX.to"
        mock_config.auth_type = "api_key_or_session"
        mock_config.requires_auth = False
        mock_config.thumbnail_sizes = []
        mock_config.thumbnail_formats = []
        mock_config.thumbnail_mode = "fixed"
        mock_config.thumbnail_range = None
        mock_config.content_types = []
        mock_config.logo = None
        # No credentials set
        mock_cred.return_value = None

        from src.gui.widgets.image_host_config_panel import ImageHostConfigPanel
        panel = ImageHostConfigPanel("imx", mock_config)

        # The cover group should be disabled
        assert not panel.cover_thumbnail_format_combo.isEnabled()

    @patch('src.gui.widgets.image_host_config_panel.get_credential')
    @patch('src.gui.widgets.image_host_config_panel.get_image_host_setting',
           side_effect=_fake_setting)
    def test_cover_group_enabled_with_credentials(self, mock_setting, mock_cred):
        """Cover group is enabled when username credential is set."""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        mock_config = MagicMock()
        mock_config.name = "IMX.to"
        mock_config.auth_type = "api_key_or_session"
        mock_config.requires_auth = False
        mock_config.thumbnail_sizes = []
        mock_config.thumbnail_formats = []
        mock_config.thumbnail_mode = "fixed"
        mock_config.thumbnail_range = None
        mock_config.content_types = []
        mock_config.logo = None
        # Username IS set
        mock_cred.side_effect = lambda key, host=None: "testuser" if key == "username" else None

        from src.gui.widgets.image_host_config_panel import ImageHostConfigPanel
        panel = ImageHostConfigPanel("imx", mock_config)

        # The cover group should be enabled
        assert panel.cover_thumbnail_format_combo.isEnabled()
