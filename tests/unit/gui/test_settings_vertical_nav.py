"""Tests for vertical navigation settings dialog layout."""
from unittest.mock import patch
from PyQt6.QtWidgets import QListWidget, QStackedWidget

from src.gui.settings import ComprehensiveSettingsDialog


class TestVerticalNavLayout:
    """Settings dialog uses vertical nav instead of horizontal tabs."""

    def test_has_nav_list_and_stack(self, qtbot):
        """Dialog has nav_list (QListWidget) and stack_widget (QStackedWidget)."""
        with patch.object(ComprehensiveSettingsDialog, 'load_settings'):
            dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        assert hasattr(dialog, 'nav_list')
        assert hasattr(dialog, 'stack_widget')
        assert isinstance(dialog.nav_list, QListWidget)
        assert isinstance(dialog.stack_widget, QStackedWidget)

    def test_nav_list_count_matches_stack(self, qtbot):
        """Nav list item count matches stack widget page count."""
        with patch.object(ComprehensiveSettingsDialog, 'load_settings'):
            dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        assert dialog.nav_list.count() == dialog.stack_widget.count()
        assert dialog.nav_list.count() >= 8  # At least 8 pages

    def test_no_tab_widget(self, qtbot):
        """Dialog should NOT have a tab_widget anymore."""
        with patch.object(ComprehensiveSettingsDialog, 'load_settings'):
            dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        assert not hasattr(dialog, 'tab_widget')

    def test_selecting_nav_item_changes_stack(self, qtbot):
        """Clicking a nav list item switches the stack page."""
        with patch.object(ComprehensiveSettingsDialog, 'load_settings'):
            dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        # Select second item
        dialog.nav_list.setCurrentRow(1)
        assert dialog.stack_widget.currentIndex() == 1

    def test_nav_list_has_expected_labels(self, qtbot):
        """Nav list contains expected page labels."""
        with patch.object(ComprehensiveSettingsDialog, 'load_settings'):
            dialog = ComprehensiveSettingsDialog()
        qtbot.addWidget(dialog)

        labels = [dialog.nav_list.item(i).text() for i in range(dialog.nav_list.count())]
        assert "General" in labels
        assert "Image Hosts" in labels
        assert "BBCode templates" in labels
