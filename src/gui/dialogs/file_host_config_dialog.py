#!/usr/bin/env python3
"""
File Host Configuration Dialog
Provides credential setup, testing, and configuration for file host uploads
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QGroupBox,
    QPushButton, QLineEdit, QCheckBox, QProgressBar, QComboBox, QWidget
)
from PyQt6.QtCore import QSettings, QTimer
from datetime import datetime
import time

from src.utils.format_utils import format_binary_size


class FileHostConfigDialog(QDialog):
    """Configuration dialog for a single file host"""

    def __init__(self, parent, host_id: str, host_config, main_widgets: dict, worker_manager=None):
        """
        Args:
            parent: Parent settings dialog or widget
            host_id: Host identifier (e.g., 'rapidgator')
            host_config: HostConfig object
            main_widgets: Dictionary of widgets from main File Hosts tab
            worker_manager: FileHostWorkerManager instance (optional)
        """
        super().__init__(parent)
        self.parent_dialog = parent
        self.host_id = host_id
        self.host_config = host_config
        self.main_widgets = main_widgets
        self.worker_manager = worker_manager
        self.worker = worker_manager.get_worker(host_id) if worker_manager else None
        
        # Connect to spinup_complete signal for credential failures
        if self.worker_manager:
            self.worker_manager.spinup_complete.connect(self._on_spinup_complete)
            
        self.settings = QSettings("ImxUploader", "ImxUploadGUI")

        # Initialize saved values EARLY (updated by widget change signals)
        self.saved_enabled = host_config.enabled
        self.saved_credentials = None
        self.saved_trigger_settings = {
            "on_added": host_config.trigger_on_added,
            "on_started": host_config.trigger_on_started,
            "on_completed": host_config.trigger_on_completed
        }

        self.setWindowTitle(f"Configure {host_config.name}")
        self.setModal(True)
        self.resize(700, 650)

        # Connect to worker signals if available
        if self.worker:
            self.worker.test_completed.connect(self._on_worker_test_completed)
            self.worker.storage_updated.connect(self._on_worker_storage_updated)

        self.setup_ui()
    
    def setup_ui(self):
        """Setup the dialog UI"""
        # Get actual enabled state from manager (source of truth)
        actual_enabled = self.worker_manager.is_enabled(self.host_id) if self.worker_manager else False

        # Load settings from INI file for triggers
        from imxup import get_config_path
        import configparser
        import os
        config_file = get_config_path()  # Use dynamic path, not hardcoded
        config = configparser.ConfigParser()
        if os.path.exists(config_file):
            config.read(config_file)

        # Read triggers from INI (NOT enabled state - manager is source of truth)
        if config.has_section("FILE_HOSTS"):
            trigger_on_added = config.getboolean("FILE_HOSTS", f"{self.host_id}_on_added", fallback=False)
            trigger_on_started = config.getboolean("FILE_HOSTS", f"{self.host_id}_on_started", fallback=False)
            trigger_on_completed = config.getboolean("FILE_HOSTS", f"{self.host_id}_on_completed", fallback=False)
        else:
            trigger_on_added = False
            trigger_on_started = False
            trigger_on_completed = False
        
        
        layout = QVBoxLayout(self)

        # Host info header
        info_label = QLabel(f"<h2>{self.host_config.name}</h2><p>Configure host settings, credentials, and test connection</p>")
        layout.addWidget(info_label)

        # Enable/Disable button - power button paradigm
        button_row = QHBoxLayout()
        
        self.enable_button = QPushButton()
        self.enable_button.setMinimumWidth(200)
        self.enable_button.clicked.connect(self._on_enable_button_clicked)
        button_row.addWidget(self.enable_button)
        
        # Error label beside button
        self.enable_error_label = QLabel()
        self.enable_error_label.setStyleSheet("color: red; font-weight: bold;")
        self.enable_error_label.setWordWrap(True)
        button_row.addWidget(self.enable_error_label, 1)
        
        layout.addLayout(button_row)
        
        # Update button text based on whether worker is running
        self._update_enable_button_state(actual_enabled)
        
        # Create container for all content (to be disabled when host is disabled)
        self.content_container = QWidget()
        content_layout = QVBoxLayout(self.content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.content_container)
        
        # Credentials section
        # Credentials section
        self.creds_input = None
        if self.host_config.requires_auth:
            creds_group = QGroupBox("Credentials")
            creds_layout = QVBoxLayout(creds_group)

            # Format info
            if self.host_config.auth_type == "token_login":
                format_text = "Format: username:password"
            elif self.host_config.auth_type == "bearer":
                format_text = "Format: api_key"
            else:
                format_text = "Format: username:password"

            creds_layout.addWidget(QLabel(format_text))

            # Credentials input
            self.creds_input = QLineEdit()
            self.creds_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.creds_input.setPlaceholderText("Enter credentials...")

            # Load current credentials from encrypted storage
            from imxup import get_credential, decrypt_password
            from src.utils.logger import log
            
            encrypted_creds = get_credential(f"file_host_{self.host_id}_credentials")
            
            if encrypted_creds:
                try:
                    decrypted = decrypt_password(encrypted_creds)
                    if decrypted:  # Only set if we got valid credentials
                        self.creds_input.setText(decrypted)
                except Exception as e:
                    log(f"Failed to load credentials for {self.host_id}: {e}", level="error", category="file_hosts")
            
            # Add show/hide button
            creds_row = QHBoxLayout()
            creds_row.addWidget(self.creds_input, 1)
            
            show_creds_btn = QPushButton("👁")
            show_creds_btn.setMaximumWidth(30)
            show_creds_btn.setCheckable(True)
            show_creds_btn.setToolTip("Show/hide credentials")
            show_creds_btn.clicked.connect(
                lambda checked: self.creds_input.setEchoMode(
                    QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
                )
            )
            creds_row.addWidget(show_creds_btn)
            
            creds_layout.addLayout(creds_row)
            content_layout.addWidget(creds_group)
        # Storage section
        self.storage_bar = None
        if self.host_config.user_info_url and (self.host_config.storage_left_path or self.host_config.storage_regex):
            storage_group = QGroupBox("Storage")
            storage_layout = QVBoxLayout(storage_group)

            self.storage_bar = QProgressBar()
            self.storage_bar.setMaximum(100)
            self.storage_bar.setValue(0)
            self.storage_bar.setTextVisible(True)
            self.storage_bar.setFormat("Loading...")
            self.storage_bar.setMaximumHeight(20)
            self.storage_bar.setProperty("class", "storage-bar")

            storage_layout.addWidget(self.storage_bar)
            content_layout.addWidget(storage_group)

            # Load storage from cache immediately if available
            self._load_storage_from_cache()

        # Trigger settings - SINGLE DROPDOWN (not checkboxes)
        triggers_group = QGroupBox("Auto-Upload Trigger")
        triggers_layout = QVBoxLayout(triggers_group)
        
        triggers_layout.addWidget(QLabel(
            "Select when to automatically upload galleries to this host:"
        ))
        
        self.trigger_combo = QComboBox()
        self.trigger_combo.addItem("Disabled / Manual", None)
        self.trigger_combo.addItem("On Added", "on_added")
        self.trigger_combo.addItem("On Started", "on_started")
        self.trigger_combo.addItem("On Completed", "on_completed")
        
        # Select current trigger (from INI file)
        if trigger_on_added:
            self.trigger_combo.setCurrentIndex(1)
        elif trigger_on_started:
            self.trigger_combo.setCurrentIndex(2)
        elif trigger_on_completed:
            self.trigger_combo.setCurrentIndex(3)
        else:
            self.trigger_combo.setCurrentIndex(0)  # Disabled
        
        triggers_layout.addWidget(self.trigger_combo)
        content_layout.addWidget(triggers_group)


        # Host info (read-only)
        info_group = QGroupBox("Host Information")
        info_layout = QFormLayout(info_group)

        info_layout.addRow("Auto-retry:", QLabel("✓ Enabled" if self.host_config.auto_retry else "○ Disabled"))
        info_layout.addRow("Max retries:", QLabel(str(self.host_config.max_retries)))
        info_layout.addRow("Max connections:", QLabel(str(self.host_config.max_connections)))
        if self.host_config.max_file_size_mb:
            info_layout.addRow("Max file size:", QLabel(f"{self.host_config.max_file_size_mb} MB"))

        content_layout.addWidget(info_group)

        # Test Results section
        self.setup_test_results_section(content_layout)

        content_layout.addStretch()

        # Button layout
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._on_save_clicked)
        save_btn.setDefault(True)
        button_layout.addWidget(save_btn)

        layout.addLayout(button_layout)

    def setup_test_results_section(self, parent_layout):
        """Setup the test results section with test button"""
        test_group = QGroupBox("Connection Test & Results")
        test_group_layout = QVBoxLayout(test_group)

        # Test button at top
        test_button_layout = QHBoxLayout()
        self.test_connection_btn = QPushButton("Test Connection")
        self.test_connection_btn.setToolTip("Run full test: credentials, user info, upload, and delete")
        test_button_layout.addWidget(self.test_connection_btn)
        test_button_layout.addStretch()
        test_group_layout.addLayout(test_button_layout)

        # Test results display
        test_results_layout = QFormLayout()

        # Create labels that will be updated
        self.test_timestamp_label = QLabel("Not tested yet")
        self.test_credentials_label = QLabel("○ Not tested")
        self.test_userinfo_label = QLabel("○ Not tested")
        self.test_upload_label = QLabel("○ Not tested")
        self.test_delete_label = QLabel("○ Not tested")
        self.test_error_label = QLabel("")
        self.test_error_label.setWordWrap(True)
        self.test_error_label.setStyleSheet("color: red; font-size: 10px;")

        test_results_layout.addRow("Last tested:", self.test_timestamp_label)
        test_results_layout.addRow("Credentials:", self.test_credentials_label)
        test_results_layout.addRow("User info:", self.test_userinfo_label)
        test_results_layout.addRow("Upload test:", self.test_upload_label)
        test_results_layout.addRow("Delete test:", self.test_delete_label)
        test_results_layout.addRow("", self.test_error_label)

        test_group_layout.addLayout(test_results_layout)
        parent_layout.addWidget(test_group)

        # Load and display existing test results
        self.load_and_display_test_results()

        # Connect test button
        self.test_connection_btn.clicked.connect(self.run_full_test)

    def _update_enable_button_state(self, enabled: bool):
        """Update button text and style based on worker state"""
        if enabled:
            self.enable_button.setText(f"Disable {self.host_config.name}")
            self.enable_button.setStyleSheet("QPushButton { background-color: #90EE90; }")  # Light green
        else:
            self.enable_button.setText(f"Enable {self.host_config.name}")
            self.enable_button.setStyleSheet("")  # Default style
    
    def _on_enable_button_clicked(self):
        """Handle enable/disable button click - power button paradigm"""
        # Check if worker is currently running
        is_enabled = self.worker_manager.is_enabled(self.host_id) if self.worker_manager else False

        if is_enabled:
            # Disable: Manager handles worker shutdown AND INI persistence
            self.worker_manager.disable_host(self.host_id)
            self._update_enable_button_state(False)
            self.enable_error_label.setText("")
        else:
            # Enable: Manager handles worker spinup AND INI persistence on success
            self.worker_manager.enable_host(self.host_id)

            # Show enabling state - wait for spinup_complete signal
            self.enable_button.setText(f"Enabling {self.host_config.name}...")
            self.enable_button.setEnabled(False)
            self.enable_error_label.setText("")
    
    def _on_spinup_complete(self, host_id: str, error: str) -> None:
        """Handle worker spinup result from manager signal.
        
        Args:
            host_id: Host that completed spinup
            error: Error message (empty = success)
        """
        # Only handle if this is our host
        if host_id != self.host_id:
            return
        
        # Re-enable button
        self.enable_button.setEnabled(True)
        
        if error:
            # Spinup failed
            self._update_enable_button_state(False)
            MAX_ERROR_LENGTH = 150
            display_error = error if len(error) <= MAX_ERROR_LENGTH else error[:MAX_ERROR_LENGTH] + "..."
            self.enable_error_label.setText(f"Failed to enable: {display_error}")
            self.enable_error_label.setToolTip(f"Failed to enable: {error}")
        else:
            # Spinup succeeded - Manager already persisted enabled state
            self._update_enable_button_state(True)
            self.enable_error_label.setText("")
            self.enable_error_label.setToolTip("")
    
    
    
    def _load_storage_from_cache(self):
        """Load and display storage from cache if available"""
        if not self.storage_bar:
            return

        # Load from worker's cache if available
        cache = None
        if self.worker:
            cache = self.worker._load_storage_cache()

        if cache and cache.get('total') and cache.get('left'):
            try:
                total = int(cache['total'])
                left = int(cache['left'])
                used = total - left
                percent_used = int((used / total) * 100) if total > 0 else 0
                percent_free = 100 - percent_used

                total_str = format_binary_size(total)
                left_str = format_binary_size(left)

                self.storage_bar.setValue(percent_free)
                self.storage_bar.setFormat(f"{left_str} / {total_str} free ({percent_free}%)")

                if percent_used >= 90:
                    self.storage_bar.setProperty("storage_status", "low")
                elif percent_used >= 75:
                    self.storage_bar.setProperty("storage_status", "medium")
                else:
                    self.storage_bar.setProperty("storage_status", "plenty")

                self.storage_bar.style().unpolish(self.storage_bar)
                self.storage_bar.style().polish(self.storage_bar)
            except:
                pass

    def load_and_display_test_results(self):
        """Load and display existing test results from QSettings cache"""
        # Read directly from QSettings - doesn't require worker to exist
        prefix = f"FileHosts/TestResults/{self.host_id}"
        test_results = {
            'timestamp': self.settings.value(f"{prefix}/timestamp", 0, type=int),
            'credentials_valid': self.settings.value(f"{prefix}/credentials_valid", False, type=bool),
            'user_info_valid': self.settings.value(f"{prefix}/user_info_valid", False, type=bool),
            'upload_success': self.settings.value(f"{prefix}/upload_success", False, type=bool),
            'delete_success': self.settings.value(f"{prefix}/delete_success", False, type=bool),
            'error_message': self.settings.value(f"{prefix}/error_message", '', type=str)
        }

        if test_results['timestamp'] > 0:
            # Format timestamp as YYYY-MM-DD HH:MM
            test_time = datetime.fromtimestamp(test_results['timestamp'])
            time_str = test_time.strftime("%Y-%m-%d %H:%M")

            # Count passed tests
            tests = [
                test_results.get('credentials_valid'),
                test_results.get('user_info_valid'),
                test_results.get('upload_success'),
                test_results.get('delete_success')
            ]
            passed = sum(1 for t in tests if t)
            total = 4

            # Set timestamp with pass count and color
            timestamp_text = f"{time_str} ({passed}/{total} tests passed)"
            self.test_timestamp_label.setText(timestamp_text)

            if passed == total:
                self.test_timestamp_label.setStyleSheet("color: green; font-weight: bold;")
            elif passed == 0:
                self.test_timestamp_label.setStyleSheet("color: red; font-weight: bold;")
            else:
                self.test_timestamp_label.setStyleSheet("color: orange; font-weight: bold;")

            # Set individual test labels with Pass/Fail/Unknown
            self._set_test_label(self.test_credentials_label, test_results.get('credentials_valid'))
            self._set_test_label(self.test_userinfo_label, test_results.get('user_info_valid'))
            self._set_test_label(self.test_upload_label, test_results.get('upload_success'))

            # Delete test can be skipped
            if test_results.get('delete_success'):
                self._set_test_label(self.test_delete_label, True)
            elif test_results.get('upload_success') and not test_results.get('delete_success'):
                self.test_delete_label.setText("Unknown")
                self.test_delete_label.setStyleSheet("color: orange;")
            else:
                self._set_test_label(self.test_delete_label, False)

            if test_results.get('error_message'):
                self.test_error_label.setText(test_results['error_message'])
            else:
                self.test_error_label.setText("")

    def _set_test_label(self, label, passed: bool):
        """Helper to set test label with color"""
        if passed:
            label.setText("Pass")
            label.setStyleSheet("color: green; font-weight: bold;")
        else:
            label.setText("Fail")
            label.setStyleSheet("color: red; font-weight: bold;")

    def run_full_test(self):
        """Run complete test sequence via worker: credentials, user info, upload, delete"""
        if not self.creds_input:
            return

        credentials = self.creds_input.text().strip()
        if not credentials:
            self.test_timestamp_label.setText("Error: No credentials entered")
            self.test_timestamp_label.setStyleSheet("color: red;")
            return

        # Check if worker available
        if not self.worker:
            self.test_timestamp_label.setText("Error: Host not enabled")
            self.test_timestamp_label.setStyleSheet("color: red;")
            return

        # Update UI to show testing
        self.test_connection_btn.setEnabled(False)
        self.test_timestamp_label.setText("Testing...")
        self.test_credentials_label.setText("⏳ Running...")
        self.test_userinfo_label.setText("⏳ Waiting...")
        self.test_upload_label.setText("⏳ Waiting...")
        self.test_delete_label.setText("⏳ Waiting...")
        self.test_error_label.setText("")

        # Update worker credentials for testing (before they're saved)
        self.worker.update_credentials(credentials)
        
        # Delegate to worker (results come via signal)
        self.worker.test_connection()

    def _on_worker_test_completed(self, host_id: str, results: dict):
        """Handle test completion from worker"""
        if host_id != self.host_id:
            return  # Not for us

        # Re-enable button
        self.test_connection_btn.setEnabled(True)

        # Update UI from results
        self._set_test_label(
            self.test_credentials_label,
            results.get('credentials_valid', False)
        )
        self._set_test_label(
            self.test_userinfo_label,
            results.get('user_info_valid', False)
        )
        self._set_test_label(
            self.test_upload_label,
            results.get('upload_success', False)
        )
        self._set_test_label(
            self.test_delete_label,
            results.get('delete_success', False)
        )

        # Show error if any
        error_msg = results.get('error_message', '')
        self.test_error_label.setText(error_msg)

        # Update timestamp
        test_time = datetime.fromtimestamp(results['timestamp'])
        time_str = test_time.strftime("%Y-%m-%d %H:%M")

        tests_passed = sum([
            results.get('credentials_valid', False),
            results.get('user_info_valid', False),
            results.get('upload_success', False),
            results.get('delete_success', False)
        ])

        self.test_timestamp_label.setText(f"{time_str} ({tests_passed}/4 tests passed)")

        if tests_passed == 4:
            self.test_timestamp_label.setStyleSheet("color: green; font-weight: bold;")
        elif tests_passed == 0:
            self.test_timestamp_label.setStyleSheet("color: red; font-weight: bold;")
        else:
            self.test_timestamp_label.setStyleSheet("color: orange; font-weight: bold;")

    def _on_worker_storage_updated(self, host_id: str, total, left):
        """Handle storage update from worker"""
        if host_id != self.host_id or not self.storage_bar:
            return  # Not for us

        # Update storage bar
        used = total - left
        percent_used = int((used / total) * 100) if total > 0 else 0
        percent_free = 100 - percent_used

        total_str = format_binary_size(total)
        left_str = format_binary_size(left)

        self.storage_bar.setValue(percent_free)
        self.storage_bar.setFormat(f"{left_str} / {total_str} free ({percent_free}%)")

        if percent_used >= 90:
            self.storage_bar.setProperty("storage_status", "low")
        elif percent_used >= 75:
            self.storage_bar.setProperty("storage_status", "medium")
        else:
            self.storage_bar.setProperty("storage_status", "plenty")

    def get_trigger_settings(self):
        """Get trigger setting from dropdown (only ONE selected)"""
        # Return saved value if dialog already closed, otherwise read from widget
        if hasattr(self, 'saved_trigger_settings'):
            return self.saved_trigger_settings
        
        selected_trigger = self.trigger_combo.currentData()
        return {
            "on_added": selected_trigger == "on_added",
            "on_started": selected_trigger == "on_started",
            "on_completed": selected_trigger == "on_completed"
        }

    def get_credentials(self):
        """Get entered credentials"""
        # Return saved value if dialog already closed, otherwise read from widget
        if hasattr(self, 'saved_credentials'):
            return self.saved_credentials
        
        if self.creds_input:
            return self.creds_input.text().strip()
        return None

    
    def get_enabled_state(self):
        """Get enabled checkbox state"""
        # Return saved value if dialog already closed, otherwise read from widget
        if hasattr(self, 'saved_enabled'):
            return self.saved_enabled
        
        return self.worker_manager.is_enabled(self.host_id) if self.worker_manager else False

    def _on_save_clicked(self):
        """Handle Save button click - read values BEFORE dialog destruction starts"""
        # Read all values directly (no existence checks - they lie!)
        self.saved_enabled = self.worker_manager.is_enabled(self.host_id) if self.worker_manager else False
        self.saved_credentials = self.creds_input.text().strip() if self.creds_input is not None else ""
        selected = self.trigger_combo.currentData()
        self.saved_trigger_settings = {
            "on_added": selected == "on_added",
            "on_started": selected == "on_started",
            "on_completed": selected == "on_completed"
        }
        # Now accept the dialog (widgets may be destroyed after this)
        self.accept()
    
    def accept(self):
        """Override accept to prevent double-saving (values already saved in _on_save_clicked)"""
        # Just close the dialog, values were already saved by _on_save_clicked
        super().accept()
