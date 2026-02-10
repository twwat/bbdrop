#!/usr/bin/env python3
"""Image Host Configuration Dialog"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap

from src.core.image_host_config import (
    ImageHostConfig, is_image_host_enabled, save_image_host_enabled
)
from src.gui.widgets.image_host_config_panel import (
    ImageHostConfigPanel, _CredentialTestThread
)
from bbdrop import get_credential, decrypt_password


class ImageHostConfigDialog(QDialog):
    """Dialog for configuring a single image host with enable/disable button.

    Matches the file host config dialog pattern:
    - Enable button tests credentials before enabling
    - Shows "Enabling..." while testing
    - Shows error next to button if credentials fail
    - Disable is immediate
    """

    # Emitted when enable state changes: (host_id, enabled)
    host_enabled_changed = pyqtSignal(str, bool)

    def __init__(self, parent, host_id: str, host_config: ImageHostConfig):
        super().__init__(parent)
        self.host_id = host_id
        self.host_config = host_config
        self._initial_enabled = is_image_host_enabled(host_id)
        self._current_enabled = self._initial_enabled
        self._test_thread = None
        self.setWindowTitle(f"Configure {host_config.name}")
        self.setModal(True)
        self.resize(550, 650)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Header with host name (left) and logo (right)
        header_layout = QHBoxLayout()
        info_label = QLabel(
            f"<h2>{self.host_config.name}</h2>"
            f"<p>Configure host settings, credentials, and upload settings</p>"
        )
        header_layout.addWidget(info_label, 1)

        logo_label = self._load_logo()
        if logo_label:
            header_layout.addWidget(logo_label)
            header_layout.addSpacing(100)

        layout.addLayout(header_layout)

        # Enable/Disable button row — same as file hosts
        button_row = QHBoxLayout()

        self.enable_button = QPushButton()
        self.enable_button.setMinimumWidth(200)
        self.enable_button.clicked.connect(self._on_enable_button_clicked)
        button_row.addWidget(self.enable_button)

        self.enable_error_label = QLabel()
        self.enable_error_label.setProperty("class", "status-error")
        self.enable_error_label.setWordWrap(True)
        button_row.addWidget(self.enable_error_label, 1)

        layout.addLayout(button_row)
        self._update_enable_button_state(self._current_enabled)

        # Configuration panel
        self.panel = ImageHostConfigPanel(self.host_id, self.host_config, self)
        layout.addWidget(self.panel)
        layout.addStretch()

        # OK/Cancel
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
        from bbdrop import get_project_root
        import os

        if not self.host_config.logo:
            return None

        logo_path = os.path.join(
            get_project_root(), "assets", "image_hosts", self.host_config.logo
        )
        if os.path.exists(logo_path):
            try:
                pixmap = QPixmap(logo_path)
                if not pixmap.isNull():
                    logo_label = QLabel()
                    scaled = pixmap.scaledToHeight(
                        40, Qt.TransformationMode.SmoothTransformation
                    )
                    logo_label.setPixmap(scaled)
                    return logo_label
            except Exception:
                pass
        return None

    def _update_enable_button_state(self, enabled: bool):
        if enabled:
            self.enable_button.setText(f"Disable {self.host_config.name}")
            self.enable_button.setProperty("class", "host-disable-btn")
        else:
            self.enable_button.setText(f"Enable {self.host_config.name}")
            self.enable_button.setProperty("class", "host-enable-btn")
        style = self.enable_button.style()
        if style:
            style.unpolish(self.enable_button)
            style.polish(self.enable_button)

    def _on_enable_button_clicked(self):
        if self._current_enabled:
            # Disable — immediate, no credential check needed
            self._current_enabled = False
            save_image_host_enabled(self.host_id, False)
            self._update_enable_button_state(False)
            self.enable_error_label.setText("")
            self.host_enabled_changed.emit(self.host_id, False)
        else:
            # Enable — test credentials if any are set, otherwise just enable
            credentials = self._gather_credentials()
            if not credentials:
                self._current_enabled = True
                save_image_host_enabled(self.host_id, True)
                self._update_enable_button_state(True)
                self.enable_error_label.setText("")
                self.host_enabled_changed.emit(self.host_id, True)
                return

            # Show "Enabling..." state, disable button while testing
            self.enable_button.setText(f"Enabling {self.host_config.name}...")
            self.enable_button.setEnabled(False)
            self.enable_error_label.setText("")

            self._test_thread = _CredentialTestThread(
                self.host_id, credentials, self
            )
            self._test_thread.result.connect(self._on_enable_test_result)
            self._test_thread.start()

    def _on_enable_test_result(self, success: bool, message: str):
        self.enable_button.setEnabled(True)

        if success:
            self._current_enabled = True
            save_image_host_enabled(self.host_id, True)
            self._update_enable_button_state(True)
            self.enable_error_label.setText("")
            self.host_enabled_changed.emit(self.host_id, True)
        else:
            # Credential check failed — stay disabled, show error
            self._update_enable_button_state(False)
            self.enable_error_label.setText(message)

    def _gather_credentials(self) -> dict:
        credentials = {}
        auth_type = self.host_config.auth_type or ""

        if "api_key" in auth_type:
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

        return credentials

    def enabled_changed(self) -> bool:
        return self._current_enabled != self._initial_enabled

    def _on_ok(self):
        self.panel.save()
        self.accept()
