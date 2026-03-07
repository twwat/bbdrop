"""Centralized notification manager for BBDrop.

Handles audio notifications (QSoundEffect), OS toast notifications
(QSystemTrayIcon.showMessage), with per-event configuration stored
in ~/.bbdrop/bbdrop.ini under [NOTIFICATIONS].
"""

import os
from typing import Optional, Dict, Any

from PyQt6.QtWidgets import QSystemTrayIcon

from src.utils.logger import log

try:
    from src.utils.paths import load_user_defaults, read_config, get_config_path
except ImportError:
    load_user_defaults = None
    read_config = None
    get_config_path = None


# Event definitions: event_id -> (display_name, description, default_sound_file)
NOTIFICATION_EVENTS = {
    'queue_finished': (
        'Queue Finished',
        'All galleries in the queue have completed uploading.',
        'woohoo.wav',
    ),
    'gallery_completed': (
        'Gallery Completed',
        'An individual gallery finishes uploading successfully.',
        'chime1.wav',
    ),
    'gallery_failed': (
        'Gallery Failed',
        'A gallery upload fails.',
        'ohno.wav',
    ),
    'filehost_upload_completed': (
        'File Host Upload Completed',
        'A file host upload finishes successfully.',
        'chime1.wav',
    ),
    'filehost_upload_failed': (
        'File Host Upload Failed',
        'A file host upload fails.',
        'ohno.wav',
    ),
    'filehost_spinup_complete': (
        'File Host Ready',
        'A file host finishes spinning up and is ready for uploads.',
        'chime1.wav',
    ),
    'disk_space_warning': (
        'Disk Space Warning',
        'Disk space has dropped below a warning threshold.',
        'attention-mid.wav',
    ),
}

# Defaults: which events have sound/toast on by default
_EVENT_DEFAULTS = {
    'queue_finished':            {'sound': True,  'volume': 0.80, 'toast': True},
    'gallery_completed':         {'sound': False, 'volume': 0.50, 'toast': False},
    'gallery_failed':            {'sound': True,  'volume': 0.80, 'toast': True},
    'filehost_upload_completed': {'sound': False, 'volume': 0.50, 'toast': False},
    'filehost_upload_failed':    {'sound': True,  'volume': 0.80, 'toast': True},
    'filehost_spinup_complete':  {'sound': False, 'volume': 0.50, 'toast': False},
    'disk_space_warning':        {'sound': True,  'volume': 0.80, 'toast': True},
}

# Toast messages per event
_TOAST_MESSAGES = {
    'queue_finished':            ('BBDrop', 'All uploads complete!'),
    'gallery_completed':         ('BBDrop', 'Gallery uploaded successfully.'),
    'gallery_failed':            ('BBDrop', 'Gallery upload failed.'),
    'filehost_upload_completed': ('BBDrop', 'File host upload complete.'),
    'filehost_upload_failed':    ('BBDrop', 'File host upload failed.'),
    'filehost_spinup_complete':  ('BBDrop', 'File host is ready.'),
    'disk_space_warning':        ('BBDrop', 'Disk space is running low!'),
}


