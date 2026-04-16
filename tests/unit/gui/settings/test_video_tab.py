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
    def test_default_value_is_640(self, qtbot):
        from PyQt6.QtCore import QSettings
        from src.gui.settings.video_tab import VideoSettingsTab

        tab = VideoSettingsTab()
        qtbot.addWidget(tab)

        settings = QSettings("BBDropUploader-Test", "VideoSheetWidthDefault")
        settings.clear()
        tab.load_settings(settings)
        assert tab.sheet_hover_preview_width.value() == 640

    def test_round_trip_through_qsettings(self, qtbot):
        from PyQt6.QtCore import QSettings
        from src.gui.settings.video_tab import VideoSettingsTab

        tab = VideoSettingsTab()
        qtbot.addWidget(tab)

        settings = QSettings("BBDropUploader-Test", "VideoSheetWidthRoundTrip")
        settings.clear()
        tab.sheet_hover_preview_width.setValue(800)
        tab.save_settings(settings)

        tab2 = VideoSettingsTab()
        qtbot.addWidget(tab2)
        tab2.load_settings(settings)
        assert tab2.sheet_hover_preview_width.value() == 800
        settings.clear()


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
        for expected in ["Screenshot Sheet", "Preview", "Timestamps", "Appearance",
                         "Image Overlay Template", "Video Details Template",
                         "Defaults", "Mixed Folders"]:
            assert expected in group_titles, f"Missing group: {expected}"
