"""Forum composer dialog — v2 multi-destination.

Always accessible. Pre-fills from get_effective_destinations(). Allows
adding/removing destinations per gallery. Supports bulk (N galleries).
Each gallery row shows N destination slots; each slot has a target picker,
template combo, and editable body.

Public interface (unchanged):
    ForumComposerDialog(conn, controller, gallery_ids, parent=None).exec()
"""

from __future__ import annotations

import os
import sqlite3
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout, QLabel,
    QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout,
    QWidget,
)

import src.storage.forum_posting as fp
from src.gui.widgets.forum_target_picker import ForumTargetPicker
from src.utils.templates import load_templates


class _DestSlot(QFrame):
    """One destination slot within a gallery row."""

    def __init__(self, conn, dest: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.Box)
        self._conn = conn
        self._build(dest or {})

    def _build(self, dest: dict):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        target_row = QHBoxLayout()
        self._picker = ForumTargetPicker(self._conn)
        if dest.get("forum_fk") and dest.get("target_id"):
            self._picker.set_targets([{
                "forum_fk": dest["forum_fk"],
                "forum_name": dest.get("forum_name", ""),
                "target_id": dest["target_id"],
                "kind": dest["kind"],
                "name": dest.get("target_name") or str(dest.get("target_id", "")),
            }])
        target_row.addWidget(self._picker, 1)

        self._template_combo = QComboBox()
        self._template_combo.setMinimumWidth(130)
        for name in load_templates().keys():
            self._template_combo.addItem(name, name)
        if dest.get("body_template_name"):
            idx = self._template_combo.findData(dest["body_template_name"])
            if idx >= 0:
                self._template_combo.setCurrentIndex(idx)
        target_row.addWidget(self._template_combo)

        remove_btn = QPushButton("×")
        remove_btn.setFixedWidth(28)
        remove_btn.setToolTip("Remove this destination")
        remove_btn.clicked.connect(self._request_remove)
        target_row.addWidget(remove_btn)
        layout.addLayout(target_row)

        self._body_edit = QPlainTextEdit()
        self._body_edit.setMaximumHeight(100)
        self._body_edit.setPlaceholderText("Post body (edit before posting)…")
        layout.addWidget(self._body_edit)

    def _request_remove(self):
        p = self.parent()
        while p and not isinstance(p, _GalleryRow):
            p = p.parent()
        if p:
            p.remove_slot(self)

    def get_destination(self) -> Optional[dict]:
        targets = self._picker.get_targets()
        if not targets:
            return None
        t = targets[0]
        return {
            "forum_fk": t["forum_fk"],
            "target_id": t["target_id"],
            "kind": t["kind"],
            "body_template_name": self._template_combo.currentData(),
            "forum_name": t.get("forum_name", ""),
            "_body_override": self._body_edit.toPlainText().strip() or None,
        }


