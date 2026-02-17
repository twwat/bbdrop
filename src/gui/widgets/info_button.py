"""Reusable info button that shows a popover with help content on click."""

from PyQt6.QtWidgets import QToolButton, QFrame, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, QPoint


class InfoButton(QToolButton):
    """A small icon button that shows an HTML popover when clicked."""

    _active_popover = None
    _active_source = None

    def __init__(self, html: str, parent=None):
        super().__init__(parent)
        self._html = html
        self._setup_button()
        self.clicked.connect(self._toggle_popover)

    def _setup_button(self):
        fm = self.fontMetrics()
        size = max(fm.height() + 4, 16)
        self.setFixedSize(size, size)
        self.setAutoRaise(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        from src.gui.icon_manager import get_icon_manager
        icon_mgr = get_icon_manager()
        if icon_mgr:
            self.setIcon(icon_mgr.get_icon('more_info'))

    def _toggle_popover(self):
        # Close any existing popover
        if InfoButton._active_popover is not None:
            InfoButton._active_popover.close()
            InfoButton._active_popover.deleteLater()
            was_self = InfoButton._active_source is self
            InfoButton._active_popover = None
            InfoButton._active_source = None
            if was_self:
                return

        popover = QFrame(self.window(), Qt.WindowType.Popup)
        popover.setProperty("class", "info-popover")

        layout = QVBoxLayout(popover)
        layout.setContentsMargins(12, 10, 12, 10)

        label = QLabel(self._html)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(label)

        popover.adjustSize()

        global_pos = self.mapToGlobal(QPoint(0, self.height() + 4))
        popover.move(global_pos)
        popover.show()

        InfoButton._active_popover = popover
        InfoButton._active_source = self
