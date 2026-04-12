"""Video settings tab for ComprehensiveSettingsDialog."""

import colorsys

from PIL import Image

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QSpinBox, QCheckBox, QComboBox, QLineEdit,
    QFontComboBox, QPlainTextEdit, QLabel, QSplitter,
    QScrollArea, QPushButton,
)
from PyQt6.QtCore import pyqtSignal, QSettings, Qt, QTimer
from PyQt6.QtGui import QFont, QImage, QPixmap
from PyQt6.QtWidgets import QGraphicsScene

from src.gui.widgets.zoom_graphics_view import ZoomGraphicsView
from src.processing.screenshot_sheet import ScreenshotSheetGenerator


class VideoSettingsTab(QWidget):
    """Settings tab for video support configuration."""

    dirty = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(200)
        self._preview_timer.timeout.connect(self._update_preview)
        self._setup_ui()

    def _setup_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        root_layout.addWidget(splitter)

        # ── Left side: settings controls in scroll area ──
        left_widget = self._build_left_panel()
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumWidth(350)
        scroll_area.setWidget(left_widget)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        splitter.addWidget(scroll_area)

        # ── Right side: live preview ──
        right_widget = self._build_right_panel()
        splitter.addWidget(right_widget)

        splitter.setSizes([380, 520])

    # ------------------------------------------------------------------ #
    #  Left panel                                                         #
    # ------------------------------------------------------------------ #
    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # -- Screenshot Sheet --
        sheet_group = QGroupBox("Screenshot Sheet")
        sheet_layout = QVBoxLayout(sheet_group)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Grid:"))
        self.grid_rows = QSpinBox()
        self.grid_rows.setRange(1, 10)
        self.grid_rows.setValue(4)
        self.grid_rows.valueChanged.connect(self.dirty.emit)
        row1.addWidget(self.grid_rows)
        row1.addWidget(QLabel("\u00d7"))  # multiplication sign
        self.grid_cols = QSpinBox()
        self.grid_cols.setRange(1, 10)
        self.grid_cols.setValue(4)
        self.grid_cols.valueChanged.connect(self.dirty.emit)
        row1.addWidget(self.grid_cols)
        row1.addStretch()
        row1.addWidget(QLabel("Format:"))
        self.output_format = QComboBox()
        self.output_format.addItems(["PNG", "JPG"])
        self.output_format.currentIndexChanged.connect(self.dirty.emit)
        row1.addWidget(self.output_format)
        sheet_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Thumb width:"))
        self.thumb_width = QSpinBox()
        self.thumb_width.setRange(100, 1920)
        self.thumb_width.setValue(320)
        self.thumb_width.setSuffix(" px")
        self.thumb_width.setSingleStep(10)
        self.thumb_width.setToolTip("Target width for each thumbnail in the grid. Height scales proportionally.")
        self.thumb_width.valueChanged.connect(self.dirty.emit)
        row2.addWidget(self.thumb_width)
        row2.addStretch()
        row2.addWidget(QLabel("Spacing:"))
        self.border_spacing = QSpinBox()
        self.border_spacing.setRange(0, 50)
        self.border_spacing.setValue(4)
        self.border_spacing.setSuffix(" px")
        self.border_spacing.setToolTip("Spacing between thumbnails and around the sheet edges.")
        self.border_spacing.valueChanged.connect(self.dirty.emit)
        row2.addWidget(self.border_spacing)
        sheet_layout.addLayout(row2)

        layout.addWidget(sheet_group)

        # -- Timestamps --
        ts_group = QGroupBox("Timestamps")
        ts_layout = QVBoxLayout(ts_group)

        ts_row1 = QHBoxLayout()
        self.show_timestamps = QCheckBox("Show timestamps")
        self.show_timestamps.setChecked(True)
        self.show_timestamps.toggled.connect(self.dirty.emit)
        ts_row1.addWidget(self.show_timestamps)
        self.show_ms = QCheckBox("Show ms")
        self.show_ms.toggled.connect(self.dirty.emit)
        ts_row1.addWidget(self.show_ms)
        self.show_frame_number = QCheckBox("Show frame#")
        self.show_frame_number.toggled.connect(self.dirty.emit)
        ts_row1.addWidget(self.show_frame_number)
        ts_row1.addStretch()
        ts_layout.addLayout(ts_row1)

        ts_row2 = QHBoxLayout()
        ts_row2.addWidget(QLabel("Font size:"))
        self.ts_font_size = QSpinBox()
        self.ts_font_size.setRange(6, 72)
        self.ts_font_size.setValue(12)
        self.ts_font_size.setSuffix(" pt")
        self.ts_font_size.valueChanged.connect(self.dirty.emit)
        ts_row2.addWidget(self.ts_font_size)
        ts_row2.addStretch()
        ts_layout.addLayout(ts_row2)

        layout.addWidget(ts_group)

        # -- Appearance --
        appearance_group = QGroupBox("Appearance")
        appearance_layout = QVBoxLayout(appearance_group)

        app_row1 = QHBoxLayout()
        app_row1.addWidget(QLabel("Font:"))
        self.font_family = QFontComboBox()
        self.font_family.currentFontChanged.connect(self.dirty.emit)
        app_row1.addWidget(self.font_family, 1)
        app_row1.addWidget(QLabel("Size:"))
        self.header_font_size = QSpinBox()
        self.header_font_size.setRange(6, 72)
        self.header_font_size.setValue(14)
        self.header_font_size.setSuffix(" pt")
        self.header_font_size.valueChanged.connect(self.dirty.emit)
        app_row1.addWidget(self.header_font_size)
        appearance_layout.addLayout(app_row1)

        app_row2 = QHBoxLayout()
        app_row2.addWidget(QLabel("Font color:"))
        self.font_color = QLineEdit("#ffffff")
        self.font_color.textChanged.connect(self.dirty.emit)
        app_row2.addWidget(self.font_color)
        app_row2.addWidget(QLabel("BG color:"))
        self.bg_color = QLineEdit("#000000")
        self.bg_color.textChanged.connect(self.dirty.emit)
        app_row2.addWidget(self.bg_color)
        appearance_layout.addLayout(app_row2)

        layout.addWidget(appearance_group)

        # -- Image Overlay Template --
        overlay_group = QGroupBox("Image Overlay Template")
        overlay_layout = QVBoxLayout(overlay_group)
        overlay_hint = QLabel(
            "Text rendered onto the sheet. Placeholders: #filename#, #duration#, #resolution#, etc."
        )
        overlay_hint.setWordWrap(True)
        overlay_layout.addWidget(overlay_hint)
        self.image_overlay_template = QPlainTextEdit()
        self.image_overlay_template.setMaximumHeight(60)
        self.image_overlay_template.setPlaceholderText(
            "e.g. #filename# | #resolution# | #duration# | #videoCodec# / #audioCodec#"
        )
        self.image_overlay_template.textChanged.connect(self.dirty.emit)
        overlay_layout.addWidget(self.image_overlay_template)
        layout.addWidget(overlay_group)

        # -- Video Details Template --
        details_group = QGroupBox("Video Details Template")
        details_layout = QVBoxLayout(details_group)
        details_hint = QLabel(
            "BBCode text for #videoDetails# placeholder. Same metadata placeholders."
        )
        details_hint.setWordWrap(True)
        details_layout.addWidget(details_hint)
        self.video_details_template = QPlainTextEdit()
        self.video_details_template.setMaximumHeight(60)
        self.video_details_template.setPlaceholderText(
            "e.g. [b]#filename#[/b]\\n#resolution# | #duration# | #filesize#"
        )
        self.video_details_template.textChanged.connect(self.dirty.emit)
        details_layout.addWidget(self.video_details_template)
        layout.addWidget(details_group)

        # -- Defaults --
        defaults_group = QGroupBox("Defaults")
        defaults_layout = QHBoxLayout(defaults_group)
        defaults_layout.addWidget(QLabel("Template:"))
        self.default_template = QComboBox()
        self.default_template.currentIndexChanged.connect(self.dirty.emit)
        defaults_layout.addWidget(self.default_template, 1)
        defaults_layout.addWidget(QLabel("Host:"))
        self.image_host_override = QComboBox()
        self.image_host_override.addItem("(use current selection)", "")
        self.image_host_override.currentIndexChanged.connect(self.dirty.emit)
        defaults_layout.addWidget(self.image_host_override, 1)
        layout.addWidget(defaults_group)

        # -- Mixed Folders --
        mixed_group = QGroupBox("Mixed Folders")
        mixed_layout = QHBoxLayout(mixed_group)
        self.remember_mixed = QCheckBox("Remember mixed folder choice")
        self.remember_mixed.toggled.connect(self.dirty.emit)
        mixed_layout.addWidget(self.remember_mixed)
        mixed_layout.addWidget(QLabel("Default:"))
        self.mixed_choice = QComboBox()
        self.mixed_choice.addItems(["Include images", "Videos only"])
        self.mixed_choice.setEnabled(False)
        self.mixed_choice.currentIndexChanged.connect(self.dirty.emit)
        self.remember_mixed.toggled.connect(self.mixed_choice.setEnabled)
        mixed_layout.addWidget(self.mixed_choice)
        layout.addWidget(mixed_group)

        layout.addStretch()

        # Connect dirty to schedule preview
        self.dirty.connect(self._schedule_preview_update)

        return panel

    # ------------------------------------------------------------------ #
    #  Right panel                                                        #
    # ------------------------------------------------------------------ #
    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        self._preview_scene = QGraphicsScene(self)
        self._preview_view = ZoomGraphicsView(self)
        self._preview_view.setScene(self._preview_scene)
        layout.addWidget(self._preview_view, 1)

        # Zoom control bar
        bar = QHBoxLayout()
        self._zoom_label = QLabel("100%")
        bar.addWidget(self._zoom_label)
        bar.addStretch()
        fit_btn = QPushButton("Fit")
        fit_btn.setFixedWidth(48)
        fit_btn.clicked.connect(self._preview_view.zoom_to_fit)
        bar.addWidget(fit_btn)
        one_to_one_btn = QPushButton("1:1")
        one_to_one_btn.setFixedWidth(48)
        one_to_one_btn.clicked.connect(lambda: self._preview_view.set_zoom(1.0))
        bar.addWidget(one_to_one_btn)
        layout.addLayout(bar)

        self._preview_view.zoom_changed.connect(
            lambda z: self._zoom_label.setText(f"{z * 100:.0f}%")
        )

        return panel

    # ------------------------------------------------------------------ #
    #  Preview generation                                                 #
    # ------------------------------------------------------------------ #
    def _schedule_preview_update(self):
        """Restart the debounce timer for preview regeneration."""
        self._preview_timer.start()

    def _update_preview(self):
        """Generate and display a synthetic screenshot sheet preview."""
        rows = self.grid_rows.value()
        cols = self.grid_cols.value()
        count = rows * cols

        # Synthetic frames with distinct hues
        frames = []
        for i in range(count):
            hue = i / max(count, 1)
            r, g, b = colorsys.hsv_to_rgb(hue, 0.4, 0.7)
            img = Image.new('RGB', (320, 240), (int(r * 255), int(g * 255), int(b * 255)))
            frames.append((img, i * 5.0))

        settings = {
            'rows': rows,
            'cols': cols,
            'thumb_width': self.thumb_width.value(),
            'border_spacing': self.border_spacing.value(),
            'show_timestamps': self.show_timestamps.isChecked(),
            'show_ms': self.show_ms.isChecked(),
            'show_frame_number': self.show_frame_number.isChecked(),
            'ts_font_size': self.ts_font_size.value(),
            'font_family': self.font_family.currentFont().family(),
            'header_font_size': self.header_font_size.value(),
            'font_color': self.font_color.text(),
            'bg_color': self.bg_color.text(),
            'header_text': self.image_overlay_template.toPlainText(),
        }

        try:
            sheet = ScreenshotSheetGenerator().composite_sheet(frames, settings)
            pixmap = self._pil_to_pixmap(sheet)
        except Exception:
            pixmap = QPixmap(320, 240)
            pixmap.fill(Qt.GlobalColor.darkGray)

        self._preview_scene.clear()
        self._preview_scene.addPixmap(pixmap)
        self._preview_scene.setSceneRect(0, 0, pixmap.width(), pixmap.height())
        self._preview_view.zoom_to_fit()

    @staticmethod
    def _pil_to_pixmap(pil_image: Image.Image) -> QPixmap:
        """Convert a PIL Image to a QPixmap."""
        if pil_image.mode != 'RGB':
            pil_image = pil_image.convert('RGB')
        data = pil_image.tobytes('raw', 'RGB')
        qimage = QImage(
            data, pil_image.width, pil_image.height,
            3 * pil_image.width, QImage.Format.Format_RGB888,
        )
        return QPixmap.fromImage(qimage)

    # ------------------------------------------------------------------ #
    #  Settings I/O                                                       #
    # ------------------------------------------------------------------ #
    def load_settings(self, settings: QSettings):
        """Load current values from QSettings."""
        widgets = [
            self.grid_rows, self.grid_cols, self.thumb_width, self.border_spacing,
            self.output_format, self.show_timestamps, self.show_ms,
            self.show_frame_number, self.ts_font_size, self.font_family,
            self.header_font_size, self.font_color, self.bg_color,
            self.image_overlay_template, self.video_details_template,
            self.remember_mixed, self.mixed_choice,
            self.default_template, self.image_host_override,
        ]
        for w in widgets:
            w.blockSignals(True)
        try:
            settings.beginGroup("Video")
            self.grid_rows.setValue(settings.value("grid_rows", 4, int))
            self.grid_cols.setValue(settings.value("grid_cols", 4, int))
            self.thumb_width.setValue(settings.value("thumb_width", 320, int))
            self.border_spacing.setValue(settings.value("border_spacing", 4, int))
            self.show_timestamps.setChecked(settings.value("show_timestamps", True, bool))
            self.show_ms.setChecked(settings.value("show_ms", False, bool))
            self.show_frame_number.setChecked(settings.value("show_frame_number", False, bool))
            self.ts_font_size.setValue(settings.value("ts_font_size", 12, int))
            self.header_font_size.setValue(settings.value("header_font_size", 14, int))
            self.font_color.setText(settings.value("font_color", "#ffffff"))
            self.bg_color.setText(settings.value("bg_color", "#000000"))
            self.output_format.setCurrentText(settings.value("output_format", "PNG"))
            self.image_overlay_template.setPlainText(settings.value("image_overlay_template", ""))
            self.video_details_template.setPlainText(settings.value("video_details_template", ""))
            self.remember_mixed.setChecked(settings.value("remember_mixed_choice", False, bool))
            saved_font = settings.value("font_family", "")
            if saved_font:
                self.font_family.setCurrentFont(QFont(saved_font))
            settings.endGroup()
        finally:
            for w in widgets:
                w.blockSignals(False)

        self._update_preview()

    def save_settings(self, settings: QSettings):
        """Save current values to QSettings."""
        settings.beginGroup("Video")
        settings.setValue("grid_rows", self.grid_rows.value())
        settings.setValue("grid_cols", self.grid_cols.value())
        settings.setValue("thumb_width", self.thumb_width.value())
        settings.setValue("border_spacing", self.border_spacing.value())
        settings.setValue("show_timestamps", self.show_timestamps.isChecked())
        settings.setValue("show_ms", self.show_ms.isChecked())
        settings.setValue("show_frame_number", self.show_frame_number.isChecked())
        settings.setValue("ts_font_size", self.ts_font_size.value())
        settings.setValue("header_font_size", self.header_font_size.value())
        settings.setValue("font_family", self.font_family.currentFont().family())
        settings.setValue("font_color", self.font_color.text())
        settings.setValue("bg_color", self.bg_color.text())
        settings.setValue("output_format", self.output_format.currentText())
        settings.setValue("image_overlay_template", self.image_overlay_template.toPlainText())
        settings.setValue("video_details_template", self.video_details_template.toPlainText())
        settings.setValue("remember_mixed_choice", self.remember_mixed.isChecked())
        settings.endGroup()
        return True
