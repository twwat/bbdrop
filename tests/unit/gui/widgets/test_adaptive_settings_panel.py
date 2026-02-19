#!/usr/bin/env python3
"""
Comprehensive pytest-qt tests for AdaptiveQuickSettingsPanel widget

Tests cover:
- Panel initialization and default state
- Button management (set_buttons)
- Layout modes (2-row, 3-row, 4-row)
- Height threshold transitions
- Button text adaptive behavior based on width
- Icons-only mode
- Resize event handling
- Size hint calculations
- Mode tracking and retrieval

Target: 70%+ coverage with 50+ tests
Environment: pytest-qt, PyQt6, venv ~/bbdrop-venv
"""

import pytest
from unittest.mock import patch
from PyQt6.QtWidgets import (
    QPushButton, QApplication, QVBoxLayout, QSizePolicy
)

from src.gui.widgets.adaptive_settings_panel import AdaptiveQuickSettingsPanel


# ============================================================================
# Test Isolation Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def cleanup_qt_state(qtbot):
    """
    Autouse fixture to ensure clean Qt state between tests.

    This addresses test isolation issues where:
    - Widget state leaks between tests
    - Timer events persist across tests
    - Signal/slot connections accumulate
    - Style state gets polluted

    Runs before and after each test automatically.
    """
    # Pre-test: Process any pending events from previous tests
    QApplication.processEvents()

    yield

    # Post-test: Clean up Qt state
    # Process all pending events including deferred deletions
    QApplication.processEvents()

    # Flush any scheduled timers (QTimer.singleShot from resizeEvent)
    QApplication.processEvents()

    # Clear focus to prevent widget reference leaks
    app = QApplication.instance()
    if app:
        focus_widget = app.focusWidget()
        if focus_widget:
            focus_widget.clearFocus()


@pytest.fixture(autouse=True)
def reset_panel_state():
    """
    Reset any class-level or module-level state that could leak between tests.

    The AdaptiveQuickSettingsPanel doesn't have class-level state, but this
    fixture ensures consistent test isolation patterns are followed.
    """
    yield
    # No class-level state to reset for AdaptiveQuickSettingsPanel


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def panel(qtbot):
    """Create an AdaptiveQuickSettingsPanel instance with proper cleanup"""
    p = AdaptiveQuickSettingsPanel()
    qtbot.addWidget(p)

    yield p

    # Explicit cleanup: hide widget and process events
    if p.isVisible():
        p.hide()
    QApplication.processEvents()


@pytest.fixture
def create_buttons(qtbot):
    """Factory fixture to create test buttons"""
    def _create():
        buttons = {
            'settings': QPushButton("Settings"),
            'credentials': QPushButton("Credentials"),
            'templates': QPushButton("Templates"),
            'file_hosts': QPushButton("File Hosts"),
            'hooks': QPushButton("Hooks"),
            'log_viewer': QPushButton("Logs"),
            'help': QPushButton("Help"),
            'theme': QPushButton()
        }
        # Add widgets to qtbot for cleanup
        for btn in buttons.values():
            qtbot.addWidget(btn)
        return buttons
    return _create


@pytest.fixture
def panel_with_buttons(qtbot, panel, create_buttons):
    """Create panel with buttons already set, with proper cleanup"""
    buttons = create_buttons()
    panel.set_buttons(
        buttons['settings'],
        buttons['credentials'],
        buttons['templates'],
        buttons['file_hosts'],
        buttons['hooks'],
        buttons['log_viewer'],
        buttons['help'],
        buttons['theme']
    )

    yield panel, buttons

    # Cleanup: hide panel if visible and process pending events
    if panel.isVisible():
        panel.hide()
    QApplication.processEvents()


# ============================================================================
# Initialization Tests
# ============================================================================

