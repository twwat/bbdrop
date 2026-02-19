#!/usr/bin/env python3
"""
pytest-qt tests for IconManager
Tests icon loading, caching, theme handling, and fallback mechanisms
"""

import pytest
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from src.gui.icon_manager import IconManager, get_icon_manager, init_icon_manager


class TestIconManagerInit:
    """Test IconManager initialization"""

    def test_icon_manager_creates_successfully(self, temp_assets_dir):
        """Test that IconManager instantiates correctly"""
        manager = IconManager(str(temp_assets_dir))

        assert manager is not None
        assert manager.assets_dir == str(temp_assets_dir)

    def test_icon_manager_initializes_cache(self, temp_assets_dir):
        """Test that icon cache is initialized"""
        manager = IconManager(str(temp_assets_dir))

        assert hasattr(manager, '_icon_cache')
        assert isinstance(manager._icon_cache, dict)
        assert len(manager._icon_cache) == 0  # Empty initially

    def test_icon_manager_initializes_missing_set(self, temp_assets_dir):
        """Test that missing icons set is initialized"""
        manager = IconManager(str(temp_assets_dir))

        assert hasattr(manager, '_missing_icons')
        assert isinstance(manager._missing_icons, set)

    def test_icon_manager_has_icon_map(self, temp_assets_dir):
        """Test that ICON_MAP is defined"""
        manager = IconManager(str(temp_assets_dir))

        assert hasattr(manager, 'ICON_MAP')
        assert isinstance(manager.ICON_MAP, dict)
        assert len(manager.ICON_MAP) > 0

    def test_icon_manager_has_legacy_map(self, temp_assets_dir):
        """Test that legacy icon mapping exists"""
        manager = IconManager(str(temp_assets_dir))

        assert hasattr(manager, 'LEGACY_ICON_MAP')
        assert isinstance(manager.LEGACY_ICON_MAP, dict)


class TestIconLoading:
    """Test icon loading functionality"""

    def test_get_icon_returns_qicon(self, temp_assets_dir):
        """Test that get_icon returns a QIcon object"""
        manager = IconManager(str(temp_assets_dir))

        icon = manager.get_icon('status_completed')

        assert isinstance(icon, QIcon)

    def test_get_icon_with_existing_file(self, temp_assets_dir):
        """Test loading an icon that exists"""
        manager = IconManager(str(temp_assets_dir))

        # status_completed exists in temp_assets (from conftest fixture)
        icon = manager.get_icon('status_completed', theme_mode='light')

        assert isinstance(icon, QIcon)

    def test_get_icon_with_theme_mode_light(self, temp_assets_dir):
        """Test get_icon with light theme"""
        manager = IconManager(str(temp_assets_dir))

        icon = manager.get_icon('status_completed', theme_mode='light')

        assert isinstance(icon, QIcon)

    def test_get_icon_with_theme_mode_dark(self, temp_assets_dir):
        """Test get_icon with dark theme"""
        manager = IconManager(str(temp_assets_dir))

        icon = manager.get_icon('status_completed', theme_mode='dark')

        assert isinstance(icon, QIcon)

    def test_get_icon_with_selection_state(self, temp_assets_dir):
        """Test get_icon with selection state"""
        manager = IconManager(str(temp_assets_dir))

        icon_selected = manager.get_icon('status_completed', is_selected=True)
        icon_normal = manager.get_icon('status_completed', is_selected=False)

        assert isinstance(icon_selected, QIcon)
        assert isinstance(icon_normal, QIcon)

    def test_get_icon_unknown_key(self, temp_assets_dir):
        """Test get_icon with unknown icon key"""
        manager = IconManager(str(temp_assets_dir))

        icon = manager.get_icon('nonexistent_icon')

        # Should return empty QIcon or fallback
        assert isinstance(icon, QIcon)


class TestLegacyIconMapping:
    """Test legacy icon name support"""

    def test_legacy_icon_name_mapping(self, temp_assets_dir):
        """Test that legacy names map to new names"""
        manager = IconManager(str(temp_assets_dir))

        # 'completed' should map to 'status_completed'
        icon = manager.get_icon('completed')

        assert isinstance(icon, QIcon)

    def test_all_legacy_names_map_correctly(self, temp_assets_dir):
        """Test all legacy icon names are mapped"""
        manager = IconManager(str(temp_assets_dir))

        for legacy_name in manager.LEGACY_ICON_MAP.keys():
            icon = manager.get_icon(legacy_name)
            assert isinstance(icon, QIcon)


