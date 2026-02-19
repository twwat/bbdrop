#!/usr/bin/env python3
"""
Image host configuration panel widget.

Renders a config panel for a single image host, driven by ImageHostConfig data.
Provides UI for credentials, connection settings, thumbnails, and host-specific options.
"""

import os
import configparser
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QGroupBox, QPushButton, QSlider, QComboBox, QCheckBox, QLineEdit,
    QDialog, QMessageBox, QStyle
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QThread

from src.core.image_host_config import (
    ImageHostConfig,
    get_image_host_setting,
    save_image_host_setting
)
from bbdrop import (
    get_config_path,
    encrypt_password,
    decrypt_password,
    get_credential,
    set_credential,
    remove_credential
)


class ImageHostConfigPanel(QWidget):
    """Configuration panel for a single image host."""

    settings_changed = pyqtSignal()
    cover_gallery_changed = pyqtSignal(str, str)  # host_id, gallery_id

    def __init__(self, host_id: str, config: ImageHostConfig, parent=None):
        """
        Initialize the image host config panel.

        Args:
            host_id: Host identifier (e.g., 'imx')
            config: ImageHostConfig data for this host
            parent: Parent widget
        """
        super().__init__(parent)
        self.host_id = host_id
        self.config = config
        self._modified = False

        self._init_ui()
        self.load_current_credentials()

    def _init_ui(self):
        """Initialize the UI components."""
        main_layout = QVBoxLayout(self)

        # Section 1: Credentials
        credentials_group = self._create_credentials_group()
        main_layout.addWidget(credentials_group)

        # Section 2: Connection
        connection_group = self._create_connection_group()
        main_layout.addWidget(connection_group)

        # Section 3: Thumbnails
        thumbnails_group = self._create_thumbnails_group()
        main_layout.addWidget(thumbnails_group)

        # Section 4: Options (only for IMX)
        if self.host_id == "imx":
            options_group = self._create_options_group()
            main_layout.addWidget(options_group)

        # Section 5: Cover Gallery (all hosts)
        cover_group = self._create_cover_group()
        main_layout.addWidget(cover_group)

    def _create_credentials_group(self) -> QGroupBox:
        """Create the credentials configuration group.

        Shows/hides credential rows based on config.auth_type:
        - "api_key_or_session" (IMX): API Key, Username, Password, Firefox Cookies
        - "session_optional" (Turbo): Username, Password only (marked optional)
        - Other: Username, Password
        """
        auth_type = self.config.auth_type or ""
        needs_api_key = "api_key" in auth_type
        needs_cookies = auth_type == "api_key_or_session"  # IMX-specific
        is_optional = not self.config.requires_auth

        if is_optional:
            group = QGroupBox("Credentials (Optional)")
        else:
            group = QGroupBox("Credentials")
        layout = QVBoxLayout(group)

        # Track which widgets exist for this host
        self._has_api_key_row = needs_api_key
        self._has_cookies_row = needs_cookies

        # API Key row (only for hosts that use API keys)
        if needs_api_key:
            api_key_row = QHBoxLayout()
            api_key_row.addWidget(QLabel("<b>API Key</b>: "))
            self.api_key_status_label = QLabel("NOT SET")
            self.api_key_status_label.setProperty("class", "status-muted")
            api_key_row.addWidget(self.api_key_status_label)
            api_key_row.addStretch()

            self.api_key_change_btn = QPushButton("Set")
            if not self.api_key_change_btn.text().startswith(" "):
                self.api_key_change_btn.setText(" " + self.api_key_change_btn.text())
            self.api_key_change_btn.clicked.connect(self.change_api_key)
            api_key_row.addWidget(self.api_key_change_btn)

            self.api_key_remove_btn = QPushButton("Unset")
            if not self.api_key_remove_btn.text().startswith(" "):
                self.api_key_remove_btn.setText(" " + self.api_key_remove_btn.text())
            self.api_key_remove_btn.clicked.connect(self.remove_api_key)
            api_key_row.addWidget(self.api_key_remove_btn)

            layout.addLayout(api_key_row)
        else:
            # Create dummy attributes so load_current_credentials() doesn't crash
            self.api_key_status_label = None
            self.api_key_change_btn = None
            self.api_key_remove_btn = None

        # Username row
        username_row = QHBoxLayout()
        username_row.addWidget(QLabel("<b>Username</b>: "))
        self.username_status_label = QLabel("NOT SET")
        self.username_status_label.setProperty("class", "status-muted")
        username_row.addWidget(self.username_status_label)
        username_row.addStretch()

        self.username_change_btn = QPushButton("Set")
        if not self.username_change_btn.text().startswith(" "):
            self.username_change_btn.setText(" " + self.username_change_btn.text())
        self.username_change_btn.clicked.connect(self.change_username)
        username_row.addWidget(self.username_change_btn)

        self.username_remove_btn = QPushButton("Unset")
        if not self.username_remove_btn.text().startswith(" "):
            self.username_remove_btn.setText(" " + self.username_remove_btn.text())
        self.username_remove_btn.clicked.connect(self.remove_username)
        username_row.addWidget(self.username_remove_btn)

        layout.addLayout(username_row)

        # Password row
        password_row = QHBoxLayout()
        password_row.addWidget(QLabel("<b>Password</b>: "))
        self.password_status_label = QLabel("NOT SET")
        self.password_status_label.setProperty("class", "status-muted")
        password_row.addWidget(self.password_status_label)
        password_row.addStretch()

        self.password_change_btn = QPushButton("Set")
        if not self.password_change_btn.text().startswith(" "):
            self.password_change_btn.setText(" " + self.password_change_btn.text())
        self.password_change_btn.clicked.connect(self.change_password)
        password_row.addWidget(self.password_change_btn)

        self.password_remove_btn = QPushButton("Unset")
        if not self.password_remove_btn.text().startswith(" "):
            self.password_remove_btn.setText(" " + self.password_remove_btn.text())
        self.password_remove_btn.clicked.connect(self.remove_password)
        password_row.addWidget(self.password_remove_btn)

        layout.addLayout(password_row)

        # Firefox Cookies row (only for hosts that use cookie-based sessions)
        if needs_cookies:
            cookies_row = QHBoxLayout()
            cookies_row.addWidget(QLabel("<b>Firefox Cookies</b>: "))
            self.cookies_status_label = QLabel("Unknown")
            self.cookies_status_label.setProperty("class", "status-muted")
            cookies_row.addWidget(self.cookies_status_label)
            cookies_row.addStretch()

            self.cookies_enable_btn = QPushButton("Enable")
            if not self.cookies_enable_btn.text().startswith(" "):
                self.cookies_enable_btn.setText(" " + self.cookies_enable_btn.text())
            self.cookies_enable_btn.clicked.connect(self.enable_cookies_setting)
            cookies_row.addWidget(self.cookies_enable_btn)

            self.cookies_disable_btn = QPushButton("Disable")
            if not self.cookies_disable_btn.text().startswith(" "):
                self.cookies_disable_btn.setText(" " + self.cookies_disable_btn.text())
            self.cookies_disable_btn.clicked.connect(self.disable_cookies_setting)
            cookies_row.addWidget(self.cookies_disable_btn)

            layout.addLayout(cookies_row)
        else:
            self.cookies_status_label = None
            self.cookies_enable_btn = None
            self.cookies_disable_btn = None

        # Test Credentials button and result
        test_row = QHBoxLayout()
        self.test_credentials_btn = QPushButton(" Test Credentials")
        self.test_credentials_btn.setToolTip("Verify stored credentials work")
        self.test_credentials_btn.clicked.connect(self._start_credential_test)
        test_row.addWidget(self.test_credentials_btn)

        self.test_result_label = QLabel("")
        self.test_result_label.setWordWrap(True)
        test_row.addWidget(self.test_result_label, 1)
        test_row.addStretch()

        layout.addLayout(test_row)

        # Keep reference to the test thread so it doesn't get GC'd
        self._test_thread = None

        # Credential storage note
        encryption_note = QLabel(
            "<small>Credentials are encrypted with Fernet (AES-128-CBC + HMAC-SHA256) using a key derived from your hostname, then stored in your OS keyring (Windows Credential Manager / macOS Keychain / Linux Secret Service).<br><br>They are tied to your user account and won't transfer to other computers.</small>"
        )
        encryption_note.setWordWrap(True)
        encryption_note.setProperty("class", "label-credential-note")
        layout.addWidget(encryption_note)

        return group

    def _create_connection_group(self) -> QGroupBox:
        """Create the connection settings group."""
        group = QGroupBox("Connection")
        layout = QGridLayout(group)

        # Max Retries
        layout.addWidget(QLabel("<b>Max Retries</b>:"), 0, 0)
        self.max_retries_slider = QSlider(Qt.Orientation.Horizontal)
        self.max_retries_slider.setMinimum(1)
        self.max_retries_slider.setMaximum(5)
        self.max_retries_slider.setValue(
            get_image_host_setting(self.host_id, 'max_retries', 'int')
        )
        self.max_retries_slider.valueChanged.connect(self._mark_modified)
        layout.addWidget(self.max_retries_slider, 0, 1)

        self.max_retries_value = QLabel(str(self.max_retries_slider.value()))
        self.max_retries_slider.valueChanged.connect(
            lambda v: self.max_retries_value.setText(str(v))
        )
        layout.addWidget(self.max_retries_value, 0, 2)

        # Concurrent Uploads
        layout.addWidget(QLabel("<b>Concurrent Uploads</b>:"), 1, 0)
        self.batch_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.batch_size_slider.setMinimum(1)
        self.batch_size_slider.setMaximum(8)
        self.batch_size_slider.setValue(
            get_image_host_setting(self.host_id, 'parallel_batch_size', 'int')
        )
        self.batch_size_slider.valueChanged.connect(self._mark_modified)
        layout.addWidget(self.batch_size_slider, 1, 1)

        self.batch_size_value = QLabel(str(self.batch_size_slider.value()))
        self.batch_size_slider.valueChanged.connect(
            lambda v: self.batch_size_value.setText(str(v))
        )
        layout.addWidget(self.batch_size_value, 1, 2)

        # Connect Timeout
        layout.addWidget(QLabel("<b>Connect Timeout (s)</b>:"), 2, 0)
        self.connect_timeout_slider = QSlider(Qt.Orientation.Horizontal)
        self.connect_timeout_slider.setMinimum(10)
        self.connect_timeout_slider.setMaximum(180)
        self.connect_timeout_slider.setValue(
            get_image_host_setting(self.host_id, 'upload_connect_timeout', 'int')
        )
        self.connect_timeout_slider.valueChanged.connect(self._mark_modified)
        layout.addWidget(self.connect_timeout_slider, 2, 1)

        self.connect_timeout_value = QLabel(str(self.connect_timeout_slider.value()))
        self.connect_timeout_value.setMinimumWidth(30)
        self.connect_timeout_slider.valueChanged.connect(
            lambda v: self.connect_timeout_value.setText(str(v))
        )
        layout.addWidget(self.connect_timeout_value, 2, 2)

        # Read Timeout
        layout.addWidget(QLabel("<b>Read Timeout (s)</b>:"), 3, 0)
        self.read_timeout_slider = QSlider(Qt.Orientation.Horizontal)
        self.read_timeout_slider.setMinimum(20)
        self.read_timeout_slider.setMaximum(600)
        self.read_timeout_slider.setValue(
            get_image_host_setting(self.host_id, 'upload_read_timeout', 'int')
        )
        self.read_timeout_slider.valueChanged.connect(self._mark_modified)
        layout.addWidget(self.read_timeout_slider, 3, 1)

        self.read_timeout_value = QLabel(str(self.read_timeout_slider.value()))
        self.read_timeout_value.setMinimumWidth(30)
        self.read_timeout_slider.valueChanged.connect(
            lambda v: self.read_timeout_value.setText(str(v))
        )
        layout.addWidget(self.read_timeout_value, 3, 2)

        return group

    def _create_thumbnails_group(self) -> QGroupBox:
        """Create the thumbnails settings group."""
        group = QGroupBox("Thumbnails")
        layout = QGridLayout(group)

        current_row = 0

        # Thumbnail Size - check if host uses variable mode (slider) or fixed mode (dropdown)
        layout.addWidget(QLabel("<b>Thumbnail Size</b>:"), current_row, 0)

        # Initialize both controls as None so save() can check which exists
        self.thumbnail_size_combo = None
        self.thumb_slider = None
        self.thumb_slider_label = None

        if self.config.thumbnail_mode == "variable" and self.config.thumbnail_range:
            # Variable mode: create slider for continuous size selection
            thumb_range = self.config.thumbnail_range
            self.thumb_slider = QSlider(Qt.Orientation.Horizontal)
            self.thumb_slider.setRange(
                thumb_range.get('min', 150),
                thumb_range.get('max', 600)
            )
            # Load saved value or use default
            saved_size = get_image_host_setting(self.host_id, 'thumbnail_size', 'int')
            default_size = thumb_range.get('default', 300)
            # For variable mode, the saved value is the actual pixel size, not an index
            if saved_size and thumb_range.get('min', 150) <= saved_size <= thumb_range.get('max', 600):
                self.thumb_slider.setValue(saved_size)
            else:
                self.thumb_slider.setValue(default_size)
            self.thumb_slider.valueChanged.connect(self._mark_modified)
            layout.addWidget(self.thumb_slider, current_row, 1)

            self.thumb_slider_label = QLabel(f"{self.thumb_slider.value()}px")
            self.thumb_slider_label.setMinimumWidth(50)
            self.thumb_slider.valueChanged.connect(
                lambda v: self.thumb_slider_label.setText(f"{v}px")
            )
            layout.addWidget(self.thumb_slider_label, current_row, 2)
        else:
            # Fixed mode: use dropdown for predefined sizes
            self.thumbnail_size_combo = QComboBox()
            for item in self.config.thumbnail_sizes:
                self.thumbnail_size_combo.addItem(item["label"])
            current_size = get_image_host_setting(self.host_id, 'thumbnail_size', 'int')
            if current_size and 1 <= current_size <= len(self.config.thumbnail_sizes):
                self.thumbnail_size_combo.setCurrentIndex(current_size - 1)
            self.thumbnail_size_combo.currentIndexChanged.connect(self._mark_modified)
            layout.addWidget(self.thumbnail_size_combo, current_row, 1)

        current_row += 1

        # Thumbnail Format (only if formats are defined)
        self.thumbnail_format_combo = None
        if self.config.thumbnail_formats:
            layout.addWidget(QLabel("<b>Thumbnail Format</b>:"), current_row, 0)
            self.thumbnail_format_combo = QComboBox()
            for item in self.config.thumbnail_formats:
                self.thumbnail_format_combo.addItem(item["label"])
            current_format = get_image_host_setting(self.host_id, 'thumbnail_format', 'int')
            if current_format and 1 <= current_format <= len(self.config.thumbnail_formats):
                self.thumbnail_format_combo.setCurrentIndex(current_format - 1)
            self.thumbnail_format_combo.currentIndexChanged.connect(self._mark_modified)
            layout.addWidget(self.thumbnail_format_combo, current_row, 1)
            current_row += 1

        # Content Type dropdown (if host supports content type filtering)
        self.content_type_combo = None
        if self.config.content_types:
            layout.addWidget(QLabel("<b>Content Type</b>:"), current_row, 0)
            self.content_type_combo = QComboBox()
            for ct in self.config.content_types:
                self.content_type_combo.addItem(ct['label'], ct['id'])
            # Load saved content type
            saved_content_type = get_image_host_setting(self.host_id, 'content_type', 'str')
            if saved_content_type:
                index = self.content_type_combo.findData(saved_content_type)
                if index >= 0:
                    self.content_type_combo.setCurrentIndex(index)
            self.content_type_combo.currentIndexChanged.connect(self._mark_modified)
            layout.addWidget(self.content_type_combo, current_row, 1)
            current_row += 1

        return group

    def _create_options_group(self) -> QGroupBox:
        """Create the options group (IMX-specific)."""
        group = QGroupBox("Options")
        layout = QVBoxLayout(group)

        self.auto_rename_check = QCheckBox("Automatically rename galleries on imx.to")
        self.auto_rename_check.setChecked(
            get_image_host_setting(self.host_id, 'auto_rename', 'bool')
        )
        self.auto_rename_check.toggled.connect(self._mark_modified)
        layout.addWidget(self.auto_rename_check)

        return group

    def _create_cover_group(self) -> QGroupBox:
        """Create cover gallery configuration group."""
        group = QGroupBox("Cover Gallery")
        layout = QVBoxLayout(group)

        gallery_row = QHBoxLayout()
        gallery_row.addWidget(QLabel("<b>Cover Gallery ID</b>:"))

        self.cover_gallery_edit = QLineEdit()
        self.cover_gallery_edit.setPlaceholderText("Gallery ID for cover uploads")
        self.cover_gallery_edit.setToolTip(
            "Gallery ID where cover photos are uploaded.\n"
            "Paste a gallery URL and the ID will be extracted."
        )
        self.cover_gallery_edit.textChanged.connect(self._on_cover_gallery_text_changed)
        gallery_row.addWidget(self.cover_gallery_edit)

        self.cover_create_btn = QPushButton("Create")
        self.cover_create_btn.setToolTip("Create a new gallery on this host")
        self.cover_create_btn.clicked.connect(self._on_cover_create_gallery)
        gallery_row.addWidget(self.cover_create_btn)

        layout.addLayout(gallery_row)

        # Anonymous warning for Turbo
        if self.host_id == "turbo":
            from src.gui.widgets.info_button import InfoButton

            self.cover_anon_widget = QWidget()
            anon_row = QHBoxLayout(self.cover_anon_widget)
            anon_row.setContentsMargins(0, 0, 0, 0)
            anon_label = QLabel("Requires account")
            anon_label.setProperty("class", "status-muted")
            anon_row.addWidget(anon_label)
            anon_row.addWidget(InfoButton(
                "<b>Cover gallery requires a TurboImageHost account.</b><br><br>"
                "Anonymous uploads cannot target a specific gallery."
            ))
            anon_row.addStretch()
            layout.addWidget(self.cover_anon_widget)

            has_creds = bool(get_credential('username', 'turbo') and get_credential('password', 'turbo'))
            self.cover_anon_widget.setVisible(not has_creds)
            self.cover_gallery_edit.setEnabled(has_creds)
            self.cover_create_btn.setEnabled(
                has_creds and not bool(self.cover_gallery_edit.text().strip())
            )
        else:
            self.cover_anon_widget = None

        # Load saved value
        saved = get_image_host_setting(self.host_id, 'cover_gallery', 'str') or ''
        self.cover_gallery_edit.setText(saved)
        self.cover_create_btn.setEnabled(not bool(saved.strip()))

        return group

    def _on_cover_gallery_text_changed(self, text: str):
        """Smart URL paste for cover gallery field."""
        import re
        self._mark_modified()

        extracted = text
        turbo_match = re.search(r'turboimagehost\.com/album/(\d+)', text)
        if turbo_match:
            extracted = turbo_match.group(1)
        else:
            imx_match = re.search(r'imx\.to/g/(\w+)', text)
            if imx_match:
                extracted = imx_match.group(1)

        if extracted != text:
            self.cover_gallery_edit.blockSignals(True)
            self.cover_gallery_edit.setText(extracted)
            self.cover_gallery_edit.blockSignals(False)

        self.cover_create_btn.setEnabled(not bool(self.cover_gallery_edit.text().strip()))

    def _on_cover_create_gallery(self):
        """Create a new cover gallery on this host."""
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Create Cover Gallery", "Gallery name:")
        if not ok or not name.strip():
            return
        try:
            from src.network.image_host_factory import create_image_host_client
            client = create_image_host_client(self.host_id)
            if hasattr(client, 'create_gallery'):
                gallery_id = client.create_gallery(name.strip())
                self.cover_gallery_edit.setText(gallery_id)
            else:
                QMessageBox.information(
                    self, "Not Supported",
                    "Create the gallery on the website and paste the URL here."
                )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create gallery: {e}")

    def on_external_cover_gallery_change(self, host_id: str, gallery_id: str):
        """Update cover gallery field when changed externally."""
        if host_id == self.host_id:
            self.cover_gallery_edit.blockSignals(True)
            self.cover_gallery_edit.setText(gallery_id)
            self.cover_gallery_edit.blockSignals(False)
            self.cover_create_btn.setEnabled(not bool(gallery_id.strip()))

    def _mark_modified(self):
        """Mark panel as modified and emit signal."""
        self._modified = True
        self.settings_changed.emit()

    def is_modified(self) -> bool:
        """Check if settings have been modified."""
        return self._modified

    def save(self) -> tuple:
        """
        Save non-credential settings to INI.

        Returns:
            tuple: (old_batch_size, new_batch_size)
        """
        old_batch = get_image_host_setting(self.host_id, 'parallel_batch_size', 'int')

        save_image_host_setting(self.host_id, 'max_retries', self.max_retries_slider.value())
        save_image_host_setting(self.host_id, 'parallel_batch_size', self.batch_size_slider.value())
        save_image_host_setting(self.host_id, 'upload_connect_timeout', self.connect_timeout_slider.value())
        save_image_host_setting(self.host_id, 'upload_read_timeout', self.read_timeout_slider.value())

        # Save thumbnail size - either slider value (variable) or combo index (fixed)
        if self.thumb_slider is not None:
            # Variable mode: save actual pixel value
            save_image_host_setting(self.host_id, 'thumbnail_size', self.thumb_slider.value())
        elif self.thumbnail_size_combo is not None:
            # Fixed mode: save 1-based index
            save_image_host_setting(self.host_id, 'thumbnail_size', self.thumbnail_size_combo.currentIndex() + 1)

        # Save thumbnail format (if available)
        if self.thumbnail_format_combo is not None:
            save_image_host_setting(self.host_id, 'thumbnail_format', self.thumbnail_format_combo.currentIndex() + 1)

        # Save content type (if available)
        if self.content_type_combo is not None:
            save_image_host_setting(self.host_id, 'content_type', self.content_type_combo.currentData())

        if self.host_id == "imx":
            save_image_host_setting(self.host_id, 'auto_rename', self.auto_rename_check.isChecked())

        save_image_host_setting(self.host_id, 'cover_gallery', self.cover_gallery_edit.text())
        self.cover_gallery_changed.emit(self.host_id, self.cover_gallery_edit.text())

        self._modified = False
        return (old_batch, self.batch_size_slider.value())

    # ========== CREDENTIAL MANAGEMENT METHODS ==========

    def load_current_credentials(self):
        """Load and display current credentials."""
        # Username
        username = get_credential('username', self.host_id)
        if username:
            self.username_status_label.setText(username)
            self.username_status_label.setProperty("class", "status-success")
            style = self.username_status_label.style()
            if style:
                style.polish(self.username_status_label)
            self.username_change_btn.setText(" Change")
            self.username_remove_btn.setEnabled(True)
        else:
            self.username_status_label.setText("NOT SET")
            self.username_status_label.setProperty("class", "status-muted")
            style = self.username_status_label.style()
            if style:
                style.polish(self.username_status_label)
            self.username_change_btn.setText(" Set")
            self.username_remove_btn.setEnabled(False)

        # Password
        password = get_credential('password', self.host_id)
        if password:
            self.password_status_label.setText("********************************")
            self.password_status_label.setProperty("class", "status-success")
            style = self.password_status_label.style()
            if style:
                style.polish(self.password_status_label)
            self.password_change_btn.setText(" Change")
            self.password_remove_btn.setEnabled(True)
        else:
            self.password_status_label.setText("NOT SET")
            self.password_status_label.setProperty("class", "status-muted")
            style = self.password_status_label.style()
            if style:
                style.polish(self.password_status_label)
            self.password_change_btn.setText(" Set")
            self.password_remove_btn.setEnabled(False)

        # API Key (only if row exists for this host)
        if self.api_key_status_label is not None:
            encrypted_api_key = get_credential('api_key', self.host_id)
            if encrypted_api_key:
                try:
                    api_key = decrypt_password(encrypted_api_key)
                    if api_key and len(api_key) > 8:
                        masked_key = api_key[:4] + "*" * 24 + api_key[-4:]
                        self.api_key_status_label.setText(masked_key)
                    else:
                        self.api_key_status_label.setText("SET")
                    self.api_key_status_label.setProperty("class", "status-success")
                    style = self.api_key_status_label.style()
                    if style:
                        style.polish(self.api_key_status_label)
                    self.api_key_change_btn.setText(" Change")
                    self.api_key_remove_btn.setEnabled(True)
                except (AttributeError, RuntimeError):
                    self.api_key_status_label.setText("SET")
                    self.api_key_status_label.setProperty("class", "status-success")
                    style = self.api_key_status_label.style()
                    if style:
                        style.polish(self.api_key_status_label)
                    self.api_key_change_btn.setText(" Change")
                    self.api_key_remove_btn.setEnabled(True)
            else:
                self.api_key_status_label.setText("NOT SET")
                self.api_key_status_label.setProperty("class", "status-muted")
                style = self.api_key_status_label.style()
                if style:
                    style.polish(self.api_key_status_label)
                self.api_key_change_btn.setText(" Set")
                self.api_key_remove_btn.setEnabled(False)

        # Firefox Cookies (only if row exists for this host)
        if self.cookies_status_label is None:
            return

        config = configparser.ConfigParser()
        config_file = get_config_path()
        cookies_enabled = True  # Default
        if os.path.exists(config_file):
            config.read(config_file, encoding='utf-8')
            if 'CREDENTIALS' in config:
                cookies_enabled_val = str(config['CREDENTIALS'].get('cookies_enabled', 'true')).lower()
                cookies_enabled = cookies_enabled_val != 'false'

        if cookies_enabled:
            self.cookies_status_label.setText("Enabled")
            self.cookies_status_label.setProperty("class", "status-success")
        else:
            self.cookies_status_label.setText("Disabled")
            self.cookies_status_label.setProperty("class", "status-error")

        style = self.cookies_status_label.style()
        if style:
            style.polish(self.cookies_status_label)

        self.cookies_enable_btn.setEnabled(not cookies_enabled)
        self.cookies_disable_btn.setEnabled(cookies_enabled)

    def change_api_key(self):
        """Open dialog to change API key."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Set API Key")
        dialog.setModal(True)
        dialog.resize(400, 150)

        layout = QVBoxLayout(dialog)

        # API Key input
        api_key_layout = QHBoxLayout()
        api_key_layout.addWidget(QLabel("API Key:"))
        api_key_edit = QLineEdit()
        api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        api_key_layout.addWidget(api_key_edit)
        layout.addLayout(api_key_layout)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        save_btn = QPushButton("Save")
        style = self.style()
        if style:
            save_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        save_btn.setIconSize(QSize(16, 16))
        if not save_btn.text().startswith(" "):
            save_btn.setText(" " + save_btn.text())
        save_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(save_btn)

        cancel_btn = QPushButton("Cancel")
        if style:
            cancel_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogCancelButton))
        cancel_btn.setIconSize(QSize(16, 16))
        if not cancel_btn.text().startswith(" "):
            cancel_btn.setText(" " + cancel_btn.text())
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

        # Non-blocking show
        def handle_api_key_result(result):
            self._handle_api_key_dialog_result(result, api_key_edit.text().strip())

        dialog.show()
        dialog.finished.connect(handle_api_key_result)

    def _handle_api_key_dialog_result(self, result, api_key):
        """Handle API key dialog result without blocking GUI."""
        if result == QDialog.DialogCode.Accepted:
            if api_key:
                try:
                    set_credential('api_key', encrypt_password(api_key), self.host_id)
                    self.load_current_credentials()
                    QMessageBox.information(self, "Success", "API key saved successfully!")
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to save API key: {str(e)}")
            else:
                QMessageBox.warning(self, "Missing Information", "Please enter your API key.")

    def change_username(self):
        """Open dialog to change username."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Set Username")
        dialog.setModal(True)
        dialog.resize(400, 140)

        layout = QVBoxLayout(dialog)

        # Username input
        username_layout = QHBoxLayout()
        username_layout.addWidget(QLabel("Username:"))
        username_edit = QLineEdit()
        username_layout.addWidget(username_edit)
        layout.addLayout(username_layout)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        save_btn = QPushButton("Save")
        style = self.style()
        if style:
            save_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        save_btn.setIconSize(QSize(16, 16))
        if not save_btn.text().startswith(" "):
            save_btn.setText(" " + save_btn.text())
        save_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(save_btn)

        cancel_btn = QPushButton("Cancel")
        if style:
            cancel_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogCancelButton))
        cancel_btn.setIconSize(QSize(16, 16))
        if not cancel_btn.text().startswith(" "):
            cancel_btn.setText(" " + cancel_btn.text())
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

        # Non-blocking show
        def handle_username_result(result):
            self._handle_username_dialog_result(result, username_edit.text().strip())

        dialog.show()
        dialog.finished.connect(handle_username_result)

    def _handle_username_dialog_result(self, result, username):
        """Handle username dialog result without blocking GUI."""
        if result == QDialog.DialogCode.Accepted:
            if username:
                try:
                    set_credential('username', username, self.host_id)
                    self.load_current_credentials()
                    QMessageBox.information(self, "Success", "Username saved successfully!")
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to save username: {str(e)}")
            else:
                QMessageBox.warning(self, "Missing Information", "Please enter a username.")

    def change_password(self):
        """Open dialog to change password."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Set Password")
        dialog.setModal(True)
        dialog.resize(400, 140)

        layout = QVBoxLayout(dialog)

        # Password input
        password_layout = QHBoxLayout()
        password_layout.addWidget(QLabel("Password:"))
        password_edit = QLineEdit()
        password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        password_layout.addWidget(password_edit)
        layout.addLayout(password_layout)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        save_btn = QPushButton("Save")
        style = self.style()
        if style:
            save_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        save_btn.setIconSize(QSize(16, 16))
        if not save_btn.text().startswith(" "):
            save_btn.setText(" " + save_btn.text())
        save_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(save_btn)

        cancel_btn = QPushButton("Cancel")
        if style:
            cancel_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogCancelButton))
        cancel_btn.setIconSize(QSize(16, 16))
        if not cancel_btn.text().startswith(" "):
            cancel_btn.setText(" " + cancel_btn.text())
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

        # Non-blocking show
        def handle_password_result(result):
            self._handle_password_dialog_result(result, password_edit.text())

        dialog.show()
        dialog.finished.connect(handle_password_result)

    def _handle_password_dialog_result(self, result, password):
        """Handle password dialog result without blocking GUI."""
        if result == QDialog.DialogCode.Accepted:
            if password:
                try:
                    set_credential('password', encrypt_password(password), self.host_id)
                    self.load_current_credentials()
                    QMessageBox.information(self, "Success", "Password saved successfully!")
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to save password: {str(e)}")
            else:
                QMessageBox.warning(self, "Missing Information", "Please enter a password.")

    def remove_api_key(self):
        """Remove stored API key with confirmation."""
        msgbox = QMessageBox(self)
        msgbox.setWindowTitle("Remove API Key")
        msgbox.setText("Without an API key, it is not possible to upload anything.\n\nRemove the stored API key?")
        msgbox.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msgbox.setDefaultButton(QMessageBox.StandardButton.No)
        msgbox.open()
        msgbox.finished.connect(self._handle_remove_api_key_confirmation)

    def _handle_remove_api_key_confirmation(self, result):
        """Handle API key removal confirmation."""
        if result != QMessageBox.StandardButton.Yes:
            return
        try:
            remove_credential('api_key', self.host_id)
            self.load_current_credentials()
            QMessageBox.information(self, "Removed", "API key removed.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to remove API key: {str(e)}")

    def remove_username(self):
        """Remove stored username with confirmation."""
        msgbox = QMessageBox(self)
        msgbox.setWindowTitle("Remove Username")
        msgbox.setText("Without username/password, all galleries will be titled 'untitled gallery'.\n\nRemove the stored username?")
        msgbox.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msgbox.setDefaultButton(QMessageBox.StandardButton.No)
        msgbox.open()
        msgbox.finished.connect(self._handle_remove_username_confirmation)

    def _handle_remove_username_confirmation(self, result):
        """Handle username removal confirmation."""
        if result != QMessageBox.StandardButton.Yes:
            return
        try:
            remove_credential('username', self.host_id)
            self.load_current_credentials()
            QMessageBox.information(self, "Removed", "Username removed.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to remove username: {str(e)}")

    def remove_password(self):
        """Remove stored password with confirmation."""
        msgbox = QMessageBox(self)
        msgbox.setWindowTitle("Remove Password")
        msgbox.setText("Without username/password, all galleries will be titled 'untitled gallery'.\n\nRemove the stored password?")
        msgbox.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msgbox.setDefaultButton(QMessageBox.StandardButton.No)
        msgbox.open()
        msgbox.finished.connect(self._handle_remove_password_confirmation)

    def _handle_remove_password_confirmation(self, result):
        """Handle password removal confirmation."""
        if result != QMessageBox.StandardButton.Yes:
            return
        try:
            remove_credential('password', self.host_id)
            self.load_current_credentials()
            QMessageBox.information(self, "Removed", "Password removed.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to remove password: {str(e)}")

    def enable_cookies_setting(self):
        """Enable Firefox cookies usage for login."""
        try:
            config = configparser.ConfigParser()
            config_file = get_config_path()
            if os.path.exists(config_file):
                config.read(config_file, encoding='utf-8')
            if 'CREDENTIALS' not in config:
                config['CREDENTIALS'] = {}
            config['CREDENTIALS']['cookies_enabled'] = 'true'
            with open(config_file, 'w', encoding='utf-8') as f:
                config.write(f)
            self.load_current_credentials()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to enable cookies: {str(e)}")

    def disable_cookies_setting(self):
        """Disable Firefox cookies usage for login."""
        try:
            config = configparser.ConfigParser()
            config_file = get_config_path()
            if os.path.exists(config_file):
                config.read(config_file, encoding='utf-8')
            if 'CREDENTIALS' not in config:
                config['CREDENTIALS'] = {}
            config['CREDENTIALS']['cookies_enabled'] = 'false'
            with open(config_file, 'w', encoding='utf-8') as f:
                config.write(f)
            self.load_current_credentials()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to disable cookies: {str(e)}")

    # ========== CREDENTIAL TESTING ==========

    def _start_credential_test(self):
        """Start a background credential test."""
        # Gather credentials for the current host
        credentials = {}

        if self._has_api_key_row:
            encrypted_key = get_credential('api_key', self.host_id)
            if encrypted_key:
                try:
                    credentials['api_key'] = decrypt_password(encrypted_key)
                except Exception:
                    pass

        username = get_credential('username', self.host_id)
        if username:
            credentials['username'] = username

        encrypted_pw = get_credential('password', self.host_id)
        if encrypted_pw:
            try:
                credentials['password'] = decrypt_password(encrypted_pw)
            except Exception:
                pass

        if not credentials:
            self.test_result_label.setText(
                "<span style='color:orange;'>No credentials set to test</span>"
            )
            return

        # Disable button, show testing state
        self.test_credentials_btn.setEnabled(False)
        self.test_result_label.setText("Testing...")

        self._test_thread = _CredentialTestThread(self.host_id, credentials, self)
        self._test_thread.result.connect(self._on_test_result)
        self._test_thread.start()

    def _on_test_result(self, success: bool, message: str):
        """Handle credential test result from background thread."""
        self.test_credentials_btn.setEnabled(True)
        if success:
            self.test_result_label.setText(
                f"<span style='color:green;'>{message}</span>"
            )
        else:
            self.test_result_label.setText(
                f"<span style='color:red;'>{message}</span>"
            )


class _CredentialTestThread(QThread):
    """Background thread for testing image host credentials."""

    result = pyqtSignal(bool, str)

    def __init__(self, host_id: str, credentials: dict, parent=None):
        super().__init__(parent)
        self.host_id = host_id
        self.credentials = credentials

    def run(self):
        """Run the credential test (called in background thread)."""
        try:
            if self.host_id == "imx":
                success, msg = self._test_imx()
            elif self.host_id == "turbo":
                success, msg = self._test_turbo()
            else:
                success, msg = False, f"No test available for '{self.host_id}'"
            self.result.emit(success, msg)
        except Exception as e:
            self.result.emit(False, f"Test failed: {e}")

    def _test_imx(self) -> tuple:
        """Test IMX API key by sending a POST without a file.

        A valid key returns a "no file" error; an invalid key returns an auth error.
        """
        import requests

        api_key = self.credentials.get('api_key')
        if not api_key:
            return False, "No API key set"

        try:
            response = requests.post(
                "https://api.imx.to/v1/upload.php",
                headers={
                    "X-API-Key": api_key,
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko/20100101 Firefox/141.0",
                },
                timeout=15,
            )

            # If the key is valid, we get a response about missing file (not an auth error)
            text = response.text.lower()

            if response.status_code == 401 or "unauthorized" in text or "invalid" in text:
                return False, "Invalid API key"

            if response.status_code == 403 or "forbidden" in text:
                return False, "API key rejected (forbidden)"

            # Any other response means the key was accepted (even errors about missing file)
            return True, "API key is valid"

        except requests.Timeout:
            return False, "Connection timed out"
        except requests.ConnectionError:
            return False, "Could not connect to imx.to"

    def _test_turbo(self) -> tuple:
        """Test Turbo credentials by attempting a login."""
        import requests

        username = self.credentials.get('username')
        password = self.credentials.get('password')

        if not username or not password:
            return False, "Username and password required"

        try:
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:141.0) Gecko/20100101 Firefox/141.0',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            })

            base_url = "https://www.turboimagehost.com"
            login_url = f"{base_url}/login.tu"

            # Get login page (for cookies/CSRF)
            session.get(login_url, timeout=15)

            # Submit login form
            response = session.post(
                login_url,
                data={
                    'username': username,
                    'password': password,
                    'submit': 'Login',
                },
                timeout=15,
                allow_redirects=True,
            )

            if 'logout' in response.text.lower() or username.lower() in response.text.lower():
                return True, f"Login successful as {username}"
            else:
                return False, "Login failed - check username/password"

        except requests.Timeout:
            return False, "Connection timed out"
        except requests.ConnectionError:
            return False, "Could not connect to turboimagehost.com"
