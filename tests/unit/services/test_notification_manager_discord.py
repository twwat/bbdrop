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
        mgr.notify('gallery_failed', detail='Set — boom',
                   fields={'gallery_name': 'Set', 'error': 'boom'})
        mgr._discord.send.assert_called_once_with(
            '❌ Gallery failed: Set — boom', suppress_embeds=True)
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

    @pytest.mark.parametrize("event,detail,fields,expected", [
        ('queue_finished', '', None, '✅ BBDrop: all uploads complete'),
        ('gallery_completed', 'My Set', {'gallery_name': 'My Set'},
         '✅ Gallery uploaded: My Set'),
        ('gallery_completed', '', None, '✅ Gallery uploaded'),
        ('gallery_failed', 'My Set — timeout',
         {'gallery_name': 'My Set', 'error': 'timeout'},
         '❌ Gallery failed: My Set — timeout'),
        ('gallery_failed', '', None, '❌ Gallery failed'),
        ('filehost_upload_completed', '', None, '✅ File host upload complete'),
        ('filehost_upload_completed', '',
         {'host_name': 'Rapidgator', 'gallery_name': 'My Set'},
         '✅ Rapidgator upload complete: My Set'),
        ('filehost_upload_failed', 'quota',
         {'host_name': 'Rapidgator', 'gallery_name': 'My Set', 'error': 'quota'},
         '❌ Rapidgator upload failed: My Set — quota'),
        ('filehost_upload_failed', '', None, '❌ File host upload failed'),
        ('filehost_spinup_complete', '', None, 'ℹ️ File host ready'),
        ('disk_space_warning', 'Disk space: critical', None,
         '⚠️ Disk space\\: critical'),
        ('disk_space_warning', '', None, '⚠️ Disk space is running low'),
    ])
    def test_message_text(self, mgr, event, detail, fields, expected):
        mgr.notify(event, detail=detail, fields=fields)
        mgr._discord.send.assert_called_once_with(expected, suppress_embeds=True)

    def test_name_with_braces_is_kept_verbatim(self, mgr):
        mgr.notify('gallery_completed', fields={'gallery_name': 'My {detail} {0} set'})
        mgr._discord.send.assert_called_once_with(
            '✅ Gallery uploaded: My {detail} {0} set', suppress_embeds=True)


class TestTemplates:
    def test_custom_template_used(self, mgr):
        mgr._event_settings['gallery_completed']['discord_message'] = 'Done: #galleryName#'
        mgr.notify('gallery_completed', fields={'gallery_name': 'A'})
        mgr._discord.send.assert_called_once_with('Done: A', suppress_embeds=True)

    def test_blank_custom_template_falls_back_to_default(self, mgr):
        mgr._event_settings['gallery_completed']['discord_message'] = '   '
        mgr.notify('gallery_completed', fields={'gallery_name': 'A'})
        mgr._discord.send.assert_called_once_with(
            '✅ Gallery uploaded: A', suppress_embeds=True)

    def test_previews_setting_turns_suppression_off(self, mgr):
        mgr._settings['discord_link_previews'] = True
        mgr.notify('queue_finished')
        mgr._discord.send.assert_called_once_with(
            '✅ BBDrop: all uploads complete', suppress_embeds=False)

    def test_long_message_sent_as_ordered_chunks(self, mgr):
        mgr._event_settings['gallery_completed']['discord_message'] = 'Head\n#hostLinks#'
        links = '\n'.join(f'[H{i}](https://h.com/{i:040d})' for i in range(60))
        mgr.notify('gallery_completed', fields={'host_links': links})
        sent = [c.args[0] for c in mgr._discord.send.call_args_list]
        assert len(sent) == 2
        assert sent[0].startswith('Head\n[H0]')
        assert '\n'.join(sent) == 'Head\n' + links

    def test_error_redacted_and_capped(self, mgr):
        error = 'boom C:\\Users\\me\\x.zip ' + 'e' * 300
        mgr._event_settings['gallery_failed']['discord_message'] = '#error#'
        mgr.notify('gallery_failed', fields={'error': error})
        sent = mgr._discord.send.call_args.args[0]
        assert 'Users' not in sent
        assert sent == ('boom x.zip ' + 'e' * 300)[:200]

    @pytest.mark.parametrize("master,event,expected", [
        (True, True, True), (True, False, False), (False, True, False), (False, False, False),
    ])
    def test_wants_discord(self, mgr, master, event, expected):
        mgr._settings['discord_enabled'] = master
        mgr._event_settings['gallery_completed']['discord'] = event
        assert mgr.wants_discord('gallery_completed') is expected

    def test_wants_discord_unknown_event(self, mgr):
        assert mgr.wants_discord('nope') is False

    @pytest.mark.parametrize("text", [
        '100% done', 'a\\nb', 'line1\nline2', '\\', '%%', 'x\\\nz',
    ])
    def test_encode_decode_round_trip(self, text):
        from src.services.notification_manager import _decode_ini_text, _encode_ini_text
        encoded = _encode_ini_text(text)
        assert '\n' not in encoded
        assert _decode_ini_text(encoded) == text


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


class TestTemplatePersistence:
    def test_discord_message_round_trip(self, clean_notifications_ini):
        text = '✅ #galleryName# 100%\nC:\\path \\n literal\n\n[if hostLinks]#hostLinks#[/if]'
        with patch(f'{CRED}.get_credential', return_value=''):
            first = NotificationManager(tray_icon=None)
            first.update_event_settings('gallery_completed', {'discord_message': text})
            first.save_settings()
            second = NotificationManager(tray_icon=None)
        assert second.get_event_settings('gallery_completed')['discord_message'] == text

    def test_empty_message_removes_key(self, clean_notifications_ini):
        from src.utils.paths import read_config
        with patch(f'{CRED}.get_credential', return_value=''):
            m = NotificationManager(tray_icon=None)
            m.update_event_settings('gallery_completed', {'discord_message': 'X'})
            m.save_settings()
            m.update_event_settings('gallery_completed', {'discord_message': ''})
            m.save_settings()
            again = NotificationManager(tray_icon=None)
        assert not read_config().has_option('NOTIFICATIONS', 'gallery_completed_discord_message')
        assert again.get_event_settings('gallery_completed')['discord_message'] == ''

    def test_link_previews_round_trip(self, clean_notifications_ini):
        with patch(f'{CRED}.get_credential', return_value=''):
            first = NotificationManager(tray_icon=None)
            assert first._settings['discord_link_previews'] is False
            first._settings['discord_link_previews'] = True
            first.save_settings()
            second = NotificationManager(tray_icon=None)
        assert second._settings['discord_link_previews'] is True


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
        from src.services.discord_message import escape_markdown
        mgr.notify('gallery_failed', detail=detail, fields={'error': detail})
        mgr._discord.send.assert_called_once_with(
            f'❌ Gallery failed — {escape_markdown(expected)}', suppress_embeds=True)

    def test_detail_is_redacted(self, mgr):
        mgr.notify('disk_space_warning', detail='see https://x.com/a now')
        mgr._discord.send.assert_called_once_with(
            '⚠️ see \\[link\\] now', suppress_embeds=True)

    def test_toast_text_is_not_redacted(self, mgr):
        mgr._settings['enabled'] = True
        mgr._event_settings['gallery_failed'] = _event_cfg(toast=True)
        detail = r"Set — not found: C:\Users\Jimbo\Set"
        mgr.notify('gallery_failed', detail=detail)
        mgr._show_toast.assert_called_once_with('gallery_failed', detail)
