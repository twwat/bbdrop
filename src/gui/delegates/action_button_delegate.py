"""Action button delegate for table cell rendering."""

from PyQt6.QtCore import Qt, QRect, QSize, QModelIndex, QEvent, pyqtSignal, QObject
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import (
    QStyledItemDelegate, QStyleOptionViewItem, QApplication, QStyle, QToolTip
)

from src.gui.icon_manager import get_icon_manager


class ActionButtonDelegateSignals(QObject):
    """Signals for ActionButtonDelegate."""
    __slots__ = ()
    button_clicked = pyqtSignal(str, str)  # (gallery_path, action)


class ActionButtonDelegate(QStyledItemDelegate):
    """Delegate for rendering action buttons in table cells."""

    BUTTON_SIZE = 22
    ICON_SIZE = 18
    PADDING = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self.signals = ActionButtonDelegateSignals()
        self._queue_manager = None

    @property
    def button_clicked(self):
        return self.signals.button_clicked

    def set_queue_manager(self, queue_manager):
        self._queue_manager = queue_manager

    def _get_status_for_path(self, path: str) -> str:
        if self._queue_manager and path:
            item = self._queue_manager.get_item(path)
            if item:
                return item.status
        return "ready"

    def _get_button_config(self, status: str) -> tuple:
        configs = {
            "ready": ("action_start", "start", "Start upload"),
            "queued": ("action_cancel", "cancel", "Cancel from queue"),
            "pending": ("action_cancel", "cancel", "Cancel from queue"),
            "uploading": ("action_stop", "stop", "Stop upload"),
            "paused": ("action_resume", "start", "Resume upload"),
            "incomplete": ("action_resume", "start", "Resume upload"),
            "completed": ("action_view", "view", "View BBCode"),
            "failed": ("action_view_error", "view_error", "View error details"),
        }
        return configs.get(status, ("", "", ""))

    def _compute_button_rect(self, cell_rect) -> QRect:
        """Compute button rectangle for a cell."""
        button_x = cell_rect.x() + self.PADDING
        button_y = cell_rect.y() + (cell_rect.height() - self.BUTTON_SIZE) // 2
        return QRect(button_x, button_y, self.BUTTON_SIZE, self.BUTTON_SIZE)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        # First, paint the default background (handles alternating rows and selection)
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter, option.widget)

        path = index.data(Qt.ItemDataRole.UserRole)
        if not path:
            return

        status = self._get_status_for_path(path)
        icon_key, action, tooltip = self._get_button_config(status)

        if not icon_key:
            return

        icon_manager = get_icon_manager()
        if not icon_manager:
            return

        icon = icon_manager.get_icon(icon_key)
        if icon.isNull():
            return

        button_rect = self._compute_button_rect(option.rect)
        icon_rect = QRect(
            button_rect.x() + (self.BUTTON_SIZE - self.ICON_SIZE) // 2,
            button_rect.y() + (self.BUTTON_SIZE - self.ICON_SIZE) // 2,
            self.ICON_SIZE, self.ICON_SIZE
        )

        pixmap = icon.pixmap(QSize(self.ICON_SIZE, self.ICON_SIZE))
        painter.drawPixmap(icon_rect, pixmap)

    def editorEvent(self, event, model, option, index) -> bool:
        if event.type() == QEvent.Type.MouseButtonRelease:
            path = index.data(Qt.ItemDataRole.UserRole)
            if not path:
                return super().editorEvent(event, model, option, index)
            
            # Compute button rect fresh using current cell rect
            button_rect = self._compute_button_rect(option.rect)
            pos = event.position().toPoint()
            
            if button_rect.contains(pos):
                status = self._get_status_for_path(path)
                _, action, _ = self._get_button_config(status)
                if action:
                    self.signals.button_clicked.emit(path, action)
                    return True
        return super().editorEvent(event, model, option, index)

    def helpEvent(self, event, view, option, index):
        """Show tooltip on hover over the button."""
        if event.type() == QEvent.Type.ToolTip:
            path = index.data(Qt.ItemDataRole.UserRole)
            if path:
                status = self._get_status_for_path(path)
                _, _, tooltip = self._get_button_config(status)
                if tooltip:
                    QToolTip.showText(event.globalPos(), tooltip, view)
                    return True
        return super().helpEvent(event, view, option, index)

    def sizeHint(self, option, index) -> QSize:
        return QSize(self.BUTTON_SIZE + self.PADDING * 2, self.BUTTON_SIZE + 4)
