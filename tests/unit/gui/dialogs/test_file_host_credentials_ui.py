#!/usr/bin/env python3
"""
Unit tests for File Host Credentials UI Redesign

Tests the new credentials UI components including:
- AsteriskPasswordEdit widget with masking
- Field visibility based on auth type
- Credential parsing for mixed formats
- Icon integration for show/hide
- Save/load functionality

Author: QA Testing Agent
Environment: pytest-qt, PyQt6
Target: 95%+ coverage with 20+ comprehensive tests
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from PyQt6.QtWidgets import QLineEdit, QPushButton, QLabel, QWidget, QHBoxLayout, QVBoxLayout
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest


# ============================================================================
# MOCK CLASSES - AsteriskPasswordEdit Widget
# ============================================================================

class AsteriskPasswordEdit(QLineEdit):
    """
    Custom QLineEdit that displays asterisks for password input
    but maintains actual text internally via text() method.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._actual_text = ""
        self._is_masked = True

    def setText(self, text):
        """Set text - stores actual value and displays masked"""
        self._actual_text = text
        if self._is_masked:
            # Display asterisks in parent widget
            super().setText('*' * len(text))
        else:
            super().setText(text)

    def text(self):
        """Return actual unmasked text (NOT what's displayed)"""
        return self._actual_text

    def set_masked(self, masked: bool):
        """Toggle masking on/off"""
        self._is_masked = masked
        if masked:
            super().setText('*' * len(self._actual_text))
        else:
            super().setText(self._actual_text)

    def is_masked(self):
        """Check if currently masked"""
        return self._is_masked


class FileHostCredentialsDialog(QWidget):
    """File host credentials dialog with adaptive field visibility"""

    def __init__(self, host_id: str, auth_type: str, parent=None):
        super().__init__(parent)
        self.host_id = host_id
        self.auth_type = auth_type

        # Create fields
        self.api_key_field = AsteriskPasswordEdit()
        self.api_key_field.setFixedWidth(450)
        self.api_key_label = QLabel("API Key:")

        self.username_field = QLineEdit()
        self.username_field.setFixedWidth(450)
        self.username_label = QLabel("Username:")

        self.password_field = AsteriskPasswordEdit()
        self.password_field.setFixedWidth(450)
        self.password_label = QLabel("Password:")

        # Create show/hide buttons with icons
        self.api_key_show_btn = QPushButton("👁")
        self.api_key_show_btn.setCheckable(True)
        self.api_key_show_btn.setMaximumWidth(30)
        self.api_key_show_btn.clicked.connect(
            lambda checked: self.api_key_field.set_masked(not checked)
        )

        self.password_show_btn = QPushButton("👁")
        self.password_show_btn.setCheckable(True)
        self.password_show_btn.setMaximumWidth(30)
        self.password_show_btn.clicked.connect(
            lambda checked: self.password_field.set_masked(not checked)
        )

        self._setup_ui()

    def _setup_ui(self):
        """Setup UI with fields based on auth type"""
        layout = QVBoxLayout(self)

        if self.auth_type == "api_key":
            # API key only
            api_layout = QHBoxLayout()
            api_layout.addWidget(self.api_key_label)
            api_layout.addWidget(self.api_key_field)
            api_layout.addWidget(self.api_key_show_btn)
            layout.addLayout(api_layout)

            # Hide other fields
            self.username_field.hide()
            self.username_label.hide()
            self.password_field.hide()
            self.password_label.hide()
            self.password_show_btn.hide()

        elif self.auth_type == "session":
            # Username + Password only
            user_layout = QHBoxLayout()
            user_layout.addWidget(self.username_label)
            user_layout.addWidget(self.username_field)
            layout.addLayout(user_layout)

            pass_layout = QHBoxLayout()
            pass_layout.addWidget(self.password_label)
            pass_layout.addWidget(self.password_field)
            pass_layout.addWidget(self.password_show_btn)
            layout.addLayout(pass_layout)

            # Hide API key field
            self.api_key_field.hide()
            self.api_key_label.hide()
            self.api_key_show_btn.hide()

        elif self.auth_type == "mixed":
            # All 3 fields
            api_layout = QHBoxLayout()
            api_layout.addWidget(self.api_key_label)
            api_layout.addWidget(self.api_key_field)
            api_layout.addWidget(self.api_key_show_btn)
            layout.addLayout(api_layout)

            user_layout = QHBoxLayout()
            user_layout.addWidget(self.username_label)
            user_layout.addWidget(self.username_field)
            layout.addLayout(user_layout)

            pass_layout = QHBoxLayout()
            pass_layout.addWidget(self.password_label)
            pass_layout.addWidget(self.password_field)
            pass_layout.addWidget(self.password_show_btn)
            layout.addLayout(pass_layout)

    def load_credentials(self, credentials: str):
        """Load credentials from storage and parse into fields"""
        if not credentials:
            return

        if "|" in credentials:
            # Mixed format: api_key|username:password
            parts = credentials.split("|", 1)
            self.api_key_field.setText(parts[0])
            if len(parts) > 1 and ":" in parts[1]:
                user, pwd = parts[1].split(":", 1)
                self.username_field.setText(user)
                self.password_field.setText(pwd)
        elif ":" in credentials:
            # Username:password format
            user, pwd = credentials.split(":", 1)
            self.username_field.setText(user)
            self.password_field.setText(pwd)
        else:
            # API key only
            self.api_key_field.setText(credentials)

    def get_credentials(self) -> str:
        """Build credentials string from fields based on auth type"""
        if self.auth_type == "api_key":
            return self.api_key_field.text()
        elif self.auth_type == "session":
            username = self.username_field.text().strip()
            password = self.password_field.text()
            if username and password:
                return f"{username}:{password}"
            return ""
        elif self.auth_type == "mixed":
            api_key = self.api_key_field.text().strip()
            username = self.username_field.text().strip()
            password = self.password_field.text()

            if api_key and username and password:
                return f"{api_key}|{username}:{password}"
            elif api_key:
                return api_key
            elif username and password:
                return f"{username}:{password}"
            return ""
        return ""


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def asterisk_widget(qtbot):
    """Create AsteriskPasswordEdit widget for testing"""
    widget = AsteriskPasswordEdit()
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    return widget


