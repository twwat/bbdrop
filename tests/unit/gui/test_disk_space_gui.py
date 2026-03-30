"""Tests for disk space GUI integration — status bar and dialog."""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestDiskStatusBar:
    """Status bar label updates based on monitor signals."""

    def test_ok_tier_clears_style(self):
        """Verify _on_disk_tier_changed clears style for ok tier."""
        from src.gui.main_window import BBDropGUI
        mw = Mock(spec=BBDropGUI)
        mw.disk_status_label = Mock()
        mw._disk_warning_dialog = None

        BBDropGUI._on_disk_tier_changed(mw, "ok")
        mw.disk_status_label.setStyleSheet.assert_called_with("")

    def test_ok_tier_hides_dialog_if_visible(self):
        """When tier returns to ok, hide the dialog if it exists."""
        from src.gui.main_window import BBDropGUI
        mw = Mock(spec=BBDropGUI)
        mw.disk_status_label = Mock()
        mw._disk_warning_dialog = Mock()
        mw._disk_warning_dialog.isVisible.return_value = True

        BBDropGUI._on_disk_tier_changed(mw, "ok")
        mw._disk_warning_dialog.hide.assert_called_once()

    def test_warning_tier_shows_yellow(self):
        from src.gui.main_window import BBDropGUI
        mw = Mock(spec=BBDropGUI)
        mw.disk_status_label = Mock()
        mw._disk_warning_dialog = None

        BBDropGUI._on_disk_tier_changed(mw, "warning")
        call_args = mw.disk_status_label.setStyleSheet.call_args[0][0]
        assert "#f0ad4e" in call_args

    def test_critical_tier_shows_red(self):
        from src.gui.main_window import BBDropGUI
        mw = Mock(spec=BBDropGUI)
        mw.disk_status_label = Mock()
        mw._disk_warning_dialog = None
        mw._disk_monitor = Mock()
        mw._disk_monitor.data_free = 300_000_000
        mw._disk_monitor.temp_free = 300_000_000

        BBDropGUI._on_disk_tier_changed(mw, "critical")
        call_args = mw.disk_status_label.setStyleSheet.call_args[0][0]
        assert "#d9534f" in call_args

    def test_critical_tier_creates_dialog_on_first_call(self):
        """First critical tier should create the dialog instance."""
        from src.gui.main_window import BBDropGUI
        mw = Mock(spec=BBDropGUI)
        mw.disk_status_label = Mock()
        mw._disk_warning_dialog = None
        mw._disk_monitor = Mock()
        mw._disk_monitor.data_free = 300_000_000
        mw._disk_monitor.temp_free = 300_000_000
        mw.isVisible.return_value = True

        with patch('src.gui.dialogs.disk_space_warning_dialog.DiskSpaceWarningDialog') as MockDialog:
            mock_instance = Mock()
            MockDialog.return_value = mock_instance

            BBDropGUI._show_disk_warning_dialog(mw, "critical")

            MockDialog.assert_called_once_with(parent=mw)
            mock_instance.update_tier.assert_called_once()
            mock_instance.show.assert_called_once()

    def test_subsequent_calls_reuse_dialog(self):
        """Second call should reuse existing dialog, not create a new one."""
        from src.gui.main_window import BBDropGUI
        mw = Mock(spec=BBDropGUI)
        mw.disk_status_label = Mock()
        mw._disk_monitor = Mock()
        mw._disk_monitor.data_free = 300_000_000
        mw._disk_monitor.temp_free = 300_000_000
        mw.isVisible.return_value = True

        existing_dialog = Mock()
        mw._disk_warning_dialog = existing_dialog

        with patch('src.gui.dialogs.disk_space_warning_dialog.DiskSpaceWarningDialog') as MockDialog:
            BBDropGUI._show_disk_warning_dialog(mw, "emergency")

            MockDialog.assert_not_called()  # Should NOT create new
            existing_dialog.update_tier.assert_called_once()
            existing_dialog.show.assert_called_once()
            existing_dialog.raise_.assert_called_once()


class TestDiskSpaceFormatting:
    """space_updated signal formats free space in the label."""

    def test_gb_formatting(self):
        from src.gui.main_window import BBDropGUI
        mw = Mock(spec=BBDropGUI)
        mw.disk_status_label = Mock()
        mw._disk_monitor = Mock()
        mw._disk_monitor._same_device = True

        BBDropGUI._on_disk_space_updated(mw, 5_368_709_120, 5_368_709_120)  # 5 GB
        label_text = mw.disk_status_label.setText.call_args[0][0]
        assert "5" in label_text
        assert "GiB" in label_text or "gib" in label_text.lower()
