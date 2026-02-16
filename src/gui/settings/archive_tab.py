"""Archive Settings Widget - Manage archive format, compression, and split settings."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QCheckBox, QSpinBox, QGroupBox, QFormLayout, QSlider,
    QPushButton, QFileDialog
)
from PyQt6.QtCore import pyqtSignal, Qt, QSettings
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

        # 7z CLI warning — only needed for 7z format splits, not ZIP
        from src.utils.archive_manager import HAS_7Z_CLI
        self._7z_warning = QLabel(
            '7-Zip is required for split 7z archives. '
            '<a href="https://www.7-zip.org/download.html">Download 7-Zip</a>'
        )
        self._7z_warning.setOpenExternalLinks(True)
        self._7z_warning.setStyleSheet("color: red; font-weight: bold;")
        self._7z_warning.setVisible(False)  # Shown dynamically based on format
        split_layout.addWidget(self._7z_warning)

        browse_row = QHBoxLayout()
        self._7z_browse_label = QLabel("If 7-Zip is installed, locate it manually:")
        browse_row.addWidget(self._7z_browse_label)
        self._7z_browse_btn = QPushButton("Browse...")
        self._7z_browse_btn.setFixedWidth(80)
        self._7z_browse_btn.clicked.connect(self._browse_for_7z)
        browse_row.addWidget(self._7z_browse_btn)
        browse_row.addStretch()
        self._7z_browse_label.setVisible(False)
        self._7z_browse_btn.setVisible(False)
        split_layout.addLayout(browse_row)

        # Split size: slider + spinbox on same row
        size_row = QHBoxLayout()
        size_label = QLabel("Size of split parts:")
        size_label.setToolTip("100 MiB to 4,095 MiB (~4 GiB)")
        size_row.addWidget(size_label)

        self.split_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.split_size_slider.setRange(100, 4095)
        self.split_size_slider.setValue(500)
        self.split_size_slider.setSingleStep(100)
        self.split_size_slider.setPageStep(500)
        self.split_size_slider.setEnabled(False)
        self.split_size_slider.setToolTip("100 MiB to 4,095 MiB (~4 GiB)")
        size_row.addWidget(self.split_size_slider, 1)

        self.split_size_spinbox = QSpinBox()
        self.split_size_spinbox.setToolTip("100 MiB to 4,095 MiB (~4 GiB)")
        self.split_size_spinbox.setRange(100, 4095)
        self.split_size_spinbox.setValue(500)
        self.split_size_spinbox.setSuffix(" MiB")
        self.split_size_spinbox.setEnabled(False)
        size_row.addWidget(self.split_size_spinbox)

        # Sync slider <-> spinbox
        self.split_size_slider.valueChanged.connect(self.split_size_spinbox.setValue)
        self.split_size_spinbox.valueChanged.connect(self.split_size_slider.setValue)
        self.split_size_spinbox.valueChanged.connect(self._on_settings_changed)

        split_layout.addLayout(size_row)

        split_note = QLabel("Maximum 4,095 MiB per volume (ZIP format limit without ZIP64)")
        split_note.setStyleSheet("color: gray; font-size: 11px;")
        split_layout.addWidget(split_note)

        layout.addWidget(split_group)


        layout.addStretch()

        # Initialize format-specific UI
        self._on_format_changed()

    def _update_7z_split_warning(self):
        """Show/hide the 7z warning based on format and split state."""
        from src.utils.archive_manager import HAS_7Z_CLI
        is_7z = self.format_combo.currentData() != 'zip'
        split_on = self.split_enabled_checkbox.isChecked()
        show = is_7z and split_on and not HAS_7Z_CLI
        self._7z_warning.setVisible(show)
        self._7z_browse_label.setVisible(show)
        self._7z_browse_btn.setVisible(show)

    def _on_format_changed(self):
        """Handle format selection change."""
        format_value = self.format_combo.currentData()
        self._update_7z_split_warning()

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

    def _browse_for_7z(self):
        """Let user browse for 7z binary manually."""
        import sys
        if sys.platform == 'win32':
            filter_str = "7z executable (7z.exe 7za.exe 7zz.exe);;All files (*)"
        else:
            filter_str = "All files (*)"
        path, _ = QFileDialog.getOpenFileName(
            self, "Locate 7-Zip executable", "", filter_str
        )
        if not path:
            return
        # Save the custom path
        settings = QSettings("BBDropUploader", "BBDropGUI")
        settings.setValue("Archive/7z_path", path)
        # Update the module-level detection
        import src.utils.archive_manager as am
        am.HAS_7Z_CLI = True
        am._custom_7z_path = path
        # Enable the UI
        self.split_enabled_checkbox.setEnabled(True)
        self.split_enabled_checkbox.setToolTip(
            "Split large archives into multiple parts for easier upload/download"
        )
        if hasattr(self, '_7z_warning'):
            self._7z_warning.setText(f"7-Zip found: {path}")
            self._7z_warning.setStyleSheet("color: green; font-weight: bold;")

    def _on_split_enabled_changed(self, checked: bool):
        """Handle split enabled checkbox change."""
        self.split_size_slider.setEnabled(checked)
        self.split_size_spinbox.setEnabled(checked)
        self._update_7z_split_warning()
        self._on_settings_changed()

    def _on_settings_changed(self):
        """Emit settings changed signal and update compression info."""
        if self.sender() == self.compression_combo:
            self._update_compression_info()
        self.settings_changed.emit()

    def load_settings(self, settings: dict):
        """Load archive settings from dict."""
        # Block signals during load to avoid false dirty state
        self.blockSignals(True)

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

        self.blockSignals(False)

    def get_settings(self) -> dict:
        """Get current archive settings as dict."""
        return {
            'archive_format': self.format_combo.currentData(),
            'archive_compression': self.compression_combo.currentData(),
            'archive_split_enabled': self.split_enabled_checkbox.isChecked(),
            'archive_split_size_mb': self.split_size_spinbox.value()
        }

    def load_from_config(self):
        """Load archive settings from user defaults (INI file)."""
        from bbdrop import load_user_defaults
        settings = load_user_defaults()
        self.load_settings(settings)

    def save_to_config(self):
        """Save archive settings to INI file."""
        import os
        import configparser
        from bbdrop import get_config_path

        config = configparser.ConfigParser()
        config_file = get_config_path()

        if os.path.exists(config_file):
            config.read(config_file, encoding='utf-8')

        if not config.has_section('DEFAULTS'):
            config.add_section('DEFAULTS')

        # Get settings from widget
        archive_settings = self.get_settings()

        # Save to DEFAULTS section
        config.set('DEFAULTS', 'archive_format', archive_settings['archive_format'])
        config.set('DEFAULTS', 'archive_compression', archive_settings['archive_compression'])
        config.set('DEFAULTS', 'archive_split_enabled', str(archive_settings['archive_split_enabled']))
        config.set('DEFAULTS', 'archive_split_size_mb', str(archive_settings['archive_split_size_mb']))

        with open(config_file, 'w', encoding='utf-8') as f:
            config.write(f)

        return True