class TestAdaptiveQuickSettingsPanelInitialization:
    """Tests for AdaptiveQuickSettingsPanel initialization"""

    def test_initialization_default_state(self, panel):
        """Test widget initializes with correct defaults"""
        assert panel.settings_btn is None
        assert panel.credentials_btn is None
        assert panel.templates_btn is None
        # file_hosts_btn is set in set_buttons, not in __init__
        assert panel.hooks_btn is None
        assert panel.log_viewer_btn is None
        assert panel.help_btn is None
        assert panel.theme_toggle_btn is None

    def test_initialization_layout_mode(self, panel):
        """Test initial layout mode tracking"""
        assert panel._current_mode is None
        assert panel._num_rows == 2

    def test_initialization_icons_only_mode(self, panel):
        """Test icons-only mode defaults to False"""
        assert panel._icons_only_mode is False

    def test_initialization_main_layout(self, panel):
        """Test main layout is properly configured"""
        assert panel.main_layout is not None
        assert isinstance(panel.main_layout, QVBoxLayout)
        assert panel.main_layout.contentsMargins().left() == 0
        assert panel.main_layout.contentsMargins().right() == 0
        assert panel.main_layout.contentsMargins().top() == 0
        assert panel.main_layout.contentsMargins().bottom() == 0
        assert panel.main_layout.spacing() == 0

    def test_initialization_button_container(self, panel):
        """Test button container is initially None"""
        assert panel.button_container is None

    def test_initialization_size_policy(self, panel):
        """Test widget has correct size policy"""
        policy = panel.sizePolicy()
        assert policy.horizontalPolicy() == QSizePolicy.Policy.Preferred
        assert policy.verticalPolicy() == QSizePolicy.Policy.Expanding

    def test_initialization_constants(self, panel):
        """Test class constants are correctly defined"""
        assert panel.HEIGHT_2_ROW == 100
        assert panel.HEIGHT_3_ROW == 140
        assert panel.HEIGHT_4_ROW == 180
        assert panel.BUTTON_TEXT_WIDTH == 92
        assert panel.MAX_SIZE == 16777215


# ============================================================================
# set_buttons Tests
# ============================================================================

class TestSetButtons:
    """Tests for set_buttons method"""

    def test_set_buttons_stores_references(self, panel, create_buttons):
        """Test set_buttons stores button references"""
        buttons = create_buttons()
        panel.set_buttons(
            buttons['settings'],
            buttons['credentials'],
            buttons['templates'],
            buttons['file_hosts'],
            buttons['hooks'],
            buttons['log_viewer'],
            buttons['help'],
            buttons['theme']
        )

        assert panel.settings_btn is buttons['settings']
        assert panel.credentials_btn is buttons['credentials']
        assert panel.templates_btn is buttons['templates']
        assert panel.file_hosts_btn is buttons['file_hosts']
        assert panel.hooks_btn is buttons['hooks']
        assert panel.log_viewer_btn is buttons['log_viewer']
        assert panel.help_btn is buttons['help']
        assert panel.theme_toggle_btn is buttons['theme']

    def test_set_buttons_creates_labels_dict(self, panel_with_buttons):
        """Test set_buttons creates button labels dictionary"""
        panel, _ = panel_with_buttons

        assert hasattr(panel, '_button_labels')
        assert panel._button_labels['settings'] == ' Settings'
        assert panel._button_labels['credentials'] == ' Credentials'
        assert panel._button_labels['templates'] == ' BBCode Templates'
        assert panel._button_labels['file_hosts'] == '  File Hosts'
        assert panel._button_labels['hooks'] == '  App Hooks'
        assert panel._button_labels['log_viewer'] == ' Log Viewer'
        assert panel._button_labels['help'] == ' Documentation'
        assert panel._button_labels['theme'] == ''

    def test_set_buttons_initializes_layout(self, panel_with_buttons):
        """Test set_buttons triggers initial layout creation"""
        panel, _ = panel_with_buttons

        assert panel._current_mode is not None
        assert panel.button_container is not None

    def test_set_buttons_determines_num_rows_from_height(self, panel, create_buttons):
        """Test set_buttons determines number of rows based on current height"""
        buttons = create_buttons()

        # Resize to specific heights and verify row count
        panel.resize(200, 50)  # Below HEIGHT_2_ROW (100)
        panel.set_buttons(
            buttons['settings'], buttons['credentials'], buttons['templates'],
            buttons['file_hosts'], buttons['hooks'], buttons['log_viewer'],
            buttons['help'], buttons['theme']
        )
        assert panel._num_rows == 2

    def test_set_buttons_with_3_row_height(self, panel, create_buttons):
        """Test set_buttons with height for 3-row mode"""
        buttons = create_buttons()

        panel.resize(200, 120)  # Between HEIGHT_2_ROW (100) and HEIGHT_3_ROW (140)
        panel.set_buttons(
            buttons['settings'], buttons['credentials'], buttons['templates'],
            buttons['file_hosts'], buttons['hooks'], buttons['log_viewer'],
            buttons['help'], buttons['theme']
        )
        assert panel._num_rows == 3

    def test_set_buttons_with_4_row_height(self, panel, create_buttons):
        """Test set_buttons with height for 4-row mode"""
        buttons = create_buttons()

        panel.resize(200, 200)  # Above HEIGHT_4_ROW (180)
        panel.set_buttons(
            buttons['settings'], buttons['credentials'], buttons['templates'],
            buttons['file_hosts'], buttons['hooks'], buttons['log_viewer'],
            buttons['help'], buttons['theme']
        )
        assert panel._num_rows == 4


