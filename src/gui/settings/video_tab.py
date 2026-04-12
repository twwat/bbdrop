"""Video settings tab for ComprehensiveSettingsDialog."""

import colorsys
import os

from PIL import Image

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QSpinBox, QCheckBox, QComboBox, QLineEdit,
    QFontComboBox, QPlainTextEdit, QLabel,
    QScrollArea, QPushButton, QGraphicsScene,
)
from PyQt6.QtCore import pyqtSignal, QSettings, Qt, QTimer
from PyQt6.QtGui import QFont, QImage, QPixmap
from src.gui.widgets.zoom_graphics_view import ZoomGraphicsView
from src.gui.widgets.info_button import InfoButton
from src.processing.screenshot_sheet import ScreenshotSheetGenerator


class _PreviewWindow(QWidget):
    """Floating preview window with zoom controls."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("Screenshot Sheet Preview")
        self.resize(800, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._scene = QGraphicsScene(self)
        self._view = ZoomGraphicsView(self)
        self._view.setScene(self._scene)
        layout.addWidget(self._view, 1)

        bar = QHBoxLayout()
        self._zoom_label = QLabel("100%")
        bar.addWidget(self._zoom_label)
        bar.addStretch()
        fit_btn = QPushButton("Fit")
        fit_btn.setFixedWidth(48)
        fit_btn.clicked.connect(self._view.zoom_to_fit)
        bar.addWidget(fit_btn)
        one_btn = QPushButton("1:1")
        one_btn.setFixedWidth(48)
        one_btn.clicked.connect(lambda: self._view.set_zoom(1.0))
        bar.addWidget(one_btn)
        layout.addLayout(bar)

        self._view.zoom_changed.connect(
            lambda z: self._zoom_label.setText(f"{z * 100:.0f}%")
        )

    def set_pixmap(self, pixmap: QPixmap):
        from PyQt6.QtCore import QRectF
        self._scene.clear()
        self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        QTimer.singleShot(0, self._view.zoom_to_fit)


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

        # Settings controls in scroll area (full width)
        left_widget = self._build_left_panel()
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(left_widget)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root_layout.addWidget(scroll_area, 1)

        # Inline preview strip at bottom
        preview_strip = self._build_preview_strip()
        root_layout.addWidget(preview_strip)

        # Floating preview window (created on demand)
        self._preview_window = None

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
        self.grid_rows.setValue(5)
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
        row1.addWidget(InfoButton(
            "<b>Screenshot Sheet</b><br>"
            "A grid of evenly-spaced frames extracted from the video. "
            "The sheet is uploaded to the image host as a single image.<br><br>"
            "<b>Thumb width</b> sets the width of each frame in the grid (height scales proportionally). "
            "<b>Spacing</b> controls the gap between frames and around the edges."
        ))
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

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("JPG quality:"))
        self.jpg_quality = QSpinBox()
        self.jpg_quality.setRange(1, 100)
        self.jpg_quality.setValue(85)
        self.jpg_quality.setSuffix("%")
        self.jpg_quality.setToolTip("JPEG compression quality (1-100). Only used when format is JPG.")
        self.jpg_quality.valueChanged.connect(self.dirty.emit)
        row3.addWidget(self.jpg_quality)
        row3.addStretch()
        sheet_layout.addLayout(row3)

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
        ts_row1.addWidget(InfoButton(
            "<b>Timestamps</b><br>"
            "Overlay the playback time on each frame in the grid. "
            "Optionally show milliseconds or frame numbers."
        ))
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
        overlay_title = QHBoxLayout()
        overlay_hint = QLabel(
            "Text rendered onto the sheet above the grid."
        )
        overlay_title.addWidget(overlay_hint)
        overlay_title.addWidget(InfoButton(
            "<b>Image Overlay Template</b><br>"
            "This text is rendered directly onto the screenshot sheet image, above the thumbnail grid. "
            "It becomes part of the uploaded image.<br><br>"
            "<b>Available placeholders:</b><br>"
            "<code>#filename#</code> — video filename<br>"
            "<code>#folderName#</code> — gallery/folder name<br>"
            "<code>#duration#</code> — playback duration (H:MM:SS)<br>"
            "<code>#resolution#</code> — video dimensions (WxH)<br>"
            "<code>#width#</code> / <code>#height#</code> — individual dimensions<br>"
            "<code>#fps#</code> — frame rate<br>"
            "<code>#bitrate#</code> — video bitrate (bps)<br>"
            "<code>#videoCodec#</code> — video codec (e.g. HEVC, H264)<br>"
            "<code>#audioCodec#</code> — primary audio codec<br>"
            "<code>#audioTracks#</code> — all audio tracks summary<br>"
            "<code>#audioTrack1#</code>, <code>#audioTrack2#</code>, … — individual tracks<br>"
            "<code>#filesize#</code> — formatted file size<br>"
            "<code>#folderSize#</code> — total folder size<br>"
            "<code>#pictureCount#</code> — number of frames in sheet"
        ))
        overlay_layout.addLayout(overlay_title)
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
        details_title = QHBoxLayout()
        details_hint = QLabel(
            "BBCode text available as #videoDetails# in your main template."
        )
        details_title.addWidget(details_hint)
        details_title.addWidget(InfoButton(
            "<b>Video Details Template</b><br>"
            "This generates BBCode text (not rendered onto the image). "
            "Use <code>#videoDetails#</code> in your main BBCode template to insert it.<br><br>"
            "Same placeholders as the image overlay template."
        ))
        details_layout.addLayout(details_title)
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
        defaults_layout.addWidget(QLabel("Image host:"))
        self.image_host_override = QComboBox()
        self.image_host_override.currentIndexChanged.connect(self.dirty.emit)
        defaults_layout.addWidget(self.image_host_override, 1)
        defaults_layout.addWidget(InfoButton(
            "<b>Defaults</b><br>"
            "<b>Template</b> — the BBCode template used for video uploads.<br>"
            "<b>Image host</b> — which host to upload the screenshot sheet to. "
            "\"Use current selection\" uses whatever image host is active in the main window."
        ))
        layout.addWidget(defaults_group)
        self._populate_combos()

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
    #  Combo population                                                   #
    # ------------------------------------------------------------------ #
    def _populate_combos(self):
        """Populate template and image host combo boxes."""
        from src.utils.templates import load_templates
        from src.network.image_host_factory import get_available_hosts
        from src.core.host_registry import get_display_name

        # Templates
        self.default_template.blockSignals(True)
        self.default_template.clear()
        for name in sorted(load_templates().keys()):
            self.default_template.addItem(name, name)
        # Default to "Video" template if it exists
        idx = self.default_template.findData("Video")
        if idx >= 0:
            self.default_template.setCurrentIndex(idx)
        self.default_template.blockSignals(False)

        # Image hosts
        self.image_host_override.blockSignals(True)
        self.image_host_override.clear()
        self.image_host_override.addItem("(use current selection)", "")
        for host_id in get_available_hosts():
            self.image_host_override.addItem(get_display_name(host_id), host_id)
        self.image_host_override.blockSignals(False)

    # ------------------------------------------------------------------ #
    #  Preview strip (inline thumbnail + pop-out)                         #
    # ------------------------------------------------------------------ #
    def _build_preview_strip(self) -> QWidget:
        strip = QWidget()
        layout = QHBoxLayout(strip)
        layout.setContentsMargins(0, 4, 0, 0)

        # Clickable thumbnail
        self._thumb_label = QLabel()
        self._thumb_label.setFixedHeight(120)
        self._thumb_label.setMinimumWidth(200)
        self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_label.setStyleSheet("border: 1px solid palette(mid); background: #111;")
        self._thumb_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._thumb_label.setToolTip("Click to open full preview")
        self._thumb_label.mousePressEvent = lambda e: self._pop_out_preview()
        layout.addWidget(self._thumb_label, 1)

        # Info + button column
        info_layout = QVBoxLayout()
        self._size_label = QLabel("")
        info_layout.addWidget(self._size_label)
        info_layout.addStretch()
        pop_out_btn = QPushButton("Pop Out")
        pop_out_btn.setFixedWidth(70)
        pop_out_btn.clicked.connect(self._pop_out_preview)
        info_layout.addWidget(pop_out_btn)
        layout.addLayout(info_layout)

        return strip

    def _pop_out_preview(self):
        """Open or focus the floating preview window."""
        if self._preview_window is None or not self._preview_window.isVisible():
            self._preview_window = _PreviewWindow(self)
        self._preview_window.show()
        self._preview_window.raise_()
        self._preview_window.activateWindow()
        # Push current pixmap into it
        if self._current_pixmap is not None:
            self._preview_window.set_pixmap(self._current_pixmap)

    # Keep a reference to the last generated pixmap for pop-out
    _current_pixmap = None

    # ------------------------------------------------------------------ #
    #  Preview generation                                                 #
    # ------------------------------------------------------------------ #
    def _schedule_preview_update(self):
        """Restart the debounce timer for preview regeneration."""
        self._preview_timer.start()

    _DEMO_PLACEHOLDERS = {
        '#filename#': 'Fantastic.Fungi.2019.1080p.x265.AAC.mkv',
        '#folderName#': 'Fantastic.Fungi.2019.1080p.x265.AAC',
        '#duration#': '1:20:01',
        '#resolution#': '1920x1080',
        '#fps#': '23.976',
        '#bitrate#': '4500000',
        '#videoCodec#': 'HEVC',
        '#audioCodec#': 'AAC',
        '#audioTracks#': 'AAC: 2-CH 48000Hz 128 kbps',
        '#audioTrack1#': 'AAC: 2-CH 48000Hz 128 kbps',
        '#filesize#': '1.24 GB',
        '#width#': '1920',
        '#height#': '1080',
        '#pictureCount#': '20',
        '#folderSize#': '1.24 GB',
    }

    _preview_frames_cache = None

    @classmethod
    def _load_preview_frames(cls):
        """Load preview frame images from assets/preview_frames/."""
        if cls._preview_frames_cache is not None:
            return cls._preview_frames_cache

        from src.utils.paths import get_project_root
        frames_dir = os.path.join(get_project_root(), 'assets', 'preview_frames')
        frames = []
        if os.path.isdir(frames_dir):
            for fname in sorted(os.listdir(frames_dir)):
                if fname.endswith(('.jpg', '.png')):
                    try:
                        img = Image.open(os.path.join(frames_dir, fname)).convert('RGB')
                        frames.append(img)
                    except Exception:
                        pass
        cls._preview_frames_cache = frames
        return frames

    def _update_preview(self):
        """Generate and display a screenshot sheet preview using real frames."""
        rows = self.grid_rows.value()
        cols = self.grid_cols.value()
        count = rows * cols

        # Use real preview frames, cycling if we need more than available
        source_frames = self._load_preview_frames()
        frames = []
        for i in range(count):
            if source_frames:
                img = source_frames[i % len(source_frames)]
            else:
                # Fallback to colored frames if no preview images exist
                hue = i / max(count, 1)
                r, g, b = colorsys.hsv_to_rgb(hue, 0.3, 0.55)
                img = Image.new('RGB', (320, 180), (int(r * 255), int(g * 255), int(b * 255)))
            # Fake timestamps as if from a ~80min video
            frames.append((img, i * (4801.0 / max(count, 1))))

        # Resolve overlay template placeholders with demo values
        overlay_text = self.image_overlay_template.toPlainText()
        if overlay_text:
            for placeholder, value in self._DEMO_PLACEHOLDERS.items():
                overlay_text = overlay_text.replace(placeholder, value)

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
            'header_text': overlay_text,
            'fps': 23.976,
        }

        try:
            sheet = ScreenshotSheetGenerator().composite_sheet(frames, settings)
            pixmap = self._pil_to_pixmap(sheet)
        except Exception:
            pixmap = QPixmap(320, 240)
            pixmap.fill(Qt.GlobalColor.darkGray)

        # Estimate file size
        import io
        buf = io.BytesIO()
        fmt = self.output_format.currentText()
        save_kwargs = {}
        if fmt == 'JPG':
            save_kwargs['quality'] = self.jpg_quality.value()
        sheet.save(buf, format='JPEG' if fmt == 'JPG' else 'PNG', **save_kwargs)
        size_bytes = buf.tell()
        if size_bytes >= 1024 * 1024:
            size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            size_str = f"{size_bytes / 1024:.0f} KB"
        self._size_label.setText(f"{sheet.width}\u00d7{sheet.height}  ~{size_str}")

        self._current_pixmap = pixmap

        # Update inline thumbnail (scaled to fit the strip)
        thumb = pixmap.scaled(
            self._thumb_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._thumb_label.setPixmap(thumb)

        # Update floating preview window if open
        if self._preview_window is not None and self._preview_window.isVisible():
            self._preview_window.set_pixmap(pixmap)

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
            self.output_format, self.jpg_quality, self.show_timestamps, self.show_ms,
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
            # Reset stale settings from pre-0.9.6 when video settings didn't work
            if settings.value("_settings_version", 0, int) < 2:
                settings.remove("")  # Clear entire Video group
                settings.endGroup()
                settings.beginGroup("Video")
                settings.setValue("_settings_version", 2)
            self.grid_rows.setValue(settings.value("grid_rows", 5, int))
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
            self.jpg_quality.setValue(settings.value("jpg_quality", 85, int))
            self.image_overlay_template.setPlainText(settings.value(
                "image_overlay_template",
                "#filename#  |  #resolution#  |  #duration#  |  #videoCodec# / #audioCodec#  |  #filesize#"
            ))
            self.video_details_template.setPlainText(settings.value("video_details_template", ""))
            self.remember_mixed.setChecked(settings.value("remember_mixed_choice", False, bool))
            saved_font = settings.value("font_family", "")
            if saved_font:
                self.font_family.setCurrentFont(QFont(saved_font))
            saved_template = settings.value("default_template", "Video")
            idx = self.default_template.findData(saved_template)
            if idx >= 0:
                self.default_template.setCurrentIndex(idx)
            saved_host = settings.value("image_host_override", "")
            idx = self.image_host_override.findData(saved_host)
            if idx >= 0:
                self.image_host_override.setCurrentIndex(idx)
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
        settings.setValue("jpg_quality", self.jpg_quality.value())
        settings.setValue("image_overlay_template", self.image_overlay_template.toPlainText())
        settings.setValue("video_details_template", self.video_details_template.toPlainText())
        settings.setValue("remember_mixed_choice", self.remember_mixed.isChecked())
        settings.setValue("default_template", self.default_template.currentData() or "Video")
        settings.setValue("image_host_override", self.image_host_override.currentData() or "")
        settings.setValue("_settings_version", 2)
        settings.endGroup()
        return True
