"""Contact Sheets settings tab for ComprehensiveSettingsDialog."""

import colorsys
import os

from PIL import Image

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout, QGroupBox,
    QSpinBox, QCheckBox, QComboBox, QColorDialog, QLineEdit,
    QFontComboBox, QPlainTextEdit, QLabel,
    QScrollArea, QPushButton, QGraphicsScene,
)
from PyQt6.QtCore import pyqtSignal, QSettings, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QImage, QPixmap
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


class _ColorPicker(QWidget):
    """Color swatch + hex input that opens QColorDialog on click."""

    colorChanged = pyqtSignal()

    def __init__(self, default="#000000", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self._swatch = QPushButton()
        self._swatch.setFixedSize(28, 22)
        self._swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self._swatch.clicked.connect(self._pick)
        lay.addWidget(self._swatch)

        self._edit = QLineEdit(default)
        self._edit.setFixedWidth(72)
        self._edit.setPlaceholderText("#000000")
        self._edit.textChanged.connect(self._on_text_changed)
        lay.addWidget(self._edit)

        self._update_swatch(default)

    # -- public API (matches QLineEdit so load/save code works unchanged) --

    def text(self) -> str:
        return self._edit.text()

    def setText(self, color: str):
        self._edit.setText(color)
        self._update_swatch(color)

    def blockSignals(self, b: bool) -> bool:
        self._edit.blockSignals(b)
        return super().blockSignals(b)

    # -- internals --

    def _update_swatch(self, color: str):
        if QColor(color).isValid():
            self._swatch.setStyleSheet(
                f"QPushButton {{ background-color: {color}; "
                f"border: 1px solid palette(mid); border-radius: 3px; }}"
            )

    def _on_text_changed(self, text: str):
        self._update_swatch(text)
        self.colorChanged.emit()

    def _pick(self):
        cur = QColor(self._edit.text())
        if not cur.isValid():
            cur = QColor("#000000")
        color = QColorDialog.getColor(cur, self, "Choose color")
        if color.isValid():
            self._edit.setText(color.name())


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

        # Floating preview window (created on demand)
        self._preview_window = None

    # ------------------------------------------------------------------ #
    #  Left panel                                                         #
    # ------------------------------------------------------------------ #
    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        layout = QGridLayout(panel)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)

        # Tab description (spans both columns)
        desc = QLabel(
            "Configure how contact sheets are generated from video files — "
            "grid layout, timestamps, appearance, and overlay text."
        )
        desc.setWordWrap(True)
        desc.setProperty("class", "tab-description")
        layout.addWidget(desc, 0, 0, 1, 2)

        # ===== Row 1, Left: Screenshot Sheet =====
        sheet_group = QGroupBox("Screenshot Sheet")
        sheet_form = QFormLayout(sheet_group)
        sheet_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        def _form_label(text: str, info_html: str) -> QWidget:
            """Build a 'Label: (i)' row-label widget for QFormLayout."""
            w = QWidget()
            lay = QHBoxLayout(w)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(4)
            lay.addWidget(QLabel(text))
            lay.addWidget(InfoButton(info_html))
            lay.addStretch()
            return w

        # Grid: rows × cols
        self.grid_rows = QSpinBox()
        self.grid_rows.setRange(1, 10)
        self.grid_rows.setValue(5)
        self.grid_rows.valueChanged.connect(self.dirty.emit)
        self.grid_cols = QSpinBox()
        self.grid_cols.setRange(1, 10)
        self.grid_cols.setValue(4)
        self.grid_cols.valueChanged.connect(self.dirty.emit)
        grid_row = QHBoxLayout()
        grid_row.setSpacing(4)
        grid_row.addWidget(self.grid_rows)
        grid_row.addWidget(QLabel("\u00d7"))
        grid_row.addWidget(self.grid_cols)
        grid_row.addStretch()
        sheet_form.addRow(
            _form_label(
                "Grid:",
                "<b>Grid</b><br>"
                "Number of rows × columns of frames extracted from the video "
                "and arranged into the screenshot sheet."
            ),
            grid_row,
        )

        # Thumbnail width (own row)
        self.thumb_width = QSpinBox()
        self.thumb_width.setRange(100, 1920)
        self.thumb_width.setValue(320)
        self.thumb_width.setSuffix(" px")
        self.thumb_width.setSingleStep(10)
        self.thumb_width.setToolTip("Target width for each thumbnail in the grid. Height scales proportionally.")
        self.thumb_width.valueChanged.connect(self.dirty.emit)
        sheet_form.addRow(
            _form_label(
                "Thumbnail width:",
                "<b>Thumbnail width</b><br>"
                "Target width in pixels for each frame in the grid. Height "
                "scales proportionally to preserve the video's aspect ratio."
            ),
            self.thumb_width,
        )

        # Spacing (own row)
        self.border_spacing = QSpinBox()
        self.border_spacing.setRange(0, 50)
        self.border_spacing.setValue(4)
        self.border_spacing.setSuffix(" px")
        self.border_spacing.setToolTip("Spacing between thumbnails and around the sheet edges.")
        self.border_spacing.valueChanged.connect(self.dirty.emit)
        sheet_form.addRow(
            _form_label(
                "Spacing:",
                "<b>Spacing</b><br>"
                "Gap in pixels between thumbnails and around the outer edges "
                "of the screenshot sheet."
            ),
            self.border_spacing,
        )

        # Format + Quality share a row; each gets its own info button.
        self.output_format = QComboBox()
        self.output_format.addItems(["JPG", "PNG"])
        self.output_format.currentIndexChanged.connect(self.dirty.emit)
        self.output_format.currentTextChanged.connect(self._on_format_changed)
        self._jpg_quality_label = QLabel("Quality:")
        self.jpg_quality = QSpinBox()
        self.jpg_quality.setRange(1, 100)
        self.jpg_quality.setValue(85)
        self.jpg_quality.setSuffix("%")
        self.jpg_quality.setToolTip("JPEG compression quality (1-100)")
        self.jpg_quality.valueChanged.connect(self.dirty.emit)
        fmt_row = QHBoxLayout()
        fmt_row.setSpacing(4)
        fmt_row.addWidget(self.output_format)
        fmt_row.addSpacing(12)
        fmt_row.addWidget(self._jpg_quality_label)
        self._jpg_quality_info = InfoButton(
            "<b>Quality</b><br>"
            "JPEG compression quality, 1–100. Higher is better quality and "
            "larger file size. Typical sweet-spot is 80–90."
        )
        fmt_row.addWidget(self._jpg_quality_info)
        fmt_row.addWidget(self.jpg_quality)
        fmt_row.addStretch()
        sheet_form.addRow(
            _form_label(
                "Format:",
                "<b>Format</b><br>"
                "Image file format for the uploaded screenshot sheet. "
                "<b>JPG</b> produces a smaller file with some compression artifacts; "
                "<b>PNG</b> is lossless but larger."
            ),
            fmt_row,
        )

        layout.addWidget(sheet_group, 1, 0)

        # ===== Row 1, Right: Preview =====
        # Thumbnail on the left, dimensions + size + Pop Out button on the
        # right — keeps the group's height close to Screenshot Sheet's.
        preview_group = QGroupBox("Preview")
        preview_lay = QHBoxLayout(preview_group)
        preview_lay.setContentsMargins(8, 8, 8, 8)
        preview_lay.setSpacing(10)

        self._preview_label = QLabel()
        self._preview_label.setFixedSize(240, 160)
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setStyleSheet(
            "QLabel { background: palette(base); "
            "border: 1px solid palette(mid); border-radius: 3px; }"
        )
        self._preview_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._preview_label.setToolTip("Click to open full-size preview")
        self._preview_label.mousePressEvent = lambda _: self._pop_out_preview()
        preview_lay.addWidget(self._preview_label, 0, Qt.AlignmentFlag.AlignTop)

        preview_info = QVBoxLayout()
        preview_info.setSpacing(6)
        self._size_label = QLabel("")
        self._size_label.setWordWrap(True)
        preview_info.addWidget(self._size_label)
        pop_out_btn = QPushButton("Pop Out \u2197")
        pop_out_btn.setFixedWidth(90)
        pop_out_btn.clicked.connect(self._pop_out_preview)
        preview_info.addWidget(pop_out_btn)
        preview_info.addStretch()
        preview_lay.addLayout(preview_info, 1)

        layout.addWidget(preview_group, 1, 1)

        # ===== Row 2, Left: Timestamps =====
        ts_group = QGroupBox("Timestamps")
        ts_layout = QVBoxLayout(ts_group)

        ts_row1 = QHBoxLayout()
        self.show_timestamps = QCheckBox("Show timestamps")
        self.show_timestamps.setChecked(True)
        self.show_timestamps.toggled.connect(self.dirty.emit)
        ts_row1.addWidget(self.show_timestamps)
        ts_row1.addWidget(InfoButton(
            "<b>Timestamps</b><br>"
            "Overlay the playback time on each frame in the grid. "
            "Optionally show milliseconds or frame numbers."
        ))
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

        layout.addWidget(ts_group, 2, 0)

        # ===== Row 2, Right: Mixed Folders (checkbox on row 1, default on row 2) =====
        mixed_group = QGroupBox("Mixed Folders")
        mixed_layout = QVBoxLayout(mixed_group)
        mixed_layout.setSpacing(4)

        mixed_row1 = QHBoxLayout()
        mixed_row1.setSpacing(4)
        self.remember_mixed = QCheckBox("Remember mixed folder choice")
        self.remember_mixed.toggled.connect(self.dirty.emit)
        mixed_row1.addWidget(self.remember_mixed)
        mixed_row1.addWidget(InfoButton(
            "<b>Remember mixed folder choice</b><br>"
            "When a folder contains both images and videos, BBDrop asks whether "
            "to include images or upload videos only. "
            "Enable this to skip the prompt and always use the selected default."
        ))
        mixed_row1.addStretch()
        mixed_layout.addLayout(mixed_row1)

        mixed_row2 = QHBoxLayout()
        mixed_row2.setSpacing(6)
        mixed_row2.addWidget(QLabel("Default:"))
        mixed_row2.addWidget(InfoButton(
            "<b>Default</b><br>"
            "Which choice to use when \"Remember\" is enabled — include images "
            "alongside the videos, or upload videos only."
        ))
        self.mixed_choice = QComboBox()
        self.mixed_choice.addItems(["Include images", "Videos only"])
        self.mixed_choice.setEnabled(False)
        self.mixed_choice.currentIndexChanged.connect(self.dirty.emit)
        self.remember_mixed.toggled.connect(self.mixed_choice.setEnabled)
        mixed_row2.addWidget(self.mixed_choice, 1)
        mixed_layout.addLayout(mixed_row2)
        layout.addWidget(mixed_group, 2, 1)

        # ===== Row 3, Left: Text Overlay Template (with Appearance controls merged in) =====
        overlay_group = QGroupBox("Text Overlay Template")
        overlay_layout = QVBoxLayout(overlay_group)
        overlay_title = QHBoxLayout()
        overlay_hint = QLabel("Text rendered onto the sheet above the grid.")
        overlay_title.addWidget(overlay_hint)
        overlay_title.addWidget(InfoButton(
            "<b>Text Overlay Template</b><br>"
            "This text is rendered directly onto the screenshot sheet image, above the thumbnail grid. "
            "It becomes part of the uploaded image.<br><br>"
            "Click the field to open the full editor with all available placeholders."
        ))
        overlay_title.addStretch()
        overlay_layout.addLayout(overlay_title)
        self.image_overlay_template = QPlainTextEdit()
        self.image_overlay_template.setReadOnly(True)
        # Roughly 5 lines of text (QPlainTextEdit line height ~18px + padding)
        self.image_overlay_template.setMinimumHeight(110)
        self.image_overlay_template.setMaximumHeight(120)
        self.image_overlay_template.setPlaceholderText(
            "e.g. #filename# | #resolution# | #duration# | #videoCodec# / #audioCodec#"
        )
        self.image_overlay_template.setToolTip("Click to open the full editor.")
        self.image_overlay_template.setCursor(Qt.CursorShape.PointingHandCursor)
        self.image_overlay_template.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        self.image_overlay_template.textChanged.connect(self.dirty.emit)
        self.image_overlay_template.viewport().installEventFilter(self)
        overlay_layout.addWidget(self.image_overlay_template)

        # Appearance controls styling the overlay header + timestamps.
        # Row: Font | Row: Font size + Font color | Row: Background color
        font_row = QHBoxLayout()
        font_row.setSpacing(6)
        font_row.addWidget(QLabel("Font:"))
        font_row.addWidget(InfoButton(
            "<b>Font</b><br>"
            "Typeface used for the header text and timestamps rendered onto "
            "the screenshot sheet."
        ))
        self.font_family = QFontComboBox()
        # QFontComboBox is editable by default — disable typing so it acts as
        # a pure dropdown (stops the text-field hover/cursor behaviour).
        self.font_family.setEditable(False)
        self.font_family.currentFontChanged.connect(self.dirty.emit)
        font_row.addWidget(self.font_family, 1)
        overlay_layout.addLayout(font_row)

        size_color_row = QHBoxLayout()
        size_color_row.setSpacing(6)
        size_color_row.addWidget(QLabel("Font size:"))
        self.header_font_size = QSpinBox()
        self.header_font_size.setRange(6, 72)
        self.header_font_size.setValue(14)
        self.header_font_size.setSuffix(" pt")
        self.header_font_size.valueChanged.connect(self.dirty.emit)
        size_color_row.addWidget(self.header_font_size)
        size_color_row.addSpacing(16)
        size_color_row.addWidget(QLabel("Font color:"))
        size_color_row.addWidget(InfoButton(
            "<b>Font color</b><br>"
            "Text color for the header and timestamps. Click the swatch to "
            "open a picker, or type a hex value."
        ))
        self.font_color = _ColorPicker("#ffffff")
        self.font_color.colorChanged.connect(self.dirty.emit)
        size_color_row.addWidget(self.font_color)
        size_color_row.addStretch()
        overlay_layout.addLayout(size_color_row)

        bg_row = QHBoxLayout()
        bg_row.setSpacing(6)
        bg_row.addWidget(QLabel("Background color:"))
        bg_row.addWidget(InfoButton(
            "<b>Background color</b><br>"
            "Background color behind the header text band. Click the swatch "
            "to open a picker, or type a hex value."
        ))
        self.bg_color = _ColorPicker("#000000")
        self.bg_color.colorChanged.connect(self.dirty.emit)
        bg_row.addWidget(self.bg_color)
        bg_row.addStretch()
        overlay_layout.addLayout(bg_row)

        layout.addWidget(overlay_group, 3, 0)

        # ===== Row 3, Right: Video Details Template =====
        details_group = QGroupBox("Video Details Template")
        details_layout = QVBoxLayout(details_group)
        details_title = QHBoxLayout()
        details_hint = QLabel("BBCode text available as #videoDetails# in your main template.")
        details_title.addWidget(details_hint)
        details_title.addWidget(InfoButton(
            "<b>Video Details Template</b><br>"
            "This generates BBCode text (not rendered onto the image). "
            "Use <code>#videoDetails#</code> in your main BBCode template to insert it.<br><br>"
            "Click the field to open the full editor with all available placeholders."
        ))
        details_title.addStretch()
        details_layout.addLayout(details_title)
        self.video_details_template = QPlainTextEdit()
        self.video_details_template.setReadOnly(True)
        self.video_details_template.setMinimumHeight(110)
        self.video_details_template.setMaximumHeight(120)
        self.video_details_template.setPlaceholderText(
            "e.g. [b]#filename#[/b]\\n#resolution# | #duration# | #filesize#"
        )
        self.video_details_template.setToolTip("Click to open the full editor.")
        self.video_details_template.setCursor(Qt.CursorShape.PointingHandCursor)
        self.video_details_template.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        self.video_details_template.textChanged.connect(self.dirty.emit)
        self.video_details_template.viewport().installEventFilter(self)
        details_layout.addWidget(self.video_details_template)
        details_layout.addStretch()
        layout.addWidget(details_group, 3, 1)

        # ===== Row 4: Defaults (Template and Image host each on own row, info per item) =====
        defaults_group = QGroupBox("Defaults")
        defaults_form = QFormLayout(defaults_group)
        defaults_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        def _label_with_info(text: str, info_html: str) -> QWidget:
            """Build a 'Label: (i)' pair for use as a QFormLayout row label."""
            w = QWidget()
            lay = QHBoxLayout(w)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(4)
            lay.addWidget(QLabel(text))
            lay.addWidget(InfoButton(info_html))
            lay.addStretch()
            return w

        self.default_template = QComboBox()
        self.default_template.currentIndexChanged.connect(self.dirty.emit)
        defaults_form.addRow(
            _label_with_info(
                "Template:",
                "<b>Template</b><br>"
                "BBCode template used when uploading galleries that contain videos."
            ),
            self.default_template,
        )

        self.image_host_override = QComboBox()
        self.image_host_override.currentIndexChanged.connect(self.dirty.emit)
        defaults_form.addRow(
            _label_with_info(
                "Image host:",
                "<b>Image host</b><br>"
                "Which image host to upload the screenshot sheet to. "
                "\"Use current selection\" uses whatever host is active in the main window."
            ),
            self.image_host_override,
        )
        layout.addWidget(defaults_group, 4, 0)
        self._populate_combos()

        # Soak up remaining vertical space so rows hug the top instead of
        # being stretched to fill the tab.
        layout.setRowStretch(5, 1)

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

    def _on_format_changed(self, fmt: str):
        """Enable JPG quality controls only when JPG is selected."""
        is_jpg = fmt == "JPG"
        self._jpg_quality_label.setEnabled(is_jpg)
        self.jpg_quality.setEnabled(is_jpg)
        self._jpg_quality_info.setEnabled(is_jpg)

    def eventFilter(self, obj, event):
        """Open template editor when the overlay or details field is clicked.

        The filter is installed on the QPlainTextEdit's viewport rather than
        the widget itself so FocusIn doesn't trigger a reopen loop after the
        dialog closes and focus returns to the field.
        """
        if event.type() == event.Type.MouseButtonPress:
            if obj is self.image_overlay_template.viewport():
                self._open_template_editor(
                    "Text Overlay Template", self.image_overlay_template
                )
                return True
            if obj is self.video_details_template.viewport():
                self._open_template_editor(
                    "Video Details Template", self.video_details_template
                )
                return True
        return super().eventFilter(obj, event)

    def _open_template_editor(self, title: str, field: QPlainTextEdit):
        """Open the placeholder editor dialog for a template field."""
        from src.gui.dialogs.bbcode_link_format_dialog import PlaceholderEditorDialog, VIDEO_PLACEHOLDERS
        dialog = PlaceholderEditorDialog(
            title=title,
            placeholders=VIDEO_PLACEHOLDERS,
            initial_text=field.toPlainText(),
            parent=self
        )
        if dialog.exec() == dialog.DialogCode.Accepted:
            new_text = dialog.get_text()
            if new_text != field.toPlainText():
                field.setPlainText(new_text)
                self.dirty.emit()

    # ------------------------------------------------------------------ #
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
        '#bitrate#': '4500 kbps',
        '#videoCodec#': 'HEVC',
        '#audioCodec#': 'AAC',
        '#audioTracks#': 'AAC: 2ch 48kHz 128 kbps',
        '#audioTrack1#': 'AAC: 2ch 48kHz 128 kbps',
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
        except Exception:
            pixmap = QPixmap(320, 240)
            pixmap.fill(Qt.GlobalColor.darkGray)
            self._size_label.setText("")

        self._current_pixmap = pixmap

        # Update inline preview
        scaled = pixmap.scaled(
            self._preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._preview_label.setPixmap(scaled)

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
            self.output_format.setCurrentText(settings.value("output_format", "JPG"))
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

        self._on_format_changed(self.output_format.currentText())
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
