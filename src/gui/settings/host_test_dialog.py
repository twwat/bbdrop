"""Host Test Dialog - Shows file host test progress with checklist."""

from typing import Dict, Any, Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QApplication
)


class HostTestDialog(QDialog):
    """Dialog showing file host test progress with checklist"""

    def __init__(self, host_name: str, parent=None):
        super().__init__(parent)
        self.host_name = host_name
        self.test_items: Dict[str, Dict[str, Any]] = {}
        self.setup_ui()

    def setup_ui(self):
        """Setup the test dialog UI"""
        self.setWindowTitle(f"Testing {self.host_name}")
        self.setModal(True)
        self.resize(400, 250)

        layout = QVBoxLayout(self)

        # Title
        title_label = QLabel(f"<b>Testing {self.host_name}</b>")
        layout.addWidget(title_label)

        layout.addSpacing(10)

        # Test items list
        self.tests_layout = QVBoxLayout()

        # Add test items
        test_names = [
            ("login", "Logging in..."),
            ("credentials", "Validating credentials..."),
            ("user_info", "Retrieving account info..."),
            ("upload", "Testing upload..."),
            ("cleanup", "Cleaning up test file...")
        ]

        for test_id, test_name in test_names:
            test_row = QHBoxLayout()

            status_label = QLabel("\u23f3")  # Waiting
            status_label.setFixedWidth(30)

            name_label = QLabel(test_name)

            test_row.addWidget(status_label)
            test_row.addWidget(name_label)
            test_row.addStretch()

            self.tests_layout.addLayout(test_row)

            # Store references
            self.test_items[test_id] = {
                'status_label': status_label,
                'name_label': name_label,
                'row': test_row
            }

        layout.addLayout(self.tests_layout)
        layout.addStretch()

        # Close button (initially hidden)
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        self.close_btn.setVisible(False)
        layout.addWidget(self.close_btn)

    def update_test_status(self, test_id: str, status: str, message: Optional[str] = None):
        """Update status of a test

        Args:
            test_id: Test identifier
            status: 'running', 'success', 'failure', 'skipped'
            message: Optional status message
        """
        if test_id not in self.test_items:
            return

        item = self.test_items[test_id]

        status_label = item['status_label']
        if status == 'running':
            status_label.setText("\u23f3")
            status_label.setProperty("status", "running")
        elif status == 'success':
            status_label.setText("\u2713")
            status_label.setProperty("status", "success")
        elif status == 'failure':
            status_label.setText("\u2717")
            status_label.setProperty("status", "failure")
        elif status == 'skipped':
            status_label.setText("\u25cb")
            status_label.setProperty("status", "skipped")
        # Reapply stylesheet to pick up property change
        status_label.style().unpolish(status_label)
        status_label.style().polish(status_label)

        if message:
            item['name_label'].setText(message)

        # Force UI update
        self.repaint()
        QApplication.processEvents()

    def set_complete(self, success: bool):
        """Mark testing as complete

        Args:
            success: True if all tests passed
        """
        self.close_btn.setVisible(True)
        if success:
            self.setWindowTitle(f"Testing {self.host_name} - Complete \u2713")
        else:
            self.setWindowTitle(f"Testing {self.host_name} - Failed \u2717")
