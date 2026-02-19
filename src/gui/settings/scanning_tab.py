"""Image Scanning settings tab -- sampling, exclusions, and statistics."""

import os
import configparser

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QCheckBox,
    QRadioButton, QSpinBox, QLineEdit, QFrame, QLabel, QButtonGroup,
)
from PyQt6.QtCore import pyqtSignal

from bbdrop import get_config_path
from src.gui.widgets.info_button import InfoButton
from src.utils.logger import log


class ScanningTab(QWidget):
    """Self-contained Image Scanning settings tab.

    Emits *dirty* whenever any control value changes so the orchestrator
    can track unsaved state without knowing the internals.
    """

    dirty = pyqtSignal()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Info label
        info_label = QLabel(
            "Configure image scanning behavior for performance optimization."
        )
        info_label.setWordWrap(True)
        info_label.setProperty("class", "tab-description")
        info_label.setMaximumHeight(40)
        from PyQt6.QtWidgets import QSizePolicy
        info_label.setSizePolicy(
            info_label.sizePolicy().horizontalPolicy(),
            QSizePolicy.Policy.Fixed,
        )
        layout.addWidget(info_label)

        # --- Scanning Strategy group ---
        strategy_group = QGroupBox("Scanning Strategy")
        strategy_layout = QVBoxLayout(strategy_group)

        # Fast scanning with imghdr
        self.fast_scan_check = QCheckBox("Use fast corruption checking (imghdr)")
        self.fast_scan_check.setToolTip("Use fast imghdr-based corruption detection")
        self.fast_scan_check.setChecked(True)
        strategy_layout.addWidget(self.fast_scan_check)

        # Separator line
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        strategy_layout.addWidget(separator)

        # PIL Sampling Section
        sampling_row = QHBoxLayout()
        sampling_label = QLabel("<b>Dimension Calculation Sampling</b>")
        sampling_row.addWidget(sampling_label)
        sampling_row.addWidget(InfoButton(
            "Opening every image to read its pixel dimensions is slow "
            "(requires decoding the image header with PIL). Sampling checks "
            "a subset and estimates the gallery's typical dimensions from that.<br><br>"
            "For most galleries where images are similar sizes, a small sample "
            "gives accurate results much faster."
        ))
        sampling_row.addStretch()
        strategy_layout.addLayout(sampling_row)

        # Sampling Method
        method_layout = QHBoxLayout()
        method_label = QLabel("Method:")
        method_layout.addWidget(method_label)

        self.sampling_fixed_radio = QRadioButton("Fixed count")
        self.sampling_fixed_radio.setToolTip("Sample a fixed number of images")
        self.sampling_fixed_radio.setProperty("class", "scanning-radio")
        self.sampling_fixed_radio.setChecked(True)
        method_layout.addWidget(self.sampling_fixed_radio)

        self.sampling_fixed_spin = QSpinBox()
        self.sampling_fixed_spin.setToolTip("Number of images to sample")
        self.sampling_fixed_spin.setRange(1, 100)
        self.sampling_fixed_spin.setValue(25)
        self.sampling_fixed_spin.setSuffix(" images")
        method_layout.addWidget(self.sampling_fixed_spin)

        self.sampling_percent_radio = QRadioButton("Percentage")
        self.sampling_percent_radio.setToolTip("Sample a percentage of images")
        self.sampling_percent_radio.setProperty("class", "scanning-radio")
        method_layout.addWidget(self.sampling_percent_radio)

        self.sampling_percent_spin = QSpinBox()
        self.sampling_percent_spin.setToolTip("Percentage of images to sample")
        self.sampling_percent_spin.setRange(1, 100)
        self.sampling_percent_spin.setValue(10)
        self.sampling_percent_spin.setSuffix("%")
        self.sampling_percent_spin.setEnabled(False)
        method_layout.addWidget(self.sampling_percent_spin)

        method_layout.addStretch()
        strategy_layout.addLayout(method_layout)

        # Create button group for sampling method (Fixed vs Percentage)
        self.sampling_method_group = QButtonGroup(self)
        self.sampling_method_group.addButton(self.sampling_fixed_radio)
        self.sampling_method_group.addButton(self.sampling_percent_radio)

        # Connect radio buttons to enable/disable spinboxes
        self.sampling_fixed_radio.toggled.connect(
            lambda checked: self.sampling_fixed_spin.setEnabled(checked)
        )
        self.sampling_fixed_radio.toggled.connect(
            lambda checked: self.sampling_percent_spin.setEnabled(not checked)
        )

        # Exclusions Section
        exclusions_label = QLabel(
            "<b>Exclusions</b> (skip these images from sampling)"
        )
        exclusions_label.setStyleSheet("margin-top: 10px;")
        strategy_layout.addWidget(exclusions_label)

        # Exclude first/last checkboxes
        position_layout = QHBoxLayout()
        self.exclude_first_check = QCheckBox("Skip first image")
        self.exclude_first_check.setToolTip("Often cover/poster image")
        position_layout.addWidget(self.exclude_first_check)

        self.exclude_last_check = QCheckBox("Skip last image")
        self.exclude_last_check.setToolTip("Often credits/logo image")
        position_layout.addWidget(self.exclude_last_check)
        position_layout.addWidget(InfoButton(
            "Many galleries follow a pattern: the first image is a cover or "
            "poster (different dimensions than the content), and the last "
            "image is a credits or watermark page.<br><br>"
            "Excluding these from dimension sampling gives a more accurate "
            "average for the actual content images."
        ))
        position_layout.addStretch()
        strategy_layout.addLayout(position_layout)

        # Exclude small images
        small_layout = QHBoxLayout()
        self.exclude_small_check = QCheckBox("Skip images smaller than")
        self.exclude_small_check.setToolTip(
            "Exclude images below a size threshold"
        )
        small_layout.addWidget(self.exclude_small_check)

        self.exclude_small_spin = QSpinBox()
        self.exclude_small_spin.setToolTip(
            "Size threshold as percentage of largest image"
        )
        self.exclude_small_spin.setRange(10, 90)
        self.exclude_small_spin.setValue(50)
        self.exclude_small_spin.setSuffix("% of largest")
        self.exclude_small_spin.setEnabled(False)
        small_layout.addWidget(self.exclude_small_spin)

        small_layout.addWidget(QLabel("(thumbnails, previews)"))
        small_layout.addStretch()
        strategy_layout.addLayout(small_layout)

        self.exclude_small_check.toggled.connect(
            self.exclude_small_spin.setEnabled
        )

        # Exclude filename patterns
        pattern_layout = QVBoxLayout()
        pattern_h_layout = QHBoxLayout()
        self.exclude_patterns_check = QCheckBox("Skip filenames matching:")
        self.exclude_patterns_check.setToolTip(
            "Exclude images matching filename patterns"
        )
        pattern_h_layout.addWidget(self.exclude_patterns_check)
        pattern_h_layout.addStretch()
        pattern_layout.addLayout(pattern_h_layout)

        self.exclude_patterns_edit = QLineEdit()
        self.exclude_patterns_edit.setToolTip(
            "Comma-separated wildcard patterns (e.g. cover*, thumb*)"
        )
        self.exclude_patterns_edit.setPlaceholderText(
            "e.g., cover*, poster*, thumb*, *_small.* (comma-separated patterns)"
        )
        self.exclude_patterns_edit.setEnabled(False)
        pattern_layout.addWidget(self.exclude_patterns_edit)
        strategy_layout.addLayout(pattern_layout)

        self.exclude_patterns_check.toggled.connect(
            self.exclude_patterns_edit.setEnabled
        )

        # Statistics Calculation
        stats_label = QLabel("<b>Statistics Calculation</b>")
        stats_label.setStyleSheet("margin-top: 10px;")
        strategy_layout.addWidget(stats_label)

        stats_layout = QHBoxLayout()
        self.stats_exclude_outliers_check = QCheckBox(
            "Exclude outliers (\u00b11.5 IQR)"
        )
        self.stats_exclude_outliers_check.setToolTip(
            "Remove images with dimensions outside 1.5x interquartile range"
        )
        stats_layout.addWidget(self.stats_exclude_outliers_check)
        stats_layout.addWidget(InfoButton(
            "<b>IQR</b> (Interquartile Range) is a statistical method to "
            "detect unusual values. With this enabled, images whose dimensions "
            "fall far outside the middle 50% of the sample are ignored.<br><br>"
            "<b>Practical effect:</b> if 24 out of 25 sampled images are "
            "1920&times;1080 but one is 100&times;100, the outlier is dropped "
            "before calculating the average."
        ))
        stats_layout.addStretch()
        strategy_layout.addLayout(stats_layout)

        # Average Method
        avg_layout = QHBoxLayout()
        avg_layout.addWidget(QLabel("Average method:"))
        self.avg_mean_radio = QRadioButton("Mean")
        self.avg_mean_radio.setProperty("class", "scanning-radio")
        self.avg_mean_radio.setToolTip("Arithmetic mean (sum / count)")
        avg_layout.addWidget(self.avg_mean_radio)

        self.avg_median_radio = QRadioButton("Median")
        self.avg_median_radio.setProperty("class", "scanning-radio")
        self.avg_median_radio.setToolTip(
            "Middle value (more robust to outliers)"
        )
        self.avg_median_radio.setChecked(True)
        avg_layout.addWidget(self.avg_median_radio)
        avg_layout.addWidget(InfoButton(
            "<b>Mean:</b> Adds all values and divides by count. Affected by "
            "extreme values (one huge image pulls the average up).<br><br>"
            "<b>Median:</b> Takes the middle value when sorted. Ignores extremes.<br><br>"
            "For galleries with consistent image sizes, both give similar results. "
            "For mixed galleries, median is more robust. <b>Recommended: Median.</b>"
        ))
        avg_layout.addStretch()
        strategy_layout.addLayout(avg_layout)

        # Create button group for average method (Mean vs Median)
        self.avg_method_group = QButtonGroup(self)
        self.avg_method_group.addButton(self.avg_mean_radio)
        self.avg_method_group.addButton(self.avg_median_radio)

        # Performance info
        perf_info = QLabel(
            "Fast mode uses imghdr for corruption detection and PIL for "
            "dimension calculations and to rescan images that fail imghdr test."
        )
        perf_info.setWordWrap(True)
        perf_info.setStyleSheet("color: #666; font-style: italic;")
        strategy_layout.addWidget(perf_info)

        layout.addWidget(strategy_group)
        layout.addStretch()

        # --- Connect change signals to dirty ---
        self.fast_scan_check.toggled.connect(self.dirty.emit)

        self.sampling_fixed_radio.toggled.connect(self.dirty.emit)
        self.sampling_percent_radio.toggled.connect(self.dirty.emit)
        self.sampling_fixed_spin.valueChanged.connect(self.dirty.emit)
        self.sampling_percent_spin.valueChanged.connect(self.dirty.emit)

        self.exclude_first_check.toggled.connect(self.dirty.emit)
        self.exclude_last_check.toggled.connect(self.dirty.emit)
        self.exclude_small_check.toggled.connect(self.dirty.emit)
        self.exclude_small_spin.valueChanged.connect(self.dirty.emit)
        self.exclude_patterns_check.toggled.connect(self.dirty.emit)
        self.exclude_patterns_edit.textChanged.connect(self.dirty.emit)

        self.stats_exclude_outliers_check.toggled.connect(self.dirty.emit)
        self.avg_mean_radio.toggled.connect(self.dirty.emit)
        self.avg_median_radio.toggled.connect(self.dirty.emit)

    # ------------------------------------------------------------------
    # Load / Reload
    # ------------------------------------------------------------------

    def load_settings(self):
        """Load scanning settings from INI file."""
        try:
            config = configparser.ConfigParser()
            config_file = get_config_path()

            if os.path.exists(config_file):
                config.read(config_file, encoding='utf-8')

            # Block ALL signals during loading to prevent marking tab as dirty
            controls_to_block = [
                self.fast_scan_check,
                self.sampling_fixed_radio, self.sampling_percent_radio,
                self.sampling_fixed_spin, self.sampling_percent_spin,
                self.exclude_first_check, self.exclude_last_check,
                self.exclude_small_check, self.exclude_small_spin,
                self.exclude_patterns_check, self.exclude_patterns_edit,
                self.stats_exclude_outliers_check,
                self.avg_mean_radio, self.avg_median_radio,
            ]
            for control in controls_to_block:
                control.blockSignals(True)

            # Load fast scan setting
            fast_scan = config.getboolean(
                'SCANNING', 'fast_scanning', fallback=True
            )
            self.fast_scan_check.setChecked(fast_scan)

            # Load sampling method and values
            sampling_method = config.getint(
                'SCANNING', 'sampling_method', fallback=0
            )
            if sampling_method == 0:
                self.sampling_fixed_radio.setChecked(True)
                self.sampling_fixed_spin.setEnabled(True)
                self.sampling_percent_spin.setEnabled(False)
            else:
                self.sampling_percent_radio.setChecked(True)
                self.sampling_fixed_spin.setEnabled(False)
                self.sampling_percent_spin.setEnabled(True)

            self.sampling_fixed_spin.setValue(
                config.getint(
                    'SCANNING', 'sampling_fixed_count', fallback=25
                )
            )
            self.sampling_percent_spin.setValue(
                config.getint(
                    'SCANNING', 'sampling_percentage', fallback=10
                )
            )

            # Load exclusion settings
            self.exclude_first_check.setChecked(
                config.getboolean(
                    'SCANNING', 'exclude_first', fallback=False
                )
            )
            self.exclude_last_check.setChecked(
                config.getboolean(
                    'SCANNING', 'exclude_last', fallback=False
                )
            )
            exclude_small = config.getboolean(
                'SCANNING', 'exclude_small_images', fallback=False
            )
            self.exclude_small_check.setChecked(exclude_small)
            self.exclude_small_spin.setEnabled(exclude_small)
            self.exclude_small_spin.setValue(
                config.getint(
                    'SCANNING', 'exclude_small_threshold', fallback=50
                )
            )
            self.exclude_patterns_check.setChecked(
                config.getboolean(
                    'SCANNING', 'exclude_patterns', fallback=False
                )
            )
            self.exclude_patterns_edit.setText(
                config.get(
                    'SCANNING', 'exclude_patterns_text', fallback=''
                )
            )

            # Load statistics calculation setting
            self.stats_exclude_outliers_check.setChecked(
                config.getboolean(
                    'SCANNING', 'stats_exclude_outliers', fallback=False
                )
            )

            # Load average method setting
            use_median = config.getboolean(
                'SCANNING', 'use_median', fallback=True
            )
            if use_median:
                self.avg_median_radio.setChecked(True)
            else:
                self.avg_mean_radio.setChecked(True)

            # Unblock signals
            for control in controls_to_block:
                control.blockSignals(False)

        except Exception as e:
            log(
                f"Failed to load scanning settings: {e}",
                level="warning", category="settings",
            )

    def reload_settings(self):
        """Reload Scanning tab form values from saved settings (discard changes)."""
        self.load_settings()

    def reset_to_defaults(self):
        """Reset Scanning-tab controls to their default values."""
        self.fast_scan_check.setChecked(True)
        self.sampling_fixed_radio.setChecked(True)
        self.sampling_fixed_spin.setValue(25)
        self.sampling_percent_spin.setValue(10)
        self.exclude_first_check.setChecked(False)
        self.exclude_last_check.setChecked(False)
        self.exclude_small_check.setChecked(False)
        self.exclude_small_spin.setValue(50)
        self.exclude_patterns_check.setChecked(False)
        self.exclude_patterns_edit.clear()
        self.stats_exclude_outliers_check.setChecked(False)
        self.avg_median_radio.setChecked(True)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save_settings(self):
        """Persist Scanning tab values to INI.

        Returns True on success, False on error.
        """
        try:
            config = configparser.ConfigParser()
            config_file = get_config_path()

            if os.path.exists(config_file):
                config.read(config_file, encoding='utf-8')

            if 'SCANNING' not in config:
                config.add_section('SCANNING')

            # Save all scanning settings
            config.set(
                'SCANNING', 'fast_scanning',
                str(self.fast_scan_check.isChecked()),
            )
            config.set(
                'SCANNING', 'sampling_method',
                '0' if self.sampling_fixed_radio.isChecked() else '1',
            )
            config.set(
                'SCANNING', 'sampling_fixed_count',
                str(self.sampling_fixed_spin.value()),
            )
            config.set(
                'SCANNING', 'sampling_percentage',
                str(self.sampling_percent_spin.value()),
            )
            config.set(
                'SCANNING', 'exclude_first',
                str(self.exclude_first_check.isChecked()),
            )
            config.set(
                'SCANNING', 'exclude_last',
                str(self.exclude_last_check.isChecked()),
            )
            config.set(
                'SCANNING', 'exclude_small_images',
                str(self.exclude_small_check.isChecked()),
            )
            config.set(
                'SCANNING', 'exclude_small_threshold',
                str(self.exclude_small_spin.value()),
            )
            config.set(
                'SCANNING', 'exclude_patterns',
                str(self.exclude_patterns_check.isChecked()),
            )
            config.set(
                'SCANNING', 'exclude_patterns_text',
                self.exclude_patterns_edit.text(),
            )
            config.set(
                'SCANNING', 'stats_exclude_outliers',
                str(self.stats_exclude_outliers_check.isChecked()),
            )
            config.set(
                'SCANNING', 'use_median',
                str(self.avg_median_radio.isChecked()),
            )

            with open(config_file, 'w', encoding='utf-8') as f:
                config.write(f)

            return True
        except Exception as e:
            log(
                f"Failed to save scanning settings: {e}",
                level="warning", category="settings",
            )
            return False
