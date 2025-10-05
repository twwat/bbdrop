#!/usr/bin/env python3
"""
Help Dialog for imx.to gallery uploader
Simple, working dialog to display documentation
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

        # Main layout
        layout = QVBoxLayout(self)

        # Tab widget
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Load documentation files
        self._load_documentation()

        # Close button
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _load_documentation(self):
        """Load documentation files into tabs"""
        # Docs directory is just "docs" relative to current working directory
        docs_dir = "docs"

        # Documentation files to load
        doc_files = [
            ("Keyboard Shortcuts", "KEYBOARD_SHORTCUTS.md"),
            ("GUI Guide", "GUI_README.md"),
            ("Quick Start (GUI)", "QUICK_START_GUI.md"),
            ("GUI Improvements", "GUI_IMPROVEMENTS.md"),
        ]

        docs_loaded = False

        for title, filename in doc_files:
            file_path = os.path.join(docs_dir, filename)

            # Create text editor
            editor = QTextEdit()
            editor.setReadOnly(True)
            editor.setProperty("class", "help-content")

            # Load content
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        # Try markdown first, fallback to plain text
                        try:
                            editor.setMarkdown(content)
                        except:
                            editor.setPlainText(content)
                        docs_loaded = True
                except Exception as e:
                    editor.setPlainText(f"Error loading {filename}: {str(e)}")
            else:
                editor.setPlainText(f"Documentation file not found: {file_path}")

            # Add tab
            self.tabs.addTab(editor, title)

        # If no docs loaded, show info
        if not docs_loaded:
            info_editor = QTextEdit()
            info_editor.setReadOnly(True)
            info_editor.setPlainText("No documentation files found in the docs directory.")
            self.tabs.addTab(info_editor, "Info")