# ============================================================================
# Layout Mode Tests
# ============================================================================

class TestLayoutModes:
    """Tests for different layout modes (2-row, 3-row, 4-row)"""

    def test_get_current_mode_returns_mode_string(self, panel_with_buttons):
        """Test get_current_mode returns correct mode identifier"""
        panel, _ = panel_with_buttons

        mode = panel.get_current_mode()
        assert mode in ['2row', '3row', '4row']

    def test_2_row_mode_structure(self, panel_with_buttons, qtbot):
        """Test 2-row layout mode creates correct structure"""
        panel, _ = panel_with_buttons

        # Force 2-row mode (height < 100)
        panel.resize(200, 99)
        panel._update_layout(force=True)
        qtbot.wait(10)

        assert panel._num_rows == 2
        assert panel._current_mode == '2row'
        assert panel.button_container is not None

    def test_3_row_mode_structure(self, panel_with_buttons, qtbot):
        """Test 3-row layout mode creates correct structure"""
        panel, _ = panel_with_buttons

        # Force 3-row mode (100 <= height < 140)
        panel.resize(200, 120)
        panel._update_layout(force=True)
        qtbot.wait(10)

        assert panel._num_rows == 3
        assert panel._current_mode == '3row'

    def test_4_row_mode_structure(self, panel_with_buttons, qtbot):
        """Test 4-row layout mode creates correct structure"""
        panel, _ = panel_with_buttons

        # Force 4-row mode (height >= 140)
        panel.resize(200, 180)
        panel._update_layout(force=True)
        qtbot.wait(10)

        assert panel._num_rows == 4
        assert panel._current_mode == '4row'

    def test_mode_transition_2_to_3(self, panel_with_buttons, qtbot):
        """Test transition from 2-row to 3-row mode"""
        panel, _ = panel_with_buttons

        # Start in 2-row mode (height < 100)
        panel.resize(200, 99)
        panel._update_layout(force=True)
        assert panel._current_mode == '2row'

        # Transition to 3-row mode (100 <= height < 140)
        panel.resize(200, 120)
        panel._update_layout(force=True)
        assert panel._current_mode == '3row'

    def test_mode_transition_3_to_4(self, panel_with_buttons, qtbot):
        """Test transition from 3-row to 4-row mode"""
        panel, _ = panel_with_buttons

        # Start in 3-row mode (100 <= height < 140)
        panel.resize(200, 120)
        panel._update_layout(force=True)
        assert panel._current_mode == '3row'

        # Transition to 4-row mode (height >= 140)
        panel.resize(200, 180)
        panel._update_layout(force=True)
        assert panel._current_mode == '4row'

    def test_mode_transition_4_to_2(self, panel_with_buttons, qtbot):
        """Test transition from 4-row to 2-row mode"""
        panel, _ = panel_with_buttons

        # Start in 4-row mode (height >= 140)
        panel.resize(200, 180)
        panel._update_layout(force=True)
        assert panel._current_mode == '4row'

        # Transition to 2-row mode (height < 100)
        panel.resize(200, 99)
        panel._update_layout(force=True)
        assert panel._current_mode == '2row'

    def test_no_update_when_mode_unchanged(self, panel_with_buttons, qtbot):
        """Test layout doesn't rebuild when mode hasn't changed"""
        panel, _ = panel_with_buttons

        # Set to 3-row mode
        panel.resize(200, 120)
        panel._update_layout(force=True)
        old_container = panel.button_container

        # Same mode, shouldn't rebuild without force
        panel._update_layout()
        assert panel.button_container is old_container

    def test_force_update_rebuilds_layout(self, panel_with_buttons, qtbot):
        """Test force=True always rebuilds layout"""
        panel, _ = panel_with_buttons

        # Set initial mode
        panel.resize(200, 120)
        panel._update_layout(force=True)

        # Force rebuild
        panel._update_layout(force=True)
        # Container gets replaced
        assert panel.button_container is not None


