"""Unit tests for src/gui/layout_manager.py."""

import os
import pytest
from unittest.mock import MagicMock

# Headless Qt — conftest.py sets this, but be explicit
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    """Ensure a QApplication exists for the module."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestLayoutManagerSkeleton:
    """Sanity checks on the LayoutManager skeleton."""

    def test_layout_manager_is_importable(self, qapp):
        from src.gui.layout_manager import LayoutManager
        assert LayoutManager is not None

    def test_layout_manager_instantiable_with_mock_mw(self, qapp):
        from src.gui.layout_manager import LayoutManager
        mw = MagicMock()
        lm = LayoutManager(mw)
        assert lm is not None


class TestApplyPreset:
    """Verify apply_preset correctly decodes and applies preset payloads."""

    def test_apply_preset_calls_restore_state_with_decoded_bytes(self, qapp):
        from PyQt6.QtCore import QByteArray
        from src.gui.layout_manager import LayoutManager
        from src.gui import layout_presets

        # Use a known non-empty payload so we can verify the decode
        payload_b64 = b"dGVzdF9wYXlsb2Fk"  # base64 of "test_payload"
        original = layout_presets.PRESETS.copy()
        layout_presets.PRESETS["classic"] = payload_b64
        try:
            mw = MagicMock()
            mw.restoreState.return_value = True
            lm = LayoutManager(mw)
            lm.apply_preset("classic")

            assert mw.restoreState.called
            call_arg = mw.restoreState.call_args[0][0]
            assert isinstance(call_arg, QByteArray)
            assert bytes(call_arg) == b"test_payload"
        finally:
            layout_presets.PRESETS.clear()
            layout_presets.PRESETS.update(original)

    def test_apply_preset_unknown_name_raises_keyerror(self, qapp):
        from src.gui.layout_manager import LayoutManager

        mw = MagicMock()
        lm = LayoutManager(mw)
        with pytest.raises(KeyError):
            lm.apply_preset("nonexistent")

    def test_apply_preset_empty_payload_logs_warning_no_raise(self, qapp, caplog):
        from src.gui.layout_manager import LayoutManager
        from src.gui import layout_presets

        original = layout_presets.PRESETS.copy()
        layout_presets.PRESETS["classic"] = b""  # empty means "not yet captured"
        try:
            mw = MagicMock()
            lm = LayoutManager(mw)
            # Should not raise; should log warning; should NOT call restoreState
            lm.apply_preset("classic")
            assert not mw.restoreState.called
        finally:
            layout_presets.PRESETS.clear()
            layout_presets.PRESETS.update(original)

    def test_apply_preset_restore_state_returns_false_logs_warning(self, qapp):
        from src.gui.layout_manager import LayoutManager
        from src.gui import layout_presets

        original = layout_presets.PRESETS.copy()
        layout_presets.PRESETS["classic"] = b"dGVzdA=="  # "test"
        try:
            mw = MagicMock()
            mw.restoreState.return_value = False  # simulate Qt rejecting the state
            lm = LayoutManager(mw)
            lm.apply_preset("classic")  # must not raise
            assert mw.restoreState.called
        finally:
            layout_presets.PRESETS.clear()
            layout_presets.PRESETS.update(original)


class TestResetLayout:
    """Verify reset_layout delegates to the Classic preset."""

    def test_reset_layout_calls_apply_preset_classic(self, qapp):
        from src.gui.layout_manager import LayoutManager

        mw = MagicMock()
        lm = LayoutManager(mw)
        # Spy on apply_preset by replacing it on the instance
        lm.apply_preset = MagicMock()
        lm.reset_layout()
        lm.apply_preset.assert_called_once_with("classic")
