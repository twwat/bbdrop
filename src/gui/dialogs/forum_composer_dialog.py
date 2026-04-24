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

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QToolButton, QVBoxLayout, QWidget,
)

from src.network.forum.factory import create_forum_client
from src.network.forum.session_store import SessionStore
from src.storage import forum_posting as fp

_ADD_NEW = "__add_new__"


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
        self.target_combo: Optional[QComboBox] = None
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

        # Target selector (dropdown with friendly names + "+" to add new)
        target_layout = QHBoxLayout()
        target_layout.addWidget(QLabel("Target:"))
        self.target_combo = QComboBox()
        self._populate_target_combo()
        self.target_combo.currentIndexChanged.connect(self._on_target_changed)
        target_layout.addWidget(self.target_combo, 1)
        target_add_btn = QToolButton()
        target_add_btn.setText("+")
        target_add_btn.setToolTip("Add a subforum or thread from a URL")
        target_add_btn.clicked.connect(self._on_add_target)
        target_layout.addWidget(target_add_btn)
        v.addLayout(target_layout)

        # Render body and title, but don't fail if render errors
        body = ""
        title = ""
        try:
            body, title = self._controller.preview_render(self.gallery_id)
        except Exception as e:
            # Render failure is not a fatal error — user can manually enter body
            v.addWidget(QLabel(f"<i>Render warning: {e}</i>"))

        if self._cfg["kind"] == "new_thread":
            title_layout = QHBoxLayout()
            title_layout.addWidget(QLabel("Title:"))
            self.title_input = QLineEdit(title)
            title_layout.addWidget(self.title_input, 1)
            v.addLayout(title_layout)

        v.addWidget(QLabel("Body:"))
        self.body_edit = QPlainTextEdit(body)
        self.body_edit.setMinimumHeight(140)
        v.addWidget(self.body_edit, 1)

        self.status_label = QLabel("Ready")
        v.addWidget(self.status_label)

    def _populate_target_combo(self) -> None:
        """Fill target dropdown with friendly names from forum_targets library."""
        self.target_combo.blockSignals(True)
        self.target_combo.clear()

        forum_id = self._cfg["forum_fk"]
        targets = fp.list_targets(self._conn, forum_id)
        current_target_id = str(self._cfg["target_id"])
        current_kind = self._cfg["kind"]

        selected_idx = -1
        for i, t in enumerate(targets):
            label = f"{t['name']} ({t['kind']} #{t['target_id']})"
            self.target_combo.addItem(label, {
                "kind": t["kind"],
                "target_id": t["target_id"],
            })
            if (str(t["target_id"]) == current_target_id
                    and t["kind"] == self._target_kind_from_cfg()):
                selected_idx = i

        # Add sentinel for "Add new target from URL"
        self.target_combo.addItem("+ Add new target from URL…", _ADD_NEW)

        if selected_idx >= 0:
            self.target_combo.setCurrentIndex(selected_idx)
        else:
            # Show current target even if not in library (orphaned entry)
            label = f"(configured) {current_kind} #{current_target_id}"
            idx = self.target_combo.count() - 1  # Insert before "Add new"
            self.target_combo.insertItem(idx, label, {
                "kind": current_kind,
                "target_id": current_target_id,
            })
            self.target_combo.setCurrentIndex(idx)

        self.target_combo.blockSignals(False)

    def _target_kind_from_cfg(self) -> str:
        """Map config kind ('new_thread'/'reply') to target kind ('subforum'/'thread')."""
        if self._cfg["kind"] == "new_thread":
            return "subforum"
        return "thread"

    def _on_target_changed(self) -> None:
        """Handle target combo changes; defer 'Add new' to next event loop."""
        if self.target_combo.currentData() == _ADD_NEW:
            QTimer.singleShot(0, self._on_add_target)

    def _on_add_target(self) -> None:
        """Prompt to add a new target from a URL."""
        forum_id = self._cfg["forum_fk"]
        forum = fp.get_forum(self._conn, forum_id)
        if not forum:
            self._restore_target_to_valid()
            return

        url, ok = QInputDialog.getText(
            self.parent(), "Add target",
            "Paste a subforum or thread URL:",
            QLineEdit.EchoMode.Normal, "",
        )
        if not ok or not (url or "").strip():
            self._restore_target_to_valid()
            return

        try:
            client = create_forum_client(
                forum["software_id"], base_url=forum["base_url"],
                session_store=SessionStore(),
            )
            ref = client.parse_target_url(url.strip())
        except Exception as e:
            QMessageBox.warning(self.parent(), "Add target", f"Error: {e}")
            self._restore_target_to_valid()
            return

        if ref is None:
            QMessageBox.warning(
                self.parent(), "Add target",
                "Couldn't recognise that URL. Paste a subforum link "
                "(e.g. /forumdisplay.php?f=…) or a thread link "
                "(e.g. /showthread.php?t=…).",
            )
            self._restore_target_to_valid()
            return

        name, ok = QInputDialog.getText(
            self.parent(), "Name this target",
            f"Name for this {ref.kind} (#{ref.target_id}):",
            QLineEdit.EchoMode.Normal,
            ref.name or f"{ref.kind} {ref.target_id}",
        )
        if not ok:
            self._restore_target_to_valid()
            return

        name = (name or "").strip() or ref.name or f"{ref.kind} {ref.target_id}"
        fp.upsert_target(
            self._conn, forum_fk=forum_id, name=name,
            kind=ref.kind, target_id=ref.target_id,
        )
        self._populate_target_combo()
        # Select the newly added target
        for i in range(self.target_combo.count()):
            data = self.target_combo.itemData(i)
            if (isinstance(data, dict)
                    and data.get("target_id") == ref.target_id
                    and data.get("kind") == ref.kind):
                self.target_combo.setCurrentIndex(i)
                break

    def _restore_target_to_valid(self) -> None:
        """Move combo off the 'Add new' sentinel back to a real entry."""
        count = self.target_combo.count()
        for i in range(count):
            if self.target_combo.itemData(i) != _ADD_NEW:
                self.target_combo.blockSignals(True)
                self.target_combo.setCurrentIndex(i)
                self.target_combo.blockSignals(False)
                return


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
            inner_layout.addWidget(row, 1)
            self._rows.append(row)
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
                # Use selected target from dropdown if available
                if hasattr(row, "target_combo"):
                    target_data = row.target_combo.currentData()
                    if target_data:
                        cfg["kind"] = target_data["kind"]
                        cfg["target_id"] = target_data["target_id"]
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