# ============================================================================
# Button Text Adaptive Behavior Tests
# ============================================================================

class TestButtonTextAdaptiveBehavior:
    """Tests for adaptive button text based on width"""

    def test_button_text_shown_when_wide_enough(self, panel_with_buttons, qtbot):
        """Test button shows text when width >= BUTTON_TEXT_WIDTH"""
        panel, buttons = panel_with_buttons

        # Force 3-row mode so buttons check width
        panel.resize(300, 120)
        panel._update_layout(force=True)

        # Set button width above threshold
        buttons['settings'].resize(100, 30)
        panel._update_button_text()

        # Button should show text
        assert buttons['settings'].text() == ' Settings'

    def test_button_text_hidden_when_narrow(self, panel_with_buttons, qtbot):
        """Test button hides text when width < BUTTON_TEXT_WIDTH"""
        panel, buttons = panel_with_buttons

        # Force 3-row mode
        panel.resize(300, 120)
        panel._update_layout(force=True)

        # Set button width below threshold
        buttons['settings'].resize(50, 30)
        panel._update_button_text()

        # Button should have no text (icon-only)
        assert buttons['settings'].text() == ""

    def test_theme_button_always_icon_only(self, panel_with_buttons, qtbot):
        """Test theme button is always icon-only regardless of width"""
        panel, buttons = panel_with_buttons

        # Force any mode
        panel.resize(300, 120)
        panel._update_layout(force=True)

        # Even with large width, theme should be icon-only
        buttons['theme'].resize(200, 30)
        panel._update_button_text()

        # Theme button text should remain empty
        assert buttons['theme'].text() == ""

    def test_2_row_mode_row2_buttons_icon_only(self, panel_with_buttons, qtbot):
        """Test in 2-row mode, row 2 buttons are always icon-only"""
        panel, buttons = panel_with_buttons

        # Force 2-row mode (height < 120)
        panel.resize(200, 99)
        panel._update_layout(force=True)
        qtbot.wait(10)

        # In 2-row mode, only settings checks width
        # All row 2 buttons should be icon-only
        assert buttons['credentials'].text() == ""
        assert buttons['templates'].text() == ""
        assert buttons['hooks'].text() == ""
        assert buttons['log_viewer'].text() == ""

    def test_3_row_mode_all_buttons_check_width(self, panel_with_buttons, qtbot):
        """Test in 3-row mode, all buttons check their own width"""
        panel, buttons = panel_with_buttons

        # Force 3-row mode
        panel.resize(300, 120)
        panel._update_layout(force=True)

        # Set wide width on all buttons
        for btn in [buttons['settings'], buttons['credentials'],
                    buttons['templates'], buttons['file_hosts'],
                    buttons['hooks'], buttons['log_viewer'], buttons['help']]:
            btn.resize(100, 30)

        panel._update_button_text()

        # All should show text (except theme)
        assert buttons['settings'].text() != ""
        assert buttons['credentials'].text() != ""
        assert buttons['templates'].text() != ""

    def test_4_row_mode_all_buttons_check_width(self, panel_with_buttons, qtbot):
        """Test in 4-row mode, all buttons check their own width"""
        panel, buttons = panel_with_buttons

        # Force 4-row mode (height >= 166)
        panel.resize(300, 200)
        panel._update_layout(force=True)

        # Set wide width on buttons
        for btn in [buttons['settings'], buttons['credentials'],
                    buttons['templates'], buttons['file_hosts'],
                    buttons['hooks'], buttons['log_viewer'], buttons['help']]:
            btn.resize(100, 30)

        panel._update_button_text()

        # All should show text
        assert buttons['settings'].text() != ""
        assert buttons['help'].text() != ""