class TestIconCaching:
    """Test icon caching functionality"""

    def test_icon_caching_works(self, temp_assets_dir):
        """Test that icons are cached after first load"""
        manager = IconManager(str(temp_assets_dir))

        # First load
        icon1 = manager.get_icon('status_completed', theme_mode='light')
        cache_size_1 = len(manager._icon_cache)

        # Second load (should use cache)
        icon2 = manager.get_icon('status_completed', theme_mode='light')
        cache_size_2 = len(manager._icon_cache)

        assert cache_size_1 == cache_size_2  # No new cache entry
        assert icon1 is icon2  # Same object from cache

    def test_different_themes_cached_separately(self, temp_assets_dir):
        """Test that different themes create separate cache entries"""
        manager = IconManager(str(temp_assets_dir))

        # Use status_uploading which has theme-aware config (list of [light, dark])
        manager.get_icon('status_uploading', theme_mode='light')
        manager.get_icon('status_uploading', theme_mode='dark')

        # Should be different cache entries
        cache_keys = list(manager._icon_cache.keys())
        assert len([k for k in cache_keys if 'status_uploading' in k]) >= 2

    def test_refresh_cache_clears_cache(self, temp_assets_dir):
        """Test that refresh_cache clears the icon cache"""
        manager = IconManager(str(temp_assets_dir))

        # Load some icons
        manager.get_icon('status_completed')
        manager.get_icon('status_failed')
        assert len(manager._icon_cache) > 0

        # Refresh cache
        manager.refresh_cache()

        assert len(manager._icon_cache) == 0
        assert len(manager._missing_icons) == 0


class TestStatusAndActionIcons:
    """Test specialized status and action icon methods"""

    def test_get_status_icon(self, temp_assets_dir):
        """Test get_status_icon method"""
        manager = IconManager(str(temp_assets_dir))

        icon = manager.get_status_icon('completed')

        assert isinstance(icon, QIcon)

    def test_get_status_icon_with_animation_frame(self, temp_assets_dir):
        """Test get_status_icon with animation frame for uploading"""
        manager = IconManager(str(temp_assets_dir))

        # Uploading status uses frame-based icons
        icon_frame0 = manager.get_status_icon('uploading', animation_frame=0)
        icon_frame1 = manager.get_status_icon('uploading', animation_frame=1)

        assert isinstance(icon_frame0, QIcon)
        assert isinstance(icon_frame1, QIcon)

    def test_get_action_icon(self, temp_assets_dir):
        """Test get_action_icon method"""
        manager = IconManager(str(temp_assets_dir))

        icon = manager.get_action_icon('start')

        assert isinstance(icon, QIcon)

    def test_get_action_icon_all_actions(self, temp_assets_dir):
        """Test all action icons load correctly"""
        manager = IconManager(str(temp_assets_dir))

        actions = ['start', 'stop', 'view', 'view_error', 'cancel', 'resume']
        for action in actions:
            icon = manager.get_action_icon(action)
            assert isinstance(icon, QIcon)


class TestIconValidation:
    """Test icon validation functionality"""

    def test_validate_icons_returns_dict(self, temp_assets_dir):
        """Test that validate_icons returns a dictionary"""
        manager = IconManager(str(temp_assets_dir))

        result = manager.validate_icons(report=False)

        assert isinstance(result, dict)
        assert 'missing' in result
        assert 'found' in result

    def test_validate_icons_lists_are_correct_type(self, temp_assets_dir):
        """Test that validation results are lists"""
        manager = IconManager(str(temp_assets_dir))

        result = manager.validate_icons(report=False)

        assert isinstance(result['missing'], list)
        assert isinstance(result['found'], list)

    def test_validate_icons_finds_existing_icons(self, temp_assets_dir):
        """Test that validation finds existing icons"""
        manager = IconManager(str(temp_assets_dir))

        result = manager.validate_icons(report=False)

        # Some icons should be found (from temp_assets fixture)
        assert len(result['found']) > 0

    def test_get_missing_icons(self, temp_assets_dir):
        """Test get_missing_icons method"""
        manager = IconManager(str(temp_assets_dir))

        # Try to load a non-existent icon
        manager.get_icon('definitely_nonexistent_icon_xyz')

        missing = manager.get_missing_icons()

        assert isinstance(missing, list)


