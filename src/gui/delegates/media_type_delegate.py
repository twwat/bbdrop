"""Media type delegate for rendering photo/video icons in table cells."""

from PyQt6.QtCore import Qt, QRect, QSize, QModelIndex
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle

from src.gui.icon_manager import get_icon_manager


class MediaTypeDelegate(QStyledItemDelegate):
    """Renders a photo or video icon based on the cell's media type value."""

    ICON_SIZE = 18

    _ICON_KEYS = {
        'image': 'media_photo',
        'video': 'media_video',
    }

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        style = option.widget.style() if option.widget else None
        if style:
            style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter, option.widget)

        media_type = index.data(Qt.ItemDataRole.UserRole) or 'image'
        icon_key = self._ICON_KEYS.get(media_type, 'media_photo')

        icon_mgr = get_icon_manager()
        if icon_mgr is None:
            return

        icon = icon_mgr.get_icon(icon_key)
        if icon.isNull():
            return

        # Center the icon in the cell
        cell = option.rect
        x = cell.x() + (cell.width() - self.ICON_SIZE) // 2
        y = cell.y() + (cell.height() - self.ICON_SIZE) // 2
        icon_rect = QRect(x, y, self.ICON_SIZE, self.ICON_SIZE)

        pixmap = icon.pixmap(QSize(self.ICON_SIZE, self.ICON_SIZE))
        painter.drawPixmap(icon_rect, pixmap)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(self.ICON_SIZE + 8, self.ICON_SIZE + 4)
