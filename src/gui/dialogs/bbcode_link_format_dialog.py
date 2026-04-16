"""BBCode Link Format editor dialog with syntax highlighting and placeholder buttons."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QPushButton,
    QLabel, QWidget, QDialogButtonBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from src.gui.widgets.placeholder_highlighter import PlaceholderHighlighter


# Placeholder definitions: (placeholder, button_label, tooltip, preview_value)
LINK_PLACEHOLDERS = [
    ("#link#", "Link", "Download URL", "https://example.com/file/abc123"),
    ("#hostName#", "Host Name", "Host display name (e.g. Rapidgator)", "Rapidgator"),
    ("#fileSize#", "File Size", "Archive part file size (e.g. 250 MiB)", "250 MiB"),
    ("#partLabel#", "Part Label", "Part label for split archives (e.g. Part 1)", "Part 1"),
    ("#partNumber#", "Part Number", "Part number (1, 2, 3...)", "1"),
    ("#partCount#", "Part Count", "Total number of parts", "2"),
]


class BBCodeLinkFormatDialog(QDialog):
    """Editor dialog for file host BBCode link formats.

    Provides a text editor with syntax highlighting for #placeholder# patterns,
    buttons to insert available placeholders, and a live preview showing
    example output.

    Args:
        initial_text: Pre-populate the editor with this text.
        parent: Parent widget.
    """

    def __init__(self, initial_text: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("BBCode Link Format")
        self.setMinimumSize(500, 350)
        self.resize(550, 380)

        layout = QVBoxLayout(self)

        # --- Editor area (horizontal: editor + buttons) ---
        editor_area = QHBoxLayout()

        # Editor with syntax highlighting
        self.editor = QPlainTextEdit()
        self.editor.setPlainText(initial_text)
        self.editor.setPlaceholderText("[url=#link#]#hostName#[/url]")
        self.highlighter = PlaceholderHighlighter(self.editor.document())
        self.editor.textChanged.connect(self._update_preview)
        editor_area.addWidget(self.editor, stretch=1)

        # Placeholder button panel
        button_panel = QWidget()
        button_panel.setFixedWidth(130)
        button_layout = QVBoxLayout(button_panel)
        button_layout.setContentsMargins(4, 0, 0, 0)

        button_label = QLabel("Insert:")
        button_label.setStyleSheet("font-weight: bold; margin-bottom: 5px;")
        button_layout.addWidget(button_label)

        self._placeholder_buttons = []
        for placeholder, label, tooltip, _ in LINK_PLACEHOLDERS:
            btn = QPushButton(label)
            btn.setToolTip(f"{tooltip}\nInserts: {placeholder}")
            btn.clicked.connect(lambda _, p=placeholder: self._insert_placeholder(p))
            btn.setStyleSheet("""
                QPushButton {
                    padding: 4px 8px;
                    max-height: 24px;
                    font-size: 11px;
                }
            """)
            button_layout.addWidget(btn)
            self._placeholder_buttons.append(btn)

        button_layout.addStretch()
        editor_area.addWidget(button_panel)

        layout.addLayout(editor_area)

        # --- Preview area ---
        preview_header = QLabel("Preview:")
        preview_header.setStyleSheet("font-weight: bold; margin-top: 8px;")
        layout.addWidget(preview_header)

        self.preview_label = QLabel()
        self.preview_label.setWordWrap(True)
        self.preview_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.preview_label.setStyleSheet(
            "QLabel { padding: 6px; border: 1px solid palette(mid); border-radius: 3px; }"
        )
        self.preview_label.setFont(QFont("monospace"))
        layout.addWidget(self.preview_label)

        # --- OK / Cancel ---
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Initial preview
        self._update_preview()

    def get_text(self) -> str:
        """Return the current editor text."""
        return self.editor.toPlainText()

    def _insert_placeholder(self, placeholder: str):
        """Insert a placeholder at the current cursor position."""
        cursor = self.editor.textCursor()
        cursor.insertText(placeholder)
        self.editor.setFocus()

    def _update_preview(self):
        """Update the live preview with example placeholder values."""
        text = self.editor.toPlainText()
        if not text:
            self.preview_label.setText("(empty — raw URLs will be used)")
            return

        for placeholder, _, _, example_value in LINK_PLACEHOLDERS:
            text = text.replace(placeholder, example_value)

        self.preview_label.setText(text)
