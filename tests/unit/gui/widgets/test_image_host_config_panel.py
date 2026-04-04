"""Tests for ImageHostConfigPanel inline credential fields."""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock, call
from PyQt6.QtWidgets import QLineEdit, QLabel, QApplication

from src.core.image_host_config import ImageHostConfig

# Ensure offscreen rendering
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    """Ensure a QApplication exists for the module."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


# Shared mocks applied to all tests
def _fake_get_setting(host_id, key, type_hint='str'):
    """Return sensible defaults based on type hint."""
    if type_hint == 'int':
        return 3
    if type_hint == 'bool':
        return False
    return None  # str settings default to None (no saved value)


@pytest.fixture(autouse=True)
def mock_deps(qapp):
    """Mock credential and config dependencies."""
    with patch('src.gui.widgets.image_host_config_panel.get_image_host_setting', side_effect=_fake_get_setting), \
         patch('src.gui.widgets.image_host_config_panel.get_credential', return_value=None), \
         patch('src.gui.widgets.image_host_config_panel.set_credential'), \
         patch('src.gui.widgets.image_host_config_panel.remove_credential'), \
         patch('src.gui.widgets.image_host_config_panel.encrypt_password', side_effect=lambda x: f'enc_{x}'), \
         patch('src.gui.widgets.image_host_config_panel.decrypt_password', return_value=None), \
         patch('src.gui.widgets.image_host_config_panel.get_config_path', return_value='/tmp/fake.ini'), \
         patch('src.gui.widgets.image_host_config_panel.InfoButton', side_effect=lambda *a, **kw: QLabel("")):
        yield


def _make_panel(host_id, **overrides):
    """Create a panel for a given host with sensible defaults."""
    from src.gui.widgets.image_host_config_panel import ImageHostConfigPanel

    defaults = {
        'imx': dict(
            name='IMX.to', host_id='imx',
            auth_type='api_key_or_session', requires_auth=True,
            thumbnail_sizes=[{"id": 1, "label": "100x100"}, {"id": 3, "label": "250x250"}],
            thumbnail_formats=[{"id": 1, "label": "Fixed width"}, {"id": 2, "label": "Proportional"}],
        ),
        'turbo': dict(
            name='TurboImageHost', host_id='turbo',
            auth_type='session_optional', requires_auth=False,
            thumbnail_mode='variable',
            thumbnail_range={'min': 150, 'max': 600, 'default': 300},
            content_types=[{"id": "all", "label": "Family Safe"}, {"id": "adult", "label": "Adult Content"}],
        ),
        'pixhost': dict(
            name='Pixhost', host_id='pixhost',
            auth_type='none', requires_auth=False,
            thumbnail_mode='variable',
            thumbnail_range={'min': 150, 'max': 500, 'default': 300},
            content_types=[{"id": "0", "label": "Family Safe"}, {"id": "1", "label": "Adult Content"}],
        ),
    }

    config_kwargs = defaults.get(host_id, {})
    config_kwargs.update(overrides)
    config = ImageHostConfig(**config_kwargs)
    panel = ImageHostConfigPanel(host_id, config)
    return panel


class TestIMXInlineCredentials:
    """Verify IMX has inline QLineEdit fields for api_key, username, password."""

    def test_has_api_key_input(self):
        panel = _make_panel('imx')
        assert panel.api_key_input is not None
        assert isinstance(panel.api_key_input, QLineEdit)

    def test_has_username_input(self):
        panel = _make_panel('imx')
        assert panel.username_input is not None
        assert isinstance(panel.username_input, QLineEdit)

    def test_has_password_input(self):
        panel = _make_panel('imx')
        assert panel.password_input is not None
        assert isinstance(panel.password_input, QLineEdit)

    def test_fields_masked_by_default(self):
        panel = _make_panel('imx')
        assert panel.api_key_input.echoMode() == QLineEdit.EchoMode.Password
        assert panel.username_input.echoMode() == QLineEdit.EchoMode.Password
        assert panel.password_input.echoMode() == QLineEdit.EchoMode.Password

    def test_has_test_button(self):
        panel = _make_panel('imx')
        assert panel.test_credentials_btn is not None

    def test_no_old_set_unset_buttons(self):
        panel = _make_panel('imx')
        assert not hasattr(panel, 'api_key_change_btn') or panel.api_key_change_btn is None
        assert not hasattr(panel, 'api_key_remove_btn') or panel.api_key_remove_btn is None
        assert not hasattr(panel, 'username_change_btn') or panel.username_change_btn is None
        assert not hasattr(panel, 'username_remove_btn') or panel.username_remove_btn is None
        assert not hasattr(panel, 'password_change_btn') or panel.password_change_btn is None
        assert not hasattr(panel, 'password_remove_btn') or panel.password_remove_btn is None

    def test_no_old_status_labels(self):
        panel = _make_panel('imx')
        assert not hasattr(panel, 'api_key_status_label') or panel.api_key_status_label is None
        assert not hasattr(panel, 'username_status_label') or panel.username_status_label is None
        assert not hasattr(panel, 'password_status_label') or panel.password_status_label is None

    def test_has_cookies_row(self):
        panel = _make_panel('imx')
        assert panel.cookies_status_label is not None
        assert panel.cookies_enable_btn is not None


class TestTurboInlineCredentials:
    """Verify Turbo has username/password but no api_key."""

    def test_has_username_input(self):
        panel = _make_panel('turbo')
        assert panel.username_input is not None
        assert isinstance(panel.username_input, QLineEdit)

    def test_has_password_input(self):
        panel = _make_panel('turbo')
        assert panel.password_input is not None
        assert isinstance(panel.password_input, QLineEdit)

    def test_no_api_key_input(self):
        panel = _make_panel('turbo')
        assert panel.api_key_input is None

    def test_fields_masked_by_default(self):
        panel = _make_panel('turbo')
        assert panel.username_input.echoMode() == QLineEdit.EchoMode.Password
        assert panel.password_input.echoMode() == QLineEdit.EchoMode.Password

    def test_no_cookies(self):
        panel = _make_panel('turbo')
        assert panel.cookies_status_label is None

    def test_has_test_button(self):
        panel = _make_panel('turbo')
        assert panel.test_credentials_btn is not None


class TestPixhostNoCredentials:
    """Verify Pixhost has no credential fields and no test button."""

    def test_no_api_key_input(self):
        panel = _make_panel('pixhost')
        assert panel.api_key_input is None

    def test_no_username_input(self):
        panel = _make_panel('pixhost')
        assert panel.username_input is None

    def test_no_password_input(self):
        panel = _make_panel('pixhost')
        assert panel.password_input is None

    def test_no_test_button(self):
        panel = _make_panel('pixhost')
        assert panel.test_credentials_btn is None

    def test_no_cookies(self):
        panel = _make_panel('pixhost')
        assert panel.cookies_status_label is None


class TestGetCredentials:
    """Verify get_credentials() returns field values correctly."""

    def test_returns_all_imx_fields(self):
        panel = _make_panel('imx')
        panel.api_key_input.setText('my_api_key')
        panel.username_input.setText('my_user')
        panel.password_input.setText('my_pass')
        creds = panel.get_credentials()
        assert creds == {'api_key': 'my_api_key', 'username': 'my_user', 'password': 'my_pass'}

    def test_strips_whitespace(self):
        panel = _make_panel('imx')
        panel.api_key_input.setText('  key  ')
        panel.username_input.setText('  user  ')
        panel.password_input.setText('  pass  ')
        creds = panel.get_credentials()
        assert creds == {'api_key': 'key', 'username': 'user', 'password': 'pass'}

    def test_turbo_no_api_key(self):
        panel = _make_panel('turbo')
        panel.username_input.setText('user')
        panel.password_input.setText('pass')
        creds = panel.get_credentials()
        assert 'api_key' not in creds
        assert creds == {'username': 'user', 'password': 'pass'}

    def test_pixhost_returns_empty(self):
        panel = _make_panel('pixhost')
        creds = panel.get_credentials()
        assert creds == {}

    def test_empty_fields_return_empty_strings(self):
        panel = _make_panel('imx')
        creds = panel.get_credentials()
        assert creds == {'api_key': '', 'username': '', 'password': ''}


class TestSaveCredentials:
    """Verify save_credentials() encrypts and stores via set_credential."""

    def test_saves_filled_fields(self):
        with patch('src.gui.widgets.image_host_config_panel.set_credential') as mock_set, \
             patch('src.gui.widgets.image_host_config_panel.remove_credential') as mock_remove:
            panel = _make_panel('imx')
            panel.api_key_input.setText('my_key')
            panel.username_input.setText('my_user')
            panel.password_input.setText('my_pass')
            panel.save_credentials()

            mock_set.assert_any_call('api_key', 'enc_my_key', 'imx')
            mock_set.assert_any_call('username', 'enc_my_user', 'imx')
            mock_set.assert_any_call('password', 'enc_my_pass', 'imx')
            mock_remove.assert_not_called()

    def test_removes_cleared_fields(self):
        with patch('src.gui.widgets.image_host_config_panel.set_credential') as mock_set, \
             patch('src.gui.widgets.image_host_config_panel.remove_credential') as mock_remove:
            panel = _make_panel('imx')
            # Leave all fields empty
            panel.save_credentials()

            mock_set.assert_not_called()
            mock_remove.assert_any_call('api_key', 'imx')
            mock_remove.assert_any_call('username', 'imx')
            mock_remove.assert_any_call('password', 'imx')

    def test_mixed_save_and_remove(self):
        with patch('src.gui.widgets.image_host_config_panel.set_credential') as mock_set, \
             patch('src.gui.widgets.image_host_config_panel.remove_credential') as mock_remove:
            panel = _make_panel('imx')
            panel.api_key_input.setText('my_key')
            # Leave username and password empty
            panel.save_credentials()

            mock_set.assert_called_once_with('api_key', 'enc_my_key', 'imx')
            mock_remove.assert_any_call('username', 'imx')
            mock_remove.assert_any_call('password', 'imx')

    def test_turbo_skips_api_key(self):
        with patch('src.gui.widgets.image_host_config_panel.set_credential') as mock_set, \
             patch('src.gui.widgets.image_host_config_panel.remove_credential') as mock_remove:
            panel = _make_panel('turbo')
            panel.username_input.setText('user')
            panel.password_input.setText('pass')
            panel.save_credentials()

            # Should not touch api_key at all
            for c in mock_set.call_args_list + mock_remove.call_args_list:
                assert c[0][0] != 'api_key'

            mock_set.assert_any_call('username', 'enc_user', 'turbo')
            mock_set.assert_any_call('password', 'enc_pass', 'turbo')


class TestSaveIncludesCredentials:
    """Verify save() calls save_credentials()."""

    def test_save_calls_save_credentials(self):
        with patch('src.gui.widgets.image_host_config_panel.save_image_host_setting'):
            panel = _make_panel('imx')
            with patch.object(panel, 'save_credentials') as mock_save_creds:
                panel.save()
                mock_save_creds.assert_called_once()


class TestDualWideLayout:
    """Verify the 2-column grid layout structure."""

    def test_imx_has_all_groups(self):
        panel = _make_panel('imx')
        assert panel.max_retries_spin is not None
        assert panel._has_cover_gallery
        assert hasattr(panel, 'cover_gallery_edit')
        assert hasattr(panel, 'auto_rename_check')

    def test_pixhost_has_no_cover_gallery(self):
        panel = _make_panel('pixhost')
        assert not panel._has_cover_gallery
        assert not hasattr(panel, 'cover_gallery_edit')


class TestContentTypeRadios:
    """Verify Content Type moved to Options as radio buttons."""

    def test_turbo_has_content_type_radios(self):
        panel = _make_panel('turbo')
        assert panel._content_type_group is not None
        buttons = panel._content_type_group.buttons()
        assert len(buttons) == 2
        labels = [b.text() for b in buttons]
        assert "Family Safe" in labels
        assert "Adult Content" in labels

    def test_pixhost_has_content_type_radios(self):
        panel = _make_panel('pixhost')
        assert panel._content_type_group is not None
        buttons = panel._content_type_group.buttons()
        assert len(buttons) == 2

    def test_imx_no_content_type(self):
        panel = _make_panel('imx')
        assert panel._content_type_group is None

    def test_content_type_not_in_thumbnails(self):
        """Content type should NOT be a QComboBox anymore."""
        panel = _make_panel('turbo')
        assert panel.content_type_combo is None


class TestPixhostErrorStrategy:
    """Verify Pixhost error strategy as radio buttons with sublabels."""

    def test_has_error_strategy_radios(self):
        panel = _make_panel('pixhost')
        assert hasattr(panel, '_error_strategy_group')
        buttons = panel._error_strategy_group.buttons()
        assert len(buttons) == 2

    def test_strategy_labels(self):
        panel = _make_panel('pixhost')
        labels = [b.text() for b in panel._error_strategy_group.buttons()]
        assert "Retry image only" in labels
        assert "Retry full gallery" in labels

    def test_default_is_retry_image(self):
        panel = _make_panel('pixhost')
        checked = panel._error_strategy_group.checkedButton()
        assert checked is not None
        assert checked.property("strategy_id") == "retry_image"

    def test_has_auto_finalize(self):
        panel = _make_panel('pixhost')
        assert hasattr(panel, 'auto_finalize_check')
        assert panel.auto_finalize_check is not None


class TestSaveWithRadios:
    """Verify save() works with the new radio button widgets."""

    def test_save_content_type_from_radio(self):
        with patch('src.gui.widgets.image_host_config_panel.save_image_host_setting') as mock_save:
            panel = _make_panel('turbo')
            # Select "Adult Content"
            for btn in panel._content_type_group.buttons():
                if btn.property("content_type_id") == "adult":
                    btn.setChecked(True)
            panel.save()
            ct_calls = [c for c in mock_save.call_args_list if c[0][1] == 'content_type']
            assert len(ct_calls) == 1
            assert ct_calls[0][0][2] == "adult"

    def test_save_error_strategy_from_radio(self):
        with patch('src.gui.widgets.image_host_config_panel.save_image_host_setting') as mock_save:
            panel = _make_panel('pixhost')
            # Select "Retry full gallery"
            for btn in panel._error_strategy_group.buttons():
                if btn.property("strategy_id") == "retry_gallery":
                    btn.setChecked(True)
            panel.save()
            strategy_calls = [c for c in mock_save.call_args_list if c[0][1] == 'error_retry_strategy']
            assert len(strategy_calls) == 1
            assert strategy_calls[0][0][2] == "retry_gallery"

    def test_save_auto_rename_from_checkbox(self):
        with patch('src.gui.widgets.image_host_config_panel.save_image_host_setting') as mock_save:
            panel = _make_panel('imx')
            panel.auto_rename_check.setChecked(True)
            panel.save()
            rename_calls = [c for c in mock_save.call_args_list if c[0][1] == 'auto_rename']
            assert len(rename_calls) == 1
            assert rename_calls[0][0][2] is True


class TestUploadSettingsGroup:
    """Upload Settings group replaces old Connection group with spinboxes."""

    def test_has_concurrent_uploads_spinbox(self):
        panel = _make_panel('imx')
        assert hasattr(panel, 'concurrent_uploads_spin')
        from PyQt6.QtWidgets import QSpinBox
        assert isinstance(panel.concurrent_uploads_spin, QSpinBox)

    def test_has_connect_timeout_spinbox(self):
        panel = _make_panel('imx')
        assert hasattr(panel, 'connect_timeout_spin')
        from PyQt6.QtWidgets import QSpinBox
        assert isinstance(panel.connect_timeout_spin, QSpinBox)

    def test_has_inactivity_timeout_spinbox(self):
        panel = _make_panel('imx')
        assert hasattr(panel, 'inactivity_timeout_spin')
        from PyQt6.QtWidgets import QSpinBox
        assert isinstance(panel.inactivity_timeout_spin, QSpinBox)

    def test_has_max_upload_time_spinbox(self):
        panel = _make_panel('imx')
        assert hasattr(panel, 'max_upload_time_spin')
        from PyQt6.QtWidgets import QSpinBox
        assert isinstance(panel.max_upload_time_spin, QSpinBox)

    def test_has_max_file_size_spinbox(self):
        panel = _make_panel('imx')
        assert hasattr(panel, 'max_file_size_spin')
        from PyQt6.QtWidgets import QSpinBox
        assert isinstance(panel.max_file_size_spin, QSpinBox)

    def test_has_auto_retry_toggle(self):
        panel = _make_panel('imx')
        assert hasattr(panel, 'auto_retry_check')
        from PyQt6.QtWidgets import QCheckBox
        assert isinstance(panel.auto_retry_check, QCheckBox)

    def test_has_max_retries_spinbox(self):
        panel = _make_panel('imx')
        assert hasattr(panel, 'max_retries_spin')
        from PyQt6.QtWidgets import QSpinBox
        assert isinstance(panel.max_retries_spin, QSpinBox)

    def test_no_old_sliders(self):
        """Old slider attributes should be gone."""
        panel = _make_panel('imx')
        assert not hasattr(panel, 'max_retries_slider')
        assert not hasattr(panel, 'batch_size_slider')
        assert not hasattr(panel, 'connect_timeout_slider')
        assert not hasattr(panel, 'read_timeout_slider')

    def test_max_retries_disabled_when_auto_retry_off(self):
        panel = _make_panel('imx')
        panel.auto_retry_check.setChecked(False)
        assert not panel.max_retries_spin.isEnabled()
