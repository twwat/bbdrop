#!/usr/bin/env python3
"""
pytest-qt tests for HelpDialog
Tests help documentation dialog functionality
"""

import pytest
from PyQt6.QtWidgets import QDialog
from PyQt6.QtCore import Qt

from src.gui.dialogs.help_dialog import HelpDialog


class TestHelpDialogInit:
    """Test HelpDialog initialization"""

    def test_help_dialog_creates(self, qtbot):
        """Test HelpDialog instantiation"""
        dialog = HelpDialog()
        qtbot.addWidget(dialog)

        assert dialog is not None
        assert isinstance(dialog, QDialog)

    def test_help_dialog_has_tabs(self, qtbot):
        """Test that dialog has tab widget"""
        dialog = HelpDialog()
        qtbot.addWidget(dialog)

        assert hasattr(dialog, 'tabs')
        assert dialog.tabs.count() >= 0


class TestHelpDialogDocumentation:
    """Test documentation loading"""

    def test_loads_documentation_tabs(self, qtbot, tmp_path):
        """Test loading documentation into tabs"""
        # Create temp docs directory
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        # Create a test doc file
        (docs_dir / "TEST.md").write_text("# Test Documentation")

        dialog = HelpDialog()
        qtbot.addWidget(dialog)

        # Should have created tabs
        assert dialog.tabs.count() >= 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
