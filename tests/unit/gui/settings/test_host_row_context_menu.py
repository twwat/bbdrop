"""Context menu on host rows — actions per kind and state."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from src.gui.settings.file_hosts_tab import FileHostsSettingsWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from src.gui.icon_manager import get_icon_manager, init_icon_manager
    from src.utils.paths import get_project_root
    if get_icon_manager() is None:
        init_icon_manager(os.path.join(get_project_root(), "assets"))
    yield app


def _action_labels(menu):
    """Extract all action labels and submenu titles from a menu."""
    out = []
    for a in menu.actions():
        if a.text():
            out.append(a.text())
        if a.menu() is not None:
            # Include submenu title
            out.append(a.text())
    return out


def test_image_host_menu_has_primary_and_cover_when_enabled(qapp, monkeypatch):
    """Image host menu shows role actions (primary, cover) when enabled."""
    from src.core import image_host_config
    monkeypatch.setattr(image_host_config, 'is_image_host_enabled', lambda hid: True)
    widget = FileHostsSettingsWidget(parent=None, worker_manager=None)
    menu = widget._build_host_menu('imx')
    labels = _action_labels(menu)
    assert 'Disable Host' in labels
    assert 'Set as Primary Host' in labels
    assert 'Set as Cover Host' in labels
    assert 'Configure Host...' in labels


def test_image_host_menu_hides_roles_when_disabled(qapp, monkeypatch):
    """Image host menu hides role actions (primary, cover) when disabled."""
    from src.core import image_host_config
    monkeypatch.setattr(image_host_config, 'is_image_host_enabled', lambda hid: False)
    widget = FileHostsSettingsWidget(parent=None, worker_manager=None)
    menu = widget._build_host_menu('imx')
    labels = _action_labels(menu)
    assert 'Enable Host' in labels
    assert 'Set as Primary Host' not in labels
    assert 'Set as Cover Host' not in labels


def test_file_host_menu_has_trigger_submenu_and_browse(qapp):
    """File host menu shows trigger submenu and browse action."""
    widget = FileHostsSettingsWidget(parent=None, worker_manager=None)
    menu = widget._build_host_menu('rapidgator')
    labels = _action_labels(menu)
    assert any('Trigger' in t for t in labels) or any('On Added' in t for t in labels)
    assert 'Browse Files...' in labels
    assert 'Configure Host...' in labels


def test_file_host_menu_enable_disable_actions(qapp, monkeypatch):
    """File host menu shows enable/disable based on current state."""
    from unittest.mock import MagicMock
    from src.core import file_host_config

    # Mock worker_manager
    worker_manager = MagicMock()
    worker_manager.is_enabled.return_value = False

    widget = FileHostsSettingsWidget(parent=None, worker_manager=worker_manager)
    menu = widget._build_host_menu('rapidgator')
    labels = _action_labels(menu)
    assert 'Enable Host' in labels


def test_image_host_menu_triggers_toggle_on_action(qapp, monkeypatch):
    """Image host menu enable action is callable."""
    from unittest.mock import MagicMock
    from src.core import image_host_config

    toggle_mock = MagicMock()
    monkeypatch.setattr(image_host_config, 'is_image_host_enabled', lambda hid: False)

    widget = FileHostsSettingsWidget(parent=None, worker_manager=None)
    widget._toggle_image_host = toggle_mock
    menu = widget._build_host_menu('imx')

    # Find and trigger the Enable Host action
    for action in menu.actions():
        if action.text() == 'Enable Host':
            action.trigger()
            toggle_mock.assert_called_once_with('imx', True)
            break


def test_file_host_menu_trigger_options(qapp, monkeypatch):
    """File host menu trigger submenu has all four options."""
    from unittest.mock import MagicMock
    from src.core import file_host_config

    monkeypatch.setattr(file_host_config, 'get_file_host_setting',
                       lambda hid, key, typ: 'disabled' if key == 'trigger' else False)

    worker_manager = MagicMock()
    worker_manager.is_enabled.return_value = True

    widget = FileHostsSettingsWidget(parent=None, worker_manager=worker_manager)
    menu = widget._build_host_menu('rapidgator')

    # Find trigger submenu
    trigger_menu = None
    for action in menu.actions():
        if action.menu() and 'Trigger' in action.text():
            trigger_menu = action.menu()
            break

    assert trigger_menu is not None
    trigger_labels = [a.text() for a in trigger_menu.actions()]
    assert 'On Added' in trigger_labels
    assert 'On Started' in trigger_labels
    assert 'On Completed' in trigger_labels
    assert 'Disabled' in trigger_labels
