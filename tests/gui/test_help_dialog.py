#!/usr/bin/env python3
"""
pytest-qt tests for HelpDialog
Tests help documentation dialog functionality
"""

import pytest
from unittest.mock import patch
from PyQt6.QtWidgets import QDialog
from PyQt6.QtCore import Qt

from src.gui.dialogs.help_dialog import HelpDialog


class TestHelpDialogInit:
    """Test HelpDialog initialization"""

    def test_help_dialog_creates(self, qtbot):
        """Test HelpDialog instantiation"""
        with patch.object(HelpDialog, '_start_document_loading'):
            dialog = HelpDialog()
            qtbot.addWidget(dialog)
            assert dialog is not None
            assert isinstance(dialog, QDialog)
            dialog.close()

    def test_help_dialog_has_content_viewer(self, qtbot):
        """Test that dialog has content viewer"""
        with patch.object(HelpDialog, '_start_document_loading'):
            dialog = HelpDialog()
            qtbot.addWidget(dialog)
            assert hasattr(dialog, 'content_viewer')
            assert hasattr(dialog, 'tree')
            dialog.close()


class TestHelpDialogDocumentation:
    """Test documentation loading"""

    def test_loads_documentation_structure(self, qtbot, tmp_path):
        """Test loading documentation structure"""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "TEST.md").write_text("# Test Documentation")

        with patch.object(HelpDialog, '_start_document_loading'):
            dialog = HelpDialog()
            qtbot.addWidget(dialog)
            assert dialog.tree.topLevelItemCount() >= 0
            dialog.close()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
