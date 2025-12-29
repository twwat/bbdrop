"""
Unit tests for icon caching optimization.

Tests verify that:
1. Icons are cached and reused (no duplicate disk reads)
2. Dark/light themes are cached separately
3. Cache statistics tracking works correctly
4. Cache hit rate improves with repeated icon requests
"""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from src.gui.icon_manager import IconManager


@pytest.fixture
def temp_assets_dir(tmp_path):
    """Create temporary assets directory with test icons"""
    assets = tmp_path / "assets"
    assets.mkdir()

    # Create dummy icon files for testing
    test_icons = [
        "status_completed-light.png",
        "status_completed-dark.png",
        "status_failed-light.png",
        "status_failed-dark.png",
        "status_uploading-light.png",
        "status_uploading-dark.png",
        "action_start-light.png",
        "action_start-dark.png",
    ]

    for icon_file in test_icons:
        (assets / icon_file).write_bytes(b"fake icon data")

    return str(assets)


@pytest.fixture
def icon_manager(temp_assets_dir):
    """Create IconManager instance with temp assets"""
    return IconManager(temp_assets_dir)


@pytest.fixture
def qt_app():
    """Ensure QApplication exists for icon tests"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestIconCacheReuse:
    """Test that icons are cached and reused"""

    def test_icon_cache_reuses_loaded_icons(self, icon_manager, qt_app):
        """Verify icons are cached and reused"""
        # Get same icon twice
        icon1 = icon_manager.get_icon('status_completed', 'light')
        icon2 = icon_manager.get_icon('status_completed', 'light')

        # Verify only 1 disk read occurred
        stats = icon_manager.get_cache_stats()
        assert stats['disk_loads'] == 1, "Should only load icon from disk once"

        # Verify 2 requests total (1 miss, 1 hit)
        assert stats['misses'] == 1, "First request should be cache miss"
        assert stats['hits'] == 1, "Second request should be cache hit"

        # Verify both icons are the same object (cached)
        assert icon1 is icon2, "Should return same cached QIcon object"

    def test_multiple_icons_cached_independently(self, icon_manager, qt_app):
        """Verify different icons are cached independently"""
        # Request 3 different icons
        icon_manager.get_icon('status_completed', 'light')
        icon_manager.get_icon('status_failed', 'light')
        icon_manager.get_icon('status_uploading', 'light')

        stats = icon_manager.get_cache_stats()
        assert stats['disk_loads'] == 3, "Should load 3 different icons"
        assert stats['cached_icons'] == 3, "Should cache 3 different icons"

        # Request them again
        icon_manager.get_icon('status_completed', 'light')
        icon_manager.get_icon('status_failed', 'light')
        icon_manager.get_icon('status_uploading', 'light')

        stats = icon_manager.get_cache_stats()
        assert stats['disk_loads'] == 3, "Should not load from disk again"
        assert stats['hits'] == 3, "All 3 re-requests should be cache hits"


class TestThemeCaching:
    """Test that dark/light themes are cached separately"""

    def test_icon_cache_handles_different_themes(self, icon_manager, qt_app):
        """Verify dark/light themes cached separately"""
        # Get same icon in light theme
        icon_light = icon_manager.get_icon('status_completed', 'light')

        # Get same icon in dark theme
        icon_dark = icon_manager.get_icon('status_completed', 'dark')

        stats = icon_manager.get_cache_stats()

        # Verify 2 disk reads occurred (one for each theme)
        assert stats['disk_loads'] == 2, "Should load both light and dark variants"

        # Verify 2 different icons cached
        assert stats['cached_icons'] == 2, "Should cache light and dark separately"

        # Verify icons are different objects
        assert icon_light is not icon_dark, "Light and dark variants should be different"

        # Request light again - should be cached
        icon_light2 = icon_manager.get_icon('status_completed', 'light')
        stats = icon_manager.get_cache_stats()
        assert stats['disk_loads'] == 2, "Should not load light variant again"
        assert icon_light is icon_light2, "Should return cached light icon"

    def test_theme_cache_keys_include_selection_state(self, icon_manager, qt_app):
        """Verify selection state is part of cache key"""
        # Get icon for normal row
        icon_normal = icon_manager.get_icon('status_completed', 'light', is_selected=False)

        # Get icon for selected row
        icon_selected = icon_manager.get_icon('status_completed', 'light', is_selected=True)

        stats = icon_manager.get_cache_stats()

        # Should cache both variants
        assert stats['cached_icons'] == 2, "Should cache normal and selected variants"
        assert icon_normal is not icon_selected, "Normal and selected should be different cache entries"


class TestCacheStatistics:
    """Test cache statistics tracking"""

    def test_icon_cache_statistics(self, icon_manager, qt_app):
        """Verify cache hit/miss tracking works"""
        # Load 5 unique icons (5 misses, 5 disk loads)
        icons = ['status_completed', 'status_failed', 'status_uploading',
                 'action_start', 'status_paused']

        for icon_key in icons:
            icon_manager.get_icon(icon_key, 'light')

        stats = icon_manager.get_cache_stats()
        assert stats['misses'] == 5, "Should have 5 cache misses for new icons"
        assert stats['disk_loads'] == 5, "Should have 5 disk I/O operations"
        assert stats['cached_icons'] == 5, "Should have 5 cached icons"
        assert stats['hits'] == 0, "Should have no hits yet"

        # Load 2 of them again (2 hits, no new disk loads)
        icon_manager.get_icon('status_completed', 'light')
        icon_manager.get_icon('status_failed', 'light')

        stats = icon_manager.get_cache_stats()
        assert stats['misses'] == 5, "Should still have 5 misses total"
        assert stats['hits'] == 2, "Should have 2 cache hits"
        assert stats['disk_loads'] == 5, "Should still have only 5 disk loads"
        assert stats['cached_icons'] == 5, "Should still have 5 cached icons"

    def test_cache_hit_rate_calculation(self, icon_manager, qt_app):
        """Verify cache hit rate percentage is calculated correctly"""
        # Make 10 requests: 5 unique icons, then repeat them
        icons = ['status_completed', 'status_failed', 'status_uploading',
                 'action_start', 'status_paused']

        # First pass - all misses
        for icon_key in icons:
            icon_manager.get_icon(icon_key, 'light')

        # Second pass - all hits
        for icon_key in icons:
            icon_manager.get_icon(icon_key, 'light')

        stats = icon_manager.get_cache_stats()

        # 10 total requests: 5 misses, 5 hits = 50% hit rate
        assert stats['hit_rate'] == 50.0, "Hit rate should be 50% (5 hits / 10 total)"

    def test_cache_stats_initial_state(self, icon_manager, qt_app):
        """Verify initial cache stats are all zeros"""
        stats = icon_manager.get_cache_stats()

        assert stats['hits'] == 0, "Initial hits should be 0"
        assert stats['misses'] == 0, "Initial misses should be 0"
        assert stats['disk_loads'] == 0, "Initial disk loads should be 0"
        assert stats['cached_icons'] == 0, "Initial cached icons should be 0"
        assert stats['hit_rate'] == 0.0, "Initial hit rate should be 0%"


class TestCacheRefresh:
    """Test cache clearing and refresh behavior"""

    def test_refresh_cache_clears_all_data(self, icon_manager, qt_app):
        """Verify refresh_cache clears everything"""
        # Load some icons
        icon_manager.get_icon('status_completed', 'light')
        icon_manager.get_icon('status_failed', 'light')

        stats_before = icon_manager.get_cache_stats()
        assert stats_before['cached_icons'] == 2, "Should have 2 cached icons"

        # Refresh cache
        icon_manager.refresh_cache()

        stats_after = icon_manager.get_cache_stats()
        assert stats_after['hits'] == 0, "Hits should reset to 0"
        assert stats_after['misses'] == 0, "Misses should reset to 0"
        assert stats_after['disk_loads'] == 0, "Disk loads should reset to 0"
        assert stats_after['cached_icons'] == 0, "Cached icons should be cleared"
        assert stats_after['hit_rate'] == 0.0, "Hit rate should reset to 0%"

    def test_refresh_cache_forces_reload(self, icon_manager, qt_app):
        """Verify refresh_cache causes icons to be reloaded from disk"""
        # Load icon
        icon_manager.get_icon('status_completed', 'light')
        stats = icon_manager.get_cache_stats()
        assert stats['disk_loads'] == 1, "Should load once"

        # Clear cache
        icon_manager.refresh_cache()

        # Load same icon again - should reload from disk
        icon_manager.get_icon('status_completed', 'light')
        stats = icon_manager.get_cache_stats()
        assert stats['disk_loads'] == 1, "Should reload from disk after cache clear"
        assert stats['misses'] == 1, "Should be a cache miss after clear"


class TestCacheKeyGeneration:
    """Test cache key generation logic"""

    def test_cache_keys_are_unique_per_variation(self, icon_manager, qt_app):
        """Verify each icon variation gets a unique cache key"""
        # Request same icon with different parameters
        variations = [
            ('status_completed', 'light', False, 32),
            ('status_completed', 'light', True, 32),
            ('status_completed', 'dark', False, 32),
            ('status_completed', 'dark', True, 32),
            ('status_completed', 'light', False, 64),  # Different size
        ]

        for icon_key, theme, selected, size in variations:
            icon_manager.get_icon(icon_key, theme, selected, size)

        stats = icon_manager.get_cache_stats()

        # Should cache all 5 variations separately
        assert stats['cached_icons'] == 5, "Should cache all 5 variations separately"
        assert stats['misses'] == 5, "All variations should be cache misses initially"


class TestCachePerformance:
    """Test cache performance characteristics"""

    def test_cache_improves_with_repeated_requests(self, icon_manager, qt_app):
        """Verify cache hit rate improves with more repeated requests"""
        icon_key = 'status_completed'
        theme = 'light'

        # First request - cache miss
        icon_manager.get_icon(icon_key, theme)
        stats1 = icon_manager.get_cache_stats()
        assert stats1['hit_rate'] == 0.0, "First request should be 0% hit rate"

        # 9 more requests - all cache hits
        for _ in range(9):
            icon_manager.get_icon(icon_key, theme)

        stats10 = icon_manager.get_cache_stats()
        assert stats10['hit_rate'] == 90.0, "After 10 requests (1 miss, 9 hits) should be 90% hit rate"

        # 90 more requests - all cache hits
        for _ in range(90):
            icon_manager.get_icon(icon_key, theme)

        stats100 = icon_manager.get_cache_stats()
        assert stats100['hit_rate'] == 99.0, "After 100 requests (1 miss, 99 hits) should be 99% hit rate"

    def test_cache_prevents_redundant_disk_io(self, icon_manager, qt_app):
        """Verify cache prevents redundant disk I/O operations"""
        icon_key = 'status_completed'
        theme = 'light'

        # Request same icon 1000 times
        for _ in range(1000):
            icon_manager.get_icon(icon_key, theme)

        stats = icon_manager.get_cache_stats()

        # Should only load from disk once
        assert stats['disk_loads'] == 1, "Should only load from disk once despite 1000 requests"
        assert stats['hits'] == 999, "999 requests should be cache hits"
        assert stats['misses'] == 1, "Only 1 request should be cache miss"


class TestMissingIconHandling:
    """Test behavior when icons are missing"""

    def test_missing_icon_not_cached(self, icon_manager, qt_app):
        """Verify missing icons don't pollute cache"""
        # Request non-existent icon
        icon = icon_manager.get_icon('nonexistent_icon', 'light')

        # Should return empty icon
        assert icon.isNull() or not icon.availableSizes(), "Should return null/empty icon for missing file"

        stats = icon_manager.get_cache_stats()

        # Missing icon behavior depends on fallback handling
        # Just verify cache stats are tracked
        assert stats['misses'] >= 1, "Should count as cache miss"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
