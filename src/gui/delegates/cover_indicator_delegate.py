"""Cover indicator delegate for table cell rendering."""

import os
from PyQt6.QtCore import Qt, QRect, QSize, QModelIndex, QEvent
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtWidgets import (
    QStyledItemDelegate, QStyleOptionViewItem, QApplication, QStyle, QToolTip
)

from src.gui.icon_manager import get_icon_manager
from src.utils.logger import log


class CoverIndicatorDelegate(QStyledItemDelegate):
    """Delegate that paints a cached cover icon when UserRole data is set."""

    ICON_SIZE = 18

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._warned = False

    def _ensure_pixmap(self) -> QPixmap | None:
        if self._pixmap is not None:
            return self._pixmap
        icon_mgr = get_icon_manager()
        if not icon_mgr:
            if not self._warned:
                log("CoverIndicatorDelegate: icon manager unavailable", level="warning", category="gui")
                self._warned = True
            return None
        icon = icon_mgr.get_icon('cover_photo')
        if icon and not icon.isNull():
            self._pixmap = icon.pixmap(QSize(self.ICON_SIZE, self.ICON_SIZE))
            return self._pixmap
        if not self._warned:
            log("CoverIndicatorDelegate: 'cover_photo' icon not found", level="warning", category="gui")
            self._warned = True
        return None

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter, option.widget)

        cover_path = index.data(Qt.ItemDataRole.UserRole)
        if not cover_path:
            return

        pixmap = self._ensure_pixmap()
        if pixmap is None:
            return

        icon_rect = QRect(
            option.rect.x() + (option.rect.width() - self.ICON_SIZE) // 2,
            option.rect.y() + (option.rect.height() - self.ICON_SIZE) // 2,
            self.ICON_SIZE, self.ICON_SIZE
        )
        painter.drawPixmap(icon_rect, pixmap)

    def helpEvent(self, event, view, option, index):
        if event.type() == QEvent.Type.ToolTip:
            cover_path = index.data(Qt.ItemDataRole.UserRole)
            if cover_path:
                QToolTip.showText(event.globalPos(), f"Cover: {os.path.basename(cover_path)}", view)
                return True
        return super().helpEvent(event, view, option, index)

    def sizeHint(self, option, index) -> QSize:
        return QSize(28, self.ICON_SIZE + 4)
