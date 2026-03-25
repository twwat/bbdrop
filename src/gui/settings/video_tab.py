"""Video settings tab for ComprehensiveSettingsDialog."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QFormLayout,
    QSpinBox, QCheckBox, QComboBox, QLineEdit,
    QFontComboBox,
)
from PyQt6.QtCore import pyqtSignal, QSettings


class VideoSettingsTab(QWidget):
    """Settings tab for video support configuration."""

    dirty = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Screenshot Sheet group
        sheet_group = QGroupBox("Screenshot Sheet")
        sheet_layout = QFormLayout(sheet_group)

        self.grid_rows = QSpinBox()
        self.grid_rows.setRange(1, 10)
        self.grid_rows.setValue(4)
        self.grid_rows.valueChanged.connect(self.dirty.emit)
        sheet_layout.addRow("Grid rows:", self.grid_rows)

        self.grid_cols = QSpinBox()
        self.grid_cols.setRange(1, 10)
        self.grid_cols.setValue(4)
        self.grid_cols.valueChanged.connect(self.dirty.emit)
        sheet_layout.addRow("Grid columns:", self.grid_cols)

        self.output_format = QComboBox()
        self.output_format.addItems(["PNG", "JPG"])
        self.output_format.currentIndexChanged.connect(self.dirty.emit)
        sheet_layout.addRow("Output format:", self.output_format)

        layout.addWidget(sheet_group)

        # Timestamp Overlay group
        ts_group = QGroupBox("Timestamp Overlay")
        ts_layout = QFormLayout(ts_group)

        self.show_timestamps = QCheckBox("Show timestamps on thumbnails")
        self.show_timestamps.setChecked(True)
        self.show_timestamps.toggled.connect(self.dirty.emit)
        ts_layout.addRow(self.show_timestamps)

        self.show_ms = QCheckBox("Show milliseconds")
        self.show_ms.toggled.connect(self.dirty.emit)
        ts_layout.addRow(self.show_ms)

        self.show_frame_number = QCheckBox("Show frame number")
        self.show_frame_number.toggled.connect(self.dirty.emit)
        ts_layout.addRow(self.show_frame_number)

        layout.addWidget(ts_group)

        # Appearance group
        appearance_group = QGroupBox("Appearance")
        appearance_layout = QFormLayout(appearance_group)

        self.font_family = QFontComboBox()
        self.font_family.currentFontChanged.connect(self.dirty.emit)
        appearance_layout.addRow("Font:", self.font_family)

        self.font_color = QLineEdit("#ffffff")
        self.font_color.textChanged.connect(self.dirty.emit)
        appearance_layout.addRow("Font color:", self.font_color)

        self.bg_color = QLineEdit("#000000")
        self.bg_color.textChanged.connect(self.dirty.emit)
        appearance_layout.addRow("Background color:", self.bg_color)

        layout.addWidget(appearance_group)

        # Defaults group
        defaults_group = QGroupBox("Defaults")
        defaults_layout = QFormLayout(defaults_group)

        self.default_template = QComboBox()
        self.default_template.currentIndexChanged.connect(self.dirty.emit)
        defaults_layout.addRow("Default video template:", self.default_template)

        self.image_host_override = QComboBox()
        self.image_host_override.addItem("(use current selection)", "")
        self.image_host_override.currentIndexChanged.connect(self.dirty.emit)
        defaults_layout.addRow("Image host for sheets:", self.image_host_override)

        layout.addWidget(defaults_group)

        # Mixed folder group
        mixed_group = QGroupBox("Mixed Folders")
        mixed_layout = QFormLayout(mixed_group)

        self.remember_mixed = QCheckBox("Remember mixed folder choice")
        self.remember_mixed.toggled.connect(self.dirty.emit)
        mixed_layout.addRow(self.remember_mixed)

        self.mixed_choice = QComboBox()
        self.mixed_choice.addItems(["Include images", "Videos only"])
        self.mixed_choice.setEnabled(False)
        self.mixed_choice.currentIndexChanged.connect(self.dirty.emit)
        self.remember_mixed.toggled.connect(self.mixed_choice.setEnabled)
        mixed_layout.addRow("Default choice:", self.mixed_choice)

        layout.addWidget(mixed_group)

        layout.addStretch()

    def load_settings(self, settings: QSettings):
        """Load current values from QSettings."""
        settings.beginGroup("Video")
        self.grid_rows.setValue(settings.value("grid_rows", 4, int))
        self.grid_cols.setValue(settings.value("grid_cols", 4, int))
        self.show_timestamps.setChecked(settings.value("show_timestamps", True, bool))
        self.show_ms.setChecked(settings.value("show_ms", False, bool))
        self.show_frame_number.setChecked(settings.value("show_frame_number", False, bool))
        self.font_color.setText(settings.value("font_color", "#ffffff"))
        self.bg_color.setText(settings.value("bg_color", "#000000"))
        self.output_format.setCurrentText(settings.value("output_format", "PNG"))
        self.remember_mixed.setChecked(settings.value("remember_mixed_choice", False, bool))
        settings.endGroup()

    def save_settings(self, settings: QSettings):
        """Save current values to QSettings."""
        settings.beginGroup("Video")
        settings.setValue("grid_rows", self.grid_rows.value())
        settings.setValue("grid_cols", self.grid_cols.value())
        settings.setValue("show_timestamps", self.show_timestamps.isChecked())
        settings.setValue("show_ms", self.show_ms.isChecked())
        settings.setValue("show_frame_number", self.show_frame_number.isChecked())
        settings.setValue("font_color", self.font_color.text())
        settings.setValue("bg_color", self.bg_color.text())
        settings.setValue("output_format", self.output_format.currentText())
        settings.setValue("remember_mixed_choice", self.remember_mixed.isChecked())
        settings.endGroup()
        return True
