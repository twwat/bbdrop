"""Tests for VideoSettingsTab."""
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
