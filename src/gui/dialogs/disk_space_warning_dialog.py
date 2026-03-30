"""Persistent disk space warning dialog.

Single instance -- created once, updated in place on tier changes.
Never stacks. Non-modal so it doesn't block the event loop.
"""

from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)
from PyQt6.QtGui import QFont

from src.gui.icon_manager import get_icon


# Tier-specific configuration
_TIER_CONFIG = {
    "warning": {
        "title": "Low Disk Space",
        "color": "#f0ad4e",
    },
    "critical": {
        "title": "Critically Low Disk Space",
        "color": "#d9534f",
    },
    "emergency": {
        "title": "Critically Low Disk Space",
        "color": "#d9534f",
    },
}


class DiskSpaceWarningDialog(QDialog):
    """Non-modal warning dialog that updates in place for disk space alerts."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Disk Space Warning")
        self.setMinimumWidth(420)
        self.setModal(False)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 16)

        # Header row: icon + title
        header_layout = QHBoxLayout()

        self._icon_label = QLabel()
        icon = get_icon('status_error')
        self._icon_label.setPixmap(icon.pixmap(48, 48))
        header_layout.addWidget(self._icon_label)

        self._header_label = QLabel()
        header_font = QFont()
        header_font.setBold(True)
        header_font.setPointSize(14)
        self._header_label.setFont(header_font)
        header_layout.addWidget(self._header_label, 1)

        layout.addLayout(header_layout)

        # Body text
        self._body_label = QLabel()
        self._body_label.setWordWrap(True)
        layout.addWidget(self._body_label)

        # OK button
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        ok_button = QPushButton("OK")
        ok_button.setFixedWidth(80)
        ok_button.clicked.connect(self.hide)
        button_layout.addWidget(ok_button)
        layout.addLayout(button_layout)

    def update_tier(self, tier: str, free_space_str: str):
        """Update dialog content for the given tier and free space."""
        config = _TIER_CONFIG.get(tier, _TIER_CONFIG["warning"])

        self._header_label.setText(config["title"])
        self._header_label.setStyleSheet(f"color: {config['color']};")


        self._body_label.setText(
            f"Only {free_space_str} of disk space remaining.\n\n"
            f"New uploads have been paused until more space is available.\n\n"
            f"Free up disk space to resume uploading."
        )

        self.setWindowTitle(config["title"])
