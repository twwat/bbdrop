"""Cover Photos settings tab -- detection rules, upload host, thumbnail format."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QCheckBox,
    QComboBox, QSpinBox, QLineEdit, QFrame, QLabel,
)
from PyQt6.QtCore import pyqtSignal

from src.core.constants import (
    DEFAULT_COVER_PATTERNS,
    COVER_THUMBNAIL_FORMATS,
    DEFAULT_COVER_DIMENSION_DIFFERS_PERCENT,
    DEFAULT_COVER_MAX_PER_GALLERY,
    DEFAULT_COVER_SKIP_DUPLICATES,
    DEFAULT_COVER_THUMBNAIL_FORMAT,
)
from src.gui.widgets.info_button import InfoButton
from src.utils.logger import log


class CoversTab(QWidget):
    """Self-contained Cover Photos settings tab.

    Emits *dirty* whenever any control value changes so the orchestrator
    can track unsaved state without knowing the internals.
    """

    dirty = pyqtSignal()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._setup_ui()
        self.load_settings()

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        """Build the Cover Photos settings UI."""
        layout = QVBoxLayout(self)

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
        detection_group = QGroupBox("Auto-Detection")
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
        self.covers_filename_edit.setEnabled(False)
        filename_row.addWidget(self.covers_filename_edit)
        detection_layout.addLayout(filename_row)

        self.covers_filename_check.toggled.connect(self.covers_filename_edit.setEnabled)

        # -- By dimensions --
        self.covers_dimension_check = QCheckBox("By dimensions:")
        self.covers_dimension_check.setToolTip("Detect covers by image dimensions")
        detection_layout.addWidget(self.covers_dimension_check)

        # Dimensions sub-container
        self.covers_dim_container = QWidget()
        dim_layout = QVBoxLayout(self.covers_dim_container)
        dim_layout.setContentsMargins(20, 0, 0, 0)

        # Differs from average
        differs_row = QHBoxLayout()
        self.covers_dim_differs_check = QCheckBox("Differs from gallery average by more than")
        self.covers_dim_differs_check.setToolTip("Flag images whose dimensions differ significantly from the gallery average")
        differs_row.addWidget(self.covers_dim_differs_check)

        self.covers_dim_differs_spin = QSpinBox()
        self.covers_dim_differs_spin.setRange(5, 100)
        self.covers_dim_differs_spin.setValue(DEFAULT_COVER_DIMENSION_DIFFERS_PERCENT)
        self.covers_dim_differs_spin.setSuffix("%")
        self.covers_dim_differs_spin.setEnabled(False)
        differs_row.addWidget(self.covers_dim_differs_spin)
        differs_row.addStretch()
        dim_layout.addLayout(differs_row)

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

        # === Upload Settings group ===
        upload_group = QGroupBox("Upload Settings")
        upload_layout = QVBoxLayout(upload_group)

        # Host combo
        host_row = QHBoxLayout()
        host_row.addWidget(QLabel("Host:"))

        self.covers_host_combo = QComboBox()
        self.covers_host_combo.setToolTip("Image host to use for cover photo uploads")
        try:
            from src.core.image_host_config import get_image_host_config_manager
            manager = get_image_host_config_manager()
            for host_id in manager.list_hosts():
                host_config = manager.get_host(host_id)
                if host_config:
                    self.covers_host_combo.addItem(host_config.name, host_id)
        except Exception:
            # Fallback: add at least IMX
            self.covers_host_combo.addItem("IMX.to", "imx")
        host_row.addWidget(self.covers_host_combo)
        host_row.addStretch()
        upload_layout.addLayout(host_row)

        # Thumbnail format combo
        thumb_row = QHBoxLayout()
        thumb_row.addWidget(QLabel("Thumbnail format:"))

        self.covers_thumb_combo = QComboBox()
        self.covers_thumb_combo.setToolTip("Thumbnail format for cover photo uploads")
        for fmt_id, fmt_label in COVER_THUMBNAIL_FORMATS.items():
            self.covers_thumb_combo.addItem(fmt_label, fmt_id)
        # Set default to Proportional (id=2)
        default_idx = self.covers_thumb_combo.findData(DEFAULT_COVER_THUMBNAIL_FORMAT)
        if default_idx >= 0:
            self.covers_thumb_combo.setCurrentIndex(default_idx)
        thumb_row.addWidget(self.covers_thumb_combo)
        thumb_row.addStretch()
        upload_layout.addLayout(thumb_row)

        # Cover gallery name
        gallery_row = QHBoxLayout()
        gallery_row.addWidget(QLabel("Cover gallery:"))

        self.covers_gallery_edit = QLineEdit()
        self.covers_gallery_edit.setPlaceholderText("Optional gallery name for cover uploads")
        self.covers_gallery_edit.setToolTip(
            "If set, cover photos are uploaded to this specific gallery.\n"
            "Leave empty to use the same gallery as the main upload."
        )
        gallery_row.addWidget(self.covers_gallery_edit)
        upload_layout.addLayout(gallery_row)

        # Also upload as gallery image
        self.covers_also_upload_check = QCheckBox("Also upload cover as gallery image")
        self.covers_also_upload_check.setToolTip(
            "When checked, the cover file is uploaded both as a cover photo\n"
            "AND as a normal gallery image. When unchecked, it only goes\n"
            "through the cover endpoint."
        )
        upload_layout.addWidget(self.covers_also_upload_check)

        container_layout.addWidget(upload_group)
        container_layout.addStretch()

        layout.addWidget(self.covers_container)

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
        self.covers_host_combo.currentIndexChanged.connect(dirty)
        self.covers_thumb_combo.currentIndexChanged.connect(dirty)
        self.covers_gallery_edit.textChanged.connect(dirty)
        self.covers_also_upload_check.toggled.connect(dirty)

    # ------------------------------------------------------------------
    # Load / Save / Reload
    # ------------------------------------------------------------------

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
                self.covers_host_combo, self.covers_thumb_combo,
                self.covers_gallery_edit, self.covers_also_upload_check,
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

            # Upload settings
            host_id = self.settings.value('cover/host_id', 'imx', type=str)
            host_idx = self.covers_host_combo.findData(host_id)
            if host_idx >= 0:
                self.covers_host_combo.setCurrentIndex(host_idx)

            thumb_fmt = self.settings.value('cover/thumbnail_format', DEFAULT_COVER_THUMBNAIL_FORMAT, type=int)
            thumb_idx = self.covers_thumb_combo.findData(thumb_fmt)
            if thumb_idx >= 0:
                self.covers_thumb_combo.setCurrentIndex(thumb_idx)

            self.covers_gallery_edit.setText(
                self.settings.value('cover/gallery', '', type=str)
            )
            self.covers_also_upload_check.setChecked(
                self.settings.value('cover/also_upload_as_gallery', False, type=bool)
            )

            # Unblock signals
            for control in controls_to_block:
                control.blockSignals(False)

            # Apply dimmed visual state
            self._update_covers_ui_state(enabled)

        except Exception as e:
            log(f"Failed to load covers settings: {e}", level="warning", category="settings")

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
            self.settings.setValue('cover/host_id', self.covers_host_combo.currentData())
            self.settings.setValue('cover/thumbnail_format', self.covers_thumb_combo.currentData())
            self.settings.setValue('cover/gallery', self.covers_gallery_edit.text())
            self.settings.setValue('cover/also_upload_as_gallery', self.covers_also_upload_check.isChecked())
            return True
        except Exception as e:
            log(f"Failed to save covers settings: {e}", level="warning", category="settings")
            return False

    def reload_settings(self):
        """Reload Covers tab form values from saved settings."""
        self.load_settings()

    def reset_to_defaults(self):
        """Reset all controls to their default values."""
        self.load_settings()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _update_covers_ui_state(self, enabled=None):
        """Enable/disable and dim/undim covers container based on master checkbox."""
        if enabled is None:
            enabled = self.covers_enabled_check.isChecked()
        self.covers_container.setEnabled(enabled)

        dimmed_class = "" if enabled else "dimmed"
        for widget in [self.covers_container] + self.covers_container.findChildren(QWidget):
            widget.setProperty("class", dimmed_class)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()