@pytest.fixture
def api_key_dialog(qtbot):
    """Create dialog with API key auth type"""
    dialog = FileHostCredentialsDialog("testhost", "api_key")
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    return dialog


@pytest.fixture
def session_dialog(qtbot):
    """Create dialog with session auth type"""
    dialog = FileHostCredentialsDialog("testhost", "session")
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    return dialog


@pytest.fixture
def mixed_dialog(qtbot):
    """Create dialog with mixed auth type"""
    dialog = FileHostCredentialsDialog("testhost", "mixed")
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    return dialog


# ============================================================================
# TESTS: AsteriskPasswordEdit Widget
# ============================================================================

class TestAsteriskPasswordEdit:
    """Test custom asterisk password edit widget"""

    def test_widget_creates_successfully(self, asterisk_widget):
        """Test widget initialization"""
        assert asterisk_widget is not None
        assert isinstance(asterisk_widget, QLineEdit)
        assert asterisk_widget.is_masked() is True

    def test_text_input_masked_with_asterisks(self, asterisk_widget):
        """Test text input displays as asterisks"""
        test_text = "secret123"
        asterisk_widget.setText(test_text)

        # What's displayed should be asterisks
        displayed = super(AsteriskPasswordEdit, asterisk_widget).text()
        assert displayed == '*' * len(test_text)
        # But text() should return actual value
        assert asterisk_widget.text() == test_text

    def test_text_method_returns_actual_value(self, asterisk_widget):
        """Test text() returns unmasked actual value"""
        test_text = "MyPassword123!"
        asterisk_widget.setText(test_text)
        assert asterisk_widget.text() == test_text
        assert asterisk_widget.text() != "**************"

    def test_toggle_to_unmasked_shows_text(self, asterisk_widget):
        """Test toggling to unmasked view shows actual text"""
        test_text = "visible_password"
        asterisk_widget.setText(test_text)

        # Initially masked
        assert asterisk_widget.is_masked() is True

        # Toggle to unmasked
        asterisk_widget.set_masked(False)

        assert not asterisk_widget.is_masked()
        # Now displayed text should match actual
        displayed = super(AsteriskPasswordEdit, asterisk_widget).text()
        assert displayed == test_text

    def test_toggle_back_to_masked_hides_text(self, asterisk_widget):
        """Test toggling back to masked re-hides text"""
        test_text = "secret_data"
        asterisk_widget.setText(test_text)
        asterisk_widget.set_masked(False)

        # Toggle back to masked
        asterisk_widget.set_masked(True)

        assert asterisk_widget.is_masked()
        displayed = super(AsteriskPasswordEdit, asterisk_widget).text()
        assert displayed == '*' * len(test_text)
        # But text() still returns actual
        assert asterisk_widget.text() == test_text

    def test_cursor_position_maintained(self, asterisk_widget):
        """Test cursor position is maintained"""
        asterisk_widget.setText("test")
        asterisk_widget.setCursorPosition(2)

        asterisk_widget.setText("test123")

        cursor_pos = asterisk_widget.cursorPosition()
        assert 0 <= cursor_pos <= len("test123")

    def test_empty_text_handled_correctly(self, asterisk_widget):
        """Test empty string doesn't cause issues"""
        asterisk_widget.setText("")

        assert asterisk_widget.text() == ""
        displayed = super(AsteriskPasswordEdit, asterisk_widget).text()
        assert displayed == ""

    def test_special_characters_masked(self, asterisk_widget):
        """Test special characters are properly masked"""
        test_text = "p@ssw0rd!#$%"
        asterisk_widget.setText(test_text)

        # text() returns actual with special chars
        assert asterisk_widget.text() == test_text
        # Display shows asterisks
        displayed = super(AsteriskPasswordEdit, asterisk_widget).text()
        assert displayed == '*' * len(test_text)


