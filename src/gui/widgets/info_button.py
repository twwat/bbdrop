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
        # Clean up stale popover (e.g. disappeared after alt-tab, or parent deleted)
        if InfoButton._active_popover is not None:
            try:
                still_visible = InfoButton._active_popover.isVisible()
            except RuntimeError:
                # C++ object deleted — clear the reference
                InfoButton._active_popover = None
                InfoButton._active_source = None
                still_visible = False
            if not still_visible and InfoButton._active_popover is not None:
                InfoButton._active_popover.deleteLater()
                InfoButton._active_popover = None
                InfoButton._active_source = None

        # Close any existing popover
        if InfoButton._active_popover is not None:
            try:
                InfoButton._active_popover.close()
                InfoButton._active_popover.deleteLater()
            except RuntimeError:
                pass
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
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        label.setOpenExternalLinks(True)
        layout.addWidget(label)

        # Constrain popup to application window
        win = self.window()
        win_rect = win.geometry()
        max_w = win_rect.width() - 40
        if max_w > 0:
            popover.setMaximumWidth(max_w)

        popover.adjustSize()

        # Position below the button, then adjust to stay inside the window
        btn_global = self.mapToGlobal(QPoint(0, self.height() + 4))
        x = btn_global.x()
        y = btn_global.y()
        pw = popover.sizeHint().width()
        ph = popover.sizeHint().height()

        win_global_tl = win_rect.topLeft()
        win_global_br = win_rect.bottomRight()

        # If popup would go below window bottom, show above button instead
        if y + ph > win_global_br.y():
            y = self.mapToGlobal(QPoint(0, 0)).y() - ph - 4

        # If popup would go off right edge, shift left
        if x + pw > win_global_br.x():
            x = win_global_br.x() - pw

        # Clamp left edge
        if x < win_global_tl.x():
            x = win_global_tl.x()

        popover.move(x, y)
        popover.show()

        InfoButton._active_popover = popover
        InfoButton._active_source = self
