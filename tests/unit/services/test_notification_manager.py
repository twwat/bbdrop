import pytest
from unittest.mock import MagicMock, patch


class TestNotificationManager:
    """Tests for NotificationManager service."""

    def test_notify_when_globally_disabled_does_nothing(self):
        """Master switch off = no notifications fired."""
        from src.services.notification_manager import NotificationManager
        mgr = NotificationManager(tray_icon=None)
        mgr._settings = {'enabled': False}
        mgr._play_sound = MagicMock()
        mgr._show_toast = MagicMock()

        mgr.notify('queue_finished')

        mgr._play_sound.assert_not_called()
        mgr._show_toast.assert_not_called()

    def test_notify_plays_sound_when_enabled(self):
        """Sound fires when event has sound enabled."""
        from src.services.notification_manager import NotificationManager
        mgr = NotificationManager(tray_icon=None)
        mgr._settings = {'enabled': True}
        mgr._event_settings = {
            'queue_finished': {
                'sound': True, 'volume': 0.8,
                'sound_file': '', 'toast': False,
            }
        }
        mgr._play_sound = MagicMock()
        mgr._show_toast = MagicMock()

        mgr.notify('queue_finished')

        mgr._play_sound.assert_called_once()
        mgr._show_toast.assert_not_called()

    def test_notify_shows_toast_when_enabled(self):
        """Toast fires when event has toast enabled."""
        from src.services.notification_manager import NotificationManager
        mgr = NotificationManager(tray_icon=MagicMock())
        mgr._settings = {'enabled': True}
        mgr._event_settings = {
            'gallery_failed': {
                'sound': False, 'volume': 0.8,
                'sound_file': '', 'toast': True,
            }
        }
        mgr._play_sound = MagicMock()
        mgr._show_toast = MagicMock()

        mgr.notify('gallery_failed')

        mgr._play_sound.assert_not_called()
        mgr._show_toast.assert_called_once()

    def test_notify_unknown_event_does_nothing(self):
        """Unknown event types are silently ignored."""
        from src.services.notification_manager import NotificationManager
        mgr = NotificationManager(tray_icon=None)
        mgr._settings = {'enabled': True}
        mgr._event_settings = {}

        # Should not raise
        mgr.notify('nonexistent_event')

    def test_load_settings_reads_ini(self):
        """Settings load from INI [NOTIFICATIONS] section."""
        from src.services.notification_manager import NotificationManager
        mgr = NotificationManager(tray_icon=None)

        with patch('src.services.notification_manager.load_user_defaults') as mock_load:
            mock_load.return_value = {
                'notifications_enabled': True,
                'notifications_queue_finished_sound': True,
                'notifications_queue_finished_volume': 0.75,
                'notifications_queue_finished_sound_file': '',
                'notifications_queue_finished_toast': True,
            }
            mgr.load_settings()

        assert mgr._settings['enabled'] is True
        assert mgr._event_settings['queue_finished']['sound'] is True
        assert mgr._event_settings['queue_finished']['volume'] == 0.75
