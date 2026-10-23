"""Placeholder editor dialog with syntax highlighting and insert buttons.

Reusable editor for any template format that uses #placeholder# patterns.
Used by file host BBCode link format, video contact sheet templates and
Discord notification messages.
"""

from typing import Callable, Optional, Sequence

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
    ("#fileName#", "File Name", "Uploaded filename incl. extension (e.g. Gallery.part1.rar)", "Gallery.part1.rar"),
    ("#fileBaseName#", "Base Name", "Filename without extension (e.g. Gallery.part1)", "Gallery.part1"),
    ("#fileExt#", "Extension", "File extension without dot, lowercased (e.g. rar)", "rar"),
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
        presets: (label, text) pairs; each adds a button that replaces the
            editor text.
        preview_renderer: When set, the preview shows preview_renderer(text)
            instead of substituting the example values.
        sample_sender: When set, adds a "Send sample to Discord" button that
            calls sample_sender(<rendered preview>), plus a status line.
    """

    def __init__(self, title: str, placeholders: list, initial_text: str = "", parent=None,
                 *, presets: Sequence[tuple] = (),
                 preview_renderer: Optional[Callable[[str], str]] = None,
                 sample_sender: Optional[Callable[[str], None]] = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(500, 350)
        self.resize(550, 380)
        self._placeholders = placeholders
        self._preview_renderer = preview_renderer
        self._sample_sender = sample_sender

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

        # --- Optional presets / sample row ---
        self._preset_buttons = []
        self.sample_button = None
        self.status_label = None
        if presets or sample_sender is not None:
            action_row = QHBoxLayout()
            for label, text in presets:
                btn = QPushButton(label)
                btn.clicked.connect(lambda _, t=text: self.editor.setPlainText(t))
                action_row.addWidget(btn)
                self._preset_buttons.append(btn)
            action_row.addStretch()
            if sample_sender is not None:
                self.sample_button = QPushButton("Send sample to Discord")
                self.sample_button.clicked.connect(
                    lambda: self._sample_sender(self._rendered_text()))
                action_row.addWidget(self.sample_button)
            layout.addLayout(action_row)
            if sample_sender is not None:
                self.status_label = QLabel("")
                self.status_label.setWordWrap(True)
                layout.addWidget(self.status_label)

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

    def set_status(self, text: str, error: bool = False) -> None:
        """Show a status line under the sample button (no-op without one)."""
        if self.status_label is None:
            return
        self.status_label.setStyleSheet("color: #c0392b;" if error else "color: #27ae60;")
        self.status_label.setText(text)

    def _rendered_text(self) -> str:
        text = self.editor.toPlainText()
        if self._preview_renderer is not None:
            return self._preview_renderer(text)
        for placeholder, _, _, example_value in self._placeholders:
            text = text.replace(placeholder, example_value)
        return text

    def _insert_placeholder(self, placeholder: str):
        """Insert a placeholder at the current cursor position."""
        cursor = self.editor.textCursor()
        cursor.insertText(placeholder)
        self.editor.setFocus()

    def _update_preview(self):
        """Update the live preview with example placeholder values."""
        if not self.editor.toPlainText():
            self.preview_label.setText("(empty)")
            return
        self.preview_label.setText(self._rendered_text())
