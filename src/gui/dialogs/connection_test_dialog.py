"""Connection test dialog for file host configuration.

Shows the 4-step connection test results (credentials, user info,
upload test, delete test) in a dedicated dialog instead of inline.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QDialogButtonBox
)


class ConnectionTestDialog(QDialog):
    """Dialog showing file host connection test results.

    Args:
        host_name: Display name of the host
        parent: Parent widget
    """

    def __init__(self, host_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Connection Test — {host_name}")
        self.setMinimumWidth(400)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Test button
        btn_row = QHBoxLayout()
        self.test_btn = QPushButton("Run Test")
        self.test_btn.setToolTip("Run full connection test: credentials, user info, upload, and delete")
        btn_row.addWidget(self.test_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Results form
        results = QFormLayout()

        self.test_timestamp_label = QLabel("Not tested yet")
        self.test_credentials_label = QLabel("○ Not tested")
        self.test_userinfo_label = QLabel("○ Not tested")
        self.test_upload_label = QLabel("○ Not tested")
        self.test_delete_label = QLabel("○ Not tested")
        self.test_error_label = QLabel("")
        self.test_error_label.setWordWrap(True)
        self.test_error_label.setProperty("class", "error-small")

        results.addRow("Last tested:", self.test_timestamp_label)
        results.addRow("Credentials:", self.test_credentials_label)
        results.addRow("User info:", self.test_userinfo_label)
        results.addRow("Upload test:", self.test_upload_label)
        results.addRow("Delete test:", self.test_delete_label)
        results.addRow("", self.test_error_label)

        layout.addLayout(results)

        # Close button
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)

    def set_error(self, error: str):
        """Show error details."""
        self.test_error_label.setText(error)

    def set_timestamp(self, ts: str):
        """Update the last tested timestamp."""
        self.test_timestamp_label.setText(ts)

    def set_all_running(self):
        """Set all steps to running state."""
        for label in [self.test_credentials_label, self.test_userinfo_label,
                      self.test_upload_label, self.test_delete_label]:
            label.setText("⏳ Running...")
            label.setStyleSheet("")
        self.test_error_label.setText("")
