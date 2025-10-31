#!/usr/bin/env python3
"""File Hosts Settings Widget - Multi-host upload configuration"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QLineEdit, QCheckBox, QFrame, QProgressBar, QScrollArea, QGroupBox,
    QSpinBox, QMessageBox, QFileDialog, QDialog
)
from PyQt6.QtCore import pyqtSignal, QSettings
from PyQt6.QtGui import QFont
from datetime import datetime
from typing import Dict, Any, Optional

from src.utils.format_utils import format_binary_size
from src.core.file_host_config import get_config_manager


class FileHostsSettingsWidget(QWidget):
    """Widget for configuring file host settings - PASSIVE: only displays and collects data"""
    settings_changed = pyqtSignal()  # Notify parent of unsaved changes

    def __init__(self, parent, worker_manager):
        """Initialize file hosts settings widget.

        Args:
            parent: Parent settings dialog
            worker_manager: FileHostWorkerManager instance
        """
        super().__init__(parent)
        self.parent_dialog = parent
        self.worker_manager = worker_manager
        self.settings = QSettings("ImxUploader", "ImxUploadGUI")
        self.host_widgets: Dict[str, Dict[str, Any]] = {}

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
            "Configure file host uploads for galleries. Enabled hosts will automatically "
            "create ZIPs of your galleries and upload them in parallel."
        )
        intro_label.setWordWrap(True)
        layout.addWidget(intro_label)

        # Connection Limits Group
        limits_group = QGroupBox("Connection Limits")
        limits_layout = QFormLayout(limits_group)

        self.global_limit_spin = QSpinBox()
        self.global_limit_spin.setMinimum(1)
        self.global_limit_spin.setMaximum(10)
        self.global_limit_spin.setToolTip(
            "Maximum total concurrent file host uploads across all hosts"
        )
        # Block signals during initial value set, then connect
        self.global_limit_spin.blockSignals(True)
        self.global_limit_spin.setValue(3)
        self.global_limit_spin.blockSignals(False)
        self.global_limit_spin.valueChanged.connect(lambda: self.settings_changed.emit())
        limits_layout.addRow("Global upload limit:", self.global_limit_spin)

        self.per_host_limit_spin = QSpinBox()
        self.per_host_limit_spin.setMinimum(1)
        self.per_host_limit_spin.setMaximum(5)
        self.per_host_limit_spin.setToolTip(
            "Maximum concurrent uploads per individual host"
        )
        # Block signals during initial value set, then connect
        self.per_host_limit_spin.blockSignals(True)
        self.per_host_limit_spin.setValue(2)
        self.per_host_limit_spin.blockSignals(False)
        self.per_host_limit_spin.valueChanged.connect(lambda: self.settings_changed.emit())
        limits_layout.addRow("Per-host limit:", self.per_host_limit_spin)

        layout.addWidget(limits_group)

        # Available Hosts Group
        hosts_group = QGroupBox("Available Hosts")
        hosts_layout = QVBoxLayout(hosts_group)

        # Create scrollable area for hosts list
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(200)

        hosts_container = QWidget()
        self.hosts_container_layout = QVBoxLayout(hosts_container)
        self.hosts_container_layout.setSpacing(2)

        # Load hosts and create UI
        config_manager = get_config_manager()
        for host_id, host_config in config_manager.hosts.items():
            self._create_host_row(host_id, host_config)

        self.hosts_container_layout.addStretch()
        scroll_area.setWidget(hosts_container)
        hosts_layout.addWidget(scroll_area)

        # Add custom host button
        add_custom_btn = QPushButton("+ Add Custom Host")
        add_custom_btn.setToolTip("Add a custom host configuration from JSON file")
        add_custom_btn.clicked.connect(self._add_custom_host)
        hosts_layout.addWidget(add_custom_btn)

        layout.addWidget(hosts_group)

        # Load initial storage for enabled hosts
        self._load_initial_storage()

    def _create_host_row(self, host_id: str, host_config):
        """Create UI row for a single host.

        Args:
            host_id: Host identifier
            host_config: HostConfig instance
        """
        # Container frame
        host_frame = QFrame()
        host_frame.setFrameShape(QFrame.Shape.StyledPanel)
        host_frame.setFrameShadow(QFrame.Shadow.Raised)
        frame_layout = QVBoxLayout(host_frame)
        frame_layout.setContentsMargins(8, 8, 8, 8)
        frame_layout.setSpacing(4)

        # Top row: Status indicator + Configure button
        top_row = QHBoxLayout()

        # Status indicator (enabled/disabled)
        status_icon = QLabel("✓" if host_config.enabled else "○")
        status_icon.setStyleSheet(f"font-size: 14px; color: {'green' if host_config.enabled else 'gray'};")
        status_icon.setFixedWidth(20)
        top_row.addWidget(status_icon)

        host_label = QLabel(host_config.name)
        host_label.setStyleSheet("font-weight: bold;")
        top_row.addWidget(host_label, 1)

        # Test status label
        status_label = QLabel()
        self._update_status_label(host_id, host_config, status_label)
        top_row.addWidget(status_label)

        top_row.addStretch()
        frame_layout.addLayout(top_row)

        # Initialize enable button to None (created only for hosts that require auth)
        enable_btn = None

        # Credentials row (if requires auth) - READ-ONLY DISPLAY
        if host_config.requires_auth:
            creds_row = QHBoxLayout()

            creds_label = QLabel("Credentials:")
            creds_label.setStyleSheet("font-size: 10px; color: gray;")
            creds_label.setFixedWidth(80)
            creds_row.addWidget(creds_label)

            # Read-only credentials display (blue dots)
            creds_display = QLineEdit()
            creds_display.setReadOnly(True)
            creds_display.setEchoMode(QLineEdit.EchoMode.Password)
            creds_display.setStyleSheet("QLineEdit { background-color: #f0f0f0; color: #1d98de; }")
            creds_display.setPlaceholderText("Not configured")
            
            # Load credentials from config if available
            from imxup import get_credential, decrypt_password
            encrypted_creds = get_credential(f"file_host_{host_id}_credentials")
            if encrypted_creds:
                try:
                    decrypted = decrypt_password(encrypted_creds)
                    creds_display.setText(decrypted)
                except:
                    pass  # Invalid/corrupted credentials
            
            creds_row.addWidget(creds_display, 1)

            # Enable/Disable button (power button paradigm)
            enable_btn = QPushButton()
            enable_btn.setMinimumWidth(70)
            enable_btn.setMaximumWidth(70)
            enable_btn.clicked.connect(lambda checked=False, hid=host_id: self._on_enable_disable_clicked(hid))
            creds_row.addWidget(enable_btn)

            # Configure button (moved here)
            configure_btn = QPushButton("Configure")
            configure_btn.setToolTip(f"Configure {host_config.name}")
            configure_btn.clicked.connect(lambda: self._show_host_config_dialog(host_id, host_config))
            configure_btn.setMaximumWidth(80)
            creds_row.addWidget(configure_btn)

            frame_layout.addLayout(creds_row)

        # Auto-upload display (read-only text)
        trigger_display = self._get_trigger_display_text(host_config)
        if trigger_display:
            trigger_row = QHBoxLayout()
            trigger_label = QLabel("Auto-upload:")
            trigger_label.setStyleSheet("font-size: 10px; color: gray;")
            trigger_label.setFixedWidth(80)
            trigger_row.addWidget(trigger_label)
            
            trigger_value = QLabel(trigger_display)
            trigger_value.setStyleSheet("font-size: 10px;")
            trigger_row.addWidget(trigger_value)
            trigger_row.addStretch()
            frame_layout.addLayout(trigger_row)

        # Storage progress bar (create for ALL hosts that support storage checking)
        storage_bar = None
        if host_config.user_info_url and (host_config.storage_left_path or host_config.storage_regex):
            storage_row = QHBoxLayout()

            storage_label_text = QLabel("Storage:")
            storage_label_text.setStyleSheet("font-size: 10px; color: gray;")
            storage_label_text.setFixedWidth(60)
            storage_row.addWidget(storage_label_text)

            storage_bar = QProgressBar()
            storage_bar.setMaximum(100)
            storage_bar.setValue(0)
            storage_bar.setTextVisible(True)
            storage_bar.setFormat("Loading...")
            storage_bar.setMaximumHeight(16)
            storage_bar.setProperty("class", "storage-bar")
            storage_row.addWidget(storage_bar, 1)

            frame_layout.addLayout(storage_row)

        # Store widgets for later access (display-only UI)
        self.host_widgets[host_id] = {
            "frame": host_frame,
            "status_label": status_label,
            "storage_bar": storage_bar,
            "creds_display": creds_display if host_config.requires_auth else None,
            "enable_btn": enable_btn if host_config.requires_auth else None
        }

        # Load cached storage immediately for this host
        self.refresh_storage_display(host_id)

        # Update enable button state
        if host_config.requires_auth:
            self._update_enable_button_state(host_id)

        # Add to layout
        self.hosts_container_layout.addWidget(host_frame)

    def _update_status_label(self, host_id: str, host_config, status_label: QLabel):
        """Update status label with test results.

        Args:
            host_id: Host identifier
            host_config: HostConfig instance
            status_label: QLabel to update
        """
        if not host_config.requires_auth:
            status_label.setText("✓ No auth required")
            status_label.setStyleSheet("color: green;")
            return

        # Load test results directly from QSettings (works even if worker doesn't exist yet)
        test_results = self._load_test_results_from_settings(host_id)
        if test_results:
            test_time = datetime.fromtimestamp(test_results['timestamp'])
            time_str = test_time.strftime("%m/%d %H:%M")

            # Count how many tests passed (out of 4)
            tests_passed = sum([
                test_results['credentials_valid'],
                test_results['user_info_valid'],
                test_results['upload_success'],
                test_results['delete_success']
            ])

            if tests_passed == 4:
                status_label.setText(f"✓ All tests passed ({time_str})")
                status_label.setStyleSheet("color: green; font-weight: bold;")
            elif tests_passed > 0:
                status_label.setText(f"⚠ {tests_passed}/4 tests passed ({time_str})")
                status_label.setStyleSheet("color: orange; font-weight: bold;")
            else:
                status_label.setText("⚠ Test failed - retest needed")
                status_label.setStyleSheet("color: red; font-weight: bold;")
            return

        status_label.setText("⚠ Requires credentials")
        status_label.setStyleSheet("color: orange;")

    def _load_test_results_from_settings(self, host_id: str) -> dict:
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

    def _get_trigger_display_text(self, host_config):
        """Get display text for auto-upload triggers."""
        triggers = []
        if host_config.trigger_on_added:
            triggers.append("On Added")
        if host_config.trigger_on_started:
            triggers.append("On Started")
        if host_config.trigger_on_completed:
            triggers.append("On Completed")
        return ", ".join(triggers) if triggers else "Disabled"

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
            status_label.setStyleSheet("color: blue; font-weight: bold;")

        # Trigger test (result will be cached in QSettings)
        worker.test_connection()

    def refresh_storage_display(self, host_id: str):
        """Update storage display by reading from QSettings cache.
        
        Args:
            host_id: Host identifier
        """
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
            # No cached data - keep current display unchanged
            # (Initial "Loading..." will stay until first successful update)
            return

        # Validate storage data before updating
        if total <= 0 or left < 0 or left > total:
            # Invalid data - keep current display unchanged (preserve existing good data)
            return

        # Calculate percentages
        used = total - left
        percent_used = int((used / total) * 100) if total > 0 else 0
        percent_free = 100 - percent_used

        # Format strings
        left_str = format_binary_size(left)
        total_str = format_binary_size(total)

        # Update progress bar
        storage_bar.setValue(percent_free)
        storage_bar.setFormat(f"{left_str} / {total_str} free ({percent_free}%)")

        # Color coding based on usage
        if percent_used >= 90:
            storage_bar.setProperty("storage_status", "low")
        elif percent_used >= 75:
            storage_bar.setProperty("storage_status", "medium")
        else:
            storage_bar.setProperty("storage_status", "plenty")

        # Refresh styling
        storage_bar.style().unpolish(storage_bar)
        storage_bar.style().polish(storage_bar)


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

        # Update status label
        test_time = datetime.fromtimestamp(results['timestamp'])
        time_str = test_time.strftime("%m/%d %H:%M")

        tests_passed = sum([
            results['credentials_valid'],
            results['user_info_valid'],
            results['upload_success'],
            results['delete_success']
        ])

        if tests_passed == 4:
            status_label.setText(f"✓ All tests passed ({time_str})")
            status_label.setStyleSheet("color: green; font-weight: bold;")
        elif tests_passed > 0:
            status_label.setText(f"⚠ {tests_passed}/4 tests passed ({time_str})")
            status_label.setStyleSheet("color: orange; font-weight: bold;")
        else:
            error = results.get('error_message', 'Unknown error')
            status_label.setText(f"✗ Test failed: {error}")
            status_label.setStyleSheet("color: red; font-weight: bold;")

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
        result = dialog.exec()

        # Save changes if user clicked Save
        if result == QDialog.DialogCode.Accepted:
            try:
                from src.utils.logger import log
                log(f"Config dialog accepted for {host_id}", level="debug", category="file_hosts")
                
                from imxup import encrypt_password, set_credential
                import configparser
                import os
                
                # Get values from dialog
                enabled = dialog.get_enabled_state()
                credentials = dialog.get_credentials()
                trigger_settings = dialog.get_trigger_settings()
                log(f"Got values: enabled={enabled}, has_creds={bool(credentials)}, triggers={trigger_settings}", 
                    level="debug", category="file_hosts")
                
                # Load INI file
                config_file = os.path.expanduser("~/.imxup/imxup.ini")
                config = configparser.ConfigParser()
                if os.path.exists(config_file):
                    config.read(config_file)
                log(f"Loaded config from {config_file}", level="debug", category="file_hosts")
                
                if "FILE_HOSTS" not in config:
                    config.add_section("FILE_HOSTS")
                
                # Save enabled state and triggers to INI
                config.set("FILE_HOSTS", f"{host_id}_enabled", str(enabled))
                config.set("FILE_HOSTS", f"{host_id}_on_added", str(trigger_settings.get("on_added", False)))
                config.set("FILE_HOSTS", f"{host_id}_on_started", str(trigger_settings.get("on_started", False)))
                config.set("FILE_HOSTS", f"{host_id}_on_completed", str(trigger_settings.get("on_completed", False)))
                log("Set INI values", level="debug", category="file_hosts")
                
                # Write INI file
                with open(config_file, "w") as f:
                    config.write(f)
                log(f"Wrote INI file for {host_id}", level="info", category="file_hosts")
                
                # Save credentials (encrypted) to QSettings
                if credentials:
                    encrypted = encrypt_password(credentials)
                    set_credential(f"file_host_{host_id}_credentials", encrypted)
                    log("Saved encrypted credentials", level="debug", category="file_hosts")
                
                # Update in-memory config
                host_config.enabled = enabled
                host_config.trigger_on_added = trigger_settings.get("on_added", False)
                host_config.trigger_on_started = trigger_settings.get("on_started", False)
                host_config.trigger_on_completed = trigger_settings.get("on_completed", False)
                log("Updated in-memory config", level="debug", category="file_hosts")
                
                # Spawn or kill worker based on enabled state
                if enabled:
                    self.worker_manager.enable_host(host_id)
                else:
                    self.worker_manager.disable_host(host_id)
                
                # Refresh display in File Hosts tab
                self._refresh_host_display(host_id, host_config, credentials)
                log(f"Refreshed display for {host_id}", level="debug", category="file_hosts")
                
                # Mark settings as changed
                self.settings_changed.emit()
                log(f"Save complete for {host_id}", level="info", category="file_hosts")
                
            except Exception as e:
                log(f"Failed to save config for {host_id}: {e}", level="error", category="file_hosts")
                import traceback
                traceback.print_exc()

    def _refresh_host_display(self, host_id: str, host_config, credentials: str = None):
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
    def _add_custom_host(self):
        """Add a custom host from JSON file"""
        # TODO: Implement custom host loading
        QMessageBox.information(
            self,
            "Not Implemented",
            "Custom host loading will be implemented in a future update."
        )

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
        # Update status labels and enable buttons for all hosts
        from src.core.file_host_config import get_config_manager
        config_manager = get_config_manager()

        for host_id, host_config in config_manager.hosts.items():
            widgets = self.host_widgets.get(host_id)
            if widgets and widgets.get('status_label'):
                self._update_status_label(host_id, host_config, widgets['status_label'])
            # Update enable button state
            if widgets and widgets.get('enable_btn'):
                self._update_enable_button_state(host_id)

    def _update_enable_button_state(self, host_id: str):
        """Update enable/disable button text and style based on worker state.

        Args:
            host_id: Host identifier
        """
        widgets = self.host_widgets.get(host_id)
        if not widgets or not widgets.get('enable_btn'):
            return

        enable_btn = widgets['enable_btn']
        is_enabled = self.worker_manager.is_enabled(host_id) if self.worker_manager else False

        if is_enabled:
            enable_btn.setText("Disable")
            enable_btn.setStyleSheet("QPushButton { background-color: #90EE90; }")  # Light green
        else:
            enable_btn.setText("Enable")
            enable_btn.setStyleSheet("")  # Default style

    def _on_enable_disable_clicked(self, host_id: str):
        """Handle enable/disable button click.

        Args:
            host_id: Host identifier
        """
        if not self.worker_manager:
            return

        is_enabled = self.worker_manager.is_enabled(host_id)

        if is_enabled:
            # Disable worker
            self.worker_manager.disable_host(host_id)
        else:
            # Enable worker (it will test credentials during spinup)
            self.worker_manager.enable_host(host_id)
