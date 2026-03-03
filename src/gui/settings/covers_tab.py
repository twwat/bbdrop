"""Cover Photos settings tab -- detection rules, upload host, thumbnail format."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QCheckBox,
    QComboBox, QSpinBox, QLineEdit, QFrame, QLabel, QPushButton,
    QRadioButton
)
from PyQt6.QtCore import pyqtSignal, Qt
from typing import Optional

from src.core.constants import (
    DEFAULT_COVER_PATTERNS,
    DEFAULT_COVER_MAX_PER_GALLERY,
    DEFAULT_COVER_SKIP_DUPLICATES,
    DEFAULT_COVER_THUMBNAIL_FORMAT,
    DEFAULT_COVER_DIMENSION_DIFFERS_PERCENT,
    COVER_THUMBNAIL_FORMATS,
)
from src.gui.widgets.info_button import InfoButton


class CoversTab(QWidget):
    """Settings tab for cover photo detection rules and logic."""
    dirty = pyqtSignal()
    cover_gallery_changed = pyqtSignal(str, str)  # host_id, gallery_id

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        """Build the Cover Photos settings UI."""
        layout = QVBoxLayout(self)

        # Tab description
        description = QLabel(
            "Cover photos are used as special thumbnails in BBCode generation and gallery previews. "
            "You can configure how covers are automatically detected from your folders and how they are handled."
        )
        description.setWordWrap(True)
        description.setProperty("class", "tab-description")
        layout.addWidget(description)

        # Master enable checkbox
        self.covers_enabled_check = QCheckBox("Enable cover photos")
        self.covers_enabled_check.setToolTip(
            "When enabled, cover images are detected and uploaded separately\n"
            "with a dedicated thumbnail format and optional cover gallery."
        )
        layout.addWidget(self.covers_enabled_check)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)

        # Container widget that gets disabled when master checkbox is unchecked
        self.covers_container = QWidget()
        container_layout = QVBoxLayout(self.covers_container)
        container_layout.setContentsMargins(0, 0, 0, 0)

        # === Auto-Detection group ===
        detection_group = QGroupBox("Auto-Detection Rules")
        detection_layout = QVBoxLayout(detection_group)

        # -- By filename --
        filename_row = QHBoxLayout()
        self.covers_filename_check = QCheckBox("By filename:")
        self.covers_filename_check.setToolTip("Detect covers by matching filename patterns")
        filename_row.addWidget(self.covers_filename_check)

        filename_row.addWidget(InfoButton(
            "<b>Patterns use shell-style wildcards (not regex).</b><br><br>"
            "<table cellpadding='2'>"
            "<tr><td><code>*</code></td><td>matches anything "
            "(e.g. <code>cover.*</code> → cover.jpg, cover.png)</td></tr>"
            "<tr><td><code>?</code></td><td>matches exactly one character</td></tr>"
            "<tr><td><code>[abc]</code></td><td>matches any character in the brackets</td></tr>"
            "</table><br>"
            "Separate multiple patterns with commas.<br>"
            "Matching is case-insensitive. First match wins.<br><br>"
            "<b>Examples:</b><br>"
            "<table cellpadding='2'>"
            "<tr><td><code>cover.*</code></td><td>any file named \"cover\" with any extension</td></tr>"
            "<tr><td><code>cover_*</code></td><td>cover_01.jpg, cover_front.png, etc.</td></tr>"
            "<tr><td><code>*_cover.*</code></td><td>gallery_cover.jpg, my_cover.png</td></tr>"
            "<tr><td><code>poster.*</code></td><td>poster.jpg, poster.png</td></tr>"
            "<tr><td><code>folder?.jpg</code></td><td>folder1.jpg, folder2.jpg (not folder10.jpg)</td></tr>"
            "</table>"
        ))

        self.covers_filename_edit = QLineEdit()
        self.covers_filename_edit.setPlaceholderText("cover.*, poster.*, *_cover.*")
        self.covers_filename_edit.setToolTip("Comma-separated filename patterns")
        filename_row.addWidget(self.covers_filename_edit)
        detection_layout.addLayout(filename_row)

        self.covers_filename_check.toggled.connect(self.covers_filename_edit.setEnabled)

        # -- By dimensions --
        self.covers_dimension_check = QCheckBox("By dimensions:")
        self.covers_dimension_check.setToolTip("Detect covers by comparing image dimensions")
        detection_layout.addWidget(self.covers_dimension_check)

        # Dimensions sub-container
        self.covers_dim_container = QWidget()
        dim_layout = QVBoxLayout(self.covers_dim_container)
        dim_layout.setContentsMargins(20, 0, 0, 0)

        # Differs from average
        diff_row = QHBoxLayout()
        self.covers_dim_differs_check = QCheckBox("Differs from average by at least:")
        self.covers_dim_differs_check.setToolTip(
            "Detect cover if dimensions differ significantly from the gallery average.\n"
            "Often used for posters/covers that are much larger/smaller than gallery images."
        )
        diff_row.addWidget(self.covers_dim_differs_check)

        self.covers_dim_differs_spin = QSpinBox()
        self.covers_dim_differs_spin.setRange(5, 95)
        self.covers_dim_differs_spin.setValue(DEFAULT_COVER_DIMENSION_DIFFERS_PERCENT)
        self.covers_dim_differs_spin.setSuffix("%")
        self.covers_dim_differs_spin.setEnabled(False)
        diff_row.addWidget(self.covers_dim_differs_spin)
        diff_row.addStretch()
        dim_layout.addLayout(diff_row)

        self.covers_dim_differs_check.toggled.connect(self.covers_dim_differs_spin.setEnabled)

        # Min shortest side
        min_row = QHBoxLayout()
        self.covers_dim_min_check = QCheckBox("Minimum (on shortest side):")
        self.covers_dim_min_check.setToolTip("Only consider images whose shortest side is at least this many pixels")
        min_row.addWidget(self.covers_dim_min_check)

        self.covers_dim_min_spin = QSpinBox()
        self.covers_dim_min_spin.setRange(0, 99999)
        self.covers_dim_min_spin.setValue(0)
        self.covers_dim_min_spin.setSuffix(" px")
        self.covers_dim_min_spin.setEnabled(False)
        min_row.addWidget(self.covers_dim_min_spin)
        min_row.addStretch()
        dim_layout.addLayout(min_row)

        self.covers_dim_min_check.toggled.connect(self.covers_dim_min_spin.setEnabled)

        # Max longest side
        max_row = QHBoxLayout()
        self.covers_dim_max_check = QCheckBox("Maximum (on longest side):")
        self.covers_dim_max_check.setToolTip("Only consider images whose longest side is no more than this many pixels")
        max_row.addWidget(self.covers_dim_max_check)

        self.covers_dim_max_spin = QSpinBox()
        self.covers_dim_max_spin.setRange(0, 99999)
        self.covers_dim_max_spin.setValue(0)
        self.covers_dim_max_spin.setSuffix(" px")
        self.covers_dim_max_spin.setEnabled(False)
        max_row.addWidget(self.covers_dim_max_spin)
        max_row.addStretch()
        dim_layout.addLayout(max_row)

        self.covers_dim_max_check.toggled.connect(self.covers_dim_max_spin.setEnabled)

        self.covers_dim_container.setEnabled(False)
        detection_layout.addWidget(self.covers_dim_container)

        self.covers_dimension_check.toggled.connect(self.covers_dim_container.setEnabled)

        # -- By file size --
        self.covers_filesize_check = QCheckBox("By file size:")
        self.covers_filesize_check.setToolTip("Detect covers by file size thresholds")
        detection_layout.addWidget(self.covers_filesize_check)

        # File size sub-container
        self.covers_filesize_container = QWidget()
        fs_layout = QVBoxLayout(self.covers_filesize_container)
        fs_layout.setContentsMargins(20, 0, 0, 0)

        # Min file size
        fs_min_row = QHBoxLayout()
        self.covers_fs_min_check = QCheckBox("Minimum:")
        self.covers_fs_min_check.setToolTip("Only consider files at least this large as covers")
        fs_min_row.addWidget(self.covers_fs_min_check)

        self.covers_fs_min_spin = QSpinBox()
        self.covers_fs_min_spin.setRange(0, 999999)
        self.covers_fs_min_spin.setValue(0)
        self.covers_fs_min_spin.setSuffix(" KB")
        self.covers_fs_min_spin.setEnabled(False)
        fs_min_row.addWidget(self.covers_fs_min_spin)
        fs_min_row.addStretch()
        fs_layout.addLayout(fs_min_row)

        self.covers_fs_min_check.toggled.connect(self.covers_fs_min_spin.setEnabled)

        # Max file size
        fs_max_row = QHBoxLayout()
        self.covers_fs_max_check = QCheckBox("Maximum:")
        self.covers_fs_max_check.setToolTip("Only consider files no larger than this as covers")
        fs_max_row.addWidget(self.covers_fs_max_check)

        self.covers_fs_max_spin = QSpinBox()
        self.covers_fs_max_spin.setRange(0, 999999)
        self.covers_fs_max_spin.setValue(0)
        self.covers_fs_max_spin.setSuffix(" KB")
        self.covers_fs_max_spin.setEnabled(False)
        fs_max_row.addWidget(self.covers_fs_max_spin)
        fs_max_row.addStretch()
        fs_layout.addLayout(fs_max_row)

        self.covers_fs_max_check.toggled.connect(self.covers_fs_max_spin.setEnabled)

        self.covers_filesize_container.setEnabled(False)
        detection_layout.addWidget(self.covers_filesize_container)

        self.covers_filesize_check.toggled.connect(self.covers_filesize_container.setEnabled)

        # -- Max covers per gallery --
        max_covers_row = QHBoxLayout()
        max_covers_row.addWidget(QLabel("Max covers per gallery:"))

        self.covers_max_spin = QSpinBox()
        self.covers_max_spin.setRange(0, 99)
        self.covers_max_spin.setValue(DEFAULT_COVER_MAX_PER_GALLERY)
        self.covers_max_spin.setSpecialValueText("Unlimited")
        self.covers_max_spin.setToolTip("Maximum number of cover images per gallery (0 = unlimited)")
        max_covers_row.addWidget(self.covers_max_spin)
        max_covers_row.addStretch()
        detection_layout.addLayout(max_covers_row)

        # -- Skip duplicate covers --
        self.covers_skip_duplicates_check = QCheckBox("Skip duplicate covers")
        self.covers_skip_duplicates_check.setToolTip(
            "Skip cover candidates that are byte-identical duplicates of another cover"
        )
        detection_layout.addWidget(self.covers_skip_duplicates_check)

        container_layout.addWidget(detection_group)

        # === Detection Logic group ===
        logic_group = QGroupBox("Detection Logic")
        logic_layout = QVBoxLayout(logic_group)
        
        self.logic_any_radio = QRadioButton("Match ANY rule (OR) - Additive")
        self.logic_any_radio.setToolTip("File is a cover if it matches ANY enabled rule (Filename OR Dimensions OR Size)")
        
        self.logic_all_radio = QRadioButton("Match ALL rules (AND) - Restrictive")
        self.logic_all_radio.setToolTip("File is a cover ONLY if it matches ALL enabled rules (Filename AND Dimensions AND Size)")
        
        logic_layout.addWidget(self.logic_any_radio)
        logic_layout.addWidget(self.logic_all_radio)
        
        # Also upload as gallery image
        self.covers_also_upload_check = QCheckBox("Also upload cover as gallery image")
        self.covers_also_upload_check.setToolTip(
            "When checked, the cover file is uploaded both as a cover photo\n"
            "AND as a normal gallery image. When unchecked, it only goes\n"
            "to the cover host/gallery and is excluded from the main gallery."
        )
        self.covers_also_upload_check.toggled.connect(self._on_settings_changed)
        logic_layout.addWidget(self.covers_also_upload_check)

        current_logic = self.settings.value('cover/rule_logic', 'any', type=str)
        if current_logic == 'all':
            self.logic_all_radio.setChecked(True)
        else:
            self.logic_any_radio.setChecked(True)
            
        self.logic_any_radio.toggled.connect(self._on_settings_changed)
        self.logic_all_radio.toggled.connect(self._on_settings_changed)
        
        container_layout.addWidget(logic_group)
        container_layout.addStretch()

        layout.addWidget(self.covers_container)
        layout.addStretch()

        # Master checkbox enables/disables the entire container
        self.covers_enabled_check.toggled.connect(self._update_covers_ui_state)

        # Connect ALL controls to dirty signal
        dirty = self.dirty.emit
        self.covers_enabled_check.toggled.connect(dirty)
        self.covers_filename_check.toggled.connect(dirty)
        self.covers_filename_edit.textChanged.connect(dirty)
        self.covers_dimension_check.toggled.connect(dirty)
        self.covers_dim_differs_check.toggled.connect(dirty)
        self.covers_dim_differs_spin.valueChanged.connect(dirty)
        self.covers_dim_min_check.toggled.connect(dirty)
        self.covers_dim_min_spin.valueChanged.connect(dirty)
        self.covers_dim_max_check.toggled.connect(dirty)
        self.covers_dim_max_spin.valueChanged.connect(dirty)
        self.covers_filesize_check.toggled.connect(dirty)
        self.covers_fs_min_check.toggled.connect(dirty)
        self.covers_fs_min_spin.valueChanged.connect(dirty)
        self.covers_fs_max_check.toggled.connect(dirty)
        self.covers_fs_max_spin.valueChanged.connect(dirty)
        self.covers_max_spin.valueChanged.connect(dirty)
        self.covers_skip_duplicates_check.toggled.connect(dirty)
        self.covers_also_upload_check.toggled.connect(dirty)

    def load_settings(self):
        """Load cover settings from QSettings."""
        try:
            # Block ALL signals during loading to prevent marking tab as dirty
            controls_to_block = [
                self.covers_enabled_check,
                self.covers_filename_check, self.covers_filename_edit,
                self.covers_dimension_check,
                self.covers_dim_differs_check, self.covers_dim_differs_spin,
                self.covers_dim_min_check, self.covers_dim_min_spin,
                self.covers_dim_max_check, self.covers_dim_max_spin,
                self.covers_filesize_check,
                self.covers_fs_min_check, self.covers_fs_min_spin,
                self.covers_fs_max_check, self.covers_fs_max_spin,
                self.covers_max_spin, self.covers_skip_duplicates_check,
                self.covers_also_upload_check,
            ]
            for control in controls_to_block:
                control.blockSignals(True)

            # Master enable
            enabled = self.settings.value('cover/enabled', False, type=bool)
            self.covers_enabled_check.setChecked(enabled)
            self.covers_container.setEnabled(enabled)

            # Filename detection
            filename_enabled = self.settings.value('cover/filename_enabled', True, type=bool)
            self.covers_filename_check.setChecked(filename_enabled)
            self.covers_filename_edit.setEnabled(filename_enabled)
            self.covers_filename_edit.setText(
                self.settings.value('cover/filename_patterns', DEFAULT_COVER_PATTERNS, type=str)
            )

            # Dimension detection
            dim_enabled = self.settings.value('cover/dimension_enabled', False, type=bool)
            self.covers_dimension_check.setChecked(dim_enabled)
            self.covers_dim_container.setEnabled(dim_enabled)

            dim_differs = self.settings.value('cover/dimension_differs_enabled', False, type=bool)
            self.covers_dim_differs_check.setChecked(dim_differs)
            self.covers_dim_differs_spin.setEnabled(dim_differs)
            self.covers_dim_differs_spin.setValue(
                self.settings.value('cover/dimension_differs_percent', DEFAULT_COVER_DIMENSION_DIFFERS_PERCENT, type=int)
            )

            dim_min = self.settings.value('cover/dimension_min_enabled', False, type=bool)
            self.covers_dim_min_check.setChecked(dim_min)
            self.covers_dim_min_spin.setEnabled(dim_min)
            self.covers_dim_min_spin.setValue(
                self.settings.value('cover/dimension_min_shortest_side', 0, type=int)
            )

            dim_max = self.settings.value('cover/dimension_max_enabled', False, type=bool)
            self.covers_dim_max_check.setChecked(dim_max)
            self.covers_dim_max_spin.setEnabled(dim_max)
            self.covers_dim_max_spin.setValue(
                self.settings.value('cover/dimension_max_longest_side', 0, type=int)
            )

            # File size detection
            fs_enabled = self.settings.value('cover/filesize_enabled', False, type=bool)
            self.covers_filesize_check.setChecked(fs_enabled)
            self.covers_filesize_container.setEnabled(fs_enabled)

            fs_min = self.settings.value('cover/filesize_min_enabled', False, type=bool)
            self.covers_fs_min_check.setChecked(fs_min)
            self.covers_fs_min_spin.setEnabled(fs_min)
            self.covers_fs_min_spin.setValue(
                self.settings.value('cover/filesize_min_kb', 0, type=int)
            )

            fs_max = self.settings.value('cover/filesize_max_enabled', False, type=bool)
            self.covers_fs_max_check.setChecked(fs_max)
            self.covers_fs_max_spin.setEnabled(fs_max)
            self.covers_fs_max_spin.setValue(
                self.settings.value('cover/filesize_max_kb', 0, type=int)
            )

            # Max covers and skip duplicates
            self.covers_max_spin.setValue(
                self.settings.value('cover/max_per_gallery', DEFAULT_COVER_MAX_PER_GALLERY, type=int)
            )
            self.covers_skip_duplicates_check.setChecked(
                self.settings.value('cover/skip_duplicates', DEFAULT_COVER_SKIP_DUPLICATES, type=bool)
            )

            # Detection logic
            current_logic = self.settings.value('cover/rule_logic', 'any', type=str)
            if current_logic == 'all':
                self.logic_all_radio.setChecked(True)
            else:
                self.logic_any_radio.setChecked(True)

            self.covers_also_upload_check.setChecked(
                self.settings.value('cover/also_upload_as_gallery', False, type=bool)
            )

            # Unblock signals
            for control in controls_to_block:
                control.blockSignals(False)

        except Exception:
            pass

    def save_settings(self):
        """Save cover settings to QSettings."""
        try:
            self.settings.setValue('cover/enabled', self.covers_enabled_check.isChecked())
            self.settings.setValue('cover/filename_enabled', self.covers_filename_check.isChecked())
            self.settings.setValue('cover/filename_patterns', self.covers_filename_edit.text())
            self.settings.setValue('cover/dimension_enabled', self.covers_dimension_check.isChecked())
            self.settings.setValue('cover/dimension_differs_enabled', self.covers_dim_differs_check.isChecked())
            self.settings.setValue('cover/dimension_differs_percent', self.covers_dim_differs_spin.value())
            self.settings.setValue('cover/dimension_min_enabled', self.covers_dim_min_check.isChecked())
            self.settings.setValue('cover/dimension_min_shortest_side', self.covers_dim_min_spin.value())
            self.settings.setValue('cover/dimension_max_enabled', self.covers_dim_max_check.isChecked())
            self.settings.setValue('cover/dimension_max_longest_side', self.covers_dim_max_spin.value())
            self.settings.setValue('cover/filesize_enabled', self.covers_filesize_check.isChecked())
            self.settings.setValue('cover/filesize_min_enabled', self.covers_fs_min_check.isChecked())
            self.settings.setValue('cover/filesize_min_kb', self.covers_fs_min_spin.value())
            self.settings.setValue('cover/filesize_max_enabled', self.covers_fs_max_check.isChecked())
            self.settings.setValue('cover/filesize_max_kb', self.covers_fs_max_spin.value())
            self.settings.setValue('cover/max_per_gallery', self.covers_max_spin.value())
            self.settings.setValue('cover/skip_duplicates', self.covers_skip_duplicates_check.isChecked())
            
            # Save detection logic
            logic = 'all' if self.logic_all_radio.isChecked() else 'any'
            self.settings.setValue('cover/rule_logic', logic)

            self.settings.setValue('cover/also_upload_as_gallery', self.covers_also_upload_check.isChecked())

            return True
        except Exception:
            return False

    def on_external_cover_host_change(self, host_id: str):
        """No longer used in this tab as host selector is removed."""
        pass

    def on_external_cover_gallery_change(self, host_id: str, gallery_id: str):
        """No longer used in this tab as gallery ID is removed."""
        pass

    def _on_settings_changed(self):
        """Emit dirty signal when any setting changes."""
        self.dirty.emit()

    def _update_covers_ui_state(self, enabled):
        """Update the enabled/disabled state of cover detection UI container."""
        self.covers_container.setEnabled(enabled)