class NotificationManager:
    """Manages audio and toast notifications based on user preferences."""

    def __init__(self, tray_icon: Optional[QSystemTrayIcon] = None):
        self._tray_icon = tray_icon
        self._settings: Dict[str, Any] = {'enabled': False}
        self._event_settings: Dict[str, Dict[str, Any]] = {}
        self._sound_effects: Dict[str, Any] = {}  # str -> QSoundEffect
        from src.utils.system_utils import get_resource_path
        self._sounds_dir = str(get_resource_path('assets/sounds'))
        self.load_settings()

    def notify(self, event_type: str, detail: str = '') -> None:
        """Fire notifications for an event if enabled.

        Args:
            event_type: One of the keys from NOTIFICATION_EVENTS.
            detail: Optional extra text appended to the toast message.
        """
        if not self._settings.get('enabled', True):
            return

        event_cfg = self._event_settings.get(event_type)
        if event_cfg is None:
            return

        if event_cfg.get('sound', False):
            self._play_sound(event_type, event_cfg)

        if event_cfg.get('toast', False):
            self._show_toast(event_type, detail)

    def _play_sound(self, event_type: str, event_cfg: dict) -> None:
        """Play the sound for an event."""
        try:
            from PyQt6.QtCore import QUrl
            from PyQt6.QtMultimedia import QSoundEffect

            custom_file = event_cfg.get('sound_file', '')
            if custom_file:
                if os.path.isabs(custom_file) and os.path.isfile(custom_file):
                    sound_path = custom_file
                else:
                    # Bare filename — look in built-in sounds dir
                    candidate = os.path.join(self._sounds_dir, custom_file)
                    if os.path.isfile(candidate):
                        sound_path = candidate
                    else:
                        sound_path = custom_file  # let the check below log it
            else:
                _, _, default_file = NOTIFICATION_EVENTS.get(
                    event_type, ('', '', '')
                )
                sound_path = os.path.join(self._sounds_dir, default_file)

            if not os.path.isfile(sound_path):
                log(
                    f"Notification sound file not found: {sound_path}",
                    level="warning", category="notifications",
                )
                return

            effect = self._sound_effects.get(sound_path)
            if effect is None:
                effect = QSoundEffect()
                effect.setSource(QUrl.fromLocalFile(sound_path))
                self._sound_effects[sound_path] = effect

            volume = float(event_cfg.get('volume', 0.8))
            effect.setVolume(volume)
            effect.play()

        except Exception as e:
            log(
                f"Error playing notification sound: {e}",
                level="warning", category="notifications",
            )

    def _show_toast(self, event_type: str, detail: str = '') -> None:
        """Show an OS toast notification via system tray icon."""
        if self._tray_icon is None:
            return

        title, message = _TOAST_MESSAGES.get(event_type, ('BBDrop', ''))
        if detail:
            message = f"{message} {detail}"

        try:
            self._tray_icon.showMessage(
                title, message,
                QSystemTrayIcon.MessageIcon.Information,
                5000,
            )
        except Exception as e:
            log(
                f"Error showing toast notification: {e}",
                level="warning", category="notifications",
            )

    def load_settings(self) -> None:
        """Load notification settings from INI file.

        Reads keys with ``notifications_`` prefix from load_user_defaults().
        Falls back to hardcoded defaults when the INI has no values.
        """
        try:
            defaults = load_user_defaults()
        except Exception:
            defaults = {}

        self._settings['enabled'] = _bool(
            defaults.get('notifications_enabled', True)
        )

        for event_id in NOTIFICATION_EVENTS:
            event_defaults = _EVENT_DEFAULTS.get(event_id, {})
            prefix = f'notifications_{event_id}_'
            self._event_settings[event_id] = {
                'sound': _bool(defaults.get(
                    f'{prefix}sound', event_defaults.get('sound', False)
                )),
                'volume': _float(defaults.get(
                    f'{prefix}volume', event_defaults.get('volume', 0.5)
                )),
                'sound_file': str(defaults.get(f'{prefix}sound_file', '')),
                'toast': _bool(defaults.get(
                    f'{prefix}toast', event_defaults.get('toast', False)
                )),
            }

    def save_settings(self) -> None:
        """Save notification settings to INI file.

        Writes a ``[NOTIFICATIONS]`` section with per-event keys.
        """
        if read_config is None or get_config_path is None:
            log(
                "Cannot save notification settings: bbdrop config helpers unavailable",
                level="warning", category="notifications",
            )
            return

        config = read_config()
        config_file = get_config_path()

        if 'NOTIFICATIONS' not in config:
            config['NOTIFICATIONS'] = {}

        config['NOTIFICATIONS']['enabled'] = str(
            self._settings.get('enabled', True)
        )

        for event_id, cfg in self._event_settings.items():
            prefix = f'{event_id}_'
            config['NOTIFICATIONS'][f'{prefix}sound'] = str(
                cfg.get('sound', False)
            )
            config['NOTIFICATIONS'][f'{prefix}volume'] = str(
                cfg.get('volume', 0.5)
            )
            config['NOTIFICATIONS'][f'{prefix}sound_file'] = str(
                cfg.get('sound_file', '')
            )
            config['NOTIFICATIONS'][f'{prefix}toast'] = str(
                cfg.get('toast', False)
            )

        with open(config_file, 'w', encoding='utf-8') as f:
            config.write(f)

    def set_tray_icon(self, tray_icon: QSystemTrayIcon) -> None:
        """Update the tray icon reference (e.g. after tray setup)."""
        self._tray_icon = tray_icon

    def get_event_settings(self, event_id: str) -> dict:
        """Get a copy of settings for a specific event."""
        return self._event_settings.get(event_id, {}).copy()

    def update_event_settings(self, event_id: str, settings: dict) -> None:
        """Update settings for a specific event."""
        if event_id in self._event_settings:
            self._event_settings[event_id].update(settings)

    def get_default_sound_path(self, event_id: str) -> str:
        """Get the default built-in sound file path for an event."""
        _, _, default_file = NOTIFICATION_EVENTS.get(event_id, ('', '', ''))
        return os.path.join(self._sounds_dir, default_file)


def _bool(val) -> bool:
    """Convert an INI value to bool."""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ('true', '1', 'yes')
    return bool(val)


def _float(val) -> float:
    """Convert an INI value to float, clamped to 0.0-1.0."""
    try:
        v = float(val)
        return max(0.0, min(1.0, v))
    except (ValueError, TypeError):
        return 0.5
