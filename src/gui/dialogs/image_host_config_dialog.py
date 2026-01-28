#!/usr/bin/env python3
"""Image Host Configuration Dialog"""
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap

from src.core.image_host_config import ImageHostConfig
from src.gui.widgets.image_host_config_panel import ImageHostConfigPanel


class ImageHostConfigDialog(QDialog):
    """Simplified dialog for configuring a single image host"""

    def __init__(self, parent, host_id: str, host_config: ImageHostConfig):
        """
        Args:
            parent: Parent widget
            host_id: Host identifier (e.g., 'imgur', 'imgbb')
            host_config: ImageHostConfig object
        """
        super().__init__(parent)
        self.host_id = host_id
        self.host_config = host_config
        self.setWindowTitle(f"Configure {host_config.name}")
        self.setModal(True)
        self.resize(550, 650)
        self.setup_ui()

    def setup_ui(self):
        """Setup the dialog UI"""
        layout = QVBoxLayout(self)

        # Header with logo and host name
        header_layout = QHBoxLayout()

        # Host logo (if available)
        logo_label = self._load_logo()
        if logo_label:
            header_layout.addWidget(logo_label)

        # Host name
        name_label = QLabel(f"<h2>{self.host_config.name}</h2>")
        header_layout.addWidget(name_label)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Embed the configuration panel
        self.panel = ImageHostConfigPanel(self.host_id, self.host_config, self)
        layout.addWidget(self.panel)
        layout.addStretch()

        # OK/Cancel buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self._on_ok)
        ok_btn.setDefault(True)
        button_layout.addWidget(ok_btn)

        layout.addLayout(button_layout)

    def _load_logo(self):
        """Load and create a QLabel with the host's logo.

        Returns:
            QLabel with scaled logo pixmap, or None if logo not found
        """
        from bbdrop import get_project_root
        import os

        # Try multiple potential logo paths
        logo_paths = [
            os.path.join(get_project_root(), "assets", "image_hosts", "logo", f"{self.host_id}.png"),
        ]

        # Also try icon path if specified in config
        if self.host_config.icon:
            logo_paths.append(os.path.join(get_project_root(), "assets", "image_hosts", self.host_config.icon))

        for logo_path in logo_paths:
            if os.path.exists(logo_path):
                try:
                    pixmap = QPixmap(logo_path)
                    if not pixmap.isNull():
                        logo_label = QLabel()
                        # Scale logo to max height of 40px for dialog header
                        scaled_pixmap = pixmap.scaledToHeight(40, Qt.TransformationMode.SmoothTransformation)
                        logo_label.setPixmap(scaled_pixmap)
                        return logo_label
                except Exception:
                    continue

        return None

    def _on_ok(self):
        """Handle OK button click - save and close"""
        self.panel.save()
        self.accept()
