"""Forum Manager dialog: thin QDialog wrapper around ForumsPanel.

The full UI/logic lives in src/gui/settings/forums_tab.py so the same
panel can also be embedded in the Settings dialog.

Spec: docs/superpowers/specs/2026-04-20-forum-posting-design.md §7.1.
"""

from __future__ import annotations

import sqlite3

from PyQt6.QtWidgets import QDialog, QVBoxLayout

from src.gui.settings.forums_tab import ForumsPanel


class ForumManagerDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Forum Manager")
        self.resize(720, 480)
        self._panel = ForumsPanel(conn, self)
        layout = QVBoxLayout(self)
        layout.addWidget(self._panel)

    def __getattr__(self, name):
        # Forward access to the embedded panel so existing callers/tests
        # can still reach forum_list, software_combo, _save_forum, etc.
        panel = self.__dict__.get("_panel")
        if panel is not None and hasattr(panel, name):
            return getattr(panel, name)
        raise AttributeError(name)