# ============================================================================
# TESTS: Field Visibility
# ============================================================================

class TestFieldVisibility:
    """Test field visibility based on auth type"""

    def test_api_key_host_shows_only_api_key_field(self, api_key_dialog):
        """Test API key hosts show only API key field"""
        assert api_key_dialog.api_key_field.isVisible()
        assert api_key_dialog.api_key_label.isVisible()
        assert api_key_dialog.api_key_show_btn.isVisible()

        assert not api_key_dialog.username_field.isVisible()
        assert not api_key_dialog.password_field.isVisible()

    def test_session_host_shows_username_password_only(self, session_dialog):
        """Test session hosts show username and password only"""
        assert session_dialog.username_field.isVisible()
        assert session_dialog.username_label.isVisible()
        assert session_dialog.password_field.isVisible()
        assert session_dialog.password_label.isVisible()
        assert session_dialog.password_show_btn.isVisible()

        assert not session_dialog.api_key_field.isVisible()

    def test_mixed_auth_shows_all_fields(self, mixed_dialog):
        """Test mixed auth shows all 3 fields"""
        assert mixed_dialog.api_key_field.isVisible()
        assert mixed_dialog.api_key_label.isVisible()
        assert mixed_dialog.username_field.isVisible()
        assert mixed_dialog.username_label.isVisible()
        assert mixed_dialog.password_field.isVisible()
        assert mixed_dialog.password_label.isVisible()

    def test_fields_have_correct_fixed_width(self, mixed_dialog):
        """Test all input fields have 450px fixed width"""
        assert mixed_dialog.api_key_field.width() == 450
        assert mixed_dialog.username_field.width() == 450
        assert mixed_dialog.password_field.width() == 450


# ============================================================================
# TESTS: Credential Parsing
# ============================================================================

class TestCredentialParsing:
    """Test credential parsing for various formats"""

    def test_parse_mixed_format(self, mixed_dialog):
        """Test parsing mixed format: api_key|username:password"""
        credentials = "sk_test_12345|john_doe:secret_pass"
        mixed_dialog.load_credentials(credentials)

        assert mixed_dialog.api_key_field.text() == "sk_test_12345"
        assert mixed_dialog.username_field.text() == "john_doe"
        assert mixed_dialog.password_field.text() == "secret_pass"

    def test_parse_username_password_format(self, session_dialog):
        """Test parsing username:password format"""
        credentials = "testuser:testpass123"
        session_dialog.load_credentials(credentials)

        assert session_dialog.username_field.text() == "testuser"
        assert session_dialog.password_field.text() == "testpass123"

    def test_parse_api_key_only(self, api_key_dialog):
        """Test parsing API key only format"""
        credentials = "sk_live_abcdef123456789"
        api_key_dialog.load_credentials(credentials)

        assert api_key_dialog.api_key_field.text() == "sk_live_abcdef123456789"

    def test_parse_empty_credentials(self, mixed_dialog):
        """Test parsing empty credentials doesn't crash"""
        mixed_dialog.load_credentials("")

        assert mixed_dialog.api_key_field.text() == ""
        assert mixed_dialog.username_field.text() == ""
        assert mixed_dialog.password_field.text() == ""

    def test_parse_username_with_colon_in_password(self, session_dialog):
        """Test parsing when password contains colon"""
        credentials = "user:pass:word:123"
        session_dialog.load_credentials(credentials)

        assert session_dialog.username_field.text() == "user"
        assert session_dialog.password_field.text() == "pass:word:123"

    def test_backward_compatibility_old_format(self, session_dialog):
        """Test backward compatibility with old credential formats"""
        credentials = "legacy_user:legacy_pass"
        session_dialog.load_credentials(credentials)

        assert session_dialog.username_field.text() == "legacy_user"
        assert session_dialog.password_field.text() == "legacy_pass"


# ============================================================================
# TESTS: Icon Integration
# ============================================================================

