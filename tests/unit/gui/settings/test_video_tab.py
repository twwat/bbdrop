"""Tests for VideoSettingsTab."""
import os

# Ensure Qt uses offscreen platform for headless testing
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


class TestVideoSettingsTab:
    def test_tab_class_exists(self):
        from src.gui.settings.video_tab import VideoSettingsTab
        assert VideoSettingsTab is not None

    def test_has_load_and_save(self):
        from src.gui.settings.video_tab import VideoSettingsTab
        assert hasattr(VideoSettingsTab, 'load_settings')
        assert hasattr(VideoSettingsTab, 'save_settings')

    def test_has_dirty_signal(self):
        from src.gui.settings.video_tab import VideoSettingsTab
        assert hasattr(VideoSettingsTab, 'dirty')


class TestSheetHoverPreviewWidth:
    """The hover preview width setting moved from the Contact Sheets tab
    to Advanced Settings. These tests cover the delegate's reader, which
    prefers the [Advanced] INI value and falls back to the legacy
    QSettings location for users upgrading from the old Contact Sheets tab.
    """

    def test_default_value_is_640(self, tmp_path, monkeypatch):
        from src.gui.delegates import media_type_delegate

        monkeypatch.setattr(
            'src.utils.paths.get_config_path',
            lambda: str(tmp_path / 'missing.ini'),
        )
        # No INI, no legacy QSettings → default 640
        assert media_type_delegate._read_sheet_preview_width() == 640

    def test_reads_from_advanced_ini(self, tmp_path, monkeypatch):
        from src.gui.delegates import media_type_delegate

        ini = tmp_path / 'bbdrop.ini'
        ini.write_text(
            "[Advanced]\n"
            "video/sheet_hover_preview_width_px = 820\n",
            encoding='utf-8',
        )
        monkeypatch.setattr(
            'src.utils.paths.get_config_path', lambda: str(ini),
        )
        assert media_type_delegate._read_sheet_preview_width() == 820

    def test_legacy_qsettings_fallback(self, tmp_path, monkeypatch, qtbot):
        from PyQt6.QtCore import QSettings
        from src.gui.delegates import media_type_delegate

        monkeypatch.setattr(
            'src.utils.paths.get_config_path',
            lambda: str(tmp_path / 'missing.ini'),
        )
        # Legacy setting in QSettings should still be honoured.
        legacy = QSettings("BBDropUploader", "BBDropGUI")
        legacy.beginGroup("Video")
        legacy.setValue("sheet_preview_width_px", 770)
        legacy.endGroup()
        try:
            assert media_type_delegate._read_sheet_preview_width() == 770
        finally:
            legacy.beginGroup("Video")
            legacy.remove("sheet_preview_width_px")
            legacy.endGroup()


class TestContactSheetsLayout:
    def test_uses_grid_layout(self, qtbot):
        from PyQt6.QtWidgets import QGridLayout
        from src.gui.settings.video_tab import VideoSettingsTab

        tab = VideoSettingsTab()
        qtbot.addWidget(tab)

        grid_layout = tab.findChild(QGridLayout)
        assert grid_layout is not None

    def test_has_all_group_boxes(self, qtbot):
        from PyQt6.QtWidgets import QGroupBox
        from src.gui.settings.video_tab import VideoSettingsTab

        tab = VideoSettingsTab()
        qtbot.addWidget(tab)

        groups = tab.findChildren(QGroupBox)
        group_titles = [g.title() for g in groups]
        # Appearance controls were merged into "Text Overlay Template", so
        # the standalone Appearance group is intentionally gone.
        for expected in ["Screenshot Sheet", "Preview", "Timestamps",
                         "Text Overlay Template", "Video Details Template",
                         "Defaults", "Mixed Folders"]:
            assert expected in group_titles, f"Missing group: {expected}"
