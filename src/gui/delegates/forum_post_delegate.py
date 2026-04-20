"""Inline-edit delegate for the gallery table's Forum Post column.

Spec: docs/superpowers/specs/2026-04-20-forum-posting-design.md §7.5.

Editor is a QLineEdit accepting a bare post ID or full URL. The owning
controller listens to commit_text and calls forum_controller.onboard_post.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLineEdit, QStyledItemDelegate


def format_cell_text(forum_post_row: Optional[dict]) -> str:
    """Render the cell label for a forum_posts row dict (or None)."""
    if not forum_post_row:
        return ""
    status = forum_post_row.get("status", "")
    pid = forum_post_row.get("posted_post_id") or ""
    label_map = {
        "queued": "⏳ Queued",
        "posting": "⏳ Posting",
        "posted": f"✓ Posted #{pid}" if pid else "✓ Posted",
        "stale": f"● Stale #{pid}" if pid else "● Stale",
        "failed": "✗ Failed",
        "updating": "⏳ Updating",
    }
    return label_map.get(status, status or "")


class ForumPostDelegate(QStyledItemDelegate):
    """Custom delegate for the Forum Post column."""

    commit_text = pyqtSignal(int, str)  # row, text

    def __init__(self, parent=None):
        super().__init__(parent)

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setPlaceholderText("paste post # or URL")
        return editor

    def setEditorData(self, editor: QLineEdit, index):
        editor.setText("")

    def setModelData(self, editor: QLineEdit, model, index):
        text = editor.text().strip()
        if not text:
            return
        self.commit_text.emit(index.row(), text)
        model.setData(index, "⏳ Queued", Qt.ItemDataRole.DisplayRole)
