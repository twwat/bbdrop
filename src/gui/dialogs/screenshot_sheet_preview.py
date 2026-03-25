"""Screenshot sheet preview dialog for video items."""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton,
    QScrollArea, QHBoxLayout, QSizePolicy,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QImage
from PIL import Image
import numpy as np


class ScreenshotSheetPreviewDialog(QDialog):
    """Shows a preview of the generated screenshot sheet for a video."""

    def __init__(self, video_path: str, video_name: str, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self.setWindowTitle(f"Screenshot Sheet Preview — {video_name}")
        self.setMinimumSize(800, 600)
        self._setup_ui()
        self._generate_preview()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Status label
        self.status_label = QLabel("Generating screenshot sheet...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        # Scrollable image area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.scroll_area.setWidget(self.image_label)
        layout.addWidget(self.scroll_area, 1)

        # Buttons
        button_layout = QHBoxLayout()
        self.regenerate_btn = QPushButton("Regenerate")
        self.regenerate_btn.clicked.connect(self._generate_preview)
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)
        button_layout.addStretch()
        button_layout.addWidget(self.regenerate_btn)
        button_layout.addWidget(self.close_btn)
        layout.addLayout(button_layout)

    def _generate_preview(self):
        """Generate the screenshot sheet and display it."""
        self.status_label.setText("Generating screenshot sheet...")
        self.status_label.show()
        self.image_label.clear()

        # Import here to avoid circular imports
        from src.processing.video_scanner import VideoScanner
        from src.processing.screenshot_sheet import ScreenshotSheetGenerator
        from PyQt6.QtCore import QSettings

        # Scan video
        scanner = VideoScanner()
        metadata = scanner.scan(self.video_path)
        if metadata is None:
            self.status_label.setText("Failed to scan video file.")
            return

        # Read settings
        settings = QSettings()
        settings.beginGroup("Video")
        sheet_settings = {
            'rows': settings.value("grid_rows", 4, int),
            'cols': settings.value("grid_cols", 4, int),
            'show_timestamps': settings.value("show_timestamps", True, bool),
            'show_ms': settings.value("show_ms", False, bool),
            'show_frame_number': settings.value("show_frame_number", False, bool),
            'font_color': settings.value("font_color", "#ffffff"),
            'bg_color': settings.value("bg_color", "#000000"),
            'output_format': settings.value("output_format", "PNG"),
            'image_overlay_template': settings.value("image_overlay_template", ""),
        }
        settings.endGroup()

        # Generate sheet
        generator = ScreenshotSheetGenerator()
        header_template = sheet_settings.get('image_overlay_template', '')
        sheet = generator.generate(self.video_path, metadata, sheet_settings, header_template)
        if sheet is None:
            self.status_label.setText("Failed to generate screenshot sheet.")
            return

        # Convert PIL Image to QPixmap
        pixmap = self._pil_to_pixmap(sheet)
        self.image_label.setPixmap(pixmap)
        self.status_label.setText(
            f"{metadata['width']}x{metadata['height']} \u00b7 "
            f"{self._format_duration(metadata['duration'])} \u00b7 "
            f"{sheet.width}x{sheet.height} sheet"
        )

    @staticmethod
    def _pil_to_pixmap(pil_image: Image.Image) -> QPixmap:
        """Convert a PIL Image to a QPixmap."""
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