class _GalleryRow(QFrame):
    """One gallery with its destination slots."""

    def __init__(self, conn, gallery_id: int, controller, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.gallery_id = gallery_id
        self._conn = conn
        self._controller = controller
        self._slots: list[_DestSlot] = []
        self.skip_gallery = False
        self._no_config: bool = False  # True when no effective destinations exist
        self._build()

    def _gallery_label(self) -> str:
        row = self._conn.execute(
            "SELECT name, path FROM galleries WHERE id=?", (self.gallery_id,)
        ).fetchone()
        if not row:
            return f"Gallery {self.gallery_id}"
        name = row[0] if row[0] else None
        path = row[1] if row[1] else None
        return name or (os.path.basename(path) if path else f"Gallery {self.gallery_id}")

    def _build(self):
        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        header.addWidget(QLabel(f"<b>{self._gallery_label()}</b>"))
        self._skip_check = QCheckBox("Skip gallery")
        self._skip_check.toggled.connect(self._on_skip_toggled)
        header.addStretch()
        header.addWidget(self._skip_check)
        layout.addLayout(header)

        self._slots_container = QWidget()
        self._slots_layout = QVBoxLayout(self._slots_container)
        self._slots_layout.setSpacing(4)
        layout.addWidget(self._slots_container)

        add_btn = QPushButton("+ Add destination")
        add_btn.clicked.connect(self._add_empty_slot)
        layout.addWidget(add_btn)

        dests = fp.get_effective_destinations(self._conn, self.gallery_id)
        if dests:
            for dest in dests:
                self._add_slot(dest)
        else:
            self._no_config = True
            self._add_slot(None)

    def _add_slot(self, dest: Optional[dict]):
        slot = _DestSlot(self._conn, dest, parent=self._slots_container)
        self._slots.append(slot)
        self._slots_layout.addWidget(slot)

    def _add_empty_slot(self):
        self._add_slot(None)

    def remove_slot(self, slot: _DestSlot):
        if slot in self._slots:
            self._slots.remove(slot)
        self._slots_layout.removeWidget(slot)
        slot.deleteLater()

    def _on_skip_toggled(self, checked: bool):
        self.skip_gallery = checked
        self._slots_container.setEnabled(not checked)

    def get_destinations(self) -> list[dict]:
        if self.skip_gallery:
            return []
        return [d for slot in self._slots if (d := slot.get_destination()) is not None]

    @property
    def body_edit(self):
        """Return the first slot's body editor (test/compat helper)."""
        if self._slots:
            return self._slots[0]._body_edit
        return None


class ForumComposerDialog(QDialog):
    """Multi-gallery, multi-destination forum post composer."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        controller,
        gallery_ids: list[int],
        parent=None,
    ):
        super().__init__(parent)
        n = len(gallery_ids)
        self.setWindowTitle(
            f"Post to Forum — {n} {'gallery' if n == 1 else 'galleries'}"
        )
        self.resize(640, 560)
        self._conn = conn
        self._controller = controller
        self._rows: list[_GalleryRow] = []
        self._build_ui(gallery_ids)

    def _build_ui(self, gallery_ids: list[int]):
        outer = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setSpacing(8)

        for gid in gallery_ids:
            row = _GalleryRow(self._conn, gid, self._controller, parent=content)
            self._rows.append(row)
            self._content_layout.addWidget(row)

        self._content_layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        n = len(gallery_ids)
        self._post_btn = QPushButton(f"Post {n} selected")
        self._post_btn.setDefault(True)
        self._post_btn.clicked.connect(self._post_all)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(cancel)
        btn_row.addWidget(self._post_btn)
        outer.addLayout(btn_row)

    def _post_all(self):
        any_posted = False
        errors: list[str] = []
        for row in self._rows:
            dests = row.get_destinations()
            if not dests:
                continue
            try:
                self._controller.post_now(row.gallery_id, dests)
                any_posted = True
            except Exception as exc:
                errors.append(f"Gallery {row.gallery_id}: {exc}")

        if errors:
            QMessageBox.warning(
                self, "Post errors",
                "Some posts failed:\n" + "\n".join(errors),
            )
        if any_posted:
            self.accept()
        elif not errors:
            QMessageBox.information(
                self, "Nothing to post",
                "All galleries were skipped or had no destinations selected.",
            )

    # ---- backward-compatible test/public helpers ----

    def post_all(self) -> None:
        """Public alias for _post_all (used by tests and callers)."""
        self._post_all()

    def row_count(self) -> int:
        """Number of gallery rows in the dialog."""
        return len(self._rows)

    def has_warning(self, idx: int) -> bool:
        """True if the gallery at *idx* has no effective destinations configured."""
        return self._rows[idx]._no_config

    def set_skipped(self, idx: int, skipped: bool) -> None:
        """Programmatically skip (or unskip) a gallery row."""
        self._rows[idx]._skip_check.setChecked(skipped)
