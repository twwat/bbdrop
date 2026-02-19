#!/usr/bin/env python3
"""
pytest-qt tests for TabManager
Tests tab management, preferences, and database coordination
"""

import pytest

from src.gui.tab_manager import TabManager, TabPreferences


class TestTabManagerInit:
    """Test TabManager initialization"""

    def test_tab_manager_creates_successfully(self, mock_queue_store, mock_qsettings):
        """Test that TabManager instantiates correctly"""
        manager = TabManager(mock_queue_store)

        assert manager is not None
        assert manager._store == mock_queue_store

    def test_tab_manager_loads_preferences(self, mock_queue_store, mock_qsettings):
        """Test that preferences are loaded on init"""
        manager = TabManager(mock_queue_store)

        assert hasattr(manager, '_preferences')
        assert isinstance(manager._preferences, TabPreferences)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