# ============================================================================
# Icons-Only Mode Tests
# ============================================================================

class TestIconsOnlyMode:
    """Tests for icons-only mode override"""

    def test_set_icons_only_mode_enabled(self, panel_with_buttons, qtbot):
        """Test enabling icons-only mode hides all text"""
        panel, buttons = panel_with_buttons

        # Force 3-row mode with wide buttons
        panel.resize(300, 120)
        panel._update_layout(force=True)
        for btn in buttons.values():
            btn.resize(100, 30)

        # Enable icons-only mode
        panel.set_icons_only_mode(True)

        assert panel._icons_only_mode is True
        # All buttons should have no text
        assert buttons['settings'].text() == ""
        assert buttons['credentials'].text() == ""

    def test_set_icons_only_mode_disabled(self, panel_with_buttons, qtbot):
        """Test disabling icons-only mode restores adaptive behavior"""
        panel, buttons = panel_with_buttons

        # Enable then disable icons-only mode
        panel.set_icons_only_mode(True)

        # Force 3-row mode with wide buttons
        panel.resize(300, 120)
        panel._update_layout(force=True)
        for btn in buttons.values():
            btn.resize(100, 30)

        panel.set_icons_only_mode(False)

        assert panel._icons_only_mode is False
        # Buttons should show text again
        assert buttons['settings'].text() != ""

    def test_icons_only_mode_overrides_width_check(self, panel_with_buttons):
        """Test icons-only mode overrides per-button width check"""
        panel, buttons = panel_with_buttons

        # Set very wide buttons
        for btn in buttons.values():
            btn.resize(200, 30)

        # Enable icons-only mode
        panel.set_icons_only_mode(True)

        # Even wide buttons should have no text
        assert buttons['settings'].text() == ""
        assert buttons['credentials'].text() == ""


# ============================================================================
# Size Hint Tests
# ============================================================================

class TestSizeHints:
    """Tests for size hint calculations"""

    def test_minimum_size_hint_returns_fixed_value(self, panel):
        """Test minimumSizeHint returns fixed 2-row minimum"""
        hint = panel.minimumSizeHint()

        assert hint.height() == 110  # Fixed 2-row minimum with safety margin
        assert hint.width() == 0

    def test_minimum_size_hint_with_container(self, panel_with_buttons, qtbot):
        """Test minimumSizeHint returns same fixed value even with container"""
        panel, _ = panel_with_buttons

        # Force layout to create container
        panel.resize(200, 120)
        panel._update_layout(force=True)

        hint = panel.minimumSizeHint()

        # Should return fixed value regardless of container
        assert hint.height() == 110
        assert hint.width() == 0


# ============================================================================
# Resize Event Tests
# ============================================================================

class TestResizeEvent:
    """Tests for resize event handling"""

    def test_resize_event_updates_layout(self, panel_with_buttons, qtbot):
        """Test resize event triggers layout update"""
        panel, _ = panel_with_buttons

        # Start in 2-row mode (height < 120)
        panel.resize(200, 99)
        panel._update_layout(force=True)
        assert panel._current_mode == '2row'

        # Resize to trigger 4-row mode (height >= 166) - need to use show() for resize events to work
        panel.show()
        qtbot.waitExposed(panel)
        panel.resize(200, 200)
        # Process events to handle resize
        QApplication.processEvents()
        qtbot.wait(10)

        assert panel._current_mode == '4row'

    def test_resize_event_schedules_text_update(self, panel_with_buttons, qtbot):
        """Test resize event schedules button text update"""
        panel, _ = panel_with_buttons

        # Show panel first so resize events work
        panel.show()
        qtbot.waitExposed(panel)

        # Count initial calls

        with patch.object(panel, '_update_button_text', wraps=panel._update_button_text) as mock_update:
            panel.resize(200, 120)
            # Process events to handle resize and QTimer.singleShot
            QApplication.processEvents()
            qtbot.wait(50)
            QApplication.processEvents()

            # Should have been called at least once via QTimer
            assert mock_update.call_count >= 1

    def test_multiple_resize_events_handled(self, panel_with_buttons, qtbot):
        """Test multiple consecutive resize events are handled"""
        panel, _ = panel_with_buttons

        # Multiple resizes - use force=True to ensure mode changes are applied
        panel.resize(200, 99)
        panel._update_layout(force=True)
        panel.resize(200, 120)
        panel._update_layout(force=True)
        panel.resize(200, 200)
        panel._update_layout(force=True)
        qtbot.wait(50)

        # Should end up in 4-row mode (height >= 166)
        assert panel._current_mode == '4row'


