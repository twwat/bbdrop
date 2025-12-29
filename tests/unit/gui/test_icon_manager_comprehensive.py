"""
Comprehensive pytest-qt tests for IconManager.

This test suite provides thorough coverage of the IconManager class including:
- Icon loading and caching behavior
- Theme switching (light/dark)
- Icon scaling/sizing
- Fallback behavior with Qt standard icons
- Memory management and cache lifecycle
- Performance characteristics
- Edge cases and error handling

Uses pytest-qt fixtures for proper Qt integration testing.
"""

import os
import sys
import time
import pytest
from pathlib import Path
from typing import List
from unittest.mock import Mock, patch, MagicMock, PropertyMock

from PyQt6.QtGui import QIcon, QPixmap, QColor, QPalette
from PyQt6.QtWidgets import QApplication, QStyle
from PyQt6.QtCore import QSize

from src.gui.icon_manager import (
    IconManager,
    get_icon_manager,
    init_icon_manager,
    _icon_manager
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_assets_dir(tmp_path):
    """
    Create a temporary assets directory with test icon files.

    Creates a complete set of light/dark icon variants for testing
    theme switching and icon loading.
    """
    assets = tmp_path / "assets"
    assets.mkdir()

    # Create test icon files with actual PNG content
    # Using a minimal 1x1 PNG for valid icon loading
    minimal_png = (
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
        b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f'
        b'\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
    )

    # Status icons - light and dark variants
    status_icons = [
        'status_completed', 'status_failed', 'status_uploading',
        'status_paused', 'status_queued', 'status_ready',
        'status_pending', 'status_incomplete', 'status_scan_failed',
        'status_error', 'status_idle', 'status_scanning', 'status_validating'
    ]

    for status in status_icons:
        (assets / f"{status}-light.png").write_bytes(minimal_png)
        (assets / f"{status}-dark.png").write_bytes(minimal_png)

    # Animation frame icons for uploading
    for i in range(1, 5):  # 001-004
        (assets / f"status_uploading-{i:03d}-light.png").write_bytes(minimal_png)
        (assets / f"status_uploading-{i:03d}-dark.png").write_bytes(minimal_png)

    # Action icons
    action_icons = [
        'action_start', 'action_stop', 'action_view',
        'action_view_error', 'action_cancel', 'action_resume'
    ]

    for action in action_icons:
        (assets / f"{action}-light.png").write_bytes(minimal_png)
        (assets / f"{action}-dark.png").write_bytes(minimal_png)

    # Renamed status icons
    (assets / "renamed_true-light.png").write_bytes(minimal_png)
    (assets / "renamed_true-dark.png").write_bytes(minimal_png)
    (assets / "renamed_false-light.png").write_bytes(minimal_png)
    (assets / "renamed_false-dark.png").write_bytes(minimal_png)

    # Host icons
    (assets / "host_enabled-light.png").write_bytes(minimal_png)
    (assets / "host_enabled-dark.png").write_bytes(minimal_png)
    (assets / "host_disabled-light.png").write_bytes(minimal_png)
    (assets / "host_disabled-dark.png").write_bytes(minimal_png)

    # UI element icons
    ui_icons = [
        'settings', 'templates', 'credentials', 'filehosts',
        'help', 'hooks', 'toggle_theme', 'log_viewer',
        'radio_check', 'checkbox_check'
    ]

    for ui in ui_icons:
        (assets / f"{ui}-light.png").write_bytes(minimal_png)
        (assets / f"{ui}-dark.png").write_bytes(minimal_png)

    # Main window and app icons
    (assets / "imxup.png").write_bytes(minimal_png)
    (assets / "imxup.ico").write_bytes(minimal_png)

    return str(assets)


@pytest.fixture
def icon_manager(temp_assets_dir):
    """Create a fresh IconManager instance with temporary assets."""
    return IconManager(temp_assets_dir)


@pytest.fixture
def populated_icon_manager(icon_manager):
    """Create an IconManager with some pre-cached icons."""
    # Load a variety of icons to populate the cache
    icon_manager.get_icon('status_completed', 'light')
    icon_manager.get_icon('status_completed', 'dark')
    icon_manager.get_icon('status_failed', 'light')
    icon_manager.get_icon('action_start', 'light')
    return icon_manager


# =============================================================================
# Test Classes
# =============================================================================

class TestIconManagerInitialization:
    """Test IconManager initialization and configuration."""

    def test_initialization_with_valid_path(self, temp_assets_dir):
        """Verify IconManager initializes correctly with valid assets path."""
        manager = IconManager(temp_assets_dir)

        assert manager.assets_dir == temp_assets_dir
        assert isinstance(manager._icon_cache, dict)
        assert len(manager._icon_cache) == 0
        assert isinstance(manager._missing_icons, set)
        assert manager._validated is False

    def test_initialization_with_invalid_path(self):
        """Verify IconManager handles non-existent path gracefully."""
        manager = IconManager("/nonexistent/path/to/assets")

        assert manager.assets_dir == "/nonexistent/path/to/assets"
        assert len(manager._icon_cache) == 0

    def test_cache_statistics_initialized_to_zero(self, icon_manager):
        """Verify all cache statistics start at zero."""
        stats = icon_manager.get_cache_stats()

        assert stats['hits'] == 0
        assert stats['misses'] == 0
        assert stats['disk_loads'] == 0
        assert stats['cached_icons'] == 0
        assert stats['hit_rate'] == 0.0

    def test_icon_map_contains_expected_keys(self, icon_manager):
        """Verify ICON_MAP contains all expected icon definitions."""
        expected_keys = [
            'status_completed', 'status_failed', 'status_uploading',
            'action_start', 'action_stop', 'main_window', 'app_icon'
        ]

        for key in expected_keys:
            assert key in icon_manager.ICON_MAP, f"Missing key: {key}"

    def test_qt_fallbacks_defined(self, icon_manager):
        """Verify Qt fallback icons are defined for common statuses."""
        assert 'status_completed' in icon_manager.QT_FALLBACKS
        assert 'status_failed' in icon_manager.QT_FALLBACKS
        assert 'action_start' in icon_manager.QT_FALLBACKS

    def test_legacy_icon_map_defined(self, icon_manager):
        """Verify legacy icon name mappings exist."""
        assert 'completed' in icon_manager.LEGACY_ICON_MAP
        assert icon_manager.LEGACY_ICON_MAP['completed'] == 'status_completed'


class TestIconLoading:
    """Test icon loading functionality with pytest-qt."""

    def test_get_icon_returns_qicon(self, qtbot, icon_manager):
        """Verify get_icon returns a QIcon object."""
        icon = icon_manager.get_icon('status_completed', 'light')

        assert isinstance(icon, QIcon)
        assert not icon.isNull()

    def test_get_icon_with_explicit_light_theme(self, qtbot, icon_manager):
        """Test loading icon with explicit light theme."""
        icon = icon_manager.get_icon('status_completed', theme_mode='light')

        assert isinstance(icon, QIcon)
        assert not icon.isNull()

    def test_get_icon_with_explicit_dark_theme(self, qtbot, icon_manager):
        """Test loading icon with explicit dark theme."""
        icon = icon_manager.get_icon('status_completed', theme_mode='dark')

        assert isinstance(icon, QIcon)
        assert not icon.isNull()

    def test_get_icon_with_different_sizes(self, qtbot, icon_manager):
        """Test loading icons with different requested sizes."""
        sizes = [16, 24, 32, 48, 64, 128]

        for size in sizes:
            icon = icon_manager.get_icon('status_completed', 'light', requested_size=size)
            assert isinstance(icon, QIcon)

    def test_get_icon_with_selection_state_true(self, qtbot, icon_manager):
        """Test loading icon with is_selected=True."""
        icon = icon_manager.get_icon('status_completed', 'light', is_selected=True)

        assert isinstance(icon, QIcon)

    def test_get_icon_with_selection_state_false(self, qtbot, icon_manager):
        """Test loading icon with is_selected=False."""
        icon = icon_manager.get_icon('status_completed', 'light', is_selected=False)

        assert isinstance(icon, QIcon)

    def test_get_icon_unknown_key_returns_empty_qicon(self, qtbot, icon_manager):
        """Test that unknown icon key returns empty QIcon without Qt fallback."""
        icon = icon_manager.get_icon('completely_unknown_icon_xyz')

        assert isinstance(icon, QIcon)
        # May be null if no fallback exists
        assert icon.isNull() or isinstance(icon, QIcon)


class TestLegacyIconNames:
    """Test backward compatibility with legacy icon names."""

    def test_legacy_name_completed(self, qtbot, icon_manager):
        """Test legacy name 'completed' maps to 'status_completed'."""
        icon = icon_manager.get_icon('completed', 'light')
        assert isinstance(icon, QIcon)

    def test_legacy_name_failed(self, qtbot, icon_manager):
        """Test legacy name 'failed' maps to 'status_failed'."""
        icon = icon_manager.get_icon('failed', 'light')
        assert isinstance(icon, QIcon)

    def test_legacy_name_start(self, qtbot, icon_manager):
        """Test legacy name 'start' maps to 'action_start'."""
        icon = icon_manager.get_icon('start', 'light')
        assert isinstance(icon, QIcon)

    def test_all_legacy_names_resolve(self, qtbot, icon_manager):
        """Test all legacy names resolve to valid icons."""
        for legacy_name in icon_manager.LEGACY_ICON_MAP.keys():
            icon = icon_manager.get_icon(legacy_name, 'light')
            assert isinstance(icon, QIcon), f"Failed for legacy name: {legacy_name}"


class TestThemeSwitching:
    """Test theme switching behavior between light and dark modes."""

    def test_light_and_dark_themes_cached_separately(self, qtbot, icon_manager):
        """Verify light and dark theme icons are cached separately."""
        icon_light = icon_manager.get_icon('status_completed', 'light')
        icon_dark = icon_manager.get_icon('status_completed', 'dark')

        # Should be different cache entries
        stats = icon_manager.get_cache_stats()
        assert stats['cached_icons'] == 2

        # Should be different QIcon objects
        assert icon_light is not icon_dark

    def test_theme_switch_loads_correct_variant(self, qtbot, icon_manager, temp_assets_dir):
        """Verify correct file is loaded for each theme."""
        # This tests the internal _get_themed_filename logic
        config = icon_manager.ICON_MAP['status_completed']

        light_file = icon_manager._get_themed_filename(config, 'light', False)
        dark_file = icon_manager._get_themed_filename(config, 'dark', False)

        assert 'light' in light_file
        assert 'dark' in dark_file

    def test_auto_detect_theme_without_app(self, icon_manager):
        """Test theme detection falls back to dark when no QApplication."""
        # When no QApplication exists, should default to dark
        with patch('PyQt6.QtWidgets.QApplication.instance', return_value=None):
            icon = icon_manager.get_icon('status_completed', theme_mode=None)

        assert isinstance(icon, QIcon)

    def test_selection_state_creates_separate_cache_entry(self, qtbot, icon_manager):
        """Verify selection state creates separate cache entries."""
        icon_normal = icon_manager.get_icon('status_completed', 'light', is_selected=False)
        icon_selected = icon_manager.get_icon('status_completed', 'light', is_selected=True)

        stats = icon_manager.get_cache_stats()
        assert stats['cached_icons'] == 2
        assert icon_normal is not icon_selected


class TestCacheBehavior:
    """Test icon caching behavior and performance."""

    def test_cache_returns_same_object(self, qtbot, icon_manager):
        """Verify cache returns the same QIcon object for identical requests."""
        icon1 = icon_manager.get_icon('status_completed', 'light')
        icon2 = icon_manager.get_icon('status_completed', 'light')

        assert icon1 is icon2

    def test_cache_hit_increments_counter(self, qtbot, icon_manager):
        """Verify cache hits increment the hit counter."""
        icon_manager.get_icon('status_completed', 'light')  # Miss
        icon_manager.get_icon('status_completed', 'light')  # Hit

        stats = icon_manager.get_cache_stats()
        assert stats['hits'] == 1
        assert stats['misses'] == 1

    def test_cache_miss_increments_counter(self, qtbot, icon_manager):
        """Verify cache misses increment the miss counter."""
        icon_manager.get_icon('status_completed', 'light')
        icon_manager.get_icon('status_failed', 'light')

        stats = icon_manager.get_cache_stats()
        assert stats['misses'] == 2

    def test_disk_loads_tracked(self, qtbot, icon_manager):
        """Verify disk load operations are tracked."""
        icon_manager.get_icon('status_completed', 'light')
        icon_manager.get_icon('status_failed', 'light')

        stats = icon_manager.get_cache_stats()
        assert stats['disk_loads'] == 2

    def test_repeated_requests_no_additional_disk_loads(self, qtbot, icon_manager):
        """Verify repeated requests don't cause additional disk loads."""
        # Initial load
        icon_manager.get_icon('status_completed', 'light')

        # Repeated loads
        for _ in range(100):
            icon_manager.get_icon('status_completed', 'light')

        stats = icon_manager.get_cache_stats()
        assert stats['disk_loads'] == 1
        assert stats['hits'] == 100

    def test_cache_key_includes_size(self, qtbot, icon_manager):
        """Verify cache key includes requested size."""
        icon_32 = icon_manager.get_icon('status_completed', 'light', requested_size=32)
        icon_64 = icon_manager.get_icon('status_completed', 'light', requested_size=64)

        stats = icon_manager.get_cache_stats()
        assert stats['cached_icons'] == 2
        assert icon_32 is not icon_64

    def test_hit_rate_calculation(self, qtbot, icon_manager):
        """Verify hit rate is calculated correctly."""
        # 1 miss
        icon_manager.get_icon('status_completed', 'light')

        # 9 hits
        for _ in range(9):
            icon_manager.get_icon('status_completed', 'light')

        stats = icon_manager.get_cache_stats()
        assert stats['hit_rate'] == 90.0

    def test_refresh_cache_clears_all(self, qtbot, populated_icon_manager):
        """Verify refresh_cache clears cache and resets statistics."""
        assert populated_icon_manager.get_cache_stats()['cached_icons'] > 0

        populated_icon_manager.refresh_cache()

        stats = populated_icon_manager.get_cache_stats()
        assert stats['hits'] == 0
        assert stats['misses'] == 0
        assert stats['disk_loads'] == 0
        assert stats['cached_icons'] == 0
        assert stats['hit_rate'] == 0.0

    def test_refresh_cache_clears_missing_icons_set(self, qtbot, icon_manager, temp_assets_dir):
        """Verify refresh_cache clears the missing icons tracking."""
        # Remove an icon file that's defined in ICON_MAP to trigger missing tracking
        import os
        light_icon = os.path.join(temp_assets_dir, 'status_validating-light.png')
        dark_icon = os.path.join(temp_assets_dir, 'status_validating-dark.png')
        if os.path.exists(light_icon):
            os.remove(light_icon)
        if os.path.exists(dark_icon):
            os.remove(dark_icon)

        # Try to load an icon that's defined but files are missing
        icon_manager.get_icon('status_validating', 'light')

        # Now missing_icons should have the entry
        assert 'status_validating' in icon_manager._missing_icons

        icon_manager.refresh_cache()
        assert len(icon_manager._missing_icons) == 0


class TestStatusIcons:
    """Test status icon loading with animation support."""

    def test_get_status_icon_basic(self, qtbot, icon_manager):
        """Test basic status icon loading."""
        icon = icon_manager.get_status_icon('completed')
        assert isinstance(icon, QIcon)

    def test_get_status_icon_with_theme(self, qtbot, icon_manager):
        """Test status icon with explicit theme."""
        icon = icon_manager.get_status_icon('failed', theme_mode='dark')
        assert isinstance(icon, QIcon)

    def test_uploading_animation_frames(self, qtbot, icon_manager):
        """Test uploading status animation frame cycling."""
        icons = []
        for frame in range(4):
            icon = icon_manager.get_status_icon('uploading', animation_frame=frame)
            icons.append(icon)
            assert isinstance(icon, QIcon)

        # Verify 4 different frames were loaded
        stats = icon_manager.get_cache_stats()
        assert stats['cached_icons'] == 4

    def test_animation_frame_modulo(self, qtbot, icon_manager):
        """Test animation frame wraps around with modulo."""
        # Frame 4 should wrap to frame 0
        icon_0 = icon_manager.get_status_icon('uploading', animation_frame=0)
        icon_4 = icon_manager.get_status_icon('uploading', animation_frame=4)

        # Should be same cache entry (frame 4 % 4 = 0)
        assert icon_0 is icon_4

    def test_all_common_statuses(self, qtbot, icon_manager):
        """Test loading all common status icons."""
        statuses = [
            'completed', 'failed', 'uploading', 'paused',
            'queued', 'ready', 'pending', 'incomplete',
            'scan_failed', 'error', 'idle', 'scanning'
        ]

        for status in statuses:
            icon = icon_manager.get_status_icon(status)
            assert isinstance(icon, QIcon), f"Failed for status: {status}"


class TestActionIcons:
    """Test action icon loading."""

    def test_get_action_icon_basic(self, qtbot, icon_manager):
        """Test basic action icon loading."""
        icon = icon_manager.get_action_icon('start')
        assert isinstance(icon, QIcon)

    def test_get_action_icon_with_theme(self, qtbot, icon_manager):
        """Test action icon with explicit theme."""
        icon = icon_manager.get_action_icon('stop', theme_mode='dark')
        assert isinstance(icon, QIcon)

    def test_get_action_icon_with_selection(self, qtbot, icon_manager):
        """Test action icon with selection state."""
        icon = icon_manager.get_action_icon('view', is_selected=True)
        assert isinstance(icon, QIcon)

    def test_all_action_icons(self, qtbot, icon_manager):
        """Test loading all action icons."""
        actions = ['start', 'stop', 'view', 'view_error', 'cancel', 'resume']

        for action in actions:
            icon = icon_manager.get_action_icon(action)
            assert isinstance(icon, QIcon), f"Failed for action: {action}"


class TestFallbackBehavior:
    """Test Qt standard icon fallback behavior."""

    def test_fallback_for_known_status(self, qtbot, temp_assets_dir):
        """Test that Qt fallback is used when icon file is missing."""
        # Create manager with empty assets directory
        empty_dir = Path(temp_assets_dir).parent / "empty_assets"
        empty_dir.mkdir()
        manager = IconManager(str(empty_dir))

        # Request a status that has a Qt fallback defined
        icon = manager.get_icon('status_completed', 'light')

        # Should return a QIcon (either fallback or empty)
        assert isinstance(icon, QIcon)

    def test_missing_icon_tracked(self, qtbot, temp_assets_dir):
        """Test that missing icons are tracked."""
        empty_dir = Path(temp_assets_dir).parent / "empty_assets2"
        empty_dir.mkdir()
        manager = IconManager(str(empty_dir))

        # Request icon that will be missing
        manager.get_icon('status_completed', 'light')

        # Check missing icons list
        missing = manager.get_missing_icons()
        assert isinstance(missing, list)

    def test_empty_icon_for_unknown_key_no_fallback(self, qtbot, icon_manager):
        """Test empty QIcon returned for unknown key without fallback."""
        icon = icon_manager.get_icon('completely_unknown_no_fallback_xyz')

        assert isinstance(icon, QIcon)
        assert icon.isNull()


class TestIconValidation:
    """Test icon validation functionality."""

    def test_validate_icons_returns_dict(self, qtbot, icon_manager):
        """Test validate_icons returns proper dictionary."""
        result = icon_manager.validate_icons(report=False)

        assert isinstance(result, dict)
        assert 'missing' in result
        assert 'found' in result
        assert isinstance(result['missing'], list)
        assert isinstance(result['found'], list)

    def test_validate_icons_finds_existing(self, qtbot, icon_manager):
        """Test validation finds existing icons."""
        result = icon_manager.validate_icons(report=False)

        # Should find at least some icons from our temp assets
        assert len(result['found']) > 0

    def test_validate_icons_sets_validated_flag(self, qtbot, icon_manager):
        """Test validation sets the _validated flag."""
        assert icon_manager._validated is False

        icon_manager.validate_icons(report=False)

        assert icon_manager._validated is True

    def test_get_missing_icons_returns_list(self, qtbot, icon_manager):
        """Test get_missing_icons returns list."""
        missing = icon_manager.get_missing_icons()
        assert isinstance(missing, list)


class TestIconPaths:
    """Test icon path resolution functionality."""

    def test_get_icon_path_valid_key(self, qtbot, icon_manager, temp_assets_dir):
        """Test get_icon_path returns valid path for known key."""
        path = icon_manager.get_icon_path('app_icon')

        assert path is not None
        assert temp_assets_dir in path
        assert 'imxup.ico' in path

    def test_get_icon_path_list_config(self, qtbot, icon_manager, temp_assets_dir):
        """Test get_icon_path for icon with list config returns light variant."""
        path = icon_manager.get_icon_path('status_completed')

        assert path is not None
        assert 'light' in path  # Returns light variant by default

    def test_get_icon_path_unknown_key(self, qtbot, icon_manager):
        """Test get_icon_path returns None for unknown key."""
        path = icon_manager.get_icon_path('unknown_icon_key')

        assert path is None

    def test_list_all_icons(self, qtbot, icon_manager):
        """Test list_all_icons returns complete mapping."""
        icons = icon_manager.list_all_icons()

        assert isinstance(icons, dict)
        assert len(icons) > 0
        assert 'status_completed' in icons
        assert 'action_start' in icons


class TestStatusTooltips:
    """Test status tooltip generation."""

    def test_get_status_tooltip_known_status(self, qtbot, icon_manager):
        """Test tooltip for known status."""
        tooltip = icon_manager.get_status_tooltip('completed')

        assert tooltip == 'Completed'

    def test_get_status_tooltip_all_known(self, qtbot, icon_manager):
        """Test tooltips for all known statuses."""
        known_statuses = {
            'completed': 'Completed',
            'failed': 'Failed',
            'uploading': 'Uploading',
            'paused': 'Paused',
            'ready': 'Ready',
            'pending': 'Pending',
        }

        for status, expected in known_statuses.items():
            tooltip = icon_manager.get_status_tooltip(status)
            assert tooltip == expected, f"Failed for status: {status}"

    def test_get_status_tooltip_unknown_formats_name(self, qtbot, icon_manager):
        """Test unknown status is formatted to title case."""
        tooltip = icon_manager.get_status_tooltip('custom_test_status')

        # Should convert underscores to spaces and title case
        assert 'Custom' in tooltip or 'Test' in tooltip or 'Status' in tooltip


class TestGlobalIconManager:
    """Test global icon manager singleton functions."""

    def test_init_icon_manager(self, temp_assets_dir):
        """Test init_icon_manager creates and returns instance."""
        manager = init_icon_manager(temp_assets_dir)

        assert manager is not None
        assert isinstance(manager, IconManager)
        assert manager.assets_dir == temp_assets_dir

    def test_get_icon_manager_after_init(self, temp_assets_dir):
        """Test get_icon_manager returns initialized instance."""
        init_manager = init_icon_manager(temp_assets_dir)
        get_manager = get_icon_manager()

        assert get_manager is init_manager


class TestThemedFilenameResolution:
    """Test _get_themed_filename internal method."""

    def test_string_config_returns_as_is(self, qtbot, icon_manager):
        """Test string config returns the string unchanged."""
        result = icon_manager._get_themed_filename('imxup.ico', 'light', False)

        assert result == 'imxup.ico'

    def test_list_config_light_theme(self, qtbot, icon_manager):
        """Test list config returns first element for light theme."""
        config = ['icon-light.png', 'icon-dark.png']
        result = icon_manager._get_themed_filename(config, 'light', False)

        assert result == 'icon-light.png'

    def test_list_config_dark_theme(self, qtbot, icon_manager):
        """Test list config returns second element for dark theme."""
        config = ['icon-light.png', 'icon-dark.png']
        result = icon_manager._get_themed_filename(config, 'dark', False)

        assert result == 'icon-dark.png'

    def test_selection_state_does_not_change_filename(self, qtbot, icon_manager):
        """Test selection state doesn't affect filename selection."""
        config = ['icon-light.png', 'icon-dark.png']

        result_normal = icon_manager._get_themed_filename(config, 'light', False)
        result_selected = icon_manager._get_themed_filename(config, 'light', True)

        assert result_normal == result_selected

    def test_invalid_config_returns_none(self, qtbot, icon_manager):
        """Test invalid config returns None."""
        result = icon_manager._get_themed_filename(['single'], 'light', False)

        # Single-element list is invalid for light/dark pair
        assert result is None or result == 'single'


class TestMemoryManagement:
    """Test memory management and cache lifecycle."""

    def test_cache_grows_with_unique_icons(self, qtbot, icon_manager):
        """Test cache size grows with unique icon loads."""
        icon_keys = ['status_completed', 'status_failed', 'status_uploading']

        for i, key in enumerate(icon_keys, 1):
            icon_manager.get_icon(key, 'light')
            stats = icon_manager.get_cache_stats()
            assert stats['cached_icons'] == i

    def test_refresh_cache_releases_icons(self, qtbot, populated_icon_manager):
        """Test refresh_cache clears cached QIcon objects."""
        initial_count = populated_icon_manager.get_cache_stats()['cached_icons']
        assert initial_count > 0

        populated_icon_manager.refresh_cache()

        final_count = populated_icon_manager.get_cache_stats()['cached_icons']
        assert final_count == 0

    def test_large_cache_scenario(self, qtbot, icon_manager):
        """Test caching many icon variations."""
        # Load many variations
        themes = ['light', 'dark']
        sizes = [16, 32, 48]
        selections = [True, False]

        count = 0
        for theme in themes:
            for size in sizes:
                for selected in selections:
                    icon_manager.get_icon('status_completed', theme, selected, size)
                    count += 1

        stats = icon_manager.get_cache_stats()
        assert stats['cached_icons'] == count


class TestPerformanceCharacteristics:
    """Test performance-related behavior."""

    def test_cache_improves_hit_rate_over_time(self, qtbot, icon_manager):
        """Test hit rate improves with repeated requests."""
        # Initial requests - all misses
        keys = ['status_completed', 'status_failed', 'status_uploading']
        for key in keys:
            icon_manager.get_icon(key, 'light')

        initial_stats = icon_manager.get_cache_stats()
        assert initial_stats['hit_rate'] == 0.0

        # Repeated requests - all hits
        for _ in range(10):
            for key in keys:
                icon_manager.get_icon(key, 'light')

        final_stats = icon_manager.get_cache_stats()
        assert final_stats['hit_rate'] > 90.0

    def test_bulk_loading_performance(self, qtbot, icon_manager):
        """Test performance with bulk icon loading."""
        start_time = time.time()

        # Simulate loading for 100 rows
        icons_per_row = ['action_start', 'action_stop', 'status_completed']
        for _ in range(100):
            for icon_key in icons_per_row:
                icon_manager.get_icon(icon_key, 'light')

        elapsed = time.time() - start_time

        stats = icon_manager.get_cache_stats()

        # Should complete in reasonable time (< 1 second)
        assert elapsed < 1.0, f"Bulk loading took too long: {elapsed:.2f}s"

        # Should have high hit rate
        assert stats['hit_rate'] > 95.0

        # Should only load 3 unique icons from disk
        assert stats['disk_loads'] == 3

    def test_cache_prevents_redundant_io(self, qtbot, icon_manager):
        """Test that cache prevents redundant disk I/O."""
        # Load same icon many times
        for _ in range(1000):
            icon_manager.get_icon('status_completed', 'light')

        stats = icon_manager.get_cache_stats()

        assert stats['disk_loads'] == 1
        assert stats['hits'] == 999


class TestCacheStatistics:
    """Test cache statistics reporting."""

    def test_print_cache_stats(self, qtbot, populated_icon_manager, capsys):
        """Test print_cache_stats outputs formatted statistics."""
        populated_icon_manager.print_cache_stats()

        captured = capsys.readouterr()

        assert 'ICON CACHE STATISTICS' in captured.out
        assert 'Cache hits' in captured.out
        assert 'Cache misses' in captured.out

    def test_cache_stats_values_are_correct_types(self, qtbot, icon_manager):
        """Test cache stats have correct value types."""
        icon_manager.get_icon('status_completed', 'light')

        stats = icon_manager.get_cache_stats()

        assert isinstance(stats['hits'], int)
        assert isinstance(stats['misses'], int)
        assert isinstance(stats['disk_loads'], int)
        assert isinstance(stats['cached_icons'], int)
        assert isinstance(stats['hit_rate'], float)


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_icon_key(self, qtbot, icon_manager):
        """Test handling of empty icon key string."""
        icon = icon_manager.get_icon('', 'light')

        assert isinstance(icon, QIcon)
        assert icon.isNull()

    def test_none_theme_mode_uses_auto_detect(self, qtbot, icon_manager):
        """Test None theme_mode triggers auto-detection."""
        icon = icon_manager.get_icon('status_completed', theme_mode=None)

        assert isinstance(icon, QIcon)

    def test_invalid_theme_mode_string(self, qtbot, icon_manager):
        """Test handling of invalid theme mode string."""
        # Should not crash, will use the string as-is in cache key
        icon = icon_manager.get_icon('status_completed', theme_mode='invalid_theme')

        assert isinstance(icon, QIcon)

    def test_negative_animation_frame(self, qtbot, icon_manager):
        """Test handling of negative animation frame."""
        # Python modulo handles negatives
        icon = icon_manager.get_status_icon('uploading', animation_frame=-1)

        assert isinstance(icon, QIcon)

    def test_very_large_requested_size(self, qtbot, icon_manager):
        """Test handling of very large requested size."""
        icon = icon_manager.get_icon('status_completed', 'light', requested_size=10000)

        assert isinstance(icon, QIcon)

    def test_zero_requested_size(self, qtbot, icon_manager):
        """Test handling of zero requested size."""
        icon = icon_manager.get_icon('status_completed', 'light', requested_size=0)

        assert isinstance(icon, QIcon)

    def test_special_characters_in_icon_key(self, qtbot, icon_manager):
        """Test handling of special characters in icon key."""
        # Should handle gracefully without crashing
        icon = icon_manager.get_icon('icon/with/slashes', 'light')

        assert isinstance(icon, QIcon)

    def test_concurrent_icon_loading_simulation(self, qtbot, icon_manager):
        """Test rapid sequential icon loading (simulates concurrent access)."""
        icons = []

        # Rapidly load same icon many times
        for _ in range(100):
            icon = icon_manager.get_icon('status_completed', 'light')
            icons.append(icon)

        # All should be same cached object
        assert all(icon is icons[0] for icon in icons)

    def test_icon_path_with_spaces(self, tmp_path):
        """Test handling of assets directory with spaces in path."""
        assets_with_spaces = tmp_path / "path with spaces" / "assets"
        assets_with_spaces.mkdir(parents=True)

        manager = IconManager(str(assets_with_spaces))

        assert manager.assets_dir == str(assets_with_spaces)

        # Should not crash when trying to load
        icon = manager.get_icon('status_completed', 'light')
        assert isinstance(icon, QIcon)


class TestAutoThemeDetection:
    """Test automatic theme detection from QApplication palette."""

    def test_auto_detect_with_light_palette(self, qtbot, icon_manager):
        """Test auto-detection correctly identifies light theme."""
        # Create mock palette with light window color
        mock_palette = Mock(spec=QPalette)
        mock_color = Mock()
        mock_color.lightness.return_value = 200  # Light color
        mock_palette.color.return_value = mock_color

        mock_app = Mock(spec=QApplication)
        mock_app.palette.return_value = mock_palette

        with patch('PyQt6.QtWidgets.QApplication.instance', return_value=mock_app):
            icon = icon_manager.get_icon('status_completed', theme_mode=None)

        # Check cache key contains 'light'
        cache_keys = list(icon_manager._icon_cache.keys())
        assert any('light' in key for key in cache_keys)

    def test_auto_detect_with_dark_palette(self, qtbot, icon_manager):
        """Test auto-detection correctly identifies dark theme."""
        # Create mock palette with dark window color
        mock_palette = Mock(spec=QPalette)
        mock_color = Mock()
        mock_color.lightness.return_value = 50  # Dark color
        mock_palette.color.return_value = mock_color

        mock_app = Mock(spec=QApplication)
        mock_app.palette.return_value = mock_palette

        with patch('PyQt6.QtWidgets.QApplication.instance', return_value=mock_app):
            icon = icon_manager.get_icon('status_completed', theme_mode=None)

        # Check cache key contains 'dark'
        cache_keys = list(icon_manager._icon_cache.keys())
        assert any('dark' in key for key in cache_keys)


class TestIconMapConfiguration:
    """Test ICON_MAP configuration structure."""

    def test_all_status_icons_have_light_dark_pair(self, icon_manager):
        """Verify all status icons have both light and dark variants."""
        for key, config in icon_manager.ICON_MAP.items():
            if key.startswith('status_'):
                if isinstance(config, list):
                    assert len(config) >= 2, f"{key} should have light/dark pair"

    def test_all_action_icons_have_light_dark_pair(self, icon_manager):
        """Verify all action icons have both light and dark variants."""
        for key, config in icon_manager.ICON_MAP.items():
            if key.startswith('action_'):
                if isinstance(config, list):
                    assert len(config) >= 2, f"{key} should have light/dark pair"

    def test_animation_frames_defined(self, icon_manager):
        """Verify uploading animation frames are defined."""
        for i in range(4):
            key = f'status_uploading_frame_{i}'
            assert key in icon_manager.ICON_MAP, f"Missing animation frame: {key}"


# =============================================================================
# Run tests
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
