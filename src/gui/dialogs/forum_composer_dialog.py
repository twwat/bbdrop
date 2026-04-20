"""Manual forum composer dialog.

One row per selected gallery: target, editable title (new_thread only),
editable body, skip toggle, live status. "Post N selected" enqueues each
unskipped row through `forum_controller.post_now`.

Spec: docs/superpowers/specs/2026-04-20-forum-posting-design.md §7.4.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from src.storage import forum_posting as fp


class _GalleryRow(QFrame):
    """Single composer row for one gallery."""

    def __init__(self, conn, gallery_id, controller, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.gallery_id = gallery_id
        self._conn = conn
        self._controller = controller
        self._cfg: Optional[dict] = fp.get_effective_posting_config(
            conn, gallery_id,
        )
        self.warning = False
        self.title_input: Optional[QLineEdit] = None
        self.body_edit: Optional[QPlainTextEdit] = None
        self.status_label: Optional[QLabel] = None
        self._build()

    def _gallery_label(self) -> str:
        row = self._conn.execute(
            "SELECT name, path FROM galleries WHERE id=?",
            (self.gallery_id,),
        ).fetchone()
        if not row:
            return f"Gallery {self.gallery_id}"
        name = row["name"] if isinstance(row, sqlite3.Row) else row[0]
        path = row["path"] if isinstance(row, sqlite3.Row) else row[1]
        if name:
            return name
        if path:
            return os.path.basename(path) or path
        return f"Gallery {self.gallery_id}"

    def _build(self):
        v = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(QLabel(f"<b>{self._gallery_label()}</b>"))
        self.skip_check = QCheckBox("Skip")
        self.skip_check.setChecked(False)
        header.addStretch()
        header.addWidget(self.skip_check)
        v.addLayout(header)

        if not self._cfg:
            self.warning = True
            v.addWidget(QLabel(
                "<i>Configure tab posting first — this gallery cannot "
                "be posted.</i>",
            ))
            return

        v.addWidget(QLabel(
            f"Target: {self._cfg['kind']} → {self._cfg['target_id']} "
            f"(forum {self._cfg['forum_fk']})",
        ))
        try:
            body, title = self._controller.preview_render(self.gallery_id)
        except Exception as e:
            self.warning = True
            v.addWidget(QLabel(f"<i>Render failed: {e}</i>"))
            return

        if self._cfg["kind"] == "new_thread":
            v.addWidget(QLabel("Title:"))
            self.title_input = QLineEdit(title)
            v.addWidget(self.title_input)

        v.addWidget(QLabel("Body:"))
        self.body_edit = QPlainTextEdit(body)
        self.body_edit.setMinimumHeight(140)
        v.addWidget(self.body_edit)

        self.status_label = QLabel("Ready")
        v.addWidget(self.status_label)


class ForumComposerDialog(QDialog):
    """Modal: lists rows for each selected gallery and posts on demand."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        controller,
        gallery_ids: list[int],
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(
            f"Post to forum — {len(gallery_ids)} gallery(ies)",
        )
        self.resize(720, 720)
        self._conn = conn
        self._controller = controller
        self._rows: list[_GalleryRow] = []
        self._post_id_to_row: dict[int, _GalleryRow] = {}
        self._build_ui(gallery_ids)
        # Live status updates from controller (skipped silently in tests
        # that pass MagicMock).
        try:
            controller.forum_post_changed.connect(
                self._on_post_changed,
                Qt.ConnectionType.QueuedConnection,
            )
        except Exception:
            pass

    def _build_ui(self, gallery_ids):
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        for gid in gallery_ids:
            row = _GalleryRow(self._conn, gid, self._controller, self)
            inner_layout.addWidget(row)
            self._rows.append(row)
        inner_layout.addStretch()
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        action = QHBoxLayout()
        self.post_btn = QPushButton(f"Post {self._postable_count()} selected")
        self.post_btn.clicked.connect(self.post_all)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        action.addStretch()
        action.addWidget(self.post_btn)
        action.addWidget(close_btn)
        outer.addLayout(action)

    # ---- public API used by tests + caller ----

    def row_count(self) -> int:
        return len(self._rows)

    def has_warning(self, idx: int) -> bool:
        return self._rows[idx].warning

    def set_skipped(self, idx: int, skipped: bool) -> None:
        self._rows[idx].skip_check.setChecked(skipped)

    def post_all(self) -> None:
        for row in self._rows:
            if row.warning or row.skip_check.isChecked():
                continue
            try:
                cfg = dict(row._cfg or {})
                if row.title_input is not None:
                    cfg["_title_override"] = row.title_input.text()
                if row.body_edit is not None:
                    cfg["_body_override"] = row.body_edit.toPlainText()
                post_id = self._controller.post_now(
                    gallery_id=row.gallery_id, override_cfg=cfg,
                )
                if post_id is not None:
                    self._post_id_to_row[post_id] = row
                if row.status_label is not None:
                    row.status_label.setText("Queued")
            except Exception as e:
                if row.status_label is not None:
                    row.status_label.setText(f"Error: {e}")
        self.post_btn.setEnabled(False)

    # ---- internals ----

    def _postable_count(self) -> int:
        return sum(
            1 for r in self._rows
            if not r.warning and not r.skip_check.isChecked()
        )

    def _on_post_changed(self, forum_post_id: int) -> None:
        row = self._post_id_to_row.get(forum_post_id)
        if not row or row.status_label is None:
            return
        post = fp.get_forum_post(self._conn, forum_post_id)
        if not post:
            return
        row.status_label.setText(f"Status: {post['status']}")
