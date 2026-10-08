"""NotificationsTab: Discord group box."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import MagicMock, patch

import pytest

from src.gui.settings.notifications_tab import NotificationsTab
from src.services.discord_webhook import DiscordWebhookSender
from src.services.notification_manager import NOTIFICATION_EVENTS, NotificationManager

URL = "https://discord.com/api/webhooks/123/SECRETTOKEN"
STORED = f"ENC({URL})"          # what the fake encrypt_password produces
MGR = 'src.services.notification_manager'


@pytest.fixture
def manager():
    # Fake crypto: the real Fernet/master-key code must never run in tests.
    with patch(f'{MGR}.get_credential', return_value=''), \
         patch(f'{MGR}.set_credential') as store, \
         patch(f'{MGR}.remove_credential') as remove, \
         patch(f'{MGR}.encrypt_password', side_effect=lambda v: f'ENC({v})'), \
         patch(f'{MGR}.decrypt_password', side_effect=lambda v: v[4:-1]):
        mgr = NotificationManager(tray_icon=None)
        mgr.save_settings = MagicMock()   # keep the shared INI untouched
        mgr._store = store
        mgr._remove = remove
        yield mgr


@pytest.fixture
def tab(qtbot, manager):
    widget = NotificationsTab(notification_manager=manager)
    qtbot.addWidget(widget)
    return widget


def test_discord_defaults_off_and_controls_disabled(tab):
    assert tab.discord_enable.isChecked() is False
    assert tab._discord_content.isEnabled() is False
    assert all(not c.isChecked() for c in tab._discord_checks.values())
    assert tab.discord_url.text() == ''


def test_has_one_checkbox_per_event(tab):
    assert set(tab._discord_checks) == set(NOTIFICATION_EVENTS)


def test_enabling_enables_controls_and_marks_dirty(qtbot, tab):
    with qtbot.waitSignal(tab.dirty, timeout=1000):
        tab.discord_enable.setChecked(True)
    assert tab._discord_content.isEnabled() is True


def test_url_field_is_masked(tab):
    from PyQt6.QtWidgets import QLineEdit
    assert tab.discord_url.echoMode() == QLineEdit.EchoMode.Password


def test_invalid_url_shows_error_and_disables_test_button(tab):
    tab.discord_enable.setChecked(True)
    tab.discord_url.setText("https://evil.com/x")
    assert tab.discord_status.text() != ''
    assert tab.discord_test_btn.isEnabled() is False


def test_valid_url_enables_test_button(tab):
    tab.discord_enable.setChecked(True)
    tab.discord_url.setText(URL)
    assert tab.discord_status.text() == ''
    assert tab.discord_test_btn.isEnabled() is True


def test_invalid_url_blocks_save(tab, manager):
    tab.discord_enable.setChecked(True)
    tab.discord_url.setText("https://evil.com/x")
    assert tab.save_settings() is False
    manager._store.assert_not_called()
    manager.save_settings.assert_not_called()


def test_save_stores_url_flags_and_event_ticks(tab, manager):
    tab.discord_enable.setChecked(True)
    tab.discord_url.setText(f"  {URL} ")
    tab._discord_checks['gallery_failed'].setChecked(True)

    assert tab.save_settings() is True

    manager._store.assert_called_once_with('discord_webhook_url', STORED)
    assert manager._settings['discord_enabled'] is True
    assert manager.get_event_settings('gallery_failed')['discord'] is True
    assert manager.get_event_settings('queue_finished')['discord'] is False
    manager.save_settings.assert_called_once()


def test_save_fails_when_keyring_refuses(tab, manager):
    manager._store.side_effect = RuntimeError("locked")
    tab.discord_enable.setChecked(True)
    tab.discord_url.setText(URL)
    assert tab.save_settings() is False
    assert "keyring" in tab.discord_status.text().lower()


def test_unchanged_url_does_not_touch_keyring(tab, manager):
    # tests/conftest.py makes any real keyring write/delete raise BaseException,
    # and a normal save must not churn the keyring anyway.
    tab.discord_enable.setChecked(True)
    assert tab.save_settings() is True
    manager._store.assert_not_called()
    manager._remove.assert_not_called()


def test_clearing_a_stored_url_removes_it(qtbot, manager):
    with patch(f'{MGR}.get_credential', return_value=STORED):
        widget = NotificationsTab(notification_manager=manager)
        qtbot.addWidget(widget)
        widget.discord_url.setText('')
        assert widget.save_settings() is True
    manager._remove.assert_called_once_with('discord_webhook_url')


def test_load_reflects_manager_state(qtbot, manager):
    manager._settings['discord_enabled'] = True
    manager.update_event_settings('gallery_completed', {'discord': True})
    with patch(f'{MGR}.get_credential', return_value=STORED):
        widget = NotificationsTab(notification_manager=manager)
    qtbot.addWidget(widget)
    assert widget.discord_enable.isChecked() is True
    assert widget.discord_url.text() == URL
    assert widget._discord_checks['gallery_completed'].isChecked() is True
    assert widget._discord_checks['gallery_failed'].isChecked() is False


def test_test_button_sends_the_typed_url(tab):
    tab.discord_enable.setChecked(True)
    tab.discord_url.setText(URL)
    with patch.object(DiscordWebhookSender, 'send_test',
                      return_value=(True, '')) as send_test:
        tab.discord_test_btn.click()
    send_test.assert_called_once_with(URL)
    assert "sent" in tab.discord_status.text().lower()


def test_test_button_shows_failure_reason(tab):
    tab.discord_enable.setChecked(True)
    tab.discord_url.setText(URL)
    with patch.object(DiscordWebhookSender, 'send_test',
                      return_value=(False, 'Could not reach Discord')):
        tab.discord_test_btn.click()
    assert tab.discord_status.text() == 'Could not reach Discord'
    assert tab.discord_test_btn.isEnabled() is True


def test_reset_to_defaults_turns_discord_off(qtbot, tab):
    tab.discord_enable.setChecked(True)
    tab.discord_url.setText(URL)
    tab._discord_checks['gallery_failed'].setChecked(True)
    with qtbot.waitSignal(tab.dirty, timeout=1000):
        tab.reset_to_defaults()
    assert tab.discord_enable.isChecked() is False
    assert tab.discord_url.text() == ''
    assert all(not c.isChecked() for c in tab._discord_checks.values())
    assert tab._discord_content.isEnabled() is False


def test_works_without_a_manager(qtbot):
    widget = NotificationsTab(notification_manager=None)
    qtbot.addWidget(widget)
    assert widget.discord_enable.isChecked() is False
    assert widget.save_settings() is False
