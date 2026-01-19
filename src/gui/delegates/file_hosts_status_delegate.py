"""File hosts status delegate for table cell rendering."""

from typing import Dict, List, Tuple, Optional
from PyQt6.QtCore import Qt, QRect, QSize, QModelIndex, QEvent, pyqtSignal, QObject
from PyQt6.QtGui import QPainter, QPixmap, QColor, QPen
from PyQt6.QtWidgets import (
    QStyledItemDelegate, QStyleOptionViewItem, QApplication, QStyle, QToolTip
)

from src.gui.icon_manager import get_icon_manager


class FileHostsStatusDelegateSignals(QObject):
    """Signals for FileHostsStatusDelegate."""
    __slots__ = ()
    host_clicked = pyqtSignal(str, str)  # (gallery_path, host_name)


class FileHostsStatusDelegate(QStyledItemDelegate):
    """Delegate for rendering file host status icons in table cells."""

    ICON_SIZE = 22
    ICON_SPACING = 2
    PADDING = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self.signals = FileHostsStatusDelegateSignals()
        self._config_manager = None
        self._enabled_hosts_cache: Optional[Dict] = None
        self._enabled_hosts_cache_time: float = 0
        self._overlay_cache: Dict[str, QPixmap] = {}

    @property
    def host_clicked(self):
        return self.signals.host_clicked

    def _get_config_manager(self):
        if self._config_manager is None:
            from src.core.file_host_config import get_config_manager
            self._config_manager = get_config_manager()
        return self._config_manager

    def _get_enabled_hosts(self) -> Dict:
        import time
        now = time.time()
        # Cache expires after 30 seconds
        if self._enabled_hosts_cache is None or (now - self._enabled_hosts_cache_time) > 30:
            config_mgr = self._get_config_manager()
            self._enabled_hosts_cache = config_mgr.get_enabled_hosts() if config_mgr else {}
            self._enabled_hosts_cache_time = now
        return self._enabled_hosts_cache

    def refresh_enabled_hosts(self):
        self._enabled_hosts_cache = None
        self._enabled_hosts_cache_time = 0

    def _get_overlay_pixmap(self, status: str) -> QPixmap:
        if status in self._overlay_cache:
            return self._overlay_cache[status]

        pixmap = QPixmap(self.ICON_SIZE, self.ICON_SIZE)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        if not painter.isActive():
            return pixmap
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if status == 'uploading':
            painter.setOpacity(0.3)
            painter.fillRect(pixmap.rect(), QColor(0, 120, 255, 100))
        elif status == 'pending':
            painter.setOpacity(0.3)
            painter.fillRect(pixmap.rect(), QColor(128, 128, 128, 150))
        elif status == 'failed':
            painter.setOpacity(1.0)
            painter.setPen(QPen(QColor(255, 0, 0), 2))
            painter.drawLine(4, 4, 18, 18)
            painter.drawLine(18, 4, 4, 18)

        painter.end()
        self._overlay_cache[status] = pixmap
        return pixmap

    def _get_status_tooltip(self, host_name: str, upload_data: Dict) -> str:
        """Generate tooltip text for a file host icon."""
        status = upload_data.get('status', 'not_uploaded')
        status_labels = {
            'not_uploaded': 'Click to upload',
            'pending': 'Pending',
            'uploading': 'Uploading...',
            'completed': 'Completed',
            'failed': 'Failed - click to retry',
        }
        status_text = status_labels.get(status, status.title())
        
        # Add download URL if completed
        download_url = upload_data.get('download_url', '')
        if status == 'completed' and download_url:
            return f"{host_name}: {status_text}\n{download_url}"
        
        # Add error message if failed
        error_msg = upload_data.get('error_message', '')
        if status == 'failed' and error_msg:
            return f"{host_name}: {status_text}\n{error_msg[:100]}"
        
        return f"{host_name}: {status_text}"

    def _compute_icon_rects(self, cell_rect: QRect, host_uploads: Dict) -> List[Tuple[str, QRect]]:
        """Compute icon rectangles for all hosts within a cell."""
        icon_manager = get_icon_manager()
        if not icon_manager:
            return []

        enabled_hosts = self._get_enabled_hosts()
        all_hosts = set(enabled_hosts.keys()) | set(host_uploads.keys())
        sorted_hosts = sorted(all_hosts, key=str.lower)

        icon_rects: List[Tuple[str, QRect]] = []
        x = cell_rect.x() + self.PADDING
        y = cell_rect.y() + (cell_rect.height() - self.ICON_SIZE) // 2

        for host_name in sorted_hosts:
            icon = icon_manager.get_file_host_icon(host_name, dimmed=True)
            if icon.isNull():
                continue
            icon_rects.append((host_name, QRect(x, y, self.ICON_SIZE, self.ICON_SIZE)))
            x += self.ICON_SIZE + self.ICON_SPACING

        return icon_rects

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        # Paint the cell background first (handles alternating rows and selection)
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter, option.widget)

        path = index.data(Qt.ItemDataRole.UserRole)
        host_uploads = index.data(Qt.ItemDataRole.UserRole + 1) or {}

        if not path:
            return

        icon_manager = get_icon_manager()
        if not icon_manager:
            return

        # Compute icon positions for this cell
        icon_rects = self._compute_icon_rects(option.rect, host_uploads)

        for host_name, icon_rect in icon_rects:
            upload = host_uploads.get(host_name, {})
            status = upload.get('status', 'not_uploaded')

            use_dimmed = (status != 'completed')
            icon = icon_manager.get_file_host_icon(host_name, dimmed=use_dimmed)
            if icon.isNull():
                continue

            pixmap = icon.pixmap(QSize(self.ICON_SIZE, self.ICON_SIZE))
            painter.drawPixmap(icon_rect, pixmap)

            overlay = self._get_overlay_pixmap(status)
            if not overlay.isNull() and status in ('uploading', 'pending', 'failed'):
                painter.drawPixmap(icon_rect, overlay)

    def editorEvent(self, event, model, option, index) -> bool:
        if event.type() == QEvent.Type.MouseButtonRelease:
            path = index.data(Qt.ItemDataRole.UserRole)
            if not path:
                return super().editorEvent(event, model, option, index)
            
            host_uploads = index.data(Qt.ItemDataRole.UserRole + 1) or {}
            # Compute positions fresh using current cell rect
            icon_rects = self._compute_icon_rects(option.rect, host_uploads)
            
            pos = event.position().toPoint()
            for host_name, rect in icon_rects:
                if rect.contains(pos):
                    self.signals.host_clicked.emit(path, host_name)
                    return True
        return super().editorEvent(event, model, option, index)

    def helpEvent(self, event, view, option, index):
        """Show tooltip on hover over file host icons."""
        if event.type() == QEvent.Type.ToolTip:
            host_uploads = index.data(Qt.ItemDataRole.UserRole + 1) or {}
            # Compute positions fresh using current cell rect
            icon_rects = self._compute_icon_rects(option.rect, host_uploads)
            
            pos = event.pos()
            for host_name, rect in icon_rects:
                if rect.contains(pos):
                    upload_data = host_uploads.get(host_name, {})
                    tooltip = self._get_status_tooltip(host_name, upload_data)
                    QToolTip.showText(event.globalPos(), tooltip, view)
                    return True
            
            # Hide tooltip if not hovering over any icon
            QToolTip.hideText()
        return super().helpEvent(event, view, option, index)

    def sizeHint(self, option, index) -> QSize:
        enabled_hosts = self._get_enabled_hosts()
        num_hosts = max(1, len(enabled_hosts))
        width = self.PADDING * 2 + num_hosts * (self.ICON_SIZE + self.ICON_SPACING)
        return QSize(width, self.ICON_SIZE + 4)