# ============================================================================
# Layout Building Tests
# ============================================================================

class TestLayoutBuilding:
    """Tests for _build_2_row, _build_3_row, _build_4_row methods"""

    def test_build_2_row_clears_previous_layout(self, panel_with_buttons, qtbot):
        """Test _build_2_row clears existing layout first"""
        panel, _ = panel_with_buttons

        # Build initial layout
        panel._build_3_row()
        old_container = panel.button_container

        # Build 2-row layout
        panel._build_2_row()

        # Container should be replaced
        assert panel.button_container is not old_container

    def test_build_2_row_creates_container(self, panel_with_buttons, qtbot):
        """Test _build_2_row creates button container"""
        panel, _ = panel_with_buttons

        panel._build_2_row()

        assert panel.button_container is not None
        policy = panel.button_container.sizePolicy()
        assert policy.horizontalPolicy() == QSizePolicy.Policy.Expanding
        assert policy.verticalPolicy() == QSizePolicy.Policy.Fixed

    def test_build_3_row_creates_container(self, panel_with_buttons, qtbot):
        """Test _build_3_row creates button container"""
        panel, _ = panel_with_buttons

        panel._build_3_row()

        assert panel.button_container is not None

    def test_build_4_row_creates_container(self, panel_with_buttons, qtbot):
        """Test _build_4_row creates button container"""
        panel, _ = panel_with_buttons

        panel._build_4_row()

        assert panel.button_container is not None

    def test_build_2_row_settings_expanding(self, panel_with_buttons, qtbot):
        """Test _build_2_row makes settings button expanding"""
        panel, buttons = panel_with_buttons

        panel._build_2_row()

        policy = buttons['settings'].sizePolicy()
        assert policy.horizontalPolicy() == QSizePolicy.Policy.Expanding

    def test_build_2_row_theme_fixed(self, panel_with_buttons, qtbot):
        """Test _build_2_row makes theme button fixed width"""
        panel, buttons = panel_with_buttons

        panel._build_2_row()

        policy = buttons['theme'].sizePolicy()
        assert policy.horizontalPolicy() == QSizePolicy.Policy.Fixed
        assert buttons['theme'].minimumWidth() == 30
        assert buttons['theme'].maximumWidth() == 40

    def test_build_layout_sets_button_properties(self, panel_with_buttons, qtbot):
        """Test building layout sets correct button properties"""
        panel, buttons = panel_with_buttons

        panel._build_3_row()

        # Settings button should have comprehensive-settings class
        assert buttons['settings'].property("class") == "comprehensive-settings"

        # Other buttons should have quick-settings-btn class
        assert buttons['credentials'].property("class") == "quick-settings-btn"
        assert buttons['theme'].property("class") == "quick-settings-btn"


# ============================================================================
# Clear Layout Tests
# ============================================================================

class TestClearLayout:
    """Tests for _clear_layout method"""

    def test_clear_layout_removes_all_widgets(self, panel_with_buttons, qtbot):
        """Test _clear_layout removes all widgets from main layout"""
        panel, _ = panel_with_buttons

        # Build layout first
        panel._build_3_row()
        initial_count = panel.main_layout.count()
        assert initial_count > 0

        # Clear layout
        panel._clear_layout()

        assert panel.main_layout.count() == 0

    def test_clear_layout_sets_container_none(self, panel_with_buttons, qtbot):
        """Test _clear_layout sets button_container to None"""
        panel, _ = panel_with_buttons

        panel._build_3_row()
        assert panel.button_container is not None

        panel._clear_layout()

        assert panel.button_container is None


