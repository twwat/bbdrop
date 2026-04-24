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

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QToolButton, QVBoxLayout, QWidget,
)

import src.storage.forum_posting as fp

_PILL_COLORS = {
    "subforum": "#2f6aa1",
    "thread": "#3d874a",
}


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
        self._pill_layout = QHBoxLayout(self._pill_container)
        self._pill_layout.setContentsMargins(0, 0, 0, 0)
        self._pill_layout.setSpacing(4)

        self._add_btn = QPushButton("+ Add")
        self._add_btn.setFixedWidth(60)
        self._add_btn.clicked.connect(self._open_picker)

        layout.addWidget(self._pill_container, 1)
        layout.addWidget(self._add_btn)

    def _refresh_pills(self):
        while self._pill_layout.count():
            item = self._pill_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for target in self._selected:
            self._pill_layout.addWidget(self._make_pill(target))
        self._pill_layout.addStretch()

    def _make_pill(self, target: dict) -> QWidget:
        kind = target.get("kind", "thread")
        name = (target.get("name")
                or target.get("target_name")
                or f"#{target.get('target_id', '?')}")
        bg = _PILL_COLORS.get(kind, "#666666")

        pill = QFrame()
        pill.setStyleSheet(
            f"QFrame {{ background-color: {bg}; border-radius: 3px; }}"
        )
        lay = QHBoxLayout(pill)
        lay.setContentsMargins(6, 2, 2, 2)
        lay.setSpacing(2)

        lbl = QLabel(name)
        lbl.setStyleSheet("color: white; font-size: 11px; background: transparent;")
        lay.addWidget(lbl)

        close = QToolButton()
        close.setText("×")
        close.setStyleSheet(
            "QToolButton { color: white; border: none; font-size: 11px; "
            "background: transparent; }"
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
    """Popup panel with search + grouped checkbox list across all forums."""

    targets_selected = pyqtSignal(list)

    def __init__(self, conn, current: list[dict], parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self._conn = conn
        self._current_keys = {(t["forum_fk"], t["target_id"]) for t in current}
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
        self._list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
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

            kind_label = "Subforum" if t["kind"] == "subforum" else "Thread"
            item = QListWidgetItem(
                f"  {t['name']}  ({kind_label} #{t['target_id']})"
            )
            item.setData(Qt.ItemDataRole.UserRole, t)
            checked = (t["forum_fk"], t["target_id"]) in self._current_keys
            item.setCheckState(
                Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            )
            self._list.addItem(item)

    def _filter(self, text: str):
        q = text.lower()
        filtered = [
            t for t in self._all
            if q in t["name"].lower() or q in t["forum_name"].lower()
        ]
        self._render(filtered)

    def _accept(self):
        selected = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if (item.flags() & Qt.ItemFlag.ItemIsEnabled and
                    item.checkState() == Qt.CheckState.Checked):
                data = item.data(Qt.ItemDataRole.UserRole)
                if data:
                    selected.append(data)
        self.targets_selected.emit(selected)
        self.close()
