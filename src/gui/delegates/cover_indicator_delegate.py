"""Cover indicator delegate for table cell rendering."""

import os
from PyQt6.QtCore import Qt, QRect, QSize, QModelIndex, QEvent
from PyQt6.QtGui import QPainter, QPixmap, QColor, QPen
from PyQt6.QtWidgets import (
    QStyledItemDelegate, QStyleOptionViewItem, QApplication, QStyle, QToolTip
)

from src.gui.icon_manager import get_icon_manager
from src.utils.logger import log


class CoverIndicatorDelegate(QStyledItemDelegate):
    """Delegate that paints a cover icon with visual status states.

    UserRole: cover_source_path (semicolon-delimited paths)
    UserRole+1: cover_status ("none", "pending", "uploading", "completed", "partial", "failed")
    """

    ICON_SIZE = 18

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._dimmed_pixmap: QPixmap | None = None
        self._overlay_cache: dict[str, QPixmap] = {}
        self._warned = False

    def _ensure_pixmaps(self) -> tuple[QPixmap | None, QPixmap | None]:
        if self._pixmap is not None:
            return self._pixmap, self._dimmed_pixmap
        icon_mgr = get_icon_manager()
        if not icon_mgr:
            if not self._warned:
                log("CoverIndicatorDelegate: icon manager unavailable", level="warning", category="gui")
                self._warned = True
            return None, None
        icon = icon_mgr.get_icon('cover_photo')
        if icon and not icon.isNull():
            self._pixmap = icon.pixmap(QSize(self.ICON_SIZE, self.ICON_SIZE))
            # Generate dimmed version at 40% opacity
            self._dimmed_pixmap = QPixmap(self.ICON_SIZE, self.ICON_SIZE)
            self._dimmed_pixmap.fill(Qt.GlobalColor.transparent)
            p = QPainter(self._dimmed_pixmap)
            p.setOpacity(0.4)
            p.drawPixmap(0, 0, self._pixmap)
            p.end()
            return self._pixmap, self._dimmed_pixmap
        if not self._warned:
            log("CoverIndicatorDelegate: 'cover_photo' icon not found", level="warning", category="gui")
            self._warned = True
        return None, None

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
        elif status == 'failed':
            painter.setOpacity(1.0)
            painter.setPen(QPen(QColor(255, 0, 0), 2))
            painter.drawLine(3, 3, 15, 15)
            painter.drawLine(15, 3, 3, 15)
        elif status == 'partial':
            painter.setOpacity(1.0)
            painter.setPen(QPen(QColor(255, 165, 0), 2))
            painter.drawLine(3, 3, 15, 15)
            painter.drawLine(15, 3, 3, 15)

        painter.end()
        self._overlay_cache[status] = pixmap
        return pixmap

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter, option.widget)

        cover_path = index.data(Qt.ItemDataRole.UserRole)
        if not cover_path:
            return

        cover_status = index.data(Qt.ItemDataRole.UserRole + 1) or "pending"

        full_pixmap, dimmed_pixmap = self._ensure_pixmaps()
        if full_pixmap is None:
            return

        # Choose icon based on status
        use_dimmed = cover_status in ("pending", "uploading")
        pixmap = dimmed_pixmap if use_dimmed else full_pixmap

        icon_rect = QRect(
            option.rect.x() + (option.rect.width() - self.ICON_SIZE) // 2,
            option.rect.y() + (option.rect.height() - self.ICON_SIZE) // 2,
            self.ICON_SIZE, self.ICON_SIZE
        )
        painter.drawPixmap(icon_rect, pixmap)

        # Draw overlay for uploading/failed/partial
        if cover_status in ('uploading', 'failed', 'partial'):
            overlay = self._get_overlay_pixmap(cover_status)
            if not overlay.isNull():
                painter.drawPixmap(icon_rect, overlay)

    def helpEvent(self, event, view, option, index):
        if event.type() == QEvent.Type.ToolTip:
            cover_path = index.data(Qt.ItemDataRole.UserRole)
            cover_status = index.data(Qt.ItemDataRole.UserRole + 1) or "pending"
            if cover_path:
                paths = [p.strip() for p in cover_path.split(';') if p.strip()]
                names = [os.path.basename(p) for p in paths]
                status_labels = {
                    'none': 'No covers',
                    'pending': 'Pending upload',
                    'uploading': 'Uploading...',
                    'completed': 'Uploaded',
                    'partial': 'Partially uploaded',
                    'failed': 'Upload failed',
                }
                status_text = status_labels.get(cover_status, cover_status)
                tooltip = f"Covers ({status_text}):\n" + "\n".join(f"  {n}" for n in names)
                QToolTip.showText(event.globalPos(), tooltip, view)
                return True
        return super().helpEvent(event, view, option, index)

    def sizeHint(self, option, index) -> QSize:
        return QSize(28, self.ICON_SIZE + 4)