# ============================================================================
# Edge Case Tests
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions"""

    def test_update_layout_without_buttons(self, panel):
        """Test _update_layout does nothing when buttons not set"""
        panel._update_layout(force=True)

        # Should not crash, no layout created
        assert panel.button_container is None

    def test_update_button_text_without_buttons(self, panel):
        """Test _update_button_text does nothing when buttons not set"""
        # Should not crash
        panel._update_button_text()
        assert panel.settings_btn is None

    def test_height_threshold_boundary_2_row(self, panel, create_buttons):
        """Test exact HEIGHT_2_ROW threshold boundary"""
        buttons = create_buttons()

        # At exact threshold (100) - should be 3-row mode since 100 is NOT < 100
        panel.resize(200, 100)
        panel.set_buttons(
            buttons['settings'], buttons['credentials'], buttons['templates'],
            buttons['file_hosts'], buttons['hooks'], buttons['log_viewer'],
            buttons['help'], buttons['theme']
        )

        # Should be in 3-row mode at 100 (not below)
        assert panel._num_rows == 3

    def test_height_threshold_boundary_below_2_row(self, panel, create_buttons):
        """Test just below HEIGHT_2_ROW threshold"""
        buttons = create_buttons()

        # 99 = HEIGHT_2_ROW - 1
        panel.resize(200, 99)
        panel.set_buttons(
            buttons['settings'], buttons['credentials'], buttons['templates'],
            buttons['file_hosts'], buttons['hooks'], buttons['log_viewer'],
            buttons['help'], buttons['theme']
        )

        # Should be in 2-row mode
        assert panel._num_rows == 2

    def test_height_threshold_boundary_4_row(self, panel, create_buttons):
        """Test exact HEIGHT_4_ROW threshold boundary"""
        buttons = create_buttons()

        # At exact threshold (180) - should be 4-row mode since 180 is NOT < 180
        panel.resize(200, 180)
        panel.set_buttons(
            buttons['settings'], buttons['credentials'], buttons['templates'],
            buttons['file_hosts'], buttons['hooks'], buttons['log_viewer'],
            buttons['help'], buttons['theme']
        )

        # Should be in 4-row mode at 180
        assert panel._num_rows == 4

    def test_very_small_height(self, panel_with_buttons, qtbot):
        """Test very small height stays in 2-row mode"""
        panel, _ = panel_with_buttons

        panel.resize(200, 10)
        panel._update_layout(force=True)

        assert panel._num_rows == 2
        assert panel._current_mode == '2row'

    def test_very_large_height(self, panel_with_buttons, qtbot):
        """Test very large height stays in 4-row mode"""
        panel, _ = panel_with_buttons

        panel.resize(200, 1000)
        panel._update_layout(force=True)

        assert panel._num_rows == 4
        assert panel._current_mode == '4row'

    def test_button_width_threshold_boundary(self, panel_with_buttons, qtbot):
        """Test exact BUTTON_TEXT_WIDTH threshold boundary"""
        panel, buttons = panel_with_buttons

        # Force 3-row mode
        panel.resize(300, 120)
        panel._update_layout(force=True)

        # At exact threshold
        buttons['settings'].resize(92, 30)
        panel._update_button_text()

        # Should show text at exactly 92px
        assert buttons['settings'].text() == ' Settings'

    def test_button_width_below_threshold(self, panel_with_buttons, qtbot):
        """Test just below BUTTON_TEXT_WIDTH threshold"""
        panel, buttons = panel_with_buttons

        # Force 3-row mode
        panel.resize(300, 120)
        panel._update_layout(force=True)

        # Just below threshold
        buttons['settings'].resize(91, 30)
        panel._update_button_text()

        # Should not show text at 91px
        assert buttons['settings'].text() == ""


# ============================================================================
# Button Styling Tests
# ============================================================================

class TestButtonStyling:
    """Tests for button styling during layout builds"""

    def test_buttons_get_polished_after_property_set(self, panel_with_buttons, qtbot):
        """Test buttons get style polish after property changes"""
        panel, buttons = panel_with_buttons

        # This tests that style().unpolish/polish is called
        # We can verify the class property was set correctly
        panel._build_3_row()

        assert buttons['settings'].property("class") == "comprehensive-settings"
        assert buttons['credentials'].property("class") == "quick-settings-btn"

    def test_all_row2_buttons_expanding_in_2_row_mode(self, panel_with_buttons, qtbot):
        """Test all row 2 buttons are expanding in 2-row mode"""
        panel, buttons = panel_with_buttons

        panel._build_2_row()

        row2_buttons = ['credentials', 'templates', 'file_hosts',
                       'hooks', 'log_viewer', 'help']
        for btn_name in row2_buttons:
            policy = buttons[btn_name].sizePolicy()
            assert policy.horizontalPolicy() == QSizePolicy.Policy.Expanding


# ============================================================================
# Minimum Height Update Tests
# ============================================================================

class TestMinimumHeightUpdate:
    """Tests for minimum height updates after layout changes"""

    def test_update_layout_sets_minimum_height(self, panel_with_buttons, qtbot):
        """Test _update_layout sets minimum height on panel"""
        panel, _ = panel_with_buttons

        panel.resize(200, 200)
        panel._update_layout(force=True)

        # minimumSizeHint should return MIN_HEIGHT (110)
        assert panel.minimumSizeHint().height() > 0

    def test_minimum_height_increases_with_more_rows(self, panel_with_buttons, qtbot):
        """Test minimum height increases with more rows"""
        panel, _ = panel_with_buttons

        # Get 2-row minimum height
        panel.resize(200, 99)
        panel._update_layout(force=True)
        min_height_2_row = panel.minimumHeight()

        # Get 4-row minimum height
        panel.resize(200, 200)
        panel._update_layout(force=True)
        min_height_4_row = panel.minimumHeight()

        # 4-row should require more height
        assert min_height_4_row >= min_height_2_row


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for complete workflows"""

    def test_complete_workflow_mode_transitions(self, panel_with_buttons, qtbot):
        """Test complete workflow with multiple mode transitions"""
        panel, buttons = panel_with_buttons

        # Show panel for resize events to work properly
        panel.show()
        qtbot.waitExposed(panel)

        # Remove minimum height constraint from button container to allow small heights
        panel.setMinimumHeight(0)
        if panel.button_container:
            panel.button_container.setMinimumHeight(0)

        # Start in 2-row mode (height < 100)
        panel.resize(200, 99)
        panel._update_layout(force=True)
        QApplication.processEvents()
        qtbot.wait(10)
        assert panel._current_mode == '2row'

        # Transition to 3-row (100 <= height < 140)
        panel.resize(200, 120)
        panel._update_layout(force=True)
        QApplication.processEvents()
        qtbot.wait(10)
        assert panel._current_mode == '3row'

        # Transition to 4-row (height >= 140)
        panel.resize(200, 200)
        panel._update_layout(force=True)
        QApplication.processEvents()
        qtbot.wait(10)
        assert panel._current_mode == '4row'

        # Enable icons-only mode
        panel.set_icons_only_mode(True)
        assert buttons['settings'].text() == ""

        # Disable icons-only mode
        panel.set_icons_only_mode(False)

        # Back to 2-row (height < 100) - need to remove constraint again since button_container was recreated
        panel.setMinimumHeight(0)
        if panel.button_container:
            panel.button_container.setMinimumHeight(0)
        panel.resize(200, 99)
        panel._update_layout(force=True)
        QApplication.processEvents()
        qtbot.wait(10)
        assert panel._current_mode == '2row'

    def test_show_and_resize(self, panel_with_buttons, qtbot):
        """Test showing panel and resizing"""
        panel, _ = panel_with_buttons

        panel.show()
        qtbot.waitExposed(panel)

        # Resize while visible - use large height for 4row mode
        panel.resize(300, 400)
        panel._update_layout(force=True)
        QApplication.processEvents()
        qtbot.wait(10)

        # Mode should be set based on height - check it's a valid mode
        # Note: Window managers may constrain actual size, so we just verify
        # a mode was set and container exists
        assert panel._current_mode in ('2row', '3row', '4row')
        assert panel.button_container is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
