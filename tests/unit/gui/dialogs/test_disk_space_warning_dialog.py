"""Tests for the persistent disk space warning dialog."""

import pytest
from unittest.mock import Mock, patch


class FakeLabel:
    """Minimal stand-in for QLabel that tracks text and styleSheet."""

    def __init__(self, *args, **kwargs):
        self._text = ""
        self._stylesheet = ""

    def text(self):
        return self._text

    def setText(self, t):
        self._text = t

    def styleSheet(self):
        return self._stylesheet

    def setStyleSheet(self, s):
        self._stylesheet = s

    def setWordWrap(self, *a):
        pass

    def setFont(self, *a):
        pass

    def setPixmap(self, *a):
        pass


@pytest.fixture
def mock_qt():
    """Patch Qt widgets for headless testing."""
    with patch('src.gui.dialogs.disk_space_warning_dialog.QDialog.__init__'), \
         patch('src.gui.dialogs.disk_space_warning_dialog.QDialog.setWindowTitle'), \
         patch('src.gui.dialogs.disk_space_warning_dialog.QDialog.setMinimumWidth'), \
         patch('src.gui.dialogs.disk_space_warning_dialog.QDialog.setModal'), \
         patch('src.gui.dialogs.disk_space_warning_dialog.QVBoxLayout'), \
         patch('src.gui.dialogs.disk_space_warning_dialog.QHBoxLayout'), \
         patch('src.gui.dialogs.disk_space_warning_dialog.QPushButton'), \
         patch('src.gui.dialogs.disk_space_warning_dialog.QFont'), \
         patch('src.gui.dialogs.disk_space_warning_dialog.QLabel', FakeLabel), \
         patch('src.gui.dialogs.disk_space_warning_dialog.get_icon') as mock_get_icon:
        mock_icon = Mock()
        mock_pixmap = Mock()
        mock_icon.pixmap.return_value = mock_pixmap
        mock_get_icon.return_value = mock_icon
        yield


class TestDiskSpaceWarningDialogInit:
    """Dialog construction and layout."""

    def test_creates_without_error(self, mock_qt):
        from src.gui.dialogs.disk_space_warning_dialog import DiskSpaceWarningDialog
        dialog = DiskSpaceWarningDialog(parent=None)
        assert dialog is not None

    def test_is_non_modal(self, mock_qt):
        from src.gui.dialogs.disk_space_warning_dialog import DiskSpaceWarningDialog
        dialog = DiskSpaceWarningDialog(parent=None)
        dialog.setModal.assert_called_with(False)


class TestUpdateTier:
    """update_tier() changes header, body, and styling."""

    def test_warning_tier_header(self, mock_qt):
        from src.gui.dialogs.disk_space_warning_dialog import DiskSpaceWarningDialog
        dialog = DiskSpaceWarningDialog(parent=None)

        dialog.update_tier("warning", "1.5 GiB")

        assert "Low Disk Space" in dialog._header_label.text()

    def test_critical_tier_header(self, mock_qt):
        from src.gui.dialogs.disk_space_warning_dialog import DiskSpaceWarningDialog
        dialog = DiskSpaceWarningDialog(parent=None)

        dialog.update_tier("critical", "400 MiB")

        assert "Critically Low" in dialog._header_label.text()

    def test_emergency_tier_header(self, mock_qt):
        from src.gui.dialogs.disk_space_warning_dialog import DiskSpaceWarningDialog
        dialog = DiskSpaceWarningDialog(parent=None)

        dialog.update_tier("emergency", "50 MiB")

        assert "Critically Low" in dialog._header_label.text()

    def test_body_includes_free_space(self, mock_qt):
        from src.gui.dialogs.disk_space_warning_dialog import DiskSpaceWarningDialog
        dialog = DiskSpaceWarningDialog(parent=None)

        dialog.update_tier("critical", "400 MiB")

        assert "400 MiB" in dialog._body_label.text()

    def test_warning_uses_orange_style(self, mock_qt):
        from src.gui.dialogs.disk_space_warning_dialog import DiskSpaceWarningDialog
        dialog = DiskSpaceWarningDialog(parent=None)

        dialog.update_tier("warning", "1.5 GiB")

        style = dialog._header_label.styleSheet()
        # Should use warning color (orange/yellow family)
        assert "#f0ad4e" in style.lower() or "orange" in style.lower()

    def test_critical_uses_red_style(self, mock_qt):
        from src.gui.dialogs.disk_space_warning_dialog import DiskSpaceWarningDialog
        dialog = DiskSpaceWarningDialog(parent=None)

        dialog.update_tier("critical", "400 MiB")

        style = dialog._header_label.styleSheet()
        assert "#d9534f" in style.lower() or "red" in style.lower()

    def test_consecutive_updates_change_content(self, mock_qt):
        """Calling update_tier twice should reflect the latest tier."""
        from src.gui.dialogs.disk_space_warning_dialog import DiskSpaceWarningDialog
        dialog = DiskSpaceWarningDialog(parent=None)

        dialog.update_tier("warning", "1.5 GiB")
        assert "Low Disk Space" in dialog._header_label.text()

        dialog.update_tier("critical", "400 MiB")
        assert "Critically Low" in dialog._header_label.text()
        assert "400 MiB" in dialog._body_label.text()
