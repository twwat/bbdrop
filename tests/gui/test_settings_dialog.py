#!/usr/bin/env python3
"""
pytest-qt tests for ComprehensiveSettingsDialog
Tests settings dialog functionality and configuration management
"""

import pytest
from unittest.mock import patch
from PyQt6.QtWidgets import QDialog

from src.gui.settings import ComprehensiveSettingsDialog


class TestSettingsDialogInit:
    """Test ComprehensiveSettingsDialog initialization"""

    def test_settings_dialog_creates(self, qtbot, mock_config_file, mock_bbdrop_functions):
        """Test ComprehensiveSettingsDialog instantiation"""
        config_path = str(mock_config_file)

        with patch('src.gui.settings.general_tab.load_user_defaults', return_value={}), \
             patch('src.gui.settings.general_tab.get_config_path', return_value=config_path), \
             patch('src.gui.settings.scanning_tab.get_config_path', return_value=config_path), \
             patch('src.gui.settings.hooks_tab.get_config_path', return_value=config_path), \
             patch.object(ComprehensiveSettingsDialog, 'load_settings'):
            dialog = ComprehensiveSettingsDialog()
            qtbot.addWidget(dialog)

            assert dialog is not None
            assert isinstance(dialog, QDialog)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
