#!/usr/bin/env python3
"""Image Hosts Settings Widget - List of hosts with config dialogs"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QGroupBox, QSizePolicy
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QPixmap
from typing import Dict, Any, Optional
import os

from src.core.image_host_config import get_image_host_config_manager
from bbdrop import get_credential, get_project_root


class ImageHostsSettingsWidget(QWidget):
    """Widget for configuring image host settings - displays list of hosts with config dialogs"""
    settings_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.host_widgets: Dict[str, Dict[str, Any]] = {}
        self.setup_ui()

    def setup_ui(self):
        """Setup the image hosts settings UI"""
        layout = QVBoxLayout(self)

        # Intro text
        intro_label = QLabel(
            "Configure image hosting services. Click Configure to set credentials and upload settings."
        )
        intro_label.setWordWrap(True)
        layout.addWidget(intro_label)

        # Available Hosts Group
        hosts_group = QGroupBox("Available Hosts")
        hosts_layout = QVBoxLayout(hosts_group)

        # Create scrollable area for hosts list
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll_area.setMinimumHeight(150)

        hosts_container = QWidget()
        self.hosts_layout = QVBoxLayout(hosts_container)
        self.hosts_layout.setSpacing(8)

        # Load hosts and create UI
        manager = get_image_host_config_manager()
        for host_id, config in manager.get_enabled_hosts().items():
            self._create_host_row(host_id, config)

        self.hosts_layout.addStretch()
        scroll_area.setWidget(hosts_container)
        hosts_layout.addWidget(scroll_area)
        layout.addWidget(hosts_group)

    def _create_host_row(self, host_id: str, config):
        """Create UI row for a single image host.

        Args:
            host_id: Host identifier
            config: ImageHostConfig instance
        """
        # Container frame
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setFrameShadow(QFrame.Shadow.Raised)
        row_layout = QHBoxLayout(frame)
        row_layout.setContentsMargins(8, 4, 8, 4)
        row_layout.setSpacing(8)

        # Logo or name (160px fixed width)
        logo_container = QWidget()
        logo_container.setFixedWidth(150)
        logo_container.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        logo_layout = QHBoxLayout(logo_container)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        logo_layout.setSpacing(0)

        logo_label = self._load_host_logo(host_id, config, height=22)
        if logo_label:
            logo_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            logo_layout.addWidget(logo_label)
        else:
            # Fallback: Show host name if no logo available
            fallback_label = QLabel(f"<b>{config.name}</b>")
            logo_layout.addWidget(fallback_label)

        row_layout.addWidget(logo_container)

        # Configure Button (80px width)
        configure_btn = QPushButton("Configure")
        configure_btn.setFixedWidth(80)
        configure_btn.setToolTip(f"Configure settings for {config.name}")
        configure_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        configure_btn.clicked.connect(lambda: self._open_dialog(host_id, config))
        row_layout.addWidget(configure_btn)

        # Status label (expanding, right-aligned)
        status_label = QLabel()
        status_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row_layout.addWidget(status_label)

        # Store widgets for later access
        self.host_widgets[host_id] = {
            "frame": frame,
            "status": status_label,
            "logo_label": logo_label
        }

        # Update status
        self._update_status(host_id)

        # Add to layout
        self.hosts_layout.addWidget(frame)

    def _load_host_logo(self, host_id: str, config, height: int = 22) -> Optional[QLabel]:
        """Load and create a QLabel with the host's logo.

        Args:
            host_id: Host identifier (used to find logo file)
            config: ImageHostConfig instance
            height: Target height in pixels (default 22). Maintains aspect ratio.

        Returns:
            QLabel with scaled logo pixmap, or None if logo not found
        """
        # Try host-specific logo first
        logo_path = os.path.join(get_project_root(), "assets", "image_hosts", "logo", f"{host_id}.png")

        # Fallback to config.icon if specified
        if not os.path.exists(logo_path) and config.icon:
            logo_path = os.path.join(get_project_root(), "assets", "image_hosts", config.icon)

        if not os.path.exists(logo_path):
            return None

        try:
            pixmap = QPixmap(logo_path)
            if pixmap.isNull():
                return None

            # Scale logo to specified height, maintaining aspect ratio
            scaled_pixmap = pixmap.scaledToHeight(height, Qt.TransformationMode.SmoothTransformation)

            logo_label = QLabel()
            logo_label.setPixmap(scaled_pixmap)
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            return logo_label
        except Exception:
            return None

    def _update_status(self, host_id: str):
        """Update status label for a host.

        Args:
            host_id: Host identifier
        """
        widgets = self.host_widgets.get(host_id)
        if not widgets:
            return

        status_label = widgets["status"]

        # Check if API key is set (using credentials system)
        api_key = get_credential('api_key')

        if api_key:
            status_label.setText("<span style='color:green;'>API Key: Set</span>")
        else:
            status_label.setText("<span style='color:orange;'>API Key: Not Set</span>")

    def _open_dialog(self, host_id: str, config):
        """Open configuration dialog for a host.

        Args:
            host_id: Host identifier
            config: ImageHostConfig instance
        """
        from src.gui.dialogs.image_host_config_dialog import ImageHostConfigDialog

        dialog = ImageHostConfigDialog(self, host_id, config)
        if dialog.exec():
            # Dialog was accepted, refresh status
            self._update_status(host_id)
            self.settings_changed.emit()

    def save(self):
        """Save settings (compatibility method).

        Returns:
            Empty list (all saving happens in dialogs)
        """
        return []
