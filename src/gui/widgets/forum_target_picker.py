"""Pill-based multi-select forum target picker.

Displays selected targets as coloured pills (blue=subforum, green=thread)
with × remove buttons. The "+ Add" button opens a popup panel where the
user can check multiple targets across multiple forums in one operation.

Usage:
    picker = ForumTargetPicker(conn)
    picker.set_targets([...])          # pre-fill
    picker.targets_changed.connect(cb) # list[dict] of selected targets
    selected = picker.get_targets()
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLayout, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QSizePolicy, QToolButton,
    QVBoxLayout, QWidget,
)

import src.storage.forum_posting as fp
from src.gui.widgets.target_kind_delegate import (
    TARGET_KIND_ROLE, TARGET_TID_ROLE, TargetKindDelegate,
)

_PILL_COLORS = {
    "subforum": "#2f6aa1",
    "thread": "#3d874a",
}


class _FlowLayout(QLayout):
    """Wrapping horizontal layout. Children flow left-to-right and wrap
    onto a new row when they would exceed the container's width. Used so
    a long list of pills can never push the parent dialog wider than the
    screen — the dialog grows downward instead."""

    def __init__(self, parent=None, spacing=4):
        super().__init__(parent)
        self._items: list = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect, test_only):
        x = rect.x()
        y = rect.y()
        line_h = 0
        for item in self._items:
            wid = item.sizeHint()
            next_x = x + wid.width() + self._spacing
            if next_x - self._spacing > rect.right() and line_h > 0:
                x = rect.x()
                y = y + line_h + self._spacing
                next_x = x + wid.width() + self._spacing
                line_h = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), wid))
            x = next_x
            line_h = max(line_h, wid.height())
        return y + line_h - rect.y()


class ForumTargetPicker(QWidget):
    """Pill strip + popup multi-select for forum targets."""

    targets_changed = pyqtSignal(list)

    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._selected: list[dict] = []
        self._build_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_targets(self, targets: list[dict]) -> None:
        self._selected = list(targets)
        self._refresh_pills()

    def get_targets(self) -> list[dict]:
        return list(self._selected)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._pill_container = QWidget()
        self._pill_container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred,
        )
        self._pill_layout = _FlowLayout(self._pill_container, spacing=4)

        self._add_btn = QPushButton("+ Add")
        self._add_btn.setFixedWidth(60)
        self._add_btn.clicked.connect(self._open_picker)

        layout.addWidget(self._pill_container, 1)
        layout.addWidget(self._add_btn, 0, Qt.AlignmentFlag.AlignTop)

    def _refresh_pills(self):
        while self._pill_layout.count():
            item = self._pill_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        for target in self._selected:
            self._pill_layout.addWidget(self._make_pill(target))
        self._pill_container.updateGeometry()

    def _make_pill(self, target: dict) -> QWidget:
        kind = target.get("kind", "thread")
        name = (target.get("name")
                or target.get("target_name")
                or f"#{target.get('target_id', '?')}")
        bg = _PILL_COLORS.get(kind, "#666666")

        pill = QFrame()
        pill.setStyleSheet(
            f"QFrame {{ background-color: {bg}; border-radius: 2px; }}"
        )
        lay = QHBoxLayout(pill)
        lay.setContentsMargins(5, 0, 1, 0)
        lay.setSpacing(0)

        lbl = QLabel(name)
        lbl.setStyleSheet(
            "color: white; font-size: 10px; background: transparent; padding: 0px;"
        )
        lay.addWidget(lbl)

        close = QToolButton()
        close.setText("×")
        close.setFixedSize(14, 14)
        close.setStyleSheet(
            "QToolButton { color: white; border: none; font-size: 11px; "
            "background: transparent; padding: 0px; }"
            "QToolButton:hover { color: #ffdddd; }"
        )
        close.clicked.connect(lambda _checked, t=target: self._remove_target(t))
        lay.addWidget(close)

        return pill

    # ------------------------------------------------------------------
    # Internal handlers
    # ------------------------------------------------------------------

    def _remove_target(self, target: dict) -> None:
        key = (target["forum_fk"], target["target_id"])
        self._selected = [
            t for t in self._selected
            if (t["forum_fk"], t["target_id"]) != key
        ]
        self._refresh_pills()
        self.targets_changed.emit(list(self._selected))

    def _open_picker(self) -> None:
        panel = _TargetPickerPanel(self._conn, self._selected, parent=self)
        panel.targets_selected.connect(self._on_picker_confirmed)
        pos = self._add_btn.mapToGlobal(self._add_btn.rect().bottomLeft())
        panel.move(pos)
        panel.show()
        panel.raise_()

    def _on_picker_confirmed(self, targets: list[dict]) -> None:
        self._selected = targets
        self._refresh_pills()
        self.targets_changed.emit(list(self._selected))


class _TargetPickerPanel(QFrame):
    """Popup panel with search + grouped multi-select list across all forums."""

    targets_selected = pyqtSignal(list)

    def __init__(self, conn, current: list[dict], parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self._conn = conn
        self._checked_keys = {(t["forum_fk"], t["target_id"]) for t in current}
        # Pre-selected targets by key: one the library no longer lists is
        # never rendered, so it can't be deselected and must survive _accept.
        self._current_by_key = {(t["forum_fk"], t["target_id"]): t for t in current}
        self._rendering = False
        self._all: list[dict] = []
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.resize(380, 320)
        self._build_ui()
        self._load()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search targets…")
        self._search.textChanged.connect(self._filter)
        layout.addWidget(self._search)

        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self._list.setItemDelegate(TargetKindDelegate(self._list))
        self._list.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._list, 1)

        btns = QHBoxLayout()
        ok = QPushButton("Add selected")
        ok.clicked.connect(self._accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.close)
        btns.addStretch()
        btns.addWidget(cancel)
        btns.addWidget(ok)
        layout.addLayout(btns)

    def _load(self):
        forums = fp.list_forums(self._conn, enabled_only=False)
        for forum in forums:
            for t in fp.list_targets(self._conn, forum["id"]):
                self._all.append({
                    "forum_fk": forum["id"],
                    "forum_name": forum["name"],
                    "target_id": t["target_id"],
                    "kind": t["kind"],
                    "name": t["name"],
                })
        self._render(self._all)

    def _render(self, targets: list[dict]):
        # clear() and the setSelected() calls below emit itemSelectionChanged.
        # They mirror _checked_keys rather than user input, so
        # _on_selection_changed must not fold them back in.
        self._rendering = True
        try:
            self._list.clear()
            current_forum: Optional[str] = None
            for t in targets:
                if t["forum_name"] != current_forum:
                    header = QListWidgetItem(t["forum_name"])
                    header.setFlags(Qt.ItemFlag.NoItemFlags)
                    f = header.font()
                    f.setBold(True)
                    header.setFont(f)
                    header.setForeground(QColor("#888888"))
                    self._list.addItem(header)
                    current_forum = t["forum_name"]

                item = QListWidgetItem(t["name"])
                item.setData(Qt.ItemDataRole.UserRole, t)
                item.setData(TARGET_KIND_ROLE, t["kind"])
                item.setData(TARGET_TID_ROLE, t["target_id"])
                self._list.addItem(item)
                if (t["forum_fk"], t["target_id"]) in self._checked_keys:
                    item.setSelected(True)
        finally:
            self._rendering = False

    def _filter(self, text: str):
        q = text.lower()
        filtered = [
            t for t in self._all
            if q in t["name"].lower() or q in t["forum_name"].lower()
        ]
        self._render(filtered)

    def _on_selection_changed(self) -> None:
        """Fold the visible rows' selection into _checked_keys.

        Rows hidden by the current search aren't in the list, so their keys
        are left as they were.
        """
        if self._rendering:
            return
        for i in range(self._list.count()):
            item = self._list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            if not data:
                continue  # forum header row
            key = (data["forum_fk"], data["target_id"])
            if item.isSelected():
                self._checked_keys.add(key)
            else:
                self._checked_keys.discard(key)

    def _accept(self):
        # Build from _checked_keys, not the visible rows, so selections the
        # current search hides are kept (library order, as before 380251d).
        library_keys = set()
        selected: list[dict] = []
        for t in self._all:
            key = (t["forum_fk"], t["target_id"])
            library_keys.add(key)
            if key in self._checked_keys:
                selected.append(t)
        selected.extend(
            t for key, t in self._current_by_key.items()
            if key in self._checked_keys and key not in library_keys
        )
        self.targets_selected.emit(selected)
        self.close()
