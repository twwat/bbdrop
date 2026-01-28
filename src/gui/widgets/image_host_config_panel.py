#!/usr/bin/env python3
"""
Image host configuration panel widget.

Renders a config panel for a single image host, driven by ImageHostConfig data.
Provides UI for credentials, connection settings, thumbnails, and host-specific options.
"""

import os
import configparser
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QGroupBox,
    QPushButton, QSlider, QComboBox, QCheckBox, QLineEdit, QDialog,
    QMessageBox, QStyle
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize

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

    def _create_credentials_group(self) -> QGroupBox:
        """Create the credentials configuration group."""
        group = QGroupBox("Credentials")
        layout = QVBoxLayout(group)

        # API Key row
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

        # Firefox Cookies row
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

        # Encryption note
        encryption_note = QLabel(
            "<small>API key and password are encrypted via Fernet (AES-128-CBC / PKCS7 padding + HMAC-SHA256) using your system's hostname and stored in the registry.<br><br>This means the encrypted data is protected from other users on this system and won't work on other computers.</small>"
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

        # Thumbnail Size
        layout.addWidget(QLabel("<b>Thumbnail Size</b>:"), 0, 0)
        self.thumbnail_size_combo = QComboBox()
        for item in self.config.thumbnail_sizes:
            self.thumbnail_size_combo.addItem(item["label"])
        current_size = get_image_host_setting(self.host_id, 'thumbnail_size', 'int')
        self.thumbnail_size_combo.setCurrentIndex(current_size - 1)
        self.thumbnail_size_combo.currentIndexChanged.connect(self._mark_modified)
        layout.addWidget(self.thumbnail_size_combo, 0, 1)

        # Thumbnail Format
        layout.addWidget(QLabel("<b>Thumbnail Format</b>:"), 1, 0)
        self.thumbnail_format_combo = QComboBox()
        for item in self.config.thumbnail_formats:
            self.thumbnail_format_combo.addItem(item["label"])
        current_format = get_image_host_setting(self.host_id, 'thumbnail_format', 'int')
        self.thumbnail_format_combo.setCurrentIndex(current_format - 1)
        self.thumbnail_format_combo.currentIndexChanged.connect(self._mark_modified)
        layout.addWidget(self.thumbnail_format_combo, 1, 1)

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
        save_image_host_setting(self.host_id, 'thumbnail_size', self.thumbnail_size_combo.currentIndex() + 1)
        save_image_host_setting(self.host_id, 'thumbnail_format', self.thumbnail_format_combo.currentIndex() + 1)

        if self.host_id == "imx":
            save_image_host_setting(self.host_id, 'auto_rename', self.auto_rename_check.isChecked())

        self._modified = False
        return (old_batch, self.batch_size_slider.value())

    # ========== CREDENTIAL MANAGEMENT METHODS ==========

    def load_current_credentials(self):
        """Load and display current credentials."""
        # Username
        username = get_credential('username')
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
        password = get_credential('password')
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

        # API Key
        encrypted_api_key = get_credential('api_key')
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

        # Firefox Cookies
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
                    set_credential('api_key', encrypt_password(api_key))
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
                    set_credential('username', username)
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
                    set_credential('password', encrypt_password(password))
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
            remove_credential('api_key')
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
            remove_credential('username')
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
            remove_credential('password')
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
