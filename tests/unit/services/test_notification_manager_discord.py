"""NotificationManager: Discord dispatch, persistence and credential handling."""

from unittest.mock import MagicMock, patch

import pytest

from src.services.notification_manager import (
    NOTIFICATION_EVENTS, NotificationManager,
)

URL = "https://discord.com/api/webhooks/123/SECRETTOKEN"
STORED = f"ENC({URL})"          # what the fake encrypt_password produces
CRED = 'src.services.notification_manager'


def _event_cfg(discord=True, toast=False):
    return {'sound': False, 'volume': 0.5, 'sound_file': '',
            'toast': toast, 'discord': discord}


@pytest.fixture(autouse=True)
def fake_crypto():
    """Never run the real Fernet/master-key code in tests (see conftest)."""
    with patch(f'{CRED}.encrypt_password', side_effect=lambda v: f'ENC({v})'), \
         patch(f'{CRED}.decrypt_password', side_effect=lambda v: v[4:-1]):
        yield


@pytest.fixture
def mgr():
    with patch(f'{CRED}.get_credential', return_value=''):
        m = NotificationManager(tray_icon=None)
    m._discord = MagicMock()
    m._settings = {'enabled': False, 'discord_enabled': True}
    m._event_settings = {e: _event_cfg() for e in NOTIFICATION_EVENTS}
    m._play_sound = MagicMock()
    m._show_toast = MagicMock()
    return m


class TestDispatch:
    def test_discord_fires_when_master_switch_off(self, mgr):
        mgr.notify('gallery_failed', detail='Set — boom')
        mgr._discord.send.assert_called_once_with('❌ Gallery failed: Set — boom')
        mgr._show_toast.assert_not_called()

    def test_discord_is_not_debounced(self, mgr):
        mgr._settings['enabled'] = True
        mgr._event_settings['gallery_completed'] = _event_cfg(toast=True)
        mgr._get_debounce_ms = MagicMock(return_value=1500)
        mgr.notify('gallery_completed', detail='A')
        mgr.notify('gallery_completed', detail='B')
        assert mgr._discord.send.call_count == 2
        assert mgr._show_toast.call_count == 1   # toasts still debounce

    def test_nothing_sent_when_discord_disabled(self, mgr):
        mgr._settings['discord_enabled'] = False
        mgr.notify('gallery_failed', detail='x')
        mgr._discord.send.assert_not_called()

    def test_nothing_sent_when_event_not_ticked(self, mgr):
        mgr._event_settings['gallery_failed'] = _event_cfg(discord=False)
        mgr.notify('gallery_failed', detail='x')
        mgr._discord.send.assert_not_called()

    def test_unknown_event_sends_nothing(self, mgr):
        mgr.notify('nonexistent_event')
        mgr._discord.send.assert_not_called()

    @pytest.mark.parametrize("event,detail,expected", [
        ('queue_finished', '', '✅ BBDrop: all uploads complete'),
        ('gallery_completed', 'My Set', '✅ Gallery uploaded: My Set'),
        ('gallery_completed', '', '✅ Gallery uploaded'),
        ('gallery_failed', 'My Set — timeout', '❌ Gallery failed: My Set — timeout'),
        ('gallery_failed', '', '❌ Gallery failed'),
        ('filehost_upload_completed', '', '✅ File host upload complete'),
        ('filehost_upload_failed', 'quota', '❌ File host upload failed: quota'),
        ('filehost_upload_failed', '', '❌ File host upload failed'),
        ('filehost_spinup_complete', '', 'ℹ️ File host ready'),
        ('disk_space_warning', 'Disk space: critical', '⚠️ Disk space: critical'),
        ('disk_space_warning', '', '⚠️ Disk space is running low'),
    ])
    def test_message_text(self, mgr, event, detail, expected):
        mgr.notify(event, detail=detail)
        mgr._discord.send.assert_called_once_with(expected)

    def test_detail_with_braces_is_kept_verbatim(self, mgr):
        mgr.notify('gallery_completed', detail='My {detail} {0} set')
        mgr._discord.send.assert_called_once_with(
            '✅ Gallery uploaded: My {detail} {0} set')


