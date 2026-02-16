"""Drop-enabled frame for icon files."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import QFrame


class IconDropFrame(QFrame):
    """Drop-enabled frame for icon files"""

    icon_dropped = pyqtSignal(str)  # Emits file path when icon is dropped

    def __init__(self, variant_type):
        super().__init__()
        self.variant_type = variant_type
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent | None) -> None:
        """Handle drag enter event"""
        if event is None:
            return
        mime_data = event.mimeData()
        if mime_data and mime_data.hasUrls():
            urls = mime_data.urls()
            if len(urls) == 1:
                file_path = urls[0].toLocalFile()
                if file_path.lower().endswith(('.png', '.ico', '.svg', '.jpg', '.jpeg')):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent | None) -> None:
        """Handle drop event"""
        if event is None:
            return
        mime_data = event.mimeData()
        if not mime_data:
            if event:
                event.ignore()
            return
        urls = mime_data.urls()
        if len(urls) == 1:
            file_path = urls[0].toLocalFile()
            if file_path.lower().endswith(('.png', '.ico', '.svg', '.jpg', '.jpeg')):
                self.icon_dropped.emit(file_path)
                event.acceptProposedAction()
                return
        event.ignore()
