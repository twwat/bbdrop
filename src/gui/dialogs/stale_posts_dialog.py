"""Stale Posts dialog — batch review and update posts whose BBCode has
regenerated since they were posted.

Spec: docs/superpowers/specs/2026-04-20-forum-posting-design.md §12.
"""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


class StalePostsDialog(QDialog):
    """Lists every stale forum_post. Offers per-row + batch update with an
    optional mode override applied to the whole batch."""

    def __init__(self, conn, controller, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Stale Posts")
        self.resize(900, 540)
        self._conn = conn
        self._controller = controller
        self._row_post_ids: list[int] = []
        self._build_ui()
        self._reload()

    # ----- UI -----

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.addWidget(QLabel(
            "Posts whose underlying BBCode has changed since they were "
            "posted. Select rows and click Update Selected."
        ))

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Gallery", "Forum", "Post #", "Last error", "Posted at"]
        )
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        v.addWidget(self.table)

        action_row = QHBoxLayout()
        action_row.addWidget(QLabel("Mode:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Use post's stored mode", None)
        for value, label in (
            ("whole", "Force whole-body replace"),
            ("surgical", "Force surgical link swap"),
            ("whole_then_surgical", "Whole, fall back to surgical"),
        ):
            self.mode_combo.addItem(label, value)
        action_row.addWidget(self.mode_combo)
        action_row.addStretch()

        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self.select_all)
        action_row.addWidget(select_all_btn)

        update_btn = QPushButton("Update Selected")
        update_btn.clicked.connect(self.update_selected)
        action_row.addWidget(update_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        action_row.addWidget(close_btn)

        v.addLayout(action_row)

    # ----- data -----

    def _reload(self):
        rows = self._conn.execute(
            """
            SELECT fp.id, fp.posted_post_id, fp.posted_url, fp.last_error,
                   fp.posted_ts, g.name AS gname, g.path AS gpath,
                   f.name AS fname
            FROM forum_posts fp
            JOIN galleries g ON g.id = fp.gallery_fk
            JOIN forums f ON f.id = fp.forum_fk
            WHERE fp.status = 'stale'
            ORDER BY fp.updated_ts DESC
            """
        ).fetchall()
        self.table.setRowCount(len(rows))
        self._row_post_ids = []
        for i, r in enumerate(rows):
            d = dict(r)
            self._row_post_ids.append(int(d["id"]))
            gallery_label = d.get("gname") or d.get("gpath") or ""
            self.table.setItem(i, 0, QTableWidgetItem(str(gallery_label)))
            self.table.setItem(i, 1, QTableWidgetItem(d.get("fname") or ""))
            self.table.setItem(
                i, 2, QTableWidgetItem(str(d.get("posted_post_id") or ""))
            )
            self.table.setItem(
                i, 3, QTableWidgetItem(str(d.get("last_error") or ""))
            )
            ts = d.get("posted_ts")
            ts_text = (
                datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
                if ts else ""
            )
            self.table.setItem(i, 4, QTableWidgetItem(ts_text))
        self.table.resizeColumnsToContents()

    # ----- test hooks + behavior -----

    def row_count(self) -> int:
        return self.table.rowCount()

    def forum_post_id_for_row(self, row: int) -> int:
        return self._row_post_ids[row]

    def select_all(self):
        self.table.selectAll()

    def update_selected(self):
        ids = [
            self._row_post_ids[i.row()]
            for i in self.table.selectionModel().selectedRows()
        ]
        if not ids:
            QMessageBox.information(
                self, "Update", "Select at least one row first."
            )
            return
        override_mode = self.mode_combo.currentData()
        results = self._controller.update_posts(
            ids, override_mode=override_mode
        )
        enqueued = sum(1 for r in results if r.get("enqueued"))
        skipped = [r for r in results if r.get("action") == "skip_and_alert"]
        noops = [r for r in results if r.get("action") == "noop"]
        lines = [f"Enqueued {enqueued} update(s)."]
        if noops:
            lines.append(f"{len(noops)} already up-to-date.")
        if skipped:
            lines.append(
                f"Skipped {len(skipped)} (manual edits or fetch failure)."
            )
        QMessageBox.information(self, "Update", "\n".join(lines))
        self._reload()
