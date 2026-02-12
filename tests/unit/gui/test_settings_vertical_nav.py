"""Tests for vertical navigation settings dialog layout."""
import pytest
from unittest.mock import patch, MagicMock


class TestVerticalNavLayout:
    """Settings dialog uses vertical nav instead of horizontal tabs."""

    @patch('src.gui.settings_dialog.load_user_defaults', return_value={})
    @patch('src.gui.settings_dialog.get_config_path', return_value='/tmp/test.ini')
    def test_has_nav_list_and_stack(self, mock_config, mock_defaults):
        """Dialog has nav_list (QListWidget) and stack_widget (QStackedWidget)."""
        from PyQt6.QtWidgets import QApplication, QListWidget, QStackedWidget
        app = QApplication.instance() or QApplication([])

        from src.gui.settings_dialog import ComprehensiveSettingsDialog
        with patch.object(ComprehensiveSettingsDialog, 'load_settings'):
            dialog = ComprehensiveSettingsDialog()

        assert hasattr(dialog, 'nav_list')
        assert hasattr(dialog, 'stack_widget')
        assert isinstance(dialog.nav_list, QListWidget)
        assert isinstance(dialog.stack_widget, QStackedWidget)

    @patch('src.gui.settings_dialog.load_user_defaults', return_value={})
    @patch('src.gui.settings_dialog.get_config_path', return_value='/tmp/test.ini')
    def test_nav_list_count_matches_stack(self, mock_config, mock_defaults):
        """Nav list item count matches stack widget page count."""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        from src.gui.settings_dialog import ComprehensiveSettingsDialog
        with patch.object(ComprehensiveSettingsDialog, 'load_settings'):
            dialog = ComprehensiveSettingsDialog()

        assert dialog.nav_list.count() == dialog.stack_widget.count()
        assert dialog.nav_list.count() >= 8  # At least 8 pages

    @patch('src.gui.settings_dialog.load_user_defaults', return_value={})
    @patch('src.gui.settings_dialog.get_config_path', return_value='/tmp/test.ini')
    def test_no_tab_widget(self, mock_config, mock_defaults):
        """Dialog should NOT have a tab_widget anymore."""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        from src.gui.settings_dialog import ComprehensiveSettingsDialog
        with patch.object(ComprehensiveSettingsDialog, 'load_settings'):
            dialog = ComprehensiveSettingsDialog()

        assert not hasattr(dialog, 'tab_widget')

    @patch('src.gui.settings_dialog.load_user_defaults', return_value={})
    @patch('src.gui.settings_dialog.get_config_path', return_value='/tmp/test.ini')
    def test_selecting_nav_item_changes_stack(self, mock_config, mock_defaults):
        """Clicking a nav list item switches the stack page."""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        from src.gui.settings_dialog import ComprehensiveSettingsDialog
        with patch.object(ComprehensiveSettingsDialog, 'load_settings'):
            dialog = ComprehensiveSettingsDialog()

        # Select second item
        dialog.nav_list.setCurrentRow(1)
        assert dialog.stack_widget.currentIndex() == 1

    @patch('src.gui.settings_dialog.load_user_defaults', return_value={})
    @patch('src.gui.settings_dialog.get_config_path', return_value='/tmp/test.ini')
    def test_nav_list_has_expected_labels(self, mock_config, mock_defaults):
        """Nav list contains expected page labels."""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        from src.gui.settings_dialog import ComprehensiveSettingsDialog
        with patch.object(ComprehensiveSettingsDialog, 'load_settings'):
            dialog = ComprehensiveSettingsDialog()

        labels = [dialog.nav_list.item(i).text() for i in range(dialog.nav_list.count())]
        assert "General" in labels
        assert "Image Hosts" in labels
        assert "Templates" in labels
