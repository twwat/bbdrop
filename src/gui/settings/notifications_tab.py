"""Notifications settings tab -- per-event audio and desktop alert configuration."""

import glob
import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QCheckBox,
    QLabel, QPushButton, QSlider, QComboBox, QGridLayout,
    QSizePolicy, QFileDialog,
)
from PyQt6.QtCore import Qt, pyqtSignal

from src.gui.widgets.info_button import InfoButton
from src.services.notification_manager import NOTIFICATION_EVENTS, _EVENT_DEFAULTS
from src.utils.logger import log


class NotificationsTab(QWidget):
    """Notifications settings tab with side-by-side Audio / Desktop Alert boxes."""

    dirty = pyqtSignal()

    def __init__(self, notification_manager=None, parent=None):
        super().__init__(parent)
        self._manager = notification_manager
        self._event_rows: dict[str, dict] = {}
        self._available_sounds = self._scan_sounds()
        self._setup_ui()
        self.load_settings()

    # ------------------------------------------------------------------
    # Sound scanning
    # ------------------------------------------------------------------

    def _scan_sounds(self) -> list[str]:
        """Return sorted list of .wav filenames in assets/sounds/."""
        from src.utils.system_utils import get_resource_path
        sounds_dir = str(get_resource_path('assets/sounds'))
        return sorted(
            os.path.basename(f)
            for f in glob.glob(os.path.join(sounds_dir, '*.wav'))
        )

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Two groupboxes side by side
        boxes_layout = QHBoxLayout()
        boxes_layout.setSpacing(8)

        # -- Audio Notifications groupbox --
        self._audio_box = QGroupBox("Audio Notifications")
        audio_layout = QVBoxLayout(self._audio_box)
        audio_layout.setContentsMargins(10, 10, 10, 10)
        audio_layout.setSpacing(6)

        # Enable checkbox + InfoButton
        audio_enable_row = QHBoxLayout()
        self.audio_enable = QCheckBox("Enable Audio Notifications")
        self.audio_enable.toggled.connect(self._on_audio_toggled)
        audio_enable_row.addWidget(self.audio_enable)
        audio_enable_row.addWidget(InfoButton(
            "<b>Audio Notifications</b><br>"
            "Play a sound when an event occurs. Choose from the built-in "
            "sounds or add your own <code>.wav</code> files to the "
            "<code>assets/sounds/</code> folder. Use the volume slider "
            "to control loudness per event. The <b>&#9654;</b> button "
            "previews the sound without needing to enable it."
        ))
        audio_enable_row.addStretch()
        audio_layout.addLayout(audio_enable_row)
        audio_layout.addSpacing(6)

        # Column headers
        audio_headers = QHBoxLayout()
        audio_headers.setSpacing(6)
        h_event = QLabel("<b>Event</b>")
        h_event.setMinimumWidth(150)
        audio_headers.addWidget(h_event)
        h_sound = QLabel("<b>Sound</b>")
        h_sound.setFixedWidth(140)
        audio_headers.addWidget(h_sound)
        h_vol = QLabel("<b>Volume</b>")
        audio_headers.addWidget(h_vol, 1)
        h_pct = QLabel("")
        h_pct.setFixedWidth(35)
        audio_headers.addWidget(h_pct)
        h_play = QLabel("<b>Preview</b>")
        h_play.setFixedWidth(50)
        audio_headers.addWidget(h_play)
        audio_layout.addLayout(audio_headers)

        # Audio event rows grid
        self._audio_content = QWidget()
        audio_grid = QGridLayout(self._audio_content)
        audio_grid.setContentsMargins(0, 0, 0, 0)
        audio_grid.setHorizontalSpacing(6)
        audio_grid.setVerticalSpacing(4)
        audio_grid.setColumnMinimumWidth(0, 150)  # checkbox + event label
        audio_grid.setColumnStretch(2, 1)  # volume slider stretches
        self._audio_grid = audio_grid

        for i, event_id in enumerate(NOTIFICATION_EVENTS):
            self._create_audio_row(i, event_id)

        audio_layout.addWidget(self._audio_content)
        audio_layout.addStretch()

        boxes_layout.addWidget(self._audio_box, 1)

        # -- Desktop Alerts groupbox --
        self._alert_box = QGroupBox("Desktop Alerts")
        alert_layout = QVBoxLayout(self._alert_box)
        alert_layout.setContentsMargins(10, 10, 10, 10)
        alert_layout.setSpacing(6)

        # Enable checkbox + InfoButton
        alert_enable_row = QHBoxLayout()
        self.alert_enable = QCheckBox("Enable Desktop Alerts")
        self.alert_enable.toggled.connect(self._on_alert_toggled)
        alert_enable_row.addWidget(self.alert_enable)
        alert_enable_row.addWidget(InfoButton(
            "<b>Desktop Alerts</b><br>"
            "Show a Windows notification banner when an event occurs. "
            "These appear briefly in the bottom-right corner of your "
            "screen. Useful when BBDrop is minimized or you're working "
            "in another application. The <b>&#9654;</b> button previews "
            "the alert without needing to enable it."
        ))
        alert_enable_row.addStretch()
        alert_layout.addLayout(alert_enable_row)
        alert_layout.addSpacing(6)

        # Column headers
        alert_headers = QHBoxLayout()
        alert_headers.setSpacing(6)
        h_event2 = QLabel("<b>Event</b>")
        h_event2.setMinimumWidth(150)
        alert_headers.addWidget(h_event2)
        alert_headers.addStretch()
        h_play2 = QLabel("<b>Preview</b>")
        h_play2.setFixedWidth(50)
        alert_headers.addWidget(h_play2)
        alert_layout.addLayout(alert_headers)

        # Alert event rows grid
        self._alert_content = QWidget()
        alert_grid = QGridLayout(self._alert_content)
        alert_grid.setContentsMargins(0, 0, 0, 0)
        alert_grid.setHorizontalSpacing(6)
        alert_grid.setVerticalSpacing(4)
        alert_grid.setColumnMinimumWidth(0, 150)  # checkbox + event label
        self._alert_grid = alert_grid

        for i, event_id in enumerate(NOTIFICATION_EVENTS):
            self._create_alert_row(i, event_id)

        alert_layout.addWidget(self._alert_content)
        alert_layout.addStretch()

        self._alert_box.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred
        )
        boxes_layout.addWidget(self._alert_box)

        root.addLayout(boxes_layout, 1)

    # ------------------------------------------------------------------
    # Row builders
    # ------------------------------------------------------------------

    def _create_audio_row(self, row_idx: int, event_id: str):
        display_name, description, default_sound = NOTIFICATION_EVENTS[event_id]

        # Checkbox with event name as label
        chk = QCheckBox(display_name)
        chk.setMinimumWidth(150)
        chk.setToolTip(description)
        chk.toggled.connect(lambda on, eid=event_id: self._on_sound_toggled(eid, on))
        chk.toggled.connect(self._emit_dirty)
        self._audio_grid.addWidget(chk, row_idx, 0)

        # Sound dropdown
        combo = QComboBox()
        combo.setFixedWidth(140)
        for wav in self._available_sounds:
            combo.addItem(wav.replace('.wav', ''), wav)
        combo.insertSeparator(combo.count())
        combo.addItem("Browse...", "__browse__")
        default_idx = combo.findData(default_sound)
        if default_idx >= 0:
            combo.setCurrentIndex(default_idx)
        combo.currentIndexChanged.connect(
            lambda idx, c=combo, eid=event_id: self._on_combo_changed(c, eid, idx)
        )
        self._audio_grid.addWidget(combo, row_idx, 1)

        # Volume slider
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setSingleStep(5)
        slider.setPageStep(10)
        slider.setMinimumWidth(80)
        slider.valueChanged.connect(self._emit_dirty)
        self._audio_grid.addWidget(slider, row_idx, 2)

        # Percentage label
        pct = QLabel("50%")
        pct.setFixedWidth(35)
        pct.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        slider.valueChanged.connect(lambda v, l=pct: l.setText(f"{v}%"))
        self._audio_grid.addWidget(pct, row_idx, 3)

        # Preview button
        play_btn = QPushButton("▶")
        play_btn.setFixedWidth(50)
        play_btn.setToolTip("Preview this sound")
        play_btn.clicked.connect(lambda _, eid=event_id: self._preview_sound(eid))
        self._audio_grid.addWidget(play_btn, row_idx, 4)

        row = self._event_rows.setdefault(event_id, {})
        row.update({
            'sound_check': chk,
            'sound_combo': combo,
            'volume_slider': slider,
            'volume_pct': pct,
        })

    def _create_alert_row(self, row_idx: int, event_id: str):
        display_name, description, _ = NOTIFICATION_EVENTS[event_id]

        # Checkbox with event name as label
        chk = QCheckBox(display_name)
        chk.setMinimumWidth(150)
        chk.setToolTip(description)
        chk.toggled.connect(self._emit_dirty)
        self._alert_grid.addWidget(chk, row_idx, 0)

        # Spacer to push play button right
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._alert_grid.addWidget(spacer, row_idx, 1)

        # Preview button
        play_btn = QPushButton("▶")
        play_btn.setFixedWidth(50)
        play_btn.setToolTip("Preview this desktop alert")
        play_btn.clicked.connect(lambda _, eid=event_id: self._preview_alert(eid))
        self._alert_grid.addWidget(play_btn, row_idx, 2)

        row = self._event_rows.setdefault(event_id, {})
        row.update({'alert_check': chk})

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _emit_dirty(self, *_args):
        self.dirty.emit()

    def _on_audio_toggled(self, enabled: bool):
        self._audio_content.setEnabled(enabled)
        self.dirty.emit()

    def _on_alert_toggled(self, enabled: bool):
        self._alert_content.setEnabled(enabled)
        self.dirty.emit()

    def _on_sound_toggled(self, event_id: str, enabled: bool):
        row = self._event_rows[event_id]
        row['sound_combo'].setEnabled(enabled)
        row['volume_slider'].setEnabled(enabled)
        row['volume_pct'].setEnabled(enabled)

    def _on_combo_changed(self, combo: QComboBox, event_id: str, idx: int):
        """Handle sound combo changes; open file dialog for 'Browse...'."""
        if combo.itemData(idx) != '__browse__':
            self._emit_dirty()
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a sound file", "", "WAV files (*.wav)"
        )
        combo.blockSignals(True)
        if path:
            filename = os.path.basename(path)
            # Add as custom entry if not already present
            existing = combo.findData(path)
            if existing < 0:
                # Insert before the separator (2nd-to-last item)
                insert_at = combo.count() - 2
                combo.insertItem(insert_at, filename, path)
                combo.setCurrentIndex(insert_at)
            else:
                combo.setCurrentIndex(existing)
            self._emit_dirty()
        else:
            # Cancelled — revert to previous selection
            _, _, default_sound = NOTIFICATION_EVENTS[event_id]
            prev = combo.findData(default_sound)
            if prev >= 0:
                combo.setCurrentIndex(prev)
        combo.blockSignals(False)

    def _preview_sound(self, event_id: str):
        """Play the selected sound at the current volume (works even if not enabled)."""
        if self._manager is None:
            return
        row = self._event_rows[event_id]
        sound_file = row['sound_combo'].currentData()
        volume = row['volume_slider'].value() / 100.0

        saved = self._manager.get_event_settings(event_id)
        saved_enabled = self._manager._settings.get('enabled', False)
        try:
            self._manager._settings['enabled'] = True
            # Custom file (full path) goes in sound_file; built-in goes via event default
            is_custom = os.path.isabs(sound_file) if sound_file else False
            self._manager.update_event_settings(event_id, {
                'sound': True,
                'volume': volume,
                'sound_file': sound_file if is_custom else '',
                'toast': False,
            })
            if not is_custom:
                import src.services.notification_manager as nm
                orig = nm.NOTIFICATION_EVENTS[event_id]
                nm.NOTIFICATION_EVENTS[event_id] = (orig[0], orig[1], sound_file)
                self._manager.notify(event_id)
                nm.NOTIFICATION_EVENTS[event_id] = orig
            else:
                self._manager.notify(event_id)
        finally:
            self._manager._settings['enabled'] = saved_enabled
            self._manager.update_event_settings(event_id, saved)

    def _preview_alert(self, event_id: str):
        """Show a desktop alert preview (works even if not enabled)."""
        if self._manager is None:
            return
        saved = self._manager.get_event_settings(event_id)
        saved_enabled = self._manager._settings.get('enabled', False)
        try:
            self._manager._settings['enabled'] = True
            self._manager.update_event_settings(event_id, {
                'sound': False,
                'volume': 0,
                'sound_file': '',
                'toast': True,
            })
            self._manager.notify(event_id, detail='(preview)')
        finally:
            self._manager._settings['enabled'] = saved_enabled
            self._manager.update_event_settings(event_id, saved)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load_settings(self):
        all_controls = self._get_all_controls()
        for ctrl in all_controls:
            ctrl.blockSignals(True)

        if self._manager is not None:
            enabled = self._manager._settings.get('enabled', False)
            self.audio_enable.setChecked(enabled)
            self.alert_enable.setChecked(enabled)
            for event_id in NOTIFICATION_EVENTS:
                cfg = self._manager.get_event_settings(event_id)
                self._apply_config(event_id, cfg)
        else:
            self.audio_enable.setChecked(False)
            self.alert_enable.setChecked(False)
            for event_id in NOTIFICATION_EVENTS:
                defaults = _EVENT_DEFAULTS.get(event_id, {})
                self._apply_config(event_id, {
                    'sound': defaults.get('sound', False),
                    'volume': defaults.get('volume', 0.5),
                    'sound_file': '',
                    'toast': defaults.get('toast', False),
                })

        for ctrl in all_controls:
            ctrl.blockSignals(False)

        self._audio_content.setEnabled(self.audio_enable.isChecked())
        self._alert_content.setEnabled(self.alert_enable.isChecked())
        for event_id in self._event_rows:
            self._on_sound_toggled(
                event_id, self._event_rows[event_id]['sound_check'].isChecked()
            )

    def _apply_config(self, event_id: str, cfg: dict):
        row = self._event_rows[event_id]
        row['sound_check'].setChecked(cfg.get('sound', False))

        volume_pct = int(cfg.get('volume', 0.5) * 100)
        row['volume_slider'].setValue(volume_pct)
        row['volume_pct'].setText(f"{volume_pct}%")

        sound_file = cfg.get('sound_file', '')
        combo = row['sound_combo']
        if sound_file:
            idx = combo.findData(sound_file)
            if idx < 0 and os.path.isabs(sound_file):
                # Custom file not in combo yet — insert before separator
                insert_at = combo.count() - 2
                combo.insertItem(insert_at, os.path.basename(sound_file), sound_file)
                idx = insert_at
            if idx >= 0:
                combo.setCurrentIndex(idx)
        else:
            _, _, default_sound = NOTIFICATION_EVENTS[event_id]
            idx = combo.findData(default_sound)
            if idx >= 0:
                combo.setCurrentIndex(idx)

        row['alert_check'].setChecked(cfg.get('toast', False))

    def save_settings(self) -> bool:
        if self._manager is None:
            log("Cannot save notification settings: manager not available",
                level="warning", category="settings")
            return False
        try:
            self._manager._settings['enabled'] = (
                self.audio_enable.isChecked() or self.alert_enable.isChecked()
            )
            for event_id, row in self._event_rows.items():
                sound_on = (
                    self.audio_enable.isChecked()
                    and row['sound_check'].isChecked()
                )
                toast_on = (
                    self.alert_enable.isChecked()
                    and row['alert_check'].isChecked()
                )
                combo_data = row['sound_combo'].currentData() or ''
                _, _, default_sound = NOTIFICATION_EVENTS[event_id]
                # Save sound_file if user picked a custom path or a
                # different built-in sound than the event default
                if combo_data == '__browse__':
                    sound_file = ''
                elif os.path.isabs(combo_data):
                    sound_file = combo_data
                elif combo_data != default_sound:
                    sound_file = combo_data
                else:
                    sound_file = ''
                self._manager.update_event_settings(event_id, {
                    'sound': sound_on,
                    'volume': row['volume_slider'].value() / 100.0,
                    'sound_file': sound_file,
                    'toast': toast_on,
                })
            self._manager.save_settings()
            return True
        except Exception as e:
            log(f"Failed to save notification settings: {e}",
                level="warning", category="settings")
            return False

    def reload_settings(self):
        if self._manager is not None:
            self._manager.load_settings()
        self.load_settings()

    def reset_to_defaults(self):
        all_controls = self._get_all_controls()
        for ctrl in all_controls:
            ctrl.blockSignals(True)

        self.audio_enable.setChecked(False)
        self.alert_enable.setChecked(False)
        for event_id in NOTIFICATION_EVENTS:
            defaults = _EVENT_DEFAULTS.get(event_id, {})
            self._apply_config(event_id, {
                'sound': defaults.get('sound', False),
                'volume': defaults.get('volume', 0.5),
                'sound_file': '',
                'toast': defaults.get('toast', False),
            })

        for ctrl in all_controls:
            ctrl.blockSignals(False)

        self._audio_content.setEnabled(False)
        self._alert_content.setEnabled(False)
        for event_id in self._event_rows:
            self._on_sound_toggled(
                event_id, self._event_rows[event_id]['sound_check'].isChecked()
            )
        self.dirty.emit()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_all_controls(self) -> list:
        controls = [self.audio_enable, self.alert_enable]
        for row in self._event_rows.values():
            controls.extend([
                row['sound_check'],
                row['sound_combo'],
                row['volume_slider'],
                row['alert_check'],
            ])
        return controls
