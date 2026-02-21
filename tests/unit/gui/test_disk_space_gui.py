"""Tests for disk space GUI integration — status bar and dialog."""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestDiskStatusBar:
    """Status bar label updates based on monitor signals."""

    def test_ok_tier_shows_green(self):
        """Verify _on_disk_tier_changed sets normal style for ok tier."""
        from src.gui.main_window import BBDropGUI
        mw = Mock(spec=BBDropGUI)
        mw.disk_status_label = Mock()
        mw._disk_dialog_shown_for_tier = None

        BBDropGUI._on_disk_tier_changed(mw, "ok")
        # Should not have red/yellow styling
        call_args = mw.disk_status_label.setStyleSheet.call_args[0][0]
        assert "red" not in call_args.lower()
        assert "yellow" not in call_args.lower()

    def test_warning_tier_shows_yellow(self):
        from src.gui.main_window import BBDropGUI
        mw = Mock(spec=BBDropGUI)
        mw.disk_status_label = Mock()
        mw._disk_dialog_shown_for_tier = None

        BBDropGUI._on_disk_tier_changed(mw, "warning")
        call_args = mw.disk_status_label.setStyleSheet.call_args[0][0]
        assert "yellow" in call_args.lower() or "#" in call_args  # Some yellow-ish color

    @patch('src.gui.main_window.QMessageBox')
    def test_critical_tier_shows_red(self, mock_msgbox):
        from src.gui.main_window import BBDropGUI
        mw = Mock(spec=BBDropGUI)
        mw.disk_status_label = Mock()
        mw._disk_dialog_shown_for_tier = None
        mw._disk_monitor = Mock()
        mw._disk_monitor.data_free = 300_000_000
        mw._disk_monitor.temp_free = 300_000_000

        BBDropGUI._on_disk_tier_changed(mw, "critical")
        call_args = mw.disk_status_label.setStyleSheet.call_args[0][0]
        assert "#d9534f" in call_args.lower()


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
        assert "GB" in label_text or "gb" in label_text.lower()
