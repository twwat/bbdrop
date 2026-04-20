"""Per-gallery posting override dialog.

Spec: docs/superpowers/specs/2026-04-20-forum-posting-design.md §2.3 / §7.2.
"""

from __future__ import annotations

import sqlite3

from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout

from src.gui.widgets.tab_posting_config_panel import TabPostingConfigPanel


class GalleryPostingOverrideDialog(QDialog):
    """Modal wrapper around TabPostingConfigPanel in override mode."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        gallery_id: int,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Per-Gallery Posting Override")
        self.resize(560, 540)
        self.panel = TabPostingConfigPanel(
            conn=conn, gallery_id=gallery_id, parent=self,
        )
        layout = QVBoxLayout(self)
        layout.addWidget(self.panel)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
        )
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

    def _accept(self):
        if self.panel.save():
            self.accept()
