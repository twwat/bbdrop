#!/usr/bin/env python3
"""
pytest-qt tests for ComprehensiveSettingsDialog
Tests settings dialog functionality and configuration management
"""

import pytest
from unittest.mock import patch, Mock, MagicMock
from PyQt6.QtWidgets import QDialog, QTabWidget

from src.gui.settings_dialog import ComprehensiveSettingsDialog


class TestSettingsDialogInit:
    """Test ComprehensiveSettingsDialog initialization"""

    @patch('src.gui.settings_dialog.load_user_defaults')
    def test_settings_dialog_creates(self, mock_load, qtbot, mock_config_file, mock_bbdrop_functions):
        """Test ComprehensiveSettingsDialog instantiation"""
        mock_load.return_value = {}

        with patch('src.gui.settings_dialog.get_config_path', return_value=str(mock_config_file.parent)):
            dialog = ComprehensiveSettingsDialog()
            qtbot.addWidget(dialog)

            assert dialog is not None
            assert isinstance(dialog, QDialog)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