class TestPersistence:
    def test_discord_settings_round_trip(self, clean_notifications_ini):
        with patch(f'{CRED}.get_credential', return_value=''):
            first = NotificationManager(tray_icon=None)
            first._settings['discord_enabled'] = True
            first.update_event_settings('queue_finished', {'discord': True})
            first.save_settings()
            second = NotificationManager(tray_icon=None)

        assert second._settings['discord_enabled'] is True
        assert second.get_event_settings('queue_finished')['discord'] is True
        assert second.get_event_settings('gallery_failed')['discord'] is False

    def test_discord_off_by_default(self, clean_notifications_ini):
        with patch(f'{CRED}.get_credential', return_value=''):
            fresh = NotificationManager(tray_icon=None)
        assert fresh._settings['discord_enabled'] is False
        assert all(fresh.get_event_settings(e)['discord'] is False
                   for e in NOTIFICATION_EVENTS)

    def test_webhook_url_never_written_to_ini(self, clean_notifications_ini):
        from src.utils.paths import get_config_path
        with patch(f'{CRED}.get_credential', return_value=STORED), \
             patch(f'{CRED}.set_credential'):
            m = NotificationManager(tray_icon=None)
            m.set_discord_webhook_url(URL)
            m.save_settings()
        with open(get_config_path(), encoding='utf-8') as f:
            text = f.read()
        assert 'SECRETTOKEN' not in text and 'discord.com' not in text

    def test_load_gives_sender_the_stored_url(self):
        with patch(f'{CRED}.get_credential', return_value=STORED):
            m = NotificationManager(tray_icon=None)
        assert m._discord.has_url is True

    def test_undecryptable_stored_url_means_no_url_and_no_crash(self):
        from src.utils.credentials import CredentialDecryptionError
        with patch(f'{CRED}.get_credential', return_value='gAAAAAgarbage'), \
             patch(f'{CRED}.decrypt_password',
                   side_effect=CredentialDecryptionError("bad key")):
            m = NotificationManager(tray_icon=None)
        assert m._discord.has_url is False

    def test_no_stored_value_never_calls_decrypt(self):
        with patch(f'{CRED}.get_credential', return_value=''), \
             patch(f'{CRED}.decrypt_password') as decrypt:
            NotificationManager(tray_icon=None)
        decrypt.assert_not_called()

    def test_keyring_failure_on_load_disables_discord(self, clean_notifications_ini):
        with patch(f'{CRED}.get_credential', return_value=''):
            first = NotificationManager(tray_icon=None)
            first._settings['discord_enabled'] = True
            first.save_settings()
        with patch(f'{CRED}.get_credential', side_effect=RuntimeError("no keyring")):
            m = NotificationManager(tray_icon=None)
        assert m._settings['discord_enabled'] is False


class TestWebhookUrl:
    def test_set_url_stores_encrypted_value_and_updates_sender(self, mgr):
        with patch(f'{CRED}.set_credential') as store:
            assert mgr.set_discord_webhook_url(f'  {URL}\n') is True
        # Encrypted, never the raw URL.
        store.assert_called_once_with('discord_webhook_url', STORED)
        mgr._discord.set_url.assert_called_once_with(URL)

    def test_invalid_url_is_refused(self, mgr):
        with patch(f'{CRED}.set_credential') as store:
            assert mgr.set_discord_webhook_url('https://evil.com/x') is False
        store.assert_not_called()
        mgr._discord.set_url.assert_not_called()

    def test_empty_url_removes_credential(self, mgr):
        with patch(f'{CRED}.remove_credential') as remove:
            assert mgr.set_discord_webhook_url('') is True
        remove.assert_called_once_with('discord_webhook_url')
        mgr._discord.set_url.assert_called_once_with('')

    def test_keyring_error_returns_false(self, mgr):
        with patch(f'{CRED}.set_credential', side_effect=RuntimeError("locked")):
            assert mgr.set_discord_webhook_url(URL) is False
        mgr._discord.set_url.assert_not_called()

    def test_get_url_reads_keyring_and_decrypts(self, mgr):
        with patch(f'{CRED}.get_credential', return_value=STORED) as get:
            assert mgr.get_discord_webhook_url() == URL
        get.assert_called_once_with('discord_webhook_url')

    def test_get_url_returns_empty_when_nothing_stored(self, mgr):
        with patch(f'{CRED}.get_credential', return_value=''):
            assert mgr.get_discord_webhook_url() == ''


class TestPrivacyRedaction:
    """The UI and docs promise file paths and links are never sent."""

    @pytest.mark.parametrize("detail,expected", [
        (r"Set 7 — Gallery folder not found: C:\Users\Jimbo\Pictures\Set 7 (x82)",
         "Set 7 — Gallery folder not found: Set 7 (x82)"),
        ("Set — Gallery folder not found: /home/jimbo/pics/Set 7",
         "Set — Gallery folder not found: Set 7"),
        (r"Set — cannot read \\nas\share\pics\a.jpg now",
         "Set — cannot read a.jpg now"),
        (r"Set — No such file: 'C:\Users\Jimbo\a.jpg'",
         "Set — No such file: 'a.jpg'"),
        ("Set — failed to POST https://api.example.com/upload?key=abc: timeout",
         "Set — failed to POST [link]: timeout"),
        ("Set — see http://host/x.", "Set — see [link]."),
        ("Set — Connection timeout", "Set — Connection timeout"),
        ("Set — 5/10 images failed and/or timed out",
         "Set — 5/10 images failed and/or timed out"),
    ])
    def test_paths_and_links_are_redacted(self, mgr, detail, expected):
        mgr.notify('gallery_failed', detail=detail)
        mgr._discord.send.assert_called_once_with(f'❌ Gallery failed: {expected}')

    def test_toast_text_is_not_redacted(self, mgr):
        mgr._settings['enabled'] = True
        mgr._event_settings['gallery_failed'] = _event_cfg(toast=True)
        detail = r"Set — not found: C:\Users\Jimbo\Set"
        mgr.notify('gallery_failed', detail=detail)
        mgr._show_toast.assert_called_once_with('gallery_failed', detail)
