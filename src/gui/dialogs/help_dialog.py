#!/usr/bin/env python3
"""
Help Dialog for imx.to gallery uploader
Dialog to display program documentation in tabs
"""

import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QTabWidget, QTextEdit, QDialogButtonBox
)


class HelpDialog(QDialog):
    """Dialog to display program documentation in tabs"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Help & Documentation")
        self.setModal(True)
        self.resize(800, 600)

        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.tabs.setProperty("class", "gallery-tabs")
        layout.addWidget(self.tabs)

        # Candidate documentation files in preferred order
        base_dir = os.path.dirname(os.path.abspath(__file__))
        doc_candidates = [
            ("GUI Guide", os.path.join(base_dir, "GUI_README.md")),
            ("Quick Start (GUI)", os.path.join(base_dir, "QUICK_START_GUI.md")),
            ("README", os.path.join(base_dir, "README.md")),
            ("Troubleshooting Drag & Drop", os.path.join(base_dir, "TROUBLESHOOT_DRAG_DROP.md")),
            ("GUI Improvements", os.path.join(base_dir, "GUI_IMPROVEMENTS.md")),
        ]

        any_docs_loaded = False
        for title, path in doc_candidates:
            if os.path.exists(path):
                any_docs_loaded = True
                editor = QTextEdit()
                editor.setReadOnly(True)
                editor.setProperty("class", "console")
                try:
                    # Prefer Markdown rendering if available
                    editor.setMarkdown(open(path, "r", encoding="utf-8").read())
                except Exception:
                    # Fallback to plain text
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            editor.setPlainText(f.read())
                    except Exception as e:
                        editor.setPlainText(f"Failed to load {path}: {e}")
                self.tabs.addTab(editor, title)

        if not any_docs_loaded:
            info = QTextEdit()
            info.setReadOnly(True)
            info.setPlainText("No documentation files found in the application directory.")
            self.tabs.addTab(info, "Info")

        # Close button
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)