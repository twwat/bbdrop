#!/usr/bin/env python3
"""Image Hosts Settings Widget - List of hosts with config dialogs"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QGroupBox, QSizePolicy, QCheckBox,
    QRadioButton, QButtonGroup
)
from PyQt6.QtCore import pyqtSignal, Qt, QSettings
from PyQt6.QtGui import QPixmap
from typing import Dict, Any, Optional
import os

from src.core.image_host_config import (
    get_image_host_config_manager,
    get_all_hosts,
    is_image_host_enabled,
    save_image_host_enabled
)
from bbdrop import get_credential, get_project_root


class ImageHostsSettingsWidget(QWidget):
    """Widget for configuring image host settings - displays list of hosts with config dialogs"""
    settings_changed = pyqtSignal()
    cover_gallery_changed = pyqtSignal(str, str)  # host_id, gallery_id
    cover_host_changed = pyqtSignal(str)          # host_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings("BBDropUploader", "BBDropGUI")
        self.host_widgets: Dict[str, Dict[str, Any]] = {}
        self.cover_host_group = QButtonGroup(self)
        self.cover_host_group.setExclusive(True)
        self.setup_ui()

    def setup_ui(self):
        """Setup the image hosts settings UI"""
        layout = QVBoxLayout(self)

        # Intro text
        intro_label = QLabel(
            "Configure image hosting services. Click Configure to set credentials and upload settings."
        )
        intro_label.setWordWrap(True)
        intro_label.setProperty("class", "tab-description")
        layout.addWidget(intro_label)

        # Available Hosts Group
        hosts_group = QGroupBox("Available Hosts")
        hosts_layout = QVBoxLayout(hosts_group)

        # Add header row
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(18, 0, 8, 4)
        header_layout.setSpacing(8)
        
        enabled_header = QLabel("Enabled")
        enabled_header.setFixedWidth(50)
        enabled_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        enabled_header.setProperty("class", "status-muted")
        header_layout.addWidget(enabled_header)

        cover_header = QLabel("Use for Covers")
        cover_header.setFixedWidth(100)
        cover_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cover_header.setProperty("class", "status-muted")
        header_layout.addWidget(cover_header)

        host_header = QLabel("Host")
        host_header.setProperty("class", "status-muted")
        header_layout.addWidget(host_header, 1)
        
        hosts_layout.addLayout(header_layout)

        # Create scrollable area for hosts list
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll_area.setMinimumHeight(150)

        hosts_container = QWidget()
        self.hosts_layout = QVBoxLayout(hosts_container)
        self.hosts_layout.setSpacing(8)

        # Load hosts and create UI (sorted: enabled first, then alphabetical by name)
        all_hosts = get_all_hosts()
        sorted_hosts = sorted(
            all_hosts.items(),
            key=lambda item: (not is_image_host_enabled(item[0]), item[1].name.lower())
        )
        for host_id, config in sorted_hosts:
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
        frame.setProperty("class", "host-panel")
        row_layout = QHBoxLayout(frame)
        row_layout.setContentsMargins(8, 4, 8, 4)
        row_layout.setSpacing(8)

        # Enable/Disable checkbox (50px width centered)
        enabled = is_image_host_enabled(host_id)
        enable_container = QWidget()
        enable_container.setFixedWidth(50)
        enable_cont_layout = QHBoxLayout(enable_container)
        enable_cont_layout.setContentsMargins(0, 0, 0, 0)
        enable_checkbox = QCheckBox()
        enable_checkbox.setChecked(enabled)
        enable_checkbox.setToolTip(f"Enable/Disable {config.name}")
        enable_checkbox.stateChanged.connect(
            lambda state: self._toggle_host(host_id, state == Qt.CheckState.Checked.value)
        )
        enable_cont_layout.addWidget(enable_checkbox, 0, Qt.AlignmentFlag.AlignCenter)
        row_layout.addWidget(enable_container)

        # Cover Host radio button (100px width centered)
        cover_container = QWidget()
        cover_container.setFixedWidth(100)
        cover_cont_layout = QHBoxLayout(cover_container)
        cover_cont_layout.setContentsMargins(0, 0, 0, 0)
        cover_radio = QRadioButton()
        current_cover_host = self.settings.value('cover/host_id', 'imx', type=str)
        cover_radio.setChecked(host_id == current_cover_host)
        cover_radio.setToolTip(f"Use {config.name} for cover photo uploads")
        cover_radio.toggled.connect(
            lambda checked, hid=host_id: self._on_cover_host_toggled(hid, checked)
        )
        self.cover_host_group.addButton(cover_radio)
        cover_cont_layout.addWidget(cover_radio, 0, Qt.AlignmentFlag.AlignCenter)
        row_layout.addWidget(cover_container)

        # Logo or name (150px fixed width)
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
            "logo_label": logo_label,
            "enable_checkbox": enable_checkbox,
            "cover_radio": cover_radio,
            "logo_container": logo_container,
            "configure_btn": configure_btn
        }

        # Update status and visual state
        self._update_status(host_id)
        self._update_visual_state(host_id, enabled)

        # Add to layout
        self.hosts_layout.addWidget(frame)

    def _on_cover_host_toggled(self, host_id: str, checked: bool):
        """Handle cover host radio button toggle."""
        if checked:
            self.settings.setValue('cover/host_id', host_id)
            self.cover_host_changed.emit(host_id)
            self.settings_changed.emit()

    def _load_host_logo(self, host_id: str, config, height: int = 22) -> Optional[QLabel]:
        """Load and create a QLabel with the host's logo.

        Args:
            host_id: Host identifier (used to find logo file)
            config: ImageHostConfig instance
            height: Target height in pixels (default 22). Maintains aspect ratio.

        Returns:
            QLabel with scaled logo pixmap, or None if logo not found
        """
        # Try config.logo (large image for settings panel)
        if not config.logo:
            return None

        logo_path = os.path.join(get_project_root(), "assets", "image_hosts", config.logo)

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

        # Check host auth requirements
        manager = get_image_host_config_manager()
        config = manager.get_host(host_id)

        if config and not config.requires_auth:
            # Host doesn't require auth (e.g. TurboImageHost)
            username = get_credential('username', host_id)
            if username:
                status_label.setText(f"<span style='color:green;'>Logged in as {username}</span>")
            else:
                status_label.setText("<span style='color:green;'>Ready (no auth required)</span>")
            return

        # Host requires auth - check host-specific API key
        api_key = get_credential('api_key', host_id)

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
        # Connect live enable/disable signal so settings widget stays in sync
        dialog.host_enabled_changed.connect(self._on_dialog_host_enabled_changed)
        # Relay cover gallery changes to Covers tab
        dialog.panel.cover_gallery_changed.connect(self.cover_gallery_changed)
        dialog.exec()

        # Always sync state after dialog closes (enable button takes effect immediately)
        if dialog.enabled_changed():
            self._refresh_host_selector()
            self.settings_changed.emit()

        self._update_status(host_id)

    def _on_dialog_host_enabled_changed(self, host_id: str, enabled: bool):
        """Handle live enable/disable changes from the config dialog."""
        widgets = self.host_widgets.get(host_id)
        if widgets:
            widgets["enable_checkbox"].blockSignals(True)
            widgets["enable_checkbox"].setChecked(enabled)
            widgets["enable_checkbox"].blockSignals(False)
            self._update_visual_state(host_id, enabled)
        # Refresh main window combo and worker status immediately
        self._refresh_host_selector()

    def _toggle_host(self, host_id: str, enabled: bool):
        """Toggle host enabled/disabled state.

        Args:
            host_id: Host identifier
            enabled: Whether host should be enabled
        """
        save_image_host_enabled(host_id, enabled)
        self._update_visual_state(host_id, enabled)
        self._update_status(host_id)
        self._refresh_host_selector()
        self.settings_changed.emit()

    def _get_main_window(self):
        """Walk up the parent chain to find the main BBDropGUI window."""
        # Settings dialog stores the main window as parent_window
        widget = self.parent()
        while widget is not None:
            if hasattr(widget, 'parent_window'):
                return widget.parent_window
            widget = widget.parent() if hasattr(widget, 'parent') else None
        return None

    def _refresh_host_selector(self):
        """Refresh the main window's image host combo and worker status."""
        try:
            main_window = self._get_main_window()
            if not main_window:
                return

            # Refresh quick settings image host combo
            if hasattr(main_window, 'refresh_image_host_combo'):
                main_window.refresh_image_host_combo()

            # Remove disabled image host workers from the worker status table
            if hasattr(main_window, 'worker_status_widget'):
                from src.core.image_host_config import get_image_host_config_manager
                enabled = get_image_host_config_manager().get_enabled_hosts()
                enabled_worker_ids = {f"upload_worker_{hid}" for hid in enabled}
                workers_to_remove = [
                    wid for wid in list(main_window.worker_status_widget._workers.keys())
                    if wid.startswith('upload_worker_') and wid not in enabled_worker_ids
                ]
                for wid in workers_to_remove:
                    main_window.worker_status_widget.remove_worker(wid)
        except Exception as e:
            from src.utils.logger import log
            log(f"Could not refresh host selector: {e}", level="debug", category="ui")

    def _update_visual_state(self, host_id: str, enabled: bool):
        """Update visual state of host row based on enabled status.

        Args:
            host_id: Host identifier
            enabled: Whether host is enabled
        """
        widgets = self.host_widgets.get(host_id)
        if not widgets:
            return

        # Update widget states
        widgets["logo_container"].setEnabled(enabled)
        widgets["configure_btn"].setEnabled(enabled)
        widgets["status"].setEnabled(enabled)

        # Update frame appearance for disabled hosts
        frame = widgets["frame"]
        # No frame styling change — match file hosts behavior

    def save(self):
        """Save settings (compatibility method).

        Returns:
            Empty list (all saving happens in dialogs)
        """
        return []

    def save_to_config(self):
        """Save Image Hosts tab settings and refresh session pool if needed.

        Returns:
            True on success, False on error.
        """
        try:
            from src.utils.logger import log

            results = self.save()
            # Check if any batch size changed to trigger pool refresh
            main_window = self._get_main_window()
            for old_batch, new_batch in results:
                if old_batch != new_batch and main_window and hasattr(main_window, 'uploader'):
                    try:
                        main_window.uploader.refresh_session_pool()
                    except Exception as e:
                        log(f"Failed to refresh connection pool: {e}", level="warning", category="settings")
                    break  # Only need to refresh once
            if main_window and hasattr(main_window, 'refresh_image_host_combo'):
                main_window.refresh_image_host_combo()
            return True
        except Exception as e:
            from src.utils.logger import log
            log(f"Error saving Image Hosts tab: {e}", level="warning", category="settings")
            return False
