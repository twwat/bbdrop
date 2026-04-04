#!/usr/bin/env python3
"""
Image host configuration panel widget.

Renders a config panel for a single image host, driven by ImageHostConfig data.
Provides UI for credentials, connection settings, thumbnails, and host-specific options.
"""

import os
import configparser
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QLabel,
    QGroupBox, QPushButton, QSlider, QComboBox, QCheckBox, QLineEdit,
    QMessageBox, QRadioButton, QButtonGroup, QFrame, QSpinBox
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, pyqtSignal, QThread

from src.core.image_host_config import (
    ImageHostConfig,
    get_image_host_setting,
    save_image_host_setting
)
from src.utils.paths import get_config_path
from src.utils.credentials import (
    encrypt_password,
    decrypt_password,
    get_credential,
    set_credential,
    remove_credential
)
from src.gui.widgets.info_button import InfoButton


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

        # Section 1: Credentials (full width, always shown for ALL hosts)
        credentials_group = self._create_credentials_group()
        main_layout.addWidget(credentials_group)

        # Section 2: 2-column grid for remaining sections
        grid = QGridLayout()
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setVerticalSpacing(12)

        # Row 0: Upload Settings (left), Thumbnails (right)
        upload_settings_group = self._create_upload_settings_group()
        grid.addWidget(upload_settings_group, 0, 0)

        thumbnails_group = self._create_thumbnails_group()
        grid.addWidget(thumbnails_group, 0, 1)

        # Row 1: Options (left), Cover Gallery (right, skip for pixhost)
        options_group = self._create_options_group()
        grid.addWidget(options_group, 1, 0)

        self._has_cover_gallery = self.config.requires_auth or (self.config.auth_type and 'session' in self.config.auth_type)
        if self._has_cover_gallery:
            cover_group = self._create_cover_group()
            grid.addWidget(cover_group, 1, 1)

        main_layout.addLayout(grid)

    def _create_inline_field(self, placeholder: str) -> tuple:
        """Create an inline QLineEdit with eye toggle button.

        Returns:
            tuple: (QLineEdit, QPushButton) - the input field and toggle button
        """
        field = QLineEdit()
        field.setFont(QFont("Consolas", 10))
        field.setEchoMode(QLineEdit.EchoMode.Password)
        field.setPlaceholderText(placeholder)

        toggle_btn = QPushButton()
        try:
            from src.gui.icon_manager import get_icon_manager
            icon_manager = get_icon_manager()
            if icon_manager:
                toggle_btn.setIcon(icon_manager.get_icon('action_view'))
        except Exception:
            pass
        toggle_btn.setMaximumWidth(30)
        toggle_btn.setCheckable(True)
        toggle_btn.setToolTip("Show/hide")
        toggle_btn.clicked.connect(
            lambda checked, f=field: f.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )

        return field, toggle_btn

    def _create_credentials_group(self) -> QGroupBox:
        """Create the credentials configuration group.

        Three branches based on auth_type:
        - "none" (Pixhost): No-account notice
        - "api_key_or_session" (IMX): API Key + Username + Password inline fields
        - "session_optional" (Turbo): Username + Password inline fields
        """
        auth_type = self.config.auth_type or ""
        needs_api_key = "api_key" in auth_type
        needs_cookies = auth_type == "api_key_or_session"  # IMX-specific
        is_optional = not self.config.requires_auth

        # Track which widgets exist for this host (set BEFORE branch checks)
        self._has_api_key_row = needs_api_key
        self._has_cookies_row = needs_cookies

        # ── Pixhost: no-account notice ──
        if auth_type == "none":
            group = QGroupBox("Credentials")
            layout = QVBoxLayout(group)

            notice_row = QHBoxLayout()
            notice_label = QLabel(
                "Pixhost does not require an account. Uploads are anonymous"
                " &mdash; once uploaded, images cannot be deleted or managed."
            )
            notice_label.setWordWrap(True)
            notice_label.setProperty("class", "info-panel")
            notice_row.addWidget(notice_label, 1)
            notice_row.addWidget(InfoButton(
                "Pixhost is a fully anonymous image host. There are no user"
                " accounts, no dashboard, and no way to delete or manage"
                " images after upload.<br><br>"
                "Once an image is uploaded, it is permanent and publicly"
                " accessible via its URL. There is no API key or login"
                " to configure."
            ))
            layout.addLayout(notice_row)

            # Set ALL dummy attributes so other methods don't crash
            self.api_key_input = None
            self.username_input = None
            self.password_input = None
            self.cookies_status_label = None
            self.cookies_enable_btn = None
            self.cookies_disable_btn = None
            self.test_credentials_btn = None
            self.test_result_label = None
            self._test_thread = None

            return group

        # ── IMX: API Key + Login hybrid ──
        if needs_api_key:
            group = QGroupBox("Credentials")
            layout = QVBoxLayout(group)

            # Bold "API Key" header
            api_key_header = QLabel("<b>API Key</b>")
            layout.addWidget(api_key_header)

            # Info-panel with link
            api_key_info = QLabel(
                '<span class="info-panel">Required for uploading files &mdash;'
                ' get your API key from'
                ' <a href="https://imx.to/user/api">imx.to/user/api</a></span>'
            )
            api_key_info.setWordWrap(True)
            api_key_info.setOpenExternalLinks(True)
            api_key_info.setProperty("class", "info-panel")
            layout.addWidget(api_key_info)

            # Inline API Key field with eye toggle
            self.api_key_input, api_key_toggle = self._create_inline_field("Enter API key...")
            api_key_row = QHBoxLayout()
            api_key_row.addWidget(self.api_key_input)
            api_key_row.addWidget(api_key_toggle)

            form = QFormLayout()
            form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
            form.addRow("API Key:", api_key_row)
            layout.addLayout(form)

            # Separator
            separator = QFrame()
            separator.setFrameShape(QFrame.Shape.HLine)
            separator.setFrameShadow(QFrame.Shadow.Sunken)
            layout.addWidget(separator)

            # Bold "Login" header
            login_header = QLabel("<b>Login</b>")
            layout.addWidget(login_header)

            # Login info-panel
            login_info = QLabel(
                "Required for renaming galleries and checking online status"
                " via Link Scanner. Without login credentials, all galleries"
                " will be named &ldquo;untitled gallery&rdquo;."
            )
            login_info.setWordWrap(True)
            login_info.setProperty("class", "info-panel")
            layout.addWidget(login_info)

            # Inline Username + Password fields with eye toggles
            self.username_input, username_toggle = self._create_inline_field("Enter username...")
            username_row = QHBoxLayout()
            username_row.addWidget(self.username_input)
            username_row.addWidget(username_toggle)

            self.password_input, password_toggle = self._create_inline_field("Enter password...")
            password_row = QHBoxLayout()
            password_row.addWidget(self.password_input)
            password_row.addWidget(password_toggle)

            login_form = QFormLayout()
            login_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
            login_form.addRow("Username:", username_row)
            login_form.addRow("Password:", password_row)
            layout.addLayout(login_form)

            # Firefox Cookies row
            cookies_row = QHBoxLayout()
            cookies_row.addWidget(QLabel("<b>Firefox Cookies</b>: "))
            cookies_row.addWidget(InfoButton(
                "When enabled, BBDrop reads your Firefox browser cookies for "
                "imx.to. This lets it use your existing login session instead "
                "of API key authentication.<br><br>"
                "Useful if your API key has issues or if you want to use "
                "account features that require a browser session.<br><br>"
                "Requires Firefox to be installed and you must be logged into "
                "imx.to in Firefox."
            ))
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

        # ── Turbo: optional session credentials ──
        else:
            group = QGroupBox("Credentials (Optional)") if is_optional else QGroupBox("Credentials")
            layout = QVBoxLayout(group)

            # Info-panel
            optional_info = QLabel(
                "Optional &mdash; an account lets you manage uploaded"
                " galleries and use cover galleries."
            )
            optional_info.setWordWrap(True)
            optional_info.setProperty("class", "info-panel")
            layout.addWidget(optional_info)

            # No API key, no cookies
            self.api_key_input = None
            self.cookies_status_label = None
            self.cookies_enable_btn = None
            self.cookies_disable_btn = None

            # Inline Username + Password fields with eye toggles
            self.username_input, username_toggle = self._create_inline_field("Enter username...")
            username_row = QHBoxLayout()
            username_row.addWidget(self.username_input)
            username_row.addWidget(username_toggle)

            self.password_input, password_toggle = self._create_inline_field("Enter password...")
            password_row = QHBoxLayout()
            password_row.addWidget(self.password_input)
            password_row.addWidget(password_toggle)

            login_form = QFormLayout()
            login_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
            login_form.addRow("Username:", username_row)
            login_form.addRow("Password:", password_row)
            layout.addLayout(login_form)

        # Test Credentials button and result (shared by IMX and Turbo)
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
            "<small>Credentials are encrypted with Fernet"
            " (AES-128-CBC + HMAC-SHA256) using a CSPRNG master key,"
            " then stored in your OS keyring (Windows Credential"
            " Manager / macOS Keychain / Linux Secret Service)."
            "<br><br>They are tied to your user account and"
            " won't transfer to other computers.</small>"
        )
        encryption_note.setWordWrap(True)
        encryption_note.setProperty("class", "label-credential-note")
        layout.addWidget(encryption_note)

        return group

    def _make_label_with_info(self, text: str, tooltip: str) -> QWidget:
        """Create a label + InfoButton widget for use in QFormLayout rows."""
        container = QWidget()
        h = QHBoxLayout(container)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(QLabel(text))
        h.addWidget(InfoButton(tooltip))
        h.addStretch()
        return container

    def _create_upload_settings_group(self) -> QGroupBox:
        """Create the upload settings group with spinboxes."""
        group = QGroupBox("Upload Settings")
        layout = QFormLayout(group)

        # --- 1. Unified retry row ---
        retry_row_widget = QWidget()
        retry_row = QHBoxLayout(retry_row_widget)
        retry_row.setContentsMargins(0, 0, 0, 0)

        retry_row.addWidget(QLabel("Auto-retry"))
        retry_row.addWidget(InfoButton(
            "When enabled, failed uploads are automatically retried up to the "
            "specified number of times. Each retry uses a fresh connection. "
            "The delay between retries increases with each attempt."
        ))

        self.auto_retry_check = QCheckBox()
        self.auto_retry_check.setChecked(
            get_image_host_setting(self.host_id, 'auto_retry', 'bool')
        )
        self.auto_retry_check.toggled.connect(self._mark_modified)
        retry_row.addWidget(self.auto_retry_check)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        retry_row.addWidget(separator)

        retry_row.addWidget(QLabel("Max retries"))
        self.max_retries_spin = QSpinBox()
        self.max_retries_spin.setMinimum(1)
        self.max_retries_spin.setMaximum(10)
        self.max_retries_spin.setValue(
            get_image_host_setting(self.host_id, 'max_retries', 'int')
        )
        self.max_retries_spin.setEnabled(self.auto_retry_check.isChecked())
        self.auto_retry_check.toggled.connect(self.max_retries_spin.setEnabled)
        self.max_retries_spin.valueChanged.connect(self._mark_modified)
        retry_row.addWidget(self.max_retries_spin)
        retry_row.addStretch()

        layout.addRow(retry_row_widget)

        # --- 2. Concurrent uploads ---
        self.concurrent_uploads_spin = QSpinBox()
        self.concurrent_uploads_spin.setMinimum(1)
        self.concurrent_uploads_spin.setMaximum(8)
        self.concurrent_uploads_spin.setValue(
            get_image_host_setting(self.host_id, 'parallel_batch_size', 'int')
        )
        self.concurrent_uploads_spin.valueChanged.connect(self._mark_modified)
        layout.addRow(
            self._make_label_with_info(
                "Concurrent uploads",
                "Number of images uploaded simultaneously within a gallery. "
                "Higher values are faster but may trigger rate limiting on some "
                "hosts. Most hosts work well with 3-4."
            ),
            self.concurrent_uploads_spin,
        )

        # --- 3. Connect timeout ---
        self.connect_timeout_spin = QSpinBox()
        self.connect_timeout_spin.setMinimum(10)
        self.connect_timeout_spin.setMaximum(180)
        self.connect_timeout_spin.setSuffix("s")
        self.connect_timeout_spin.setValue(
            get_image_host_setting(self.host_id, 'upload_connect_timeout', 'int')
        )
        self.connect_timeout_spin.valueChanged.connect(self._mark_modified)
        layout.addRow(
            self._make_label_with_info(
                "Connect timeout",
                "How long to wait when establishing a connection to the host "
                "before giving up. Increase if you're on a slow or unreliable "
                "network. Most connections complete in under 10 seconds."
            ),
            self.connect_timeout_spin,
        )

        # --- 4. Inactivity timeout ---
        self.inactivity_timeout_spin = QSpinBox()
        self.inactivity_timeout_spin.setMinimum(20)
        self.inactivity_timeout_spin.setMaximum(600)
        self.inactivity_timeout_spin.setSuffix("s")
        self.inactivity_timeout_spin.setValue(
            get_image_host_setting(self.host_id, 'upload_read_timeout', 'int')
        )
        self.inactivity_timeout_spin.valueChanged.connect(self._mark_modified)
        layout.addRow(
            self._make_label_with_info(
                "Inactivity timeout",
                "How long to wait for data during an active upload before "
                "treating it as stalled. If no data is received for this long, "
                "the upload is considered failed. Increase for slow connections "
                "or large files."
            ),
            self.inactivity_timeout_spin,
        )

        # --- 5. Max upload time ---
        self.max_upload_time_spin = QSpinBox()
        self.max_upload_time_spin.setMinimum(0)
        self.max_upload_time_spin.setMaximum(7200)
        self.max_upload_time_spin.setSuffix("s")
        self.max_upload_time_spin.setSpecialValueText("Off")
        self.max_upload_time_spin.setValue(
            get_image_host_setting(self.host_id, 'max_upload_time', 'int')
        )
        self.max_upload_time_spin.valueChanged.connect(self._mark_modified)
        layout.addRow(
            self._make_label_with_info(
                "Max upload time",
                "Maximum total time allowed for a single image upload. Set to "
                "0 to disable. Useful as a safety net to prevent uploads from "
                "hanging indefinitely."
            ),
            self.max_upload_time_spin,
        )

        # --- 6. Max file size ---
        self.max_file_size_spin = QSpinBox()
        self.max_file_size_spin.setMinimum(0)
        self.max_file_size_spin.setMaximum(10000)
        self.max_file_size_spin.setSuffix(" MiB")
        self.max_file_size_spin.setSpecialValueText("No limit")
        self.max_file_size_spin.setValue(
            get_image_host_setting(self.host_id, 'max_file_size_mb', 'int')
        )
        self.max_file_size_spin.valueChanged.connect(self._mark_modified)
        layout.addRow(
            self._make_label_with_info(
                "Max file size",
                "Maximum file size this host accepts. Files larger than this "
                "will be skipped. The default is the host\u2019s documented limit "
                "\u2014 increase only if your account has higher limits."
            ),
            self.max_file_size_spin,
        )

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

        return group

    def _create_options_group(self) -> QGroupBox:
        """Create host-specific options group.

        Serves ALL hosts. Contains content rating (radio buttons),
        plus host-specific options like auto-rename (IMX) or
        auto-finalize and error strategy (Pixhost).
        """
        group = QGroupBox("Options")
        layout = QVBoxLayout(group)

        # Legacy compat
        self.content_type_combo = None
        self._content_type_group = None

        # Content Rating (if host defines content_types)
        if self.config.content_types:
            content_rating_label = QLabel("<b>Content Rating</b>")
            layout.addWidget(content_rating_label)

            self._content_type_group = QButtonGroup(self)
            saved_content_type = get_image_host_setting(self.host_id, 'content_type', 'str')
            first_radio = None
            for ct in self.config.content_types:
                radio = QRadioButton(ct['label'])
                radio.setProperty("content_type_id", ct['id'])
                self._content_type_group.addButton(radio)
                layout.addWidget(radio)
                if first_radio is None:
                    first_radio = radio
                if saved_content_type and ct['id'] == saved_content_type:
                    radio.setChecked(True)
            # Fall back to first option if nothing was saved
            if not saved_content_type and first_radio:
                first_radio.setChecked(True)
            self._content_type_group.buttonClicked.connect(
                lambda _btn: self._mark_modified()
            )

        # IMX: Auto-rename checkbox
        if self.host_id == "imx":
            self.auto_rename_check = QCheckBox("Automatically rename galleries on imx.to")
            self.auto_rename_check.setChecked(
                get_image_host_setting(self.host_id, 'auto_rename', 'bool')
            )
            self.auto_rename_check.toggled.connect(self._mark_modified)
            layout.addWidget(self.auto_rename_check)

        # Pixhost-only additions
        if self.host_id == "pixhost":
            # Auto-finalize with InfoButton
            finalize_row = QHBoxLayout()
            self.auto_finalize_check = QCheckBox("Auto-finalize galleries")
            self.auto_finalize_check.setChecked(
                get_image_host_setting(self.host_id, 'auto_finalize_gallery', 'bool')
            )
            self.auto_finalize_check.toggled.connect(self._mark_modified)
            finalize_row.addWidget(self.auto_finalize_check)
            finalize_row.addWidget(InfoButton(
                "Finalization makes images visible on Pixhost. Without"
                " finalization, uploaded images remain in a draft state"
                " and are not accessible via their URLs.<br><br>"
                "Leave this enabled unless you have a specific reason"
                " to finalize galleries manually."
            ))
            finalize_row.addStretch()
            layout.addLayout(finalize_row)

            # Failed Upload Strategy header with InfoButton
            strategy_header_row = QHBoxLayout()
            strategy_header_label = QLabel("<b>Failed Upload Strategy</b>")
            strategy_header_row.addWidget(strategy_header_label)
            strategy_header_row.addWidget(InfoButton(
                "Pixhost occasionally returns fake &ldquo;success&rdquo;"
                " responses (HTTP 200) for uploads that actually failed."
                " When BBDrop detects this, it needs to decide how to"
                " retry.<br><br>"
                "The trade-off is between bandwidth usage and whether"
                " retried images are included in the gallery&rsquo;s"
                " zip download on Pixhost."
            ))
            strategy_header_row.addStretch()
            layout.addLayout(strategy_header_row)

            self._error_strategy_group = QButtonGroup(self)
            saved_strategy = get_image_host_setting(
                self.host_id, 'error_retry_strategy', 'str'
            ) or 'retry_image'

            # Option 1: Retry image only
            retry_image_radio = QRadioButton("Retry image only")
            retry_image_radio.setProperty("strategy_id", "retry_image")
            self._error_strategy_group.addButton(retry_image_radio)
            layout.addWidget(retry_image_radio)

            retry_image_sublabel = QLabel(
                "Re-uploads just the failed image. Saves bandwidth but the"
                " retried image won&rsquo;t be included in the gallery&rsquo;s"
                " zip download on Pixhost."
            )
            retry_image_sublabel.setWordWrap(True)
            retry_image_sublabel.setProperty("class", "label-credential-note")
            retry_image_sublabel.setContentsMargins(20, 0, 0, 4)
            layout.addWidget(retry_image_sublabel)

            # Option 2: Retry full gallery
            retry_gallery_radio = QRadioButton("Retry full gallery")
            retry_gallery_radio.setProperty("strategy_id", "retry_gallery")
            self._error_strategy_group.addButton(retry_gallery_radio)
            layout.addWidget(retry_gallery_radio)

            retry_gallery_sublabel = QLabel(
                "Re-uploads the entire gallery from scratch. Uses more"
                " bandwidth but keeps all images together in the zip download."
            )
            retry_gallery_sublabel.setWordWrap(True)
            retry_gallery_sublabel.setProperty("class", "label-credential-note")
            retry_gallery_sublabel.setContentsMargins(20, 0, 0, 4)
            layout.addWidget(retry_gallery_sublabel)

            # Select saved value, default to retry_image
            if saved_strategy == "retry_gallery":
                retry_gallery_radio.setChecked(True)
            else:
                retry_image_radio.setChecked(True)

            self._error_strategy_group.buttonClicked.connect(
                lambda _btn: self._mark_modified()
            )

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
        Save credentials and non-credential settings.

        Returns:
            tuple: (old_batch_size, new_batch_size)
        """
        self.save_credentials()
        old_batch = get_image_host_setting(self.host_id, 'parallel_batch_size', 'int')

        save_image_host_setting(self.host_id, 'auto_retry', self.auto_retry_check.isChecked())
        save_image_host_setting(self.host_id, 'max_retries', self.max_retries_spin.value())
        save_image_host_setting(self.host_id, 'parallel_batch_size', self.concurrent_uploads_spin.value())
        save_image_host_setting(self.host_id, 'upload_connect_timeout', self.connect_timeout_spin.value())
        save_image_host_setting(self.host_id, 'upload_read_timeout', self.inactivity_timeout_spin.value())
        save_image_host_setting(self.host_id, 'max_upload_time', self.max_upload_time_spin.value())
        save_image_host_setting(self.host_id, 'max_file_size_mb', self.max_file_size_spin.value())

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
        if self._content_type_group is not None:
            checked = self._content_type_group.checkedButton()
            if checked:
                save_image_host_setting(
                    self.host_id, 'content_type',
                    checked.property("content_type_id")
                )

        if self.host_id == "imx":
            save_image_host_setting(self.host_id, 'auto_rename', self.auto_rename_check.isChecked())
        elif self.host_id == "pixhost":
            save_image_host_setting(self.host_id, 'auto_finalize_gallery', self.auto_finalize_check.isChecked())
            checked_strategy = self._error_strategy_group.checkedButton()
            if checked_strategy:
                save_image_host_setting(
                    self.host_id, 'error_retry_strategy',
                    checked_strategy.property("strategy_id")
                )

        if self._has_cover_gallery:
            save_image_host_setting(self.host_id, 'cover_gallery', self.cover_gallery_edit.text())
            self.cover_gallery_changed.emit(self.host_id, self.cover_gallery_edit.text())

        self._modified = False
        return (old_batch, self.concurrent_uploads_spin.value())

    # ========== CREDENTIAL MANAGEMENT METHODS ==========

    def load_current_credentials(self):
        """Load and populate inline credential fields from keyring."""
        if self.username_input is None:
            return

        # Helper to decrypt and populate a field
        def _populate_field(field, credential_key):
            if field is None:
                return
            encrypted = get_credential(credential_key, self.host_id)
            if encrypted:
                try:
                    value = decrypt_password(encrypted)
                    if value:
                        field.blockSignals(True)
                        field.setText(value)
                        field.blockSignals(False)
                        return
                except Exception:
                    pass

        _populate_field(self.api_key_input, 'api_key')
        _populate_field(self.username_input, 'username')
        _populate_field(self.password_input, 'password')

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

    def get_credentials(self) -> dict:
        """Read current credential values from the inline fields.

        Returns:
            dict: Keys are 'api_key', 'username', 'password' (only for fields
                  that exist on this host). Values are stripped strings.
        """
        creds = {}
        if self.api_key_input is not None:
            creds['api_key'] = self.api_key_input.text().strip()
        if self.username_input is not None:
            creds['username'] = self.username_input.text().strip()
        if self.password_input is not None:
            creds['password'] = self.password_input.text().strip()
        return creds

    def save_credentials(self):
        """Persist credential field values to the OS keyring.

        Non-empty values are encrypted and stored.
        Empty values trigger removal of any previously stored credential.
        """
        creds = self.get_credentials()
        for key in ['api_key', 'username', 'password']:
            if key not in creds:
                continue
            value = creds[key]
            if value:
                set_credential(key, encrypt_password(value), self.host_id)
            else:
                remove_credential(key, self.host_id)

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
        """Start a background credential test using current field values."""
        creds = self.get_credentials()
        credentials = {k: v for k, v in creds.items() if v}

        if not credentials:
            self.test_result_label.setText(
                "<span style='color:orange;'>No credentials entered to test</span>"
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
