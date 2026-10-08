"""Per-event notification settings must survive a restart."""


def test_saved_settings_survive_reload(clean_notifications_ini):
    from src.services.notification_manager import NotificationManager

    first = NotificationManager(tray_icon=None)
    first._settings['enabled'] = True
    first.update_event_settings(
        'gallery_completed', {'sound': True, 'volume': 0.25, 'toast': True}
    )
    first.save_settings()

    second = NotificationManager(tray_icon=None)

    cfg = second.get_event_settings('gallery_completed')
    assert cfg['sound'] is True
    assert cfg['volume'] == 0.25
    assert cfg['toast'] is True


def test_saved_disabled_state_survives_reload(clean_notifications_ini):
    from src.services.notification_manager import NotificationManager

    first = NotificationManager(tray_icon=None)
    first._settings['enabled'] = False
    first.save_settings()

    assert NotificationManager(tray_icon=None)._settings['enabled'] is False
