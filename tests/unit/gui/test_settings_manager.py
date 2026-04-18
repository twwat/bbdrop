"""Unit tests for src/gui/settings_manager.py layout persistence."""

import os
import pytest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QByteArray
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestLayoutStatePersistence:
    """Verify layout/state QSettings save and restore."""

    def _make_mw(self):
        mw = MagicMock()
        mw.settings = MagicMock()
        mw.saveState.return_value = QByteArray(b"example_state")
        mw.saveGeometry.return_value = QByteArray(b"example_geometry")
        mw.layout_manager = MagicMock()
        return mw

    def test_save_settings_writes_layout_state(self, qapp):
        from src.gui.settings_manager import SettingsManager

        mw = self._make_mw()
        sm = SettingsManager(mw)
        # Bypass table settings saving which requires a gallery_table
        with patch.object(sm, "save_table_settings"):
            sm.save_settings()

        # Verify settings.setValue was called with "layout/state" and the saveState bytes
        calls = mw.settings.setValue.call_args_list
        layout_calls = [c for c in calls if c.args and c.args[0] == "layout/state"]
        assert len(layout_calls) == 1
        assert bytes(layout_calls[0].args[1]) == b"example_state"

    def test_restore_settings_applies_saved_state(self, qapp):
        from src.gui.settings_manager import SettingsManager

        mw = self._make_mw()
        # Return saved state for layout/state key, None for others
        def settings_value(key, default=None, type=None):
            if key == "layout/state":
                return QByteArray(b"saved_state")
            return default
        mw.settings.value.side_effect = settings_value
        mw.restoreState.return_value = True

        sm = SettingsManager(mw)
        with patch.object(sm, "restore_table_settings"):
            sm.restore_settings()

        assert mw.restoreState.called
        call_arg = mw.restoreState.call_args[0][0]
        assert bytes(call_arg) == b"saved_state"
        # Classic fallback should NOT be invoked when state restores successfully
        mw.layout_manager.apply_preset.assert_not_called()

    def test_restore_settings_falls_back_to_classic_when_missing(self, qapp):
        from src.gui.settings_manager import SettingsManager

        mw = self._make_mw()
        mw.settings.value.return_value = None  # no saved state

        sm = SettingsManager(mw)
        with patch.object(sm, "restore_table_settings"):
            sm.restore_settings()

        mw.layout_manager.apply_preset.assert_called_once_with("classic")

    def test_restore_settings_falls_back_when_restore_state_returns_false(self, qapp):
        from src.gui.settings_manager import SettingsManager

        mw = self._make_mw()
        mw.settings.value.return_value = QByteArray(b"corrupt")
        mw.restoreState.return_value = False  # Qt rejected the state

        sm = SettingsManager(mw)
        with patch.object(sm, "restore_table_settings"):
            sm.restore_settings()

        mw.layout_manager.apply_preset.assert_called_once_with("classic")
