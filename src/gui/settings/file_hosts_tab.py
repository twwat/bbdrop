#!/usr/bin/env python3
"""File Hosts Settings Widget - Multi-host upload configuration"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QLineEdit, QCheckBox, QFrame, QProgressBar, QScrollArea, QGroupBox,
    QSpinBox, QMessageBox, QFileDialog, QDialog
)
from PyQt6.QtCore import pyqtSignal, QSettings, Qt, QTimer
from PyQt6.QtGui import QFont, QPixmap
from datetime import datetime
from typing import Dict, Any, Optional

from src.utils.format_utils import format_binary_size
from src.utils.logger import log
from src.core.file_host_config import get_config_manager, HostConfig
from src.gui.icon_manager import get_icon_manager


class FileHostsSettingsWidget(QWidget):
    """Widget for configuring file host settings - PASSIVE: only displays and collects data"""
    settings_changed = pyqtSignal()  # Notify parent of unsaved changes
    primary_host_changed = pyqtSignal(str)       # host_id — new primary image host
    cover_host_changed = pyqtSignal(str)         # host_id — new cover image host
    cover_gallery_changed = pyqtSignal(str, str) # host_id, gallery_id

    def __init__(self, parent, worker_manager):
        """Initialize file hosts settings widget.

        Args:
            parent: Parent settings dialog
            worker_manager: FileHostWorkerManager instance
        """
        super().__init__(parent)
        self.parent_dialog = parent
        self.worker_manager = worker_manager
        self.settings = QSettings("BBDropUploader", "BBDropGUI")
        self.host_widgets: Dict[str, Dict[str, Any]] = {}

        # Track active image host and cover settings state
        self._active_image_host: str = self.settings.value(
            'image_host/default', 'imx', type=str
        )
        self._covers_enabled = self.settings.value('cover/enabled', False, type=bool)

        # Icon manager for status icons
        self.icon_manager = get_icon_manager()

        # Track storage load state
        self.storage_loaded_this_session = False

        # Connect to manager signals for real-time updates
        if self.worker_manager:
            self.worker_manager.storage_updated.connect(self._on_storage_updated)
            self.worker_manager.enabled_workers_changed.connect(self._on_enabled_workers_changed)

        self.setup_ui()

    def setup_ui(self):
        """Setup the file hosts settings UI"""
        layout = QVBoxLayout(self)

        # Intro text
        intro_label = QLabel(
            "Configure file hosts. Galleries will be uploaded to enabled hosts "
            "as ZIP files (automatically or manually, as per settings)"
        )
        intro_label.setWordWrap(True)
        intro_label.setProperty("class", "tab-description")
        layout.addWidget(intro_label)

        # Image Hosts groupbox - sized to content (no scroll; only a handful of hosts)
        from PyQt6.QtWidgets import QSizePolicy
        image_hosts_group = QGroupBox("Image Hosts")
        image_hosts_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.image_hosts_layout_inner = QVBoxLayout(image_hosts_group)
        self.image_hosts_layout_inner.setSpacing(8)

        from src.core.image_host_config import get_all_hosts, is_image_host_enabled
        all_image_hosts = get_all_hosts()
        sorted_image_hosts = sorted(
            all_image_hosts.items(),
            key=lambda item: (not is_image_host_enabled(item[0]), item[1].name.lower())
        )
        for host_id, config in sorted_image_hosts:
            self._create_image_host_row(host_id, config)

        layout.addWidget(image_hosts_group)

        # File Hosts Group
        hosts_group = QGroupBox("File Hosts")
        hosts_layout = QVBoxLayout(hosts_group)

        # Create scrollable area for hosts list
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)  # Remove scroll area border
        scroll_area.setMinimumHeight(200)

        hosts_container = QWidget()
        self.hosts_container_layout = QVBoxLayout(hosts_container)
        self.hosts_container_layout.setSpacing(8)  # Increased spacing for better separation

        # Load hosts and create UI
        config_manager = get_config_manager()
        for host_id, host_config in config_manager.hosts.items():
            self._create_host_row(host_id, host_config, kind='file')

        self.hosts_container_layout.addStretch()
        scroll_area.setWidget(hosts_container)
        hosts_layout.addWidget(scroll_area)

        layout.addWidget(hosts_group)

        # Load initial storage for enabled hosts
        self._load_initial_storage()

    def _create_host_row(self, host_id: str, host_config, kind: str = 'file'):
        """Create UI row for a single file host (image hosts use _create_image_host_row).

        Args:
            host_id: Host identifier
            host_config: HostConfig instance
            kind: retained for backward compat; only 'file' is supported here.
        """
        from PyQt6.QtWidgets import QSizePolicy
        from src.core.file_host_config import get_file_host_setting

        # Container frame
        host_frame = QFrame()
        host_frame.setFrameShape(QFrame.Shape.StyledPanel)
        host_frame.setFrameShadow(QFrame.Shadow.Raised)
        host_frame.setProperty("class", "host-panel")

        # Enable right-click context menu
        host_frame.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        host_frame.customContextMenuRequested.connect(
            lambda pos, hid=host_id, f=host_frame: self._build_host_menu(hid).exec(
                f.mapToGlobal(pos)
            )
        )

        frame_layout = QHBoxLayout(host_frame)
        frame_layout.setContentsMargins(8, 4, 8, 4)  # Tighter vertical spacing
        frame_layout.setSpacing(8)

        # 1. Status Icon (20×20px) - enabled/disabled indicator
        status_icon = QLabel()
        status_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_icon.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        frame_layout.addWidget(status_icon)

        # 2. Logo Container (160px fixed width) - logos scaled to 28px height, centered
        logo_container = QWidget()
        logo_container.setFixedWidth(150)
        logo_container.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        logo_layout = QHBoxLayout(logo_container)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        logo_layout.setSpacing(0)
        #logo_layout.addStretch()  # Center the logo

        logo_label = self._load_host_logo(host_id, host_config, height=22)
        if logo_label:
            logo_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            logo_layout.addWidget(logo_label)
        else:
            # Fallback: Show host name if no logo available
            fallback_label = QLabel(host_config.name)
            #fallback_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
            logo_layout.addWidget(fallback_label)

        #logo_layout.addStretch()  # Center the logo
        frame_layout.addWidget(logo_container)

        # 3. Configure Button (100px width) - for all hosts
        configure_btn = QPushButton("Configure")
        configure_btn.setFixedWidth(80)
        configure_btn.setToolTip(f"Configuration settings for {host_config.name}")
        configure_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        configure_btn.clicked.connect(
            lambda: self._show_host_config_dialog(host_id, host_config)
        )
        frame_layout.addWidget(configure_btn)

        # 4. Storage Bar — same StorageTrafficBar used in the worker table.
        #    Hosts without a per-host quota render the bar in unlimited mode.
        from src.core.file_host_config import get_host_family
        from src.gui.widgets.custom_widgets import StorageTrafficBar

        has_per_host_storage = (
            hasattr(host_config, 'user_info_url')
            and host_config.user_info_url
            and (hasattr(host_config, 'storage_left_path') and host_config.storage_left_path
                 or hasattr(host_config, 'storage_regex') and host_config.storage_regex)
        )
        is_k2s_family = get_host_family(host_id) == 'k2s'

        storage_bar = StorageTrafficBar()
        storage_bar.setMinimumWidth(180)
        storage_bar.setMaximumHeight(20)
        storage_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        if not (has_per_host_storage or is_k2s_family):
            storage_bar.set_unlimited()
        frame_layout.addWidget(storage_bar)
        unlimited_label = None  # retained key for back-compat with existing code paths

        # 5. Status Display (expanding, shows Ready/Disabled status)
        status_label = QLabel()
        status_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        status_text = self._get_status_text(host_id, host_config)
        status_label.setText(status_text)
        self._update_status_label_style(host_id, host_config, status_label)
        frame_layout.addWidget(status_label)

        # Store widgets for later access
        self.host_widgets[host_id] = {
            "frame": host_frame,
            "status_icon": status_icon,
            "status_label": status_label,
            "storage_bar": storage_bar,
            "unlimited_label": unlimited_label,
            "logo_label": logo_label,  # Store logo for theme updates
            "configure_btn": configure_btn,
            "kind": 'file',
            "enable_btn": None  # Removed - redundant with status icon
        }

        # Load cached storage immediately and update status icon
        self.refresh_storage_display(host_id)
        self._update_status_icon(host_id)

        self.hosts_container_layout.addWidget(host_frame)

    def _create_image_host_row(self, host_id: str, config) -> None:
        """Create UI row for a single image host.

        Ported from the pre-merge image_hosts_tab.py: status icon + logo + Configure
        + right-aligned status label. The Enable checkbox and Cover radio that used
        to sit here moved into the right-click context menu.
        """
        from PyQt6.QtWidgets import QSizePolicy

        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setFrameShadow(QFrame.Shadow.Raised)
        frame.setProperty("class", "host-panel")
        frame.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        frame.customContextMenuRequested.connect(
            lambda pos, hid=host_id, f=frame: self._build_host_menu(hid).exec(
                f.mapToGlobal(pos)
            )
        )
        row_layout = QHBoxLayout(frame)
        row_layout.setContentsMargins(8, 4, 8, 4)
        row_layout.setSpacing(8)

        # Status icon (20×20)
        status_icon = QLabel()
        status_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_icon.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        row_layout.addWidget(status_icon)

        # Logo (150px fixed)
        logo_container = QWidget()
        logo_container.setFixedWidth(150)
        logo_container.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        logo_layout = QHBoxLayout(logo_container)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        logo_layout.setSpacing(0)

        logo_label = self._load_image_host_logo(host_id, config, height=22)
        if logo_label:
            logo_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            logo_layout.addWidget(logo_label)
        else:
            logo_layout.addWidget(QLabel(f"<b>{config.name}</b>"))
        row_layout.addWidget(logo_container)

        # Configure button (80px)
        configure_btn = QPushButton("Configure")
        configure_btn.setFixedWidth(80)
        configure_btn.setToolTip(f"Configure settings for {config.name}")
        configure_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        configure_btn.clicked.connect(
            lambda: self._open_image_host_dialog(host_id, config)
        )
        row_layout.addWidget(configure_btn)

        # Storage bar — image hosts have no quota, so display the unlimited state
        # via the same StorageTrafficBar used in the worker table.
        from src.gui.widgets.custom_widgets import StorageTrafficBar
        storage_bar = StorageTrafficBar()
        storage_bar.setMinimumWidth(180)
        storage_bar.setMaximumHeight(20)
        storage_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        storage_bar.set_unlimited()
        row_layout.addWidget(storage_bar)

        # Status label (right-aligned, same fixed styling as file-host column).
        status_label = QLabel()
        status_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row_layout.addWidget(status_label)

        self.host_widgets[host_id] = {
            "frame": frame,
            "status_icon": status_icon,
            "status_label": status_label,
            "logo_label": logo_label,
            "configure_btn": configure_btn,
            "kind": 'image',
        }

        self._update_image_status_label(host_id)
        self._update_image_status_icon(host_id)

        self.image_hosts_layout_inner.addWidget(frame)

    def _load_image_host_logo(self, host_id: str, config, height: int = 22) -> Optional[QLabel]:
        """Load image-host logo from assets/image_hosts/<config.logo>.

        Ported verbatim from the pre-merge image_hosts_tab.py.
        """
        from src.utils.paths import get_project_root
        import os

        if not getattr(config, 'logo', None):
            return None

        logo_path = os.path.join(get_project_root(), "assets", "image_hosts", config.logo)
        if not os.path.exists(logo_path):
            return None

        try:
            pixmap = QPixmap(logo_path)
            if pixmap.isNull():
                return None

            scaled = pixmap.scaledToHeight(height, Qt.TransformationMode.SmoothTransformation)
            logo_label = QLabel()
            logo_label.setPixmap(scaled)
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            return logo_label
        except Exception:
            return None

    def _load_host_logo(self, host_id: str, host_config: HostConfig, height: int = 40) -> Optional[QLabel]:
        """Load and create a clickable QLabel with the host's logo.

        Args:
            host_id: Host identifier (used to find logo file)
            host_config: HostConfig instance (for referral URL)
            height: Target height in pixels (default 40 for dialogs, 28 for settings tab).
                   Maintains aspect ratio.

        Returns:
            Clickable QLabel with scaled logo pixmap, or None if logo not found
        """
        from src.utils.paths import get_project_root
        import os

        logo_path = os.path.join(get_project_root(), "assets", "hosts", "logo", f"{host_id}.png")
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

            # Make clickable if referral URL exists
            if host_config.referral_url:
                from PyQt6.QtGui import QCursor
                logo_label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                logo_label.setToolTip(f"Click to visit {host_config.name}")

                # Install event filter to detect clicks
                def open_referral_url(event):
                    if event.button() == Qt.MouseButton.LeftButton:
                        from PyQt6.QtGui import QDesktopServices
                        from PyQt6.QtCore import QUrl
                        QDesktopServices.openUrl(QUrl(host_config.referral_url))
                        event.accept()

                logo_label.mousePressEvent = open_referral_url  # type: ignore[method-assign]

            return logo_label
        except Exception:
            return None

    def _update_status_icon(self, host_id: str):
        """Update status icon based on enabled state and auto-trigger.

        Args:
            host_id: Host identifier
        """
        widgets = self.host_widgets.get(host_id)
        if not widgets or not widgets.get('status_icon'):
            return

        # Guard against image hosts - use _update_image_status_icon instead
        if widgets.get('kind') == 'image':
            return

        status_icon = widgets['status_icon']
        is_enabled = self.worker_manager.is_enabled(host_id) if self.worker_manager else False

        if is_enabled:
            from src.core.file_host_config import get_file_host_setting
            trigger = get_file_host_setting(host_id, "trigger", "str")
            has_auto = trigger and trigger != "disabled"
            icon_key = 'status-active' if has_auto else 'status-enabled'
            tooltip = f"Auto-upload: {trigger}" if has_auto else "Enabled"
        else:
            icon_key = 'status-disabled'
            tooltip = "Disabled"

        icon = self.icon_manager.get_icon(icon_key, theme_mode=None)
        pixmap = icon.pixmap(20, 20)
        status_icon.setPixmap(pixmap)
        status_icon.setToolTip(tooltip)

    def _get_status_text(self, host_id: str, host_config) -> str:
        """Get semantic status text for a host.

        Returns: "Ready (Auto)", "Ready (Manual)", "Credentials Required", or "Disabled"
        """
        from src.core.file_host_config import get_file_host_setting

        # Guard against image hosts - they use _update_image_status_label
        widgets = self.host_widgets.get(host_id, {})
        if widgets.get('kind') == 'image':
            return ""

        # Check if host is enabled
        is_enabled = get_file_host_setting(host_id, "enabled", "bool")

        if not is_enabled:
            # Check if credentials exist
            test_results = self._load_test_results_from_settings(host_id)
            has_credentials = test_results and test_results.get('credentials_valid', False)

            if not has_credentials and host_config.requires_auth:
                return "Credentials Required"
            else:
                return "Disabled"

        # Host is enabled — but are credentials actually configured?
        if host_config.requires_auth:
            test_results = self._load_test_results_from_settings(host_id)
            has_credentials = test_results and test_results.get('credentials_valid', False)
            if not has_credentials:
                return "Credentials Required"

        # Host is enabled and credentials OK - check auto-upload trigger
        trigger = get_file_host_setting(host_id, "trigger", "str")
        is_auto = trigger in ["on_added", "on_started", "on_completed"]

        if is_auto:
            map = {"on_added": "Add", "on_started": "Start", "on_completed": "Done"}
            automsg = trigger.replace("on_","").capitalize()
            return f"Ready (AUTO: On-{map[trigger]})"
        else:
            return "Ready (Manual)"

    def _update_status_label_style(self, host_id: str, host_config, status_label: QLabel):
        """Update status label styling based on current status.

        Args:
            host_id: Host identifier
            host_config: HostConfig instance
            status_label: QLabel to update
        """
        from src.core.file_host_config import get_file_host_setting

        # Guard against image hosts - they use _update_image_status_label
        widgets = self.host_widgets.get(host_id, {})
        if widgets.get('kind') == 'image':
            return

        # Get current status
        is_enabled = get_file_host_setting(host_id, "enabled", "bool")

        if not is_enabled:
            status_label.setProperty("class", "status-disabled")
        elif not host_config.requires_auth:
            status_label.setProperty("class", "status-success-light")
        else:
            test_results = self._load_test_results_from_settings(host_id)
            if not test_results:
                status_label.setProperty("class", "status-warning-light")
            else:
                tests_passed = sum([
                    test_results['credentials_valid'],
                    test_results['user_info_valid'],
                    test_results['upload_success'],
                    test_results['delete_success']
                ])

                if tests_passed == 4:
                    status_label.setProperty("class", "status-success")
                elif tests_passed > 0:
                    status_label.setProperty("class", "status-warning")
                else:
                    status_label.setProperty("class", "status-error")

        # Force style refresh
        label_style = status_label.style()
        if label_style:
            label_style.unpolish(status_label)
            label_style.polish(status_label)

    def _update_status_label(self, host_id: str, host_config, status_label: QLabel):
        """Update status label with semantic status text.

        Args:
            host_id: Host identifier
            host_config: HostConfig instance
            status_label: QLabel to update
        """
        status_text = self._get_status_text(host_id, host_config)
        status_label.setText(status_text)
        self._update_status_label_style(host_id, host_config, status_label)

    def _load_test_results_from_settings(self, host_id: str) -> Optional[dict]:
        """Load test results directly from QSettings.

        This is used at widget initialization when workers may not exist yet.

        Args:
            host_id: Host identifier

        Returns:
            Dictionary with test results, or None if no results exist
        """
        prefix = f"FileHosts/TestResults/{host_id}"
        ts = self.settings.value(f"{prefix}/timestamp", None, type=int)
        if not ts or ts == 0:
            return None

        return {
            'timestamp': ts,
            'credentials_valid': self.settings.value(f"{prefix}/credentials_valid", False, type=bool),
            'user_info_valid': self.settings.value(f"{prefix}/user_info_valid", False, type=bool),
            'upload_success': self.settings.value(f"{prefix}/upload_success", False, type=bool),
            'delete_success': self.settings.value(f"{prefix}/delete_success", False, type=bool),
            'error_message': self.settings.value(f"{prefix}/error_message", '', type=str)
        }

    def _get_trigger_display_text(self, host_id):
        """Get display text for auto-upload trigger (single string value)."""
        from src.core.file_host_config import get_file_host_setting
        trigger = get_file_host_setting(host_id, "trigger", "str")

        if trigger == "on_added":
            return "On Added"
        elif trigger == "on_started":
            return "On Started"
        elif trigger == "on_completed":
            return "On Completed"
        else:  # "disabled" or any other value
            return "Disabled"

    def _on_test_clicked(self, host_id: str):
        """Handle test button click - delegate to worker.

        Args:
            host_id: Host identifier
        """
        if not self.worker_manager:
            QMessageBox.warning(
                self,
                "Not Available",
                "Worker manager not available"
            )
            return

        worker = self.worker_manager.get_worker(host_id)
        if not worker:
            QMessageBox.warning(
                self,
                "Not Enabled",
                "Please enable the host first to test it."
            )
            return

        # Update UI to show testing
        widgets = self.host_widgets.get(host_id, {})
        status_label = widgets.get('status_label')

        if status_label:
            status_label.setText("⏳ Test started - close and re-open settings to see results")
            # Use QSS class for theme-aware styling
            status_label.setProperty("class", "status-info")
            status_label.style().unpolish(status_label)
            status_label.style().polish(status_label)

        # Trigger test (result will be cached in QSettings)
        worker.test_connection()

    def _format_storage_compact(self, left: int, total: int, host_id: str = "") -> str:
        """Format storage as compact string showing amount free.

        Args:
            left: Free storage in bytes
            total: Total storage in bytes
            host_id: Host identifier for family-aware formatting

        Returns:
            Compact storage string showing free amount (e.g., "15.2 GB free")
        """
        if total <= 0:
            return "Unknown"

        from src.utils.format_utils import format_host_storage_size
        left_formatted = format_host_storage_size(host_id, left)
        return f"{left_formatted} free"

    def refresh_storage_display(self, host_id: str):
        """Update storage display by reading from QSettings cache.

        Args:
            host_id: Host identifier
        """
        widgets = self.host_widgets.get(host_id, {})
        # Guard against image hosts - they don't have storage
        if widgets.get('kind') == 'image':
            return

        from src.core.file_host_config import get_host_family
        if get_host_family(host_id) == 'k2s':
            from src.core.file_host_config import get_k2s_family_storage
            used, total = get_k2s_family_storage()
            left = max(0, total - used)
        else:
            # Read from QSettings cache (written by worker as strings to avoid Qt 32-bit overflow)
            total_str = self.settings.value(f"FileHosts/{host_id}/storage_total", "0")
            left_str = self.settings.value(f"FileHosts/{host_id}/storage_left", "0")

            try:
                total = int(total_str) if total_str else 0
                left = int(left_str) if left_str else 0
            except (ValueError, TypeError):
                total = 0
                left = 0

        widgets = self.host_widgets.get(host_id, {})
        storage_bar = widgets.get('storage_bar')

        # Skip if no storage bar widget exists
        if not storage_bar:
            return

        # ONLY update if we have valid data - NEVER clear existing display
        if total == 0 and left == 0:
            return

        # Validate storage data before updating
        if total <= 0 or left < 0 or left > total:
            return

        # StorageTrafficBar handles formatting, colors and tooltip internally.
        storage_bar.update_storage(total, left, host_id)


    def refresh_test_results(self, host_id: str):
        """Update test results display by reading from QSettings cache.

        Args:
            host_id: Host identifier
        """
        # Read from QSettings cache (written by worker) - CONSISTENT keys for all hosts
        prefix = f"FileHosts/TestResults/{host_id}"
        results = {
            "timestamp": self.settings.value(f"{prefix}/timestamp", 0.0, type=float),
            "credentials_valid": self.settings.value(f"{prefix}/credentials_valid", False, type=bool),
            "user_info_valid": self.settings.value(f"{prefix}/user_info_valid", False, type=bool),
            "upload_success": self.settings.value(f"{prefix}/upload_success", False, type=bool),
            "delete_success": self.settings.value(f"{prefix}/delete_success", False, type=bool),
            "error_message": self.settings.value(f"{prefix}/error_message", "", type=str)
        }
        if results["timestamp"] == 0.0:
            return  # No test results cached
        widgets = self.host_widgets.get(host_id, {})
        status_label = widgets.get('status_label')
        test_btn = widgets.get('test_btn')

        # Re-enable test button
        if test_btn:
            test_btn.setEnabled(True)

        if not status_label:
            return

        # Update status label with semantic status (NOT test results)
        from src.core.file_host_config import get_config_manager
        config_manager = get_config_manager()
        host_config = config_manager.hosts.get(host_id)
        if host_config:
            status_text = self._get_status_text(host_id, host_config)
            status_label.setText(status_text)
            self._update_status_label_style(host_id, host_config, status_label)

    def _show_host_config_dialog(self, host_id: str, host_config):
        """Show detailed configuration dialog for a host.

        Args:
            host_id: Host identifier
            host_config: HostConfig instance
        """
        from src.gui.dialogs.file_host_config_dialog import FileHostConfigDialog

        # Get main widgets for this host
        main_widgets = self.host_widgets.get(host_id, {})

        # Create and show config dialog with worker_manager
        dialog = FileHostConfigDialog(self, host_id, host_config, main_widgets, self.worker_manager)
        # Defer file-manager open past dialog.exec() return to avoid modal blocking
        main_window = getattr(self.parent_dialog, 'parent_window', None)
        if main_window is not None and hasattr(main_window, 'open_file_manager_dialog'):
            dialog.browse_files_requested.connect(
                lambda hid: QTimer.singleShot(0, lambda: main_window.open_file_manager_dialog(host_id=hid))
            )
        else:
            from src.utils.logger import log
            log("Browse Files button wired but parent_window.open_file_manager_dialog unavailable",
                level="warning", category="file_hosts")
        result = dialog.exec()

        # Save changes if user clicked Save
        if result == QDialog.DialogCode.Accepted:
            try:
                from src.utils.logger import log
                log(f"Config dialog accepted for {host_id}", level="debug", category="file_hosts")

                # Get values from dialog (credentials already saved by dialog._on_apply_clicked)
                enabled = dialog.get_enabled_state()
                trigger_value = dialog.get_trigger_settings()
                log(f"Got values: enabled={enabled}, trigger={trigger_value}",
                    level="debug", category="file_hosts")

                # Save enabled state and trigger using new API
                from src.core.file_host_config import save_file_host_setting
                save_file_host_setting(host_id, "enabled", enabled)
                save_file_host_setting(host_id, "trigger", trigger_value)
                log(f"Saved settings for {host_id}", level="info", category="file_hosts")

                # NOTE: Credentials are already saved by dialog._on_apply_clicked()
                # Do NOT save again here - widgets may be destroyed, returning wrong value

                # Spawn or kill worker based on enabled state
                if enabled:
                    self.worker_manager.enable_host(host_id)
                else:
                    self.worker_manager.disable_host(host_id)

                # Refresh display in File Hosts tab
                self._refresh_host_display(host_id, host_config)
                log(f"Refreshed display for {host_id}", level="debug", category="file_hosts")

                # Mark settings as changed
                self.settings_changed.emit()
                log(f"Save complete for {host_id}", level="info", category="file_hosts")

            except Exception as e:
                log(f"Failed to save config for {host_id}: {e}", level="error", category="file_hosts")
                import traceback
                traceback.print_exc()

    def _refresh_host_display(self, host_id: str, host_config, credentials: Optional[str] = None):
        """Refresh display for a host after config changes.

        Args:
            host_id: Host identifier
            host_config: Updated HostConfig
            credentials: New credentials (optional)
        """
        widgets = self.host_widgets.get(host_id)
        if not widgets:
            return

        # Update credentials display if provided
        if credentials and widgets.get("creds_display"):
            widgets["creds_display"].setText(credentials)

        # Refresh status label and storage
        if widgets.get("status_label"):
            self._update_status_label(host_id, host_config, widgets["status_label"])

        self.refresh_storage_display(host_id)
    def _update_image_status_icon(self, host_id: str) -> None:
        """Update status icon for an image host based on enabled/active/cover state.

        Args:
            host_id: Image host identifier
        """
        widgets = self.host_widgets.get(host_id)
        if not widgets:
            return

        from src.core.image_host_config import is_image_host_enabled
        enabled = is_image_host_enabled(host_id)
        is_active = (host_id == self._active_image_host)
        cover_host = self.settings.value('cover/host_id', 'imx', type=str)
        is_cover = self._covers_enabled and (host_id == cover_host)

        if enabled and is_active:
            key = 'status-active-cover' if is_cover else 'status-active'
        elif enabled:
            key = 'status-enabled-cover' if is_cover else 'status-enabled'
        else:
            key = 'status-disabled-cover' if is_cover else 'status-disabled'

        if self.icon_manager is None:
            return

        icon = self.icon_manager.get_icon(key, theme_mode=None)
        widgets['status_icon'].setPixmap(icon.pixmap(20, 20))

    def _update_image_status_label(self, host_id: str) -> None:
        """Update status label for an image host based on credentials.

        Args:
            host_id: Image host identifier
        """
        widgets = self.host_widgets.get(host_id)
        if not widgets:
            return

        from src.core.image_host_config import get_image_host_config_manager
        from src.utils.credentials import get_credential

        manager = get_image_host_config_manager()
        config = manager.get_host(host_id)
        label = widgets['status_label']

        from src.core.image_host_config import is_image_host_enabled
        enabled = is_image_host_enabled(host_id)

        if not enabled:
            text, css = "Disabled", "status-disabled"
        elif config and not config.requires_auth:
            username = get_credential('username', host_id)
            text = "Credentials: Set" if username else "Ready (no auth required)"
            css = "status-success-light"
        else:
            api_key = get_credential('api_key', host_id)
            if api_key:
                text, css = "API Key: Set", "status-success-light"
            else:
                text, css = "API Key: Not Set", "status-warning-light"

        label.setText(text)
        label.setProperty("class", css)
        style = label.style()
        if style is not None:
            style.unpolish(label)
            style.polish(label)

    def _open_image_host_dialog(self, host_id: str, config) -> None:
        """Open configuration dialog for an image host.

        Args:
            host_id: Image host identifier
            config: ImageHostConfig instance
        """
        from src.gui.dialogs.image_host_config_dialog import ImageHostConfigDialog

        dialog = ImageHostConfigDialog(self, host_id, config)
        dialog.panel.cover_gallery_changed.connect(self.cover_gallery_changed)
        dialog.exec()

        if dialog.enabled_changed():
            self.settings_changed.emit()

        self._update_image_status_label(host_id)
        self._update_image_status_icon(host_id)

    def _build_host_menu(self, host_id: str) -> 'QMenu':
        """Build the right-click menu for a host row.

        Mirrors the worker-table menu in worker_status_widget.py so users
        learn one menu and use it in both places.

        Args:
            host_id: Host identifier

        Returns:
            QMenu with appropriate actions for this host kind and state
        """
        from PyQt6.QtWidgets import QMenu

        widgets = self.host_widgets.get(host_id)
        if not widgets:
            return QMenu(self)
        kind = widgets.get('kind', 'file')
        menu = QMenu(self)
        menu.setToolTipsVisible(True)

        if kind == 'image':
            from src.core.image_host_config import is_image_host_enabled
            enabled = is_image_host_enabled(host_id)
            if enabled:
                disable_action = menu.addAction("Disable Host")
                disable_action.triggered.connect(
                    lambda: self._toggle_image_host(host_id, False)
                )
            else:
                enable_action = menu.addAction("Enable Host")
                enable_action.triggered.connect(
                    lambda: self._toggle_image_host(host_id, True)
                )

            if enabled:
                menu.addSeparator()
                is_primary = (host_id == self._active_image_host)
                primary_action = menu.addAction("Set as Primary Host")
                primary_action.setCheckable(True)
                primary_action.setChecked(is_primary)
                primary_action.setEnabled(not is_primary)
                primary_action.triggered.connect(
                    lambda: self.primary_host_changed.emit(host_id)
                )

                qsettings = QSettings("BBDropUploader", "BBDropGUI")
                covers_on = qsettings.value('cover/enabled', False, type=bool)
                current_cover = qsettings.value('cover/host_id', 'imx', type=str)
                is_cover = covers_on and (host_id == current_cover)
                cover_action = menu.addAction("Set as Cover Host")
                cover_action.setCheckable(True)
                cover_action.setChecked(is_cover)
                cover_action.setEnabled(not is_cover)
                cover_action.triggered.connect(
                    lambda: self._on_cover_host_selected(host_id)
                )

            menu.addSeparator()
            configure_action = menu.addAction("Configure Host...")
            configure_action.triggered.connect(
                lambda: self._open_image_host_dialog(
                    host_id, self._get_image_host_config(host_id)
                )
            )
            return menu

        # ----- file host menu -----
        from src.core.file_host_config import get_file_host_setting, get_config_manager
        enabled = bool(self.worker_manager and self.worker_manager.is_enabled(host_id))
        trigger = get_file_host_setting(host_id, "trigger", "str") or "disabled"

        if enabled:
            disable_action = menu.addAction("Disable Host")
            disable_action.triggered.connect(
                lambda: self._toggle_file_host(host_id, False)
            )
        else:
            enable_action = menu.addAction("Enable Host")
            enable_action.triggered.connect(
                lambda: self._toggle_file_host(host_id, True)
            )

        menu.addSeparator()
        trigger_menu = menu.addMenu("Set Auto-Upload Trigger")
        for label, value in [
            ("On Added", "on_added"),
            ("On Started", "on_started"),
            ("On Completed", "on_completed"),
            ("Disabled", "disabled"),
        ]:
            action = trigger_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(trigger == value)
            action.triggered.connect(
                lambda checked, v=value: self._set_file_host_trigger(host_id, v)
            )

        menu.addSeparator()
        from src.network.file_manager.factory import is_host_supported
        browse_action = menu.addAction("Browse Files...")
        supported = is_host_supported(host_id)
        browse_action.setEnabled(enabled and supported)
        if not supported:
            browse_action.setToolTip("File manager not supported for this host")
        elif not enabled:
            browse_action.setToolTip("Enable the host to browse its files")
        browse_action.triggered.connect(
            lambda: self._browse_files_for_host(host_id)
        )

        hc = get_config_manager().hosts.get(host_id)
        configure_action = menu.addAction("Configure Host...")
        if hc is not None:
            configure_action.triggered.connect(
                lambda: self._show_host_config_dialog(host_id, hc)
            )
        return menu

    def _get_image_host_config(self, host_id: str):
        """Get the ImageHostConfig for an image host.

        Args:
            host_id: Image host identifier

        Returns:
            ImageHostConfig instance or None
        """
        from src.core.image_host_config import get_image_host_config_manager
        return get_image_host_config_manager().get_host(host_id)

    def _toggle_image_host(self, host_id: str, enabled: bool) -> None:
        """Enable or disable an image host.

        Args:
            host_id: Image host identifier
            enabled: Whether to enable or disable
        """
        from src.core.image_host_config import save_image_host_enabled
        save_image_host_enabled(host_id, enabled)
        self._update_image_status_icon(host_id)
        self._update_image_status_label(host_id)
        self.settings_changed.emit()

    def _toggle_file_host(self, host_id: str, enabled: bool) -> None:
        """Enable or disable a file host.

        Args:
            host_id: File host identifier
            enabled: Whether to enable or disable
        """
        if not self.worker_manager:
            return
        if enabled:
            self.worker_manager.enable_host(host_id)
        else:
            self.worker_manager.disable_host(host_id)
        self._update_status_icon(host_id)
        self.settings_changed.emit()

    def _set_file_host_trigger(self, host_id: str, trigger: str) -> None:
        """Set the auto-upload trigger for a file host.

        Args:
            host_id: File host identifier
            trigger: Trigger value ('on_added', 'on_started', 'on_completed', 'disabled')
        """
        from src.core.file_host_config import save_file_host_setting
        save_file_host_setting(host_id, "trigger", trigger)
        self._update_status_icon(host_id)
        self.settings_changed.emit()

    def _on_cover_host_selected(self, host_id: str) -> None:
        """Handle cover host selection from menu.

        Args:
            host_id: Image host identifier to set as cover host
        """
        self.settings.setValue('cover/host_id', host_id)
        self.cover_host_changed.emit(host_id)
        for hid, widgets in self.host_widgets.items():
            if widgets.get('kind') == 'image':
                self._update_image_status_icon(hid)
        self.settings_changed.emit()

    def _browse_files_for_host(self, host_id: str) -> None:
        """Open the File Manager parented to the Settings dialog.

        Parenting to the settings dialog (rather than the main window) lets
        the child dialog receive input and stack above the modal parent.
        Without this, the File Manager opens behind the Settings dialog
        and is unreachable until Settings closes.
        """
        from src.gui.dialogs.file_manager_dialog import FileManagerDialog
        from PyQt6.QtCore import Qt as _Qt

        settings_dialog = getattr(self, 'parent_dialog', None) or self.window()
        dialog = FileManagerDialog(parent=settings_dialog, host_id=host_id)
        dialog.setAttribute(_Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _load_initial_storage(self):
        """Load cached storage ONLY - no workers, no timers"""
        if self.storage_loaded_this_session:
            return

        # Just read from QSettings cache for ALL hosts (enabled or not)
        from src.core.file_host_config import get_config_manager
        config_manager = get_config_manager()

        for host_id in config_manager.hosts.keys():
            self.refresh_storage_display(host_id)
            self.refresh_test_results(host_id)

        self.storage_loaded_this_session = True


    def load_settings(self, settings: dict):
        """Refresh display from current config (display-only UI)."""
        # File Hosts tab is display-only - all data loaded in _create_host_row()
        # This method exists for compatibility but does nothing
        pass

    def get_settings(self) -> dict:
        """Get settings (display-only UI returns empty)."""
        # File Hosts tab is display-only - no settings to get
        # All editing happens in config dialog
        return {"global_limit": 3, "per_host_limit": 2, "hosts": {}}

    def load_from_config(self):
        """Load file hosts settings from INI and encrypted credentials from OS keyring."""
        try:
            import os
            import configparser
            from src.core.file_host_config import get_config_manager, get_file_host_setting
            from src.utils.paths import get_config_path
            from src.utils.credentials import get_credential, decrypt_password

            config = configparser.ConfigParser()
            config_file = get_config_path()

            if os.path.exists(config_file):
                config.read(config_file, encoding='utf-8')

            # Prepare settings dict
            settings_dict = {
                'global_limit': 3,
                'per_host_limit': 2,
                'hosts': {}
            }

            # Load connection limits
            if 'FILE_HOSTS' in config:
                settings_dict['global_limit'] = config.getint('FILE_HOSTS', 'global_limit', fallback=3)
                settings_dict['per_host_limit'] = config.getint('FILE_HOSTS', 'per_host_limit', fallback=2)

            # Load per-host settings
            config_manager = get_config_manager()
            for host_id in config_manager.hosts.keys():
                host_settings = {
                    'enabled': get_file_host_setting(host_id, 'enabled', 'bool'),
                    'credentials': '',
                    'trigger': get_file_host_setting(host_id, 'trigger', 'str')
                }

                # Load encrypted credentials from OS keyring
                encrypted_creds = get_credential(f'file_host_{host_id}_credentials')
                if encrypted_creds:
                    decrypted = decrypt_password(encrypted_creds)
                    if decrypted:
                        host_settings['credentials'] = decrypted

                settings_dict['hosts'][host_id] = host_settings

            # Apply settings to widget
            self.load_settings(settings_dict)

        except Exception as e:
            import traceback
            log(f"Failed to load file hosts settings: {e}", level="error", category="settings")
            traceback.print_exc()

    def save_to_config(self):
        """Save file hosts settings to INI and encrypted credentials to OS keyring."""
        try:
            import os
            import configparser
            from src.core.file_host_config import save_file_host_setting
            from src.utils.paths import get_config_path
            from src.utils.credentials import set_credential, encrypt_password

            config = configparser.ConfigParser()
            config_file = get_config_path()

            if os.path.exists(config_file):
                config.read(config_file, encoding='utf-8')

            if 'FILE_HOSTS' not in config:
                config.add_section('FILE_HOSTS')

            # Get settings from widget
            widget_settings = self.get_settings()

            # Save connection limits
            config.set('FILE_HOSTS', 'global_limit', str(widget_settings['global_limit']))
            config.set('FILE_HOSTS', 'per_host_limit', str(widget_settings['per_host_limit']))

            # Save per-host settings
            for host_id, host_settings in widget_settings['hosts'].items():
                save_file_host_setting(host_id, 'enabled', host_settings['enabled'])
                save_file_host_setting(host_id, 'trigger', host_settings['trigger'])

                # Save encrypted credentials to OS keyring
                creds_text = host_settings.get('credentials', '')
                if creds_text:
                    encrypted = encrypt_password(creds_text)
                    set_credential(f'file_host_{host_id}_credentials', encrypted)
                else:
                    set_credential(f'file_host_{host_id}_credentials', '')

            # Write INI file
            with open(config_file, 'w', encoding='utf-8') as f:
                config.write(f)

        except Exception as e:
            log(f"Failed to save file hosts settings: {e}", level="warning", category="settings")

    def _on_storage_updated(self, host_id: str, total: int, left: int):
        """Handle storage update signal from manager.

        Args:
            host_id: Host that was updated
            total: Total storage in bytes
            left: Free storage in bytes
        """
        # Refresh storage display for this host
        self.refresh_storage_display(host_id)

    def _on_enabled_workers_changed(self, enabled_hosts: list):
        """Handle enabled workers list change from manager.

        Args:
            enabled_hosts: List of enabled host IDs
        """
        # Update status labels and icons for all hosts
        from src.core.file_host_config import get_config_manager
        config_manager = get_config_manager()

        for host_id, host_config in config_manager.hosts.items():
            widgets = self.host_widgets.get(host_id)
            if widgets:
                # Update status label
                if widgets.get('status_label'):
                    self._update_status_label(host_id, host_config, widgets['status_label'])
                # Update status icon
                self._update_status_icon(host_id)

    def _update_enable_button_state(self, host_id: str):
        """Legacy method - no longer used with compact layout.

        The enable/disable button has been removed from the compact layout.
        Enable/disable is now done through the Configure dialog.

        Args:
            host_id: Host identifier
        """
        # Method kept for backward compatibility but does nothing
        pass

    def _on_enable_disable_clicked(self, host_id: str):
        """Legacy method - no longer used with compact layout.

        Args:
            host_id: Host identifier
        """
        # Method kept for backward compatibility but does nothing
        pass

    def set_active_image_host(self, host_id: str) -> None:
        """Update the active (primary) image host indicator.

        Args:
            host_id: Image host identifier (e.g., 'imx', 'turbo', 'pixhost')
        """
        self._active_image_host = host_id
        # Refresh status icons for all image hosts
        for hid, widgets in self.host_widgets.items():
            if widgets.get('kind') == 'image':
                self._update_image_status_icon(hid)

    def set_covers_enabled(self, enabled: bool) -> None:
        """Called by the Covers tab when cover uploads toggle.

        Args:
            enabled: Whether cover uploads are enabled
        """
        self._covers_enabled = enabled
        # Refresh status icons for all image hosts
        for hid, widgets in self.host_widgets.items():
            if widgets.get('kind') == 'image':
                self._update_image_status_icon(hid)
