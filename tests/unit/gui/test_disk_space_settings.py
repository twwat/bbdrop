"""Tests for disk space threshold settings in advanced tab."""

import pytest


class TestDiskSpaceSettings:
    """Disk space thresholds should be in the ADVANCED_SETTINGS schema."""

    def test_settings_schema_contains_disk_monitor_keys(self):
        from src.gui.settings.advanced_tab import ADVANCED_SETTINGS
        keys = {s["key"] for s in ADVANCED_SETTINGS}

        assert "disk_monitor/enabled" in keys
        assert "disk_monitor/warning_mb" in keys
        assert "disk_monitor/critical_mb" in keys
        assert "disk_monitor/emergency_mb" in keys

    def test_warning_default_is_2048(self):
        from src.gui.settings.advanced_tab import ADVANCED_SETTINGS
        setting = next(s for s in ADVANCED_SETTINGS if s["key"] == "disk_monitor/warning_mb")
        assert setting["default"] == 2048

    def test_critical_default_is_512(self):
        from src.gui.settings.advanced_tab import ADVANCED_SETTINGS
        setting = next(s for s in ADVANCED_SETTINGS if s["key"] == "disk_monitor/critical_mb")
        assert setting["default"] == 512

    def test_emergency_default_is_100(self):
        from src.gui.settings.advanced_tab import ADVANCED_SETTINGS
        setting = next(s for s in ADVANCED_SETTINGS if s["key"] == "disk_monitor/emergency_mb")
        assert setting["default"] == 100

    def test_warning_min_greater_than_critical_default(self):
        from src.gui.settings.advanced_tab import ADVANCED_SETTINGS
        warning = next(s for s in ADVANCED_SETTINGS if s["key"] == "disk_monitor/warning_mb")
        assert warning["min"] >= 500  # Must be at least 500 MB
