"""Screenshot sheet preview dialog for video items."""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton,
    QHBoxLayout, QGraphicsView, QGraphicsScene,
    QGraphicsPixmapItem, QApplication,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRectF
from PyQt6.QtGui import QPixmap, QImage, QWheelEvent, QMouseEvent
from PIL import Image
from src.gui.widgets.zoom_graphics_view import ZoomGraphicsView


class _GenerateThread(QThread):
    """Generate screenshot sheet off the GUI thread."""
    finished = pyqtSignal(object, object)  # (PIL.Image | None, metadata dict | None)

    def __init__(self, video_path: str):
        super().__init__()
        self.video_path = video_path

    def run(self):
        try:
            from src.processing.video_scanner import VideoScanner
            from src.processing.screenshot_sheet import ScreenshotSheetGenerator
            from PyQt6.QtCore import QSettings

            scanner = VideoScanner()
            metadata = scanner.scan(self.video_path)
            if metadata is None:
                self.finished.emit(None, None)
                return

            settings = QSettings("BBDropUploader", "BBDropGUI")
            settings.beginGroup("Video")
            sheet_settings = {
                'rows': settings.value("grid_rows", 5, int),
                'cols': settings.value("grid_cols", 4, int),
                'thumb_width': settings.value("thumb_width", 320, int),
                'border_spacing': settings.value("border_spacing", 4, int),
                'show_timestamps': settings.value("show_timestamps", True, bool),
                'show_ms': settings.value("show_ms", False, bool),
                'show_frame_number': settings.value("show_frame_number", False, bool),
                'ts_font_size': settings.value("ts_font_size", 12, int),
                'header_font_size': settings.value("header_font_size", 14, int),
                'font_family': settings.value("font_family", "monospace"),
                'font_color': settings.value("font_color", "#ffffff"),
                'bg_color': settings.value("bg_color", "#000000"),
                'output_format': settings.value("output_format", "PNG"),
                'image_overlay_template': settings.value("image_overlay_template", ""),
            }
            settings.endGroup()

            generator = ScreenshotSheetGenerator()
            header_template = sheet_settings.get('image_overlay_template', '')
            sheet = generator.generate(self.video_path, metadata, sheet_settings, header_template)
            self.finished.emit(sheet, metadata)
        except Exception as e:
            from src.utils.logger import log
            log(f"Screenshot sheet generation failed: {e}", level="error", category="video")
            self.finished.emit(None, None)


class ScreenshotSheetPreviewDialog(QDialog):
    """Shows a preview of the generated screenshot sheet for a video."""

    def __init__(self, video_path: str, video_name: str, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self._thread = None
        self.setWindowTitle(f"Screenshot Sheet Preview \u2014 {video_name}")
        self.setMinimumSize(800, 600)
        self.resize(1200, 800)
        self._setup_ui()
        self._generate_preview()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Status label
        self.status_label = QLabel("Generating screenshot sheet...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        # Graphics view with zoom
        self.scene = QGraphicsScene(self)
        self.view = ZoomGraphicsView(self)
        self.view.setScene(self.scene)
        self.view.zoom_changed.connect(self._on_zoom_changed)
        layout.addWidget(self.view, 1)

        # Bottom bar
        bottom = QHBoxLayout()

        self.zoom_label = QLabel("")
        bottom.addWidget(self.zoom_label)

        bottom.addStretch()

        fit_btn = QPushButton("Fit")
        fit_btn.setToolTip("Zoom to fit (Ctrl+0)")
        fit_btn.clicked.connect(self.view.zoom_to_fit)
        bottom.addWidget(fit_btn)

        actual_btn = QPushButton("100%")
        actual_btn.setToolTip("Actual size (Ctrl+1)")
        actual_btn.clicked.connect(lambda: self.view.set_zoom(1.0))
        bottom.addWidget(actual_btn)

        self.regenerate_btn = QPushButton("Regenerate")
        self.regenerate_btn.clicked.connect(self._generate_preview)
        bottom.addWidget(self.regenerate_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        bottom.addWidget(close_btn)

        layout.addLayout(bottom)

    def _generate_preview(self):
        if self._thread and self._thread.isRunning():
            return

        self.status_label.setText("Generating screenshot sheet...")
        self.status_label.show()
        self.regenerate_btn.setEnabled(False)
        self.scene.clear()

        self._thread = _GenerateThread(self.video_path)
        self._thread.finished.connect(self._on_generated)
        self._thread.start()

    def _on_generated(self, sheet: Image.Image | None, metadata: dict | None):
        self.regenerate_btn.setEnabled(True)

        if sheet is None or metadata is None:
            self.status_label.setText("Failed to generate screenshot sheet.")
            return

        pixmap = self._pil_to_pixmap(sheet)
        self.scene.clear()
        self.scene.addPixmap(pixmap)
        self.scene.setSceneRect(QRectF(pixmap.rect()))

        self.view.zoom_to_fit()

        self.status_label.setText(
            f"{metadata['width']}\u00d7{metadata['height']} \u00b7 "
            f"{self._format_duration(metadata['duration'])} \u00b7 "
            f"{sheet.width}\u00d7{sheet.height} sheet"
        )

    def _on_zoom_changed(self, zoom: float):
        self.zoom_label.setText(f"{zoom * 100:.0f}%")

    @staticmethod
    def _pil_to_pixmap(pil_image: Image.Image) -> QPixmap:
        if pil_image.mode != 'RGB':
            pil_image = pil_image.convert('RGB')
        data = pil_image.tobytes('raw', 'RGB')
        qimage = QImage(data, pil_image.width, pil_image.height,
                        3 * pil_image.width, QImage.Format.Format_RGB888)
        return QPixmap.fromImage(qimage)

    @staticmethod
    def _format_duration(seconds: float) -> str:
        seconds = max(0, int(seconds))
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    def closeEvent(self, event):
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(3000)
        super().closeEvent(event)
