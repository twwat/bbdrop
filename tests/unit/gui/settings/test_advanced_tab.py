"""Tests for AdvancedSettingsWidget — schema-driven settings table."""
import os

# Ensure Qt uses offscreen platform for headless testing
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import patch

import pytest

from src.gui.settings.advanced_tab import (
    ADVANCED_SETTINGS,
    AdvancedSettingsWidget,
)


class TestK2SFamilyDedupInTable:
    """The K2S family dedup toggle must live as a regular row in the
    settings table — not a hand-rolled section above it — and must
    route load/save to the file_host_config helpers because it stores
    in the [FILE_HOSTS] INI section, not [Advanced]."""

    def test_first_row_is_k2s_family_dedup(self):
        assert ADVANCED_SETTINGS[0]["key"] == "file_hosts/k2s_family_dedup"
        assert ADVANCED_SETTINGS[0]["type"] == "bool"
        assert ADVANCED_SETTINGS[0]["backend"] == "file_hosts_section"

    def test_widget_has_no_standalone_checkbox_attr(self, qtbot):
        widget = AdvancedSettingsWidget()
        qtbot.addWidget(widget)
        assert not hasattr(widget, "k2s_family_dedup_checkbox")

    def test_table_includes_dedup_row_at_top(self, qtbot):
        widget = AdvancedSettingsWidget()
        qtbot.addWidget(widget)
        assert widget.table.rowCount() == len(ADVANCED_SETTINGS)
        first_key_item = widget.table.item(0, 0)
        assert first_key_item is not None
        assert first_key_item.text() == "file_hosts/k2s_family_dedup"

    def test_load_from_config_routes_dedup_via_file_host_helper(self, qtbot, tmp_path):
        widget = AdvancedSettingsWidget()
        qtbot.addWidget(widget)

        # Point INI at a temp file so [Advanced] load is a no-op
        with patch(
            "src.utils.paths.get_config_path",
            return_value=str(tmp_path / "bbdrop.ini"),
        ), patch(
            "src.core.file_host_config.is_family_dedup_enabled",
            return_value=False,
        ):
            widget.load_from_config()

        assert widget.get_values()["file_hosts/k2s_family_dedup"] is False

    def test_save_to_config_routes_dedup_via_file_host_helper(self, qtbot, tmp_path):
        widget = AdvancedSettingsWidget()
        qtbot.addWidget(widget)
        widget._current_values["file_hosts/k2s_family_dedup"] = False

        with patch(
            "src.utils.paths.get_config_path",
            return_value=str(tmp_path / "bbdrop.ini"),
        ), patch(
            "src.core.file_host_config.set_family_dedup_enabled",
        ) as mock_set:
            widget.save_to_config(parent_window=None)

        mock_set.assert_called_once_with(False)

    def test_save_to_config_excludes_dedup_from_advanced_ini_section(
        self, qtbot, tmp_path
    ):
        """Non-default dedup value must NOT leak into [Advanced] in the INI
        file — its home is [FILE_HOSTS]."""
        ini_path = tmp_path / "bbdrop.ini"
        widget = AdvancedSettingsWidget()
        qtbot.addWidget(widget)
        widget._current_values["file_hosts/k2s_family_dedup"] = False

        with patch(
            "src.utils.paths.get_config_path",
            return_value=str(ini_path),
        ), patch("src.core.file_host_config.set_family_dedup_enabled"):
            widget.save_to_config(parent_window=None)

        if ini_path.exists():
            content = ini_path.read_text()
            assert "file_hosts/k2s_family_dedup" not in content


class TestBoolWidgetCentering:
    """Bool value widgets must be wrapped in a centered container so the
    checkbox sits in the middle of the value column rather than the
    QTableWidget's default top-left anchor."""

    def test_bool_value_widget_is_wrapped_container(self, qtbot):
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QWidget

        widget = AdvancedSettingsWidget()
        qtbot.addWidget(widget)

        wrapper = widget._value_widgets["file_hosts/k2s_family_dedup"]
        # The wrapper is a plain QWidget, not the QCheckBox itself.
        assert isinstance(wrapper, QWidget)
        assert not isinstance(wrapper, QCheckBox)

        # The actual checkbox is exposed on the wrapper.
        assert hasattr(wrapper, "_checkbox")
        assert isinstance(wrapper._checkbox, QCheckBox)

        # The wrapper's layout centers the checkbox.
        layout = wrapper.layout()
        assert isinstance(layout, QHBoxLayout)
        assert layout.contentsMargins().left() == 0
        assert layout.contentsMargins().right() == 0
        # Item alignment includes AlignCenter.
        item = layout.itemAt(0)
        assert item is not None
        assert bool(item.alignment() & Qt.AlignmentFlag.AlignCenter)

    def test_set_values_updates_wrapped_checkbox(self, qtbot):
        widget = AdvancedSettingsWidget()
        qtbot.addWidget(widget)

        widget.set_values({"file_hosts/k2s_family_dedup": False})

        wrapper = widget._value_widgets["file_hosts/k2s_family_dedup"]
        assert wrapper._checkbox.isChecked() is False
        assert widget._current_values["file_hosts/k2s_family_dedup"] is False

    def test_non_bool_widgets_unchanged(self, qtbot):
        """Int/float/string widgets must NOT be wrapped — only bool widgets
        need the centering container."""
        from PyQt6.QtWidgets import QSpinBox

        widget = AdvancedSettingsWidget()
        qtbot.addWidget(widget)

        log_font = widget._value_widgets["gui/log_font_size"]
        assert isinstance(log_font, QSpinBox)
        assert not hasattr(log_font, "_checkbox")
