"""Advanced settings widget for power users."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
    QSpinBox, QDoubleSpinBox, QComboBox, QStyledItemDelegate,
    QStyleOptionViewItem
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

# Schema for advanced settings
# Each setting has: key, description, default, type, and optional constraints
ADVANCED_SETTINGS = [
    {
        "key": "gui/log_font_size",
        "description": "Font size for the GUI log display",
        "default": 10,
        "type": "int",
        "min": 6,
        "max": 24
    },
    {
        "key": "uploads/retry_delay_seconds",
        "description": "Seconds to wait before retrying a failed upload",
        "default": 5,
        "type": "int",
        "min": 1,
        "max": 300
    },
    {
        "key": "scanning/skip_hidden_files",
        "description": "Skip hidden files (starting with .) when scanning folders",
        "default": True,
        "type": "bool"
    },
    # Bandwidth display smoothing settings
    {
        "key": "bandwidth/alpha_up",
        "description": "Speed display attack rate (higher = faster rise). Audio-style EMA smoothing.",
        "default": 0.6,
        "type": "float",
        "min": 0.1,
        "max": 1.0,
        "decimals": 2
    },
    {
        "key": "bandwidth/alpha_down",
        "description": "Speed display release rate (lower = slower decay). Audio-style EMA smoothing.",
        "default": 0.35,
        "type": "float",
        "min": 0.01,
        "max": 0.5,
        "decimals": 2
    },
    # Disk space monitoring thresholds
    {
        "key": "disk_monitor/enabled",
        "description": "Enable disk space monitoring with status bar indicator and upload gating",
        "default": True,
        "type": "bool"
    },
    {
        "key": "disk_monitor/warning_mb",
        "description": "Warning threshold in MB — status bar turns yellow (default: 2 GB)",
        "default": 2048,
        "type": "int",
        "min": 500,
        "max": 50000
    },
    {
        "key": "disk_monitor/critical_mb",
        "description": "Critical threshold in MB — new uploads blocked, dialog shown (default: 500 MB)",
        "default": 512,
        "type": "int",
        "min": 100,
        "max": 10000
    },
    {
        "key": "disk_monitor/emergency_mb",
        "description": "Emergency threshold in MB — reserve file deleted, DB flushed (default: 100 MB)",
        "default": 100,
        "type": "int",
        "min": 20,
        "max": 2000
    },
]


class AdvancedSettingsWidget(QWidget):
    """Widget for displaying and editing advanced settings."""

    settings_changed = pyqtSignal()  # Emitted when any setting changes

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_values = {}  # key -> current value
        self._setup_ui()
        self._load_defaults()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Warning header
        warning = QLabel(
            "⚠️ Advanced Settings - For experienced users only! "
            "Only change these if you understand what they do."
        )
        warning.setStyleSheet(
            "background-color: #fff3cd; color: #856404; "
            "padding: 10px; border-radius: 4px; font-weight: bold;"
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)

        # Filter box
        filter_layout = QHBoxLayout()
        filter_label = QLabel("Filter:")
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Type to filter settings...")
        self.filter_edit.textChanged.connect(self._apply_filter)
        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self.filter_edit)
        layout.addLayout(filter_layout)

        # Settings table
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Key", "Description", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)

        self._populate_table()

    def _populate_table(self):
        """Populate the table with all advanced settings."""
        self.table.setRowCount(len(ADVANCED_SETTINGS))
        self._value_widgets = {}  # key -> widget

        for row, setting in enumerate(ADVANCED_SETTINGS):
            key = setting["key"]

            # Key column
            key_item = QTableWidgetItem(key)
            key_item.setFlags(key_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, key_item)

            # Description column
            desc_item = QTableWidgetItem(setting["description"])
            desc_item.setFlags(desc_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 1, desc_item)

            # Value column - create appropriate widget
            widget = self._create_value_widget(setting)
            self._value_widgets[key] = widget
            self.table.setCellWidget(row, 2, widget)

    def _create_value_widget(self, setting):
        """Create the appropriate widget for a setting type."""
        setting_type = setting.get("type", "str")
        key = setting["key"]
        default = setting.get("default", "")

        if setting_type == "bool":
            widget = QCheckBox()
            widget.setChecked(bool(default))
            widget.toggled.connect(lambda val, k=key: self._on_value_changed(k, val))

        elif setting_type == "int":
            widget = QSpinBox()
            widget.setMinimum(setting.get("min", 0))
            widget.setMaximum(setting.get("max", 99999))
            widget.setValue(int(default))
            widget.valueChanged.connect(lambda val, k=key: self._on_value_changed(k, val))

        elif setting_type == "float":
            widget = QDoubleSpinBox()
            widget.setMinimum(setting.get("min", 0.0))
            widget.setMaximum(setting.get("max", 99999.0))
            widget.setDecimals(setting.get("decimals", 2))
            widget.setValue(float(default))
            widget.valueChanged.connect(lambda val, k=key: self._on_value_changed(k, val))

        elif setting_type == "choice":
            widget = QComboBox()
            choices = setting.get("choices", [])
            widget.addItems(choices)
            if default in choices:
                widget.setCurrentText(str(default))
            widget.currentTextChanged.connect(lambda val, k=key: self._on_value_changed(k, val))

        else:  # Default to string
            widget = QLineEdit()
            widget.setText(str(default))
            widget.textChanged.connect(lambda val, k=key: self._on_value_changed(k, val))

        return widget

    def _on_value_changed(self, key, value):
        """Handle when a setting value changes."""
        self._current_values[key] = value
        self.settings_changed.emit()

    def _load_defaults(self):
        """Load default values into current_values."""
        for setting in ADVANCED_SETTINGS:
            self._current_values[setting["key"]] = setting.get("default", "")

    def _apply_filter(self, text):
        """Filter table rows based on search text."""
        text = text.lower()
        for row in range(self.table.rowCount()):
            key_item = self.table.item(row, 0)
            desc_item = self.table.item(row, 1)
            key_text = key_item.text().lower() if key_item else ""
            desc_text = desc_item.text().lower() if desc_item else ""

            matches = text in key_text or text in desc_text
            self.table.setRowHidden(row, not matches)

    def get_values(self) -> dict:
        """Get all current setting values."""
        return self._current_values.copy()

    def get_non_default_values(self) -> dict:
        """Get only values that differ from defaults."""
        result = {}
        for setting in ADVANCED_SETTINGS:
            key = setting["key"]
            default = setting.get("default", "")
            current = self._current_values.get(key)
            if current != default:
                result[key] = current
        return result

    def set_values(self, values: dict):
        """Set values from a dictionary (e.g., loaded from INI)."""
        for key, value in values.items():
            if key in self._value_widgets:
                self._current_values[key] = value
                widget = self._value_widgets[key]

                # Find the setting schema for type info
                setting = next((s for s in ADVANCED_SETTINGS if s["key"] == key), None)
                if not setting:
                    continue

                setting_type = setting.get("type", "str")

                # Block signals to avoid triggering settings_changed
                widget.blockSignals(True)

                try:
                    if setting_type == "bool":
                        widget.setChecked(bool(value) if not isinstance(value, str) else value.lower() == 'true')
                    elif setting_type == "int":
                        widget.setValue(int(value))
                    elif setting_type == "float":
                        widget.setValue(float(value))
                    elif setting_type == "choice":
                        widget.setCurrentText(str(value))
                    else:
                        widget.setText(str(value))
                except (ValueError, TypeError):
                    # Invalid value, keep widget at current/default value
                    pass

                widget.blockSignals(False)

    def reset_to_defaults(self):
        """Reset all settings to their default values."""
        defaults = {s["key"]: s.get("default", "") for s in ADVANCED_SETTINGS}
        self.set_values(defaults)
        self._current_values = defaults.copy()
        self.settings_changed.emit()

    def load_from_config(self):
        """Load advanced settings from INI file and QSettings."""
        import os
        import configparser
        from bbdrop import get_config_path
        from PyQt6.QtCore import QSettings

        config = configparser.ConfigParser()
        config_file = get_config_path()
        values = {}

        if os.path.exists(config_file):
            config.read(config_file, encoding='utf-8')
            if config.has_section('Advanced'):
                for key, value in config.items('Advanced'):
                    # Convert string values back to appropriate types
                    if value.lower() in ('true', 'false'):
                        values[key] = value.lower() == 'true'
                    else:
                        try:
                            values[key] = int(value)
                        except ValueError:
                            try:
                                values[key] = float(value)
                            except ValueError:
                                values[key] = value

        # Load bandwidth settings from QSettings (where BandwidthManager stores them)
        qsettings = QSettings("BBDropUploader", "Settings")
        alpha_up = qsettings.value("bandwidth/alpha_up", None)
        alpha_down = qsettings.value("bandwidth/alpha_down", None)
        if alpha_up is not None:
            values["bandwidth/alpha_up"] = float(alpha_up)
        if alpha_down is not None:
            values["bandwidth/alpha_down"] = float(alpha_down)

        if values:
            self.set_values(values)

    def save_to_config(self, parent_window=None):
        """Save advanced settings to INI file (only non-default values).

        Bandwidth settings are also saved to QSettings for BandwidthManager.

        Args:
            parent_window: Optional parent window for accessing BandwidthManager.
        """
        import os
        import configparser
        from bbdrop import get_config_path
        from PyQt6.QtCore import QSettings

        config = configparser.ConfigParser()
        config_file = get_config_path()

        if os.path.exists(config_file):
            config.read(config_file, encoding='utf-8')

        # Remove existing Advanced section and recreate with current values
        if config.has_section('Advanced'):
            config.remove_section('Advanced')

        all_values = self.get_values()
        non_defaults = self.get_non_default_values()

        # Save non-defaults to INI (excluding bandwidth settings which use QSettings)
        non_bandwidth_settings = {k: v for k, v in non_defaults.items()
                                  if not k.startswith('bandwidth/')}
        if non_bandwidth_settings:
            config.add_section('Advanced')
            for key, value in non_bandwidth_settings.items():
                config.set('Advanced', key, str(value))

        with open(config_file, 'w', encoding='utf-8') as f:
            config.write(f)

        # Save bandwidth settings to QSettings (for BandwidthManager)
        alpha_up = all_values.get('bandwidth/alpha_up', 0.6)
        alpha_down = all_values.get('bandwidth/alpha_down', 0.15)

        qsettings = QSettings("BBDropUploader", "Settings")
        qsettings.setValue("bandwidth/alpha_up", alpha_up)
        qsettings.setValue("bandwidth/alpha_down", alpha_down)

        # Update the running BandwidthManager if available
        if parent_window and hasattr(parent_window, 'worker_signal_handler'):
            handler = parent_window.worker_signal_handler
            if hasattr(handler, 'bandwidth_manager'):
                handler.bandwidth_manager.update_smoothing(alpha_up, alpha_down)

        return True
