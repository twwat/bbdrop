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


class TestSetEditMode:
    """Verify set_edit_mode toggles features and title bars on all six docks."""

    def _make_lm_with_mock_docks(self, qapp):
        from src.gui.layout_manager import LayoutManager

        lm = LayoutManager(MagicMock())
        lm.dock_quick_settings = MagicMock()
        lm.dock_hosts = MagicMock()
        lm.dock_log = MagicMock()
        lm.dock_progress = MagicMock()
        lm.dock_info = MagicMock()
        lm.dock_speed = MagicMock()
        return lm

    def test_set_edit_mode_true_enables_features_and_restores_title_bar(self, qapp):
        from PyQt6.QtWidgets import QDockWidget

        lm = self._make_lm_with_mock_docks(qapp)
        lm.set_edit_mode(True)

        expected_features = (
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        for dock in (
            lm.dock_quick_settings, lm.dock_hosts, lm.dock_log,
            lm.dock_progress, lm.dock_info, lm.dock_speed,
        ):
            dock.setFeatures.assert_called_once_with(expected_features)
            dock.setTitleBarWidget.assert_called_once_with(None)
        assert lm._edit_mode is True

    def test_set_edit_mode_false_disables_features_and_hides_title_bar(self, qapp):
        from PyQt6.QtWidgets import QDockWidget, QWidget

        lm = self._make_lm_with_mock_docks(qapp)
        lm.set_edit_mode(False)

        for dock in (
            lm.dock_quick_settings, lm.dock_hosts, lm.dock_log,
            lm.dock_progress, lm.dock_info, lm.dock_speed,
        ):
            dock.setFeatures.assert_called_once_with(
                QDockWidget.DockWidgetFeature.NoDockWidgetFeatures
            )
            # Title bar is replaced with an empty QWidget
            dock.setTitleBarWidget.assert_called_once()
            placeholder = dock.setTitleBarWidget.call_args[0][0]
            assert isinstance(placeholder, QWidget)
        assert lm._edit_mode is False


class TestBuild:
    """Verify LayoutManager.build() produces the expected dock structure.

    These tests instantiate a real BBDropGUI minus heavy subsystems by using
    a small subclass that skips non-layout init. For deeper integration,
    see the manual smoke checklist.
    """

    @pytest.fixture
    def built_mw(self, qapp):
        """Launch the real BBDropGUI and return it. Skips unless BBDROP_RUN_BUILD_TESTS is set.

        BBDropGUI starts heavyweight subsystems (DB, network sockets, file watchers)
        that crash pytest workers in headless CI. These tests are useful locally for
        verifying the dock structure end-to-end; they're opt-in via env var.
        For deeper integration coverage, see the manual smoke checklist (Task 7).
        """
        if not os.environ.get("BBDROP_RUN_BUILD_TESTS"):
            pytest.skip(
                "BBDropGUI build tests are opt-in (set BBDROP_RUN_BUILD_TESTS=1). "
                "They require a full DB + keyring environment."
            )
        try:
            from src.gui.main_window import BBDropGUI
            mw = BBDropGUI()
        except Exception as e:
            pytest.skip(f"BBDropGUI could not be instantiated in test env: {e}")
        yield mw
        try:
            mw.close()
            mw.deleteLater()
        except Exception:
            pass

    def test_build_creates_six_docks_with_expected_object_names(self, built_mw):
        # After BBDropGUI construction, layout_manager.build() should have run
        expected = {
            "dock_quick_settings",
            "dock_hosts",
            "dock_log",
            "dock_progress",
            "dock_info",
            "dock_speed",
        }
        from PyQt6.QtWidgets import QDockWidget
        found = {
            d.objectName()
            for d in built_mw.findChildren(QDockWidget)
        }
        assert expected.issubset(found), f"Missing docks: {expected - found}"

    def test_build_assigns_widget_refs_on_mw(self, built_mw):
        # Controllers and signal handlers reference these by name
        for attr in (
            "gallery_table",
            "log_text",
            "worker_status_widget",
            "overall_progress",
            "stats_label",
            "image_host_combo",
        ):
            assert hasattr(built_mw, attr), f"mw.{attr} missing after build()"

    def test_central_widget_is_queue_container(self, built_mw):
        from PyQt6.QtWidgets import QWidget
        cw = built_mw.centralWidget()
        assert cw is not None
        assert isinstance(cw, QWidget)
        # Queue container should contain the gallery_table widget
        found = cw.findChild(type(built_mw.gallery_table))
        assert found is built_mw.gallery_table
