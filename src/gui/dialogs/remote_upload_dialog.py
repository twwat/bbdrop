"""Remote upload dialog for the file manager.

Lets users submit URLs for server-side download to their host account.
Shows a progress table for active remote upload jobs.
"""

from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from src.network.file_manager.client import RemoteJobStatus


class RemoteUploadDialog(QDialog):
    """Dialog for submitting URLs for remote upload and tracking progress."""

    def __init__(self, parent=None, submit_callback=None, status_callback=None):
        super().__init__(parent)
        self.setWindowTitle("Remote Upload")
        self.setMinimumSize(600, 450)

        self._submit_callback = submit_callback
        self._status_callback = status_callback
        self._job_ids: List[str] = []

        self._setup_ui()

        # Poll timer for status updates
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(3000)
        self._poll_timer.timeout.connect(self._poll_status)

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # URL input
        layout.addWidget(QLabel("Enter URLs (one per line):"))

        self._url_input = QPlainTextEdit()
        self._url_input.setPlaceholderText(
            "https://example.com/file1.zip\nhttps://example.com/file2.zip"
        )
        self._url_input.setMaximumHeight(120)
        layout.addWidget(self._url_input)

        # Submit button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._btn_submit = QPushButton("Submit URLs")
        self._btn_submit.clicked.connect(self._on_submit)
        btn_layout.addWidget(self._btn_submit)
        layout.addLayout(btn_layout)

        # Status table
        layout.addWidget(QLabel("Active Jobs:"))

        self._table = QTableWidget()
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["URL / Job ID", "Status", "Progress"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table)

        # Close button
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_submit(self):
        text = self._url_input.toPlainText().strip()
        if not text:
            return

        urls = [u.strip() for u in text.splitlines() if u.strip()]
        if not urls:
            return

        if self._submit_callback:
            self._submit_callback(urls)

        self._url_input.clear()

        # Start polling
        if not self._poll_timer.isActive():
            self._poll_timer.start()

    def update_jobs(self, jobs: List[RemoteJobStatus]):
        """Update the job status table."""
        self._table.setRowCount(len(jobs))

        for row, job in enumerate(jobs):
            self._table.setItem(row, 0, QTableWidgetItem(job.job_id))
            self._table.setItem(row, 1, QTableWidgetItem(job.status))

            progress_text = f"{job.progress}%"
            if job.status == "done":
                progress_text = "Complete"
            elif job.status == "failed":
                progress_text = "Failed"
            self._table.setItem(row, 2, QTableWidgetItem(progress_text))

    def _poll_status(self):
        if self._status_callback:
            self._status_callback()

    def closeEvent(self, event):
        self._poll_timer.stop()
        super().closeEvent(event)