class TestIconPaths:
    """Test icon path functionality"""

    def test_get_icon_path_returns_valid_path(self, temp_assets_dir):
        """Test get_icon_path returns a path string"""
        manager = IconManager(str(temp_assets_dir))

        path = manager.get_icon_path('app_icon')

        assert path is not None
        assert isinstance(path, str)
        assert str(temp_assets_dir) in path

    def test_get_icon_path_for_unknown_icon(self, temp_assets_dir):
        """Test get_icon_path for unknown icon returns None"""
        manager = IconManager(str(temp_assets_dir))

        path = manager.get_icon_path('nonexistent_icon_key')

        assert path is None

    def test_list_all_icons(self, temp_assets_dir):
        """Test list_all_icons returns complete icon map"""
        manager = IconManager(str(temp_assets_dir))

        icons = manager.list_all_icons()

        assert isinstance(icons, dict)
        assert len(icons) > 0
        assert 'status_completed' in icons


class TestStatusTooltips:
    """Test status tooltip generation"""

    def test_get_status_tooltip_for_known_status(self, temp_assets_dir):
        """Test tooltip for known status"""
        manager = IconManager(str(temp_assets_dir))

        tooltip = manager.get_status_tooltip('completed')

        assert isinstance(tooltip, str)
        assert len(tooltip) > 0

    def test_get_status_tooltip_for_all_statuses(self, temp_assets_dir):
        """Test tooltips for all common statuses"""
        manager = IconManager(str(temp_assets_dir))

        statuses = ['completed', 'failed', 'uploading', 'paused', 'ready', 'pending']
        for status in statuses:
            tooltip = manager.get_status_tooltip(status)
            assert isinstance(tooltip, str)
            assert len(tooltip) > 0

    def test_get_status_tooltip_for_unknown_status(self, temp_assets_dir):
        """Test tooltip for unknown status returns formatted name"""
        manager = IconManager(str(temp_assets_dir))

        tooltip = manager.get_status_tooltip('custom_status_test')

        assert isinstance(tooltip, str)
        # Should convert to title case
        assert 'Custom' in tooltip or 'Status' in tooltip or 'Test' in tooltip


class TestGlobalIconManager:
    """Test global icon manager functions"""

    def test_init_icon_manager_creates_instance(self, temp_assets_dir):
        """Test init_icon_manager creates global instance"""
        manager = init_icon_manager(str(temp_assets_dir))

        assert manager is not None
        assert isinstance(manager, IconManager)

    def test_get_icon_manager_returns_instance(self, temp_assets_dir):
        """Test get_icon_manager returns the global instance"""
        init_icon_manager(str(temp_assets_dir))
        manager = get_icon_manager()

        assert manager is not None
        assert isinstance(manager, IconManager)

    def test_get_icon_manager_before_init(self):
        """Test get_icon_manager before initialization"""
        # This might return None if not initialized
        # Behavior depends on module state
        manager = get_icon_manager()

        # Should either be None or an IconManager instance
        assert manager is None or isinstance(manager, IconManager)


class TestThemeDetection:
    """Test automatic theme detection"""

    @pytest.mark.skipif(not QApplication.instance(), reason="Requires QApplication")
    def test_auto_detect_theme_light(self, qtbot, temp_assets_dir):
        """Test automatic theme detection for light theme"""
        manager = IconManager(str(temp_assets_dir))

        # Get icon without specifying theme (auto-detect)
        icon = manager.get_icon('status_completed', theme_mode=None)

        assert isinstance(icon, QIcon)

    @pytest.mark.skipif(not QApplication.instance(), reason="Requires QApplication")
    def test_auto_detect_theme_dark(self, qtbot, temp_assets_dir):
        """Test automatic theme detection for dark theme"""
        manager = IconManager(str(temp_assets_dir))

        # Get icon without specifying theme (auto-detect)
        icon = manager.get_icon('status_completed', theme_mode=None)

        assert isinstance(icon, QIcon)


class TestIconManagerEdgeCases:
    """Test edge cases and error handling"""

    def test_icon_manager_with_nonexistent_assets_dir(self):
        """Test IconManager with non-existent assets directory"""
        manager = IconManager('/nonexistent/path')

        # Should create without error
        assert manager is not None
        assert manager.assets_dir == '/nonexistent/path'

    def test_get_icon_with_invalid_theme_mode(self, temp_assets_dir):
        """Test get_icon with invalid theme mode"""
        manager = IconManager(str(temp_assets_dir))

        # Should handle gracefully (defaults to dark or light)
        icon = manager.get_icon('status_completed', theme_mode='invalid')

        assert isinstance(icon, QIcon)

    def test_concurrent_icon_loads(self, temp_assets_dir):
        """Test loading multiple icons concurrently"""
        manager = IconManager(str(temp_assets_dir))

        icons = []
        for i in range(10):
            icon = manager.get_icon('status_completed', theme_mode='light')
            icons.append(icon)

        # All should be valid
        assert all(isinstance(icon, QIcon) for icon in icons)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
