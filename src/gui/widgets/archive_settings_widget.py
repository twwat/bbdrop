"""Archive Settings Widget - Manage archive format, compression, and split settings."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QCheckBox, QSpinBox, QGroupBox, QFormLayout
)
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont
import logging

logger = logging.getLogger(__name__)


class ArchiveSettingsWidget(QWidget):
    """Widget for configuring archive creation settings."""

    settings_changed = pyqtSignal()

    # Compression options per format
    ZIP_COMPRESSION_OPTIONS = {
        'Store (no compression)': 'store',
        'Deflate (standard)': 'deflate',
        'LZMA (best compression)': 'lzma',
        'BZip2': 'bzip2'
    }

    SEVENZ_COMPRESSION_OPTIONS = {
        'Copy (no compression)': 'copy',
        'LZMA2 (best compression)': 'lzma2',
        'LZMA': 'lzma',
        'Deflate': 'deflate',
        'BZip2': 'bzip2'
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        """Setup the archive settings UI."""
        layout = QVBoxLayout(self)

        # Description
        info_label = QLabel(
            "These settings control how gallery folders are archived before uploading to file hosts.<br><br>"
            "<b>Format:</b> ZIP is widely compatible; 7Z offers better compression.<br>"
            "<b>Compression:</b> Higher compression = smaller files but slower creation.<br>"
            "<b>Split:</b> Break large archives into parts using pure Python libraries."
        )
        info_label.setWordWrap(True)
        info_label.setProperty("class", "tab-description")
        layout.addWidget(info_label)

        # Format Selection Group
        format_group = QGroupBox("Archive Format")
        format_layout = QFormLayout(format_group)

        # Format ComboBox
        self.format_combo = QComboBox()
        self.format_combo.setToolTip("Archive format: ZIP (universal) or 7Z (better compression)")
        self.format_combo.addItem("ZIP", "zip")
        self.format_combo.addItem("7-Zip (7Z)", "7z")
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        format_layout.addRow("Format:", self.format_combo)

        # Info label for format
        self.format_info_label = QLabel()
        self.format_info_label.setWordWrap(True)
        font = QFont()
        font.setPointSize(font.pointSize() - 1)
        self.format_info_label.setFont(font)
        self.format_info_label.setStyleSheet("color: #666;")
        format_layout.addRow("", self.format_info_label)

        layout.addWidget(format_group)

        # Compression Group
        compression_group = QGroupBox("Compression")
        compression_layout = QFormLayout(compression_group)

        # Compression ComboBox (dynamic based on format)
        self.compression_combo = QComboBox()
        self.compression_combo.setToolTip("Compression method and level")
        self.compression_combo.currentIndexChanged.connect(self._on_settings_changed)
        compression_layout.addRow("Method:", self.compression_combo)

        # Info label for compression
        self.compression_info_label = QLabel()
        self.compression_info_label.setWordWrap(True)
        self.compression_info_label.setFont(font)
        self.compression_info_label.setStyleSheet("color: #666;")
        compression_layout.addRow("", self.compression_info_label)

        layout.addWidget(compression_group)

        # Split Archives Group
        split_group = QGroupBox("Split Archives")
        split_layout = QVBoxLayout(split_group)

        # Enable split checkbox
        self.split_enabled_checkbox = QCheckBox("Enable split archives")
        self.split_enabled_checkbox.setToolTip(
            "Split large archives into multiple parts for easier upload/download"
        )
        self.split_enabled_checkbox.toggled.connect(self._on_split_enabled_changed)
        split_layout.addWidget(self.split_enabled_checkbox)

        # Split size spinbox
        size_layout = QFormLayout()
        self.split_size_spinbox = QSpinBox()
        self.split_size_spinbox.setToolTip("Maximum size per archive part in MB")
        self.split_size_spinbox.setRange(100, 10240)  # 100MB to 10GB
        self.split_size_spinbox.setValue(500)
        self.split_size_spinbox.setSuffix(" MB")
        self.split_size_spinbox.setEnabled(False)
        self.split_size_spinbox.valueChanged.connect(self._on_settings_changed)
        size_layout.addRow("Part size:", self.split_size_spinbox)
        split_layout.addLayout(size_layout)

        layout.addWidget(split_group)


        layout.addStretch()

        # Initialize format-specific UI
        self._on_format_changed()

    def _on_format_changed(self):
        """Handle format selection change."""
        format_value = self.format_combo.currentData()

        # Update compression options based on format
        self.compression_combo.blockSignals(True)
        self.compression_combo.clear()

        if format_value == 'zip':
            for display, value in self.ZIP_COMPRESSION_OPTIONS.items():
                self.compression_combo.addItem(display, value)
            self.format_info_label.setText(
                "ZIP format is universally supported and works on all platforms."
            )
        else:  # 7z
            for display, value in self.SEVENZ_COMPRESSION_OPTIONS.items():
                self.compression_combo.addItem(display, value)
            self.format_info_label.setText(
                "7-Zip format provides better compression ratios than ZIP."
            )

        self.compression_combo.blockSignals(False)
        self._update_compression_info()
        self._on_settings_changed()

    def _update_compression_info(self):
        """Update compression method info label."""
        compression_value = self.compression_combo.currentData()

        info_texts = {
            'store': 'No compression - fastest but largest file size.',
            'copy': 'No compression - fastest but largest file size.',
            'deflate': 'Standard compression - good balance of speed and size.',
            'lzma': 'High compression - slower but smaller files.',
            'lzma2': 'Best compression - slowest but smallest files.',
            'bzip2': 'Good compression - moderate speed and size.'
        }

        self.compression_info_label.setText(
            info_texts.get(compression_value, '')
        )

    def _on_split_enabled_changed(self, checked: bool):
        """Handle split enabled checkbox change."""
        self.split_size_spinbox.setEnabled(checked)
        self._on_settings_changed()

    def _on_settings_changed(self):
        """Emit settings changed signal and update compression info."""
        if self.sender() == self.compression_combo:
            self._update_compression_info()
        self.settings_changed.emit()

    def load_settings(self, settings: dict):
        """Load archive settings from dict."""
        # Load format
        archive_format = settings.get('archive_format', 'zip')
        for i in range(self.format_combo.count()):
            if self.format_combo.itemData(i) == archive_format:
                self.format_combo.setCurrentIndex(i)
                break

        # Load compression (after format is set, since options are format-dependent)
        archive_compression = settings.get('archive_compression', 'store')
        for i in range(self.compression_combo.count()):
            if self.compression_combo.itemData(i) == archive_compression:
                self.compression_combo.setCurrentIndex(i)
                break

        # Load split settings
        split_enabled = settings.get('archive_split_enabled', False)
        self.split_enabled_checkbox.setChecked(split_enabled)

        split_size_mb = settings.get('archive_split_size_mb', 500)
        self.split_size_spinbox.setValue(split_size_mb)

    def get_settings(self) -> dict:
        """Get current archive settings as dict."""
        return {
            'archive_format': self.format_combo.currentData(),
            'archive_compression': self.compression_combo.currentData(),
            'archive_split_enabled': self.split_enabled_checkbox.isChecked(),
            'archive_split_size_mb': self.split_size_spinbox.value()
        }
