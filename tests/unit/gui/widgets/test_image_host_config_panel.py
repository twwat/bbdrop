"""Tests for ImageHostConfigPanel redesign."""
import pytest
from unittest.mock import patch

from src.core.image_host_config import ImageHostConfig


# Shared mocks applied to all tests
def _fake_get_setting(host_id, key, type_hint='str'):
    """Return sensible defaults based on type hint."""
    if type_hint == 'int':
        return 3
    if type_hint == 'bool':
        return False
    return None  # str settings default to None (no saved value)


@pytest.fixture(autouse=True)
def mock_deps():
    """Mock credential and config dependencies."""
    with patch('src.gui.widgets.image_host_config_panel.get_image_host_setting', side_effect=_fake_get_setting), \
         patch('src.gui.widgets.image_host_config_panel.get_credential', return_value=None), \
         patch('src.gui.widgets.image_host_config_panel.decrypt_password', return_value=None), \
         patch('src.gui.widgets.image_host_config_panel.get_config_path', return_value='/tmp/fake.ini'):
        yield


def _make_panel(qtbot, host_id, **overrides):
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
    qtbot.addWidget(panel)
    return panel


class TestDualWideLayout:
    """Verify the 2-column grid layout structure."""

    def test_imx_has_all_groups(self, qtbot):
        panel = _make_panel(qtbot, 'imx')
        assert panel.max_retries_slider is not None
        assert panel.api_key_status_label is not None
        assert panel._has_cover_gallery
        assert hasattr(panel, 'cover_gallery_edit')
        assert hasattr(panel, 'auto_rename_check')

    def test_pixhost_has_no_cover_gallery(self, qtbot):
        panel = _make_panel(qtbot, 'pixhost')
        assert not panel._has_cover_gallery
        assert not hasattr(panel, 'cover_gallery_edit')


class TestIMXCredentials:
    """Verify IMX hybrid credential sub-sections."""

    def test_has_api_key_section(self, qtbot):
        panel = _make_panel(qtbot, 'imx')
        assert panel.api_key_status_label is not None
        assert panel.api_key_change_btn is not None

    def test_has_username_password(self, qtbot):
        panel = _make_panel(qtbot, 'imx')
        assert panel.username_status_label is not None
        assert panel.password_status_label is not None

    def test_has_cookies_row(self, qtbot):
        panel = _make_panel(qtbot, 'imx')
        assert panel.cookies_status_label is not None
        assert panel.cookies_enable_btn is not None

    def test_has_test_credentials_btn(self, qtbot):
        panel = _make_panel(qtbot, 'imx')
        assert panel.test_credentials_btn is not None


class TestTurboCredentials:
    """Verify Turbo optional credentials with context."""

    def test_has_username_password(self, qtbot):
        panel = _make_panel(qtbot, 'turbo')
        assert panel.username_status_label is not None
        assert panel.password_status_label is not None

    def test_no_api_key(self, qtbot):
        panel = _make_panel(qtbot, 'turbo')
        assert panel.api_key_status_label is None

    def test_no_cookies(self, qtbot):
        panel = _make_panel(qtbot, 'turbo')
        assert panel.cookies_status_label is None


class TestPixhostCredentials:
    """Verify Pixhost no-account notice."""

    def test_no_credential_widgets(self, qtbot):
        panel = _make_panel(qtbot, 'pixhost')
        assert panel.username_status_label is None
        assert panel.password_status_label is None
        assert panel.api_key_status_label is None
        assert panel.cookies_status_label is None
        assert panel.test_credentials_btn is None


class TestContentTypeRadios:
    """Verify Content Type moved to Options as radio buttons."""

    def test_turbo_has_content_type_radios(self, qtbot):
        panel = _make_panel(qtbot, 'turbo')
        assert panel._content_type_group is not None
        buttons = panel._content_type_group.buttons()
        assert len(buttons) == 2
        labels = [b.text() for b in buttons]
        assert "Family Safe" in labels
        assert "Adult Content" in labels

    def test_pixhost_has_content_type_radios(self, qtbot):
        panel = _make_panel(qtbot, 'pixhost')
        assert panel._content_type_group is not None
        buttons = panel._content_type_group.buttons()
        assert len(buttons) == 2

    def test_imx_no_content_type(self, qtbot):
        panel = _make_panel(qtbot, 'imx')
        assert panel._content_type_group is None

    def test_content_type_not_in_thumbnails(self, qtbot):
        """Content type should NOT be a QComboBox anymore."""
        panel = _make_panel(qtbot, 'turbo')
        assert panel.content_type_combo is None


class TestPixhostErrorStrategy:
    """Verify Pixhost error strategy as radio buttons with sublabels."""

    def test_has_error_strategy_radios(self, qtbot):
        panel = _make_panel(qtbot, 'pixhost')
        assert hasattr(panel, '_error_strategy_group')
        buttons = panel._error_strategy_group.buttons()
        assert len(buttons) == 2

    def test_strategy_labels(self, qtbot):
        panel = _make_panel(qtbot, 'pixhost')
        labels = [b.text() for b in panel._error_strategy_group.buttons()]
        assert "Retry image only" in labels
        assert "Retry full gallery" in labels

    def test_default_is_retry_image(self, qtbot):
        panel = _make_panel(qtbot, 'pixhost')
        checked = panel._error_strategy_group.checkedButton()
        assert checked is not None
        assert checked.property("strategy_id") == "retry_image"

    def test_has_auto_finalize(self, qtbot):
        panel = _make_panel(qtbot, 'pixhost')
        assert hasattr(panel, 'auto_finalize_check')
        assert panel.auto_finalize_check is not None


class TestSaveWithRadios:
    """Verify save() works with the new radio button widgets."""

    def test_save_content_type_from_radio(self, qtbot):
        with patch('src.gui.widgets.image_host_config_panel.save_image_host_setting') as mock_save:
            panel = _make_panel(qtbot, 'turbo')
            # Select "Adult Content"
            for btn in panel._content_type_group.buttons():
                if btn.property("content_type_id") == "adult":
                    btn.setChecked(True)
            panel.save()
            ct_calls = [c for c in mock_save.call_args_list if c[0][1] == 'content_type']
            assert len(ct_calls) == 1
            assert ct_calls[0][0][2] == "adult"

    def test_save_error_strategy_from_radio(self, qtbot):
        with patch('src.gui.widgets.image_host_config_panel.save_image_host_setting') as mock_save:
            panel = _make_panel(qtbot, 'pixhost')
            # Select "Retry full gallery"
            for btn in panel._error_strategy_group.buttons():
                if btn.property("strategy_id") == "retry_gallery":
                    btn.setChecked(True)
            panel.save()
            strategy_calls = [c for c in mock_save.call_args_list if c[0][1] == 'error_retry_strategy']
            assert len(strategy_calls) == 1
            assert strategy_calls[0][0][2] == "retry_gallery"

    def test_save_auto_rename_from_checkbox(self, qtbot):
        with patch('src.gui.widgets.image_host_config_panel.save_image_host_setting') as mock_save:
            panel = _make_panel(qtbot, 'imx')
            panel.auto_rename_check.setChecked(True)
            panel.save()
            rename_calls = [c for c in mock_save.call_args_list if c[0][1] == 'auto_rename']
            assert len(rename_calls) == 1
            assert rename_calls[0][0][2] is True