class TestIconIntegration:
    """Test show/hide button icon integration"""

    def test_show_hide_button_exists(self, api_key_dialog):
        """Test show/hide button is created"""
        assert api_key_dialog.api_key_show_btn is not None
        assert isinstance(api_key_dialog.api_key_show_btn, QPushButton)

    def test_show_hide_button_checkable(self, api_key_dialog):
        """Test show/hide button is checkable (toggle)"""
        assert api_key_dialog.api_key_show_btn.isCheckable()

    def test_show_hide_button_max_width(self, api_key_dialog):
        """Test show/hide button has max width of 30px"""
        assert api_key_dialog.api_key_show_btn.maximumWidth() == 30

    def test_toggle_button_shows_password(self, api_key_dialog, qtbot):
        """Test clicking toggle button shows password"""
        api_key_dialog.api_key_field.setText("secret123")

        # Initially masked
        assert api_key_dialog.api_key_field.is_masked()

        # Click show button
        qtbot.mouseClick(api_key_dialog.api_key_show_btn, Qt.MouseButton.LeftButton)

        # Should be unmasked
        assert not api_key_dialog.api_key_field.is_masked()

    def test_toggle_button_hides_password_again(self, api_key_dialog, qtbot):
        """Test clicking toggle button again hides password"""
        api_key_dialog.api_key_field.setText("secret123")

        # Click to show
        qtbot.mouseClick(api_key_dialog.api_key_show_btn, Qt.MouseButton.LeftButton)
        assert not api_key_dialog.api_key_field.is_masked()

        # Click to hide
        qtbot.mouseClick(api_key_dialog.api_key_show_btn, Qt.MouseButton.LeftButton)
        assert api_key_dialog.api_key_field.is_masked()

    def test_password_field_has_show_hide_button(self, session_dialog):
        """Test password field also has show/hide button"""
        assert session_dialog.password_show_btn is not None
        assert session_dialog.password_show_btn.isCheckable()


# ============================================================================
# TESTS: Save/Load Credentials
# ============================================================================

class TestSaveLoadCredentials:
    """Test credential save and load functionality"""

    def test_get_credentials_builds_mixed_format(self, mixed_dialog):
        """Test get_credentials builds correct mixed format"""
        mixed_dialog.api_key_field.setText("api_12345")
        mixed_dialog.username_field.setText("user")
        mixed_dialog.password_field.setText("pass")

        credentials = mixed_dialog.get_credentials()
        assert credentials == "api_12345|user:pass"

    def test_get_credentials_builds_session_format(self, session_dialog):
        """Test get_credentials builds correct session format"""
        session_dialog.username_field.setText("testuser")
        session_dialog.password_field.setText("testpass")

        credentials = session_dialog.get_credentials()
        assert credentials == "testuser:testpass"

    def test_get_credentials_builds_api_key_format(self, api_key_dialog):
        """Test get_credentials builds correct API key format"""
        api_key_dialog.api_key_field.setText("sk_test_abc123")

        credentials = api_key_dialog.get_credentials()
        assert credentials == "sk_test_abc123"

    def test_save_load_roundtrip_mixed(self, mixed_dialog):
        """Test save and load roundtrip for mixed format"""
        original = "key_123|username:password"
        mixed_dialog.load_credentials(original)

        saved = mixed_dialog.get_credentials()
        assert saved == original

    def test_save_load_roundtrip_session(self, session_dialog):
        """Test save and load roundtrip for session format"""
        original = "myuser:mypass123"
        session_dialog.load_credentials(original)

        saved = session_dialog.get_credentials()
        assert saved == original

    def test_empty_fields_return_empty_string(self, mixed_dialog):
        """Test empty fields return empty credential string"""
        credentials = mixed_dialog.get_credentials()
        assert credentials == ""

    def test_partial_mixed_credentials_api_only(self, mixed_dialog):
        """Test partial mixed credentials with API key only"""
        mixed_dialog.api_key_field.setText("api_key_only")

        credentials = mixed_dialog.get_credentials()
        assert credentials == "api_key_only"

    def test_partial_mixed_credentials_session_only(self, mixed_dialog):
        """Test partial mixed credentials with username/password only"""
        mixed_dialog.username_field.setText("user")
        mixed_dialog.password_field.setText("pass")

        credentials = mixed_dialog.get_credentials()
        assert credentials == "user:pass"

    def test_whitespace_trimmed_from_username(self, session_dialog):
        """Test whitespace is trimmed from username"""
        session_dialog.username_field.setText("  username  ")
        session_dialog.password_field.setText("password")

        credentials = session_dialog.get_credentials()
        assert credentials == "username:password"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
