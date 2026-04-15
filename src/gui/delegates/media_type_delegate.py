"""Media type delegate for rendering photo/video icons in table cells."""

from PyQt6.QtCore import QEvent, Qt, QRect, QSize, QModelIndex
from PyQt6.QtGui import QHelpEvent, QPainter
from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle, QToolTip

from src.gui.icon_manager import get_icon_manager
from src.gui.widgets.video_sheet_utils import resolve_sheet_path
from src.utils.logger import log


class MediaTypeDelegate(QStyledItemDelegate):
    """Renders a photo or video icon based on the cell's media type value.

    For video cells, also handles a hover preview tooltip via ``helpEvent``.
    """

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

        cell = option.rect
        x = cell.x() + (cell.width() - self.ICON_SIZE) // 2
        y = cell.y() + (cell.height() - self.ICON_SIZE) // 2
        icon_rect = QRect(x, y, self.ICON_SIZE, self.ICON_SIZE)

        pixmap = icon.pixmap(QSize(self.ICON_SIZE, self.ICON_SIZE))
        painter.drawPixmap(icon_rect, pixmap)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(self.ICON_SIZE + 8, self.ICON_SIZE + 4)

    def helpEvent(self, event: QHelpEvent, view, option: QStyleOptionViewItem,
                  index: QModelIndex) -> bool:
        """Show a hover preview of the screenshot sheet for video rows."""
        if event is None or event.type() != QEvent.Type.ToolTip:
            return super().helpEvent(event, view, option, index)

        media_type = index.data(Qt.ItemDataRole.UserRole) or 'image'
        if media_type != 'video':
            return super().helpEvent(event, view, option, index)

        item = self._resolve_item(view, index)
        if item is None:
            return super().helpEvent(event, view, option, index)

        sheet_path = resolve_sheet_path(item)
        if not sheet_path:
            QToolTip.showText(event.globalPos(),
                              "Screenshot sheet not yet generated",
                              view, option.rect)
            return True

        QToolTip.showText(event.globalPos(),
                          "Screenshot sheet preview",
                          view, option.rect)
        return True

    def _resolve_item(self, view, index: QModelIndex):
        """Resolve the gallery queue item for a given media-type cell."""
        try:
            from src.gui.widgets.gallery_table import GalleryTableWidget
            model = index.model()
            if model is None:
                return None
            name_index = model.index(index.row(), GalleryTableWidget.COL_NAME)
            path = name_index.data(Qt.ItemDataRole.UserRole)
            if not path:
                return None

            window = view.window() if view is not None else None
            qm = getattr(window, 'queue_manager', None)
            if qm is None and view is not None:
                qm = getattr(view, 'queue_manager', None)
            if qm is None:
                return None
            return qm.get_item(path)
        except Exception as e:
            log(f"MediaTypeDelegate._resolve_item failed: {e}",
                level="warning", category="ui")
            return None
