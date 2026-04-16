"""Placeholder editor dialog with syntax highlighting and insert buttons.

Reusable editor for any template format that uses #placeholder# patterns.
Used by file host BBCode link format and video contact sheet templates.
"""

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

VIDEO_PLACEHOLDERS = [
    ("#filename#", "Filename", "Video filename", "Big_Buck_Bunny.mp4"),
    ("#folderName#", "Folder Name", "Gallery/folder name", "My Videos"),
    ("#duration#", "Duration", "Playback duration (H:MM:SS)", "0:10:34"),
    ("#resolution#", "Resolution", "Video dimensions (WxH)", "1920x1080"),
    ("#width#", "Width", "Video width", "1920"),
    ("#height#", "Height", "Video height", "1080"),
    ("#fps#", "FPS", "Frame rate", "23.976"),
    ("#bitrate#", "Bitrate", "Video bitrate", "8500 kbps"),
    ("#videoCodec#", "Video Codec", "Video codec name", "HEVC"),
    ("#audioCodec#", "Audio Codec", "Primary audio codec", "AAC"),
    ("#audioTracks#", "Audio Tracks", "All audio tracks summary", "AAC 2.0, AC3 5.1"),
    ("#filesize#", "File Size", "Video file size", "1.4 GiB"),
    ("#folderSize#", "Folder Size", "Total folder size", "4.2 GiB"),
    ("#pictureCount#", "Frame Count", "Number of frames in sheet", "20"),
]


class PlaceholderEditorDialog(QDialog):
    """Editor dialog for template formats using #placeholder# patterns.

    Provides a text editor with syntax highlighting, buttons to insert
    available placeholders, and a live preview with example values.

    Args:
        title: Dialog window title.
        placeholders: List of (placeholder, button_label, tooltip, preview_value) tuples.
        initial_text: Pre-populate the editor with this text.
        parent: Parent widget.
    """

    def __init__(self, title: str, placeholders: list, initial_text: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(500, 350)
        self.resize(550, 380)
        self._placeholders = placeholders

        layout = QVBoxLayout(self)

        # --- Editor area (horizontal: editor + buttons) ---
        editor_area = QHBoxLayout()

        # Editor with syntax highlighting
        self.editor = QPlainTextEdit()
        self.editor.setPlainText(initial_text)
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
        for placeholder, label, tooltip, _ in placeholders:
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
        self.preview_label.setTextFormat(Qt.TextFormat.PlainText)
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
            self.preview_label.setText("(empty)")
            return

        for placeholder, _, _, example_value in self._placeholders:
            text = text.replace(placeholder, example_value)

        self.preview_label.setText(text)
