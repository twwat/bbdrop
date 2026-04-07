"""File details dialog for the file manager.

Shows detailed info for one or more files: name, size, date, access,
availability, MD5, and content type.
"""

from __future__ import annotations

from typing import List

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.network.file_manager.client import FileInfo
from src.utils.format_utils import format_binary_size


class FileDetailsDialog(QDialog):
    """Modal dialog showing file/folder details."""

    def __init__(self, files: List[FileInfo], parent=None):
        super().__init__(parent)
        self.setWindowTitle("File Details" if len(files) == 1 else f"{len(files)} Files")
        self.setMinimumWidth(400)
        self._setup_ui(files)

    def _setup_ui(self, files: List[FileInfo]):
        layout = QVBoxLayout(self)

        if len(files) == 1:
            layout.addWidget(self._build_detail_form(files[0]))
        else:
            tabs = QTabWidget()
            for fi in files[:20]:  # Limit tabs
                tabs.addTab(self._build_detail_form(fi), fi.name[:30])
            layout.addWidget(tabs)

            if len(files) > 20:
                layout.addWidget(QLabel(f"... and {len(files) - 20} more"))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _build_detail_form(fi: FileInfo) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)
        form.setSpacing(8)

        form.addRow("Name:", QLabel(fi.name))
        form.addRow("Type:", QLabel("Folder" if fi.is_folder else "File"))

        if not fi.is_folder:
            form.addRow("Size:", QLabel(format_binary_size(fi.size)))

        if fi.created:
            form.addRow("Created:", QLabel(fi.created.strftime("%Y-%m-%d %H:%M:%S")))

        form.addRow("Access:", QLabel(fi.access))

        status = "Available" if fi.is_available else "Unavailable"
        status_label = QLabel(status)
        if not fi.is_available:
            status_label.setStyleSheet("color: red;")
        form.addRow("Status:", status_label)

        if fi.md5:
            form.addRow("MD5:", QLabel(fi.md5))

        if fi.content_type:
            form.addRow("Content Type:", QLabel(fi.content_type))

        if fi.download_count is not None:
            form.addRow("Downloads:", QLabel(str(fi.download_count)))

        form.addRow("ID:", QLabel(fi.id))

        return widget
