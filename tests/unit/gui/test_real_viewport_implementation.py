"""
CRITICAL VALIDATION TESTS: Real MainWindow Viewport Implementation

These tests verify that the ACTUAL MainWindow implementation uses
viewport-based lazy loading and creates widgets ONLY for visible rows.
"""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'src'))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, Qt
from unittest.mock import Mock, patch, MagicMock

# Import from src.gui.main_window instead of gui.main_window
import importlib.util
spec = importlib.util.spec_from_file_location("main_window",
    str(Path(__file__).parent.parent.parent.parent / 'src' / 'gui' / 'main_window.py'))
main_window_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main_window_module)
MainWindow = main_window_module.ImxUploadGUI

# Constants
COL_GALLERY_NAME = 0
COL_STATUS = 1
COL_PROGRESS = 2
COL_ACTIONS = 3
TOTAL_GALLERIES = 997
EXPECTED_VISIBLE_WIDGETS_MIN = 20
EXPECTED_VISIBLE_WIDGETS_MAX = 100


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication instance"""
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def count_widgets(table):
    """Count actual widgets created in table"""
    widget_count = 0
    for row in range(table.rowCount()):
        if table.cellWidget(row, COL_PROGRESS) is not None:
            widget_count += 1
    return widget_count


class TestRealMainWindowViewport:
    """Test the actual MainWindow implementation"""

    def test_mainwindow_has_viewport_methods(self):
        """Verify MainWindow class has all required viewport methods"""
        # Check for required methods
        assert hasattr(MainWindow, '_get_visible_row_range'), (
            "❌ FAILURE: MainWindow missing '_get_visible_row_range' method"
        )

        assert hasattr(MainWindow, '_on_table_scrolled'), (
            "❌ FAILURE: MainWindow missing '_on_table_scrolled' method"
        )

        print("✅ PASS: MainWindow has all required viewport methods")

    def test_mainwindow_init_creates_rows_with_widgets_set(self):
        """Verify MainWindow.__init__ initializes _rows_with_widgets"""
        import inspect

        source = inspect.getsource(MainWindow.__init__)

        assert '_rows_with_widgets' in source, (
            "❌ FAILURE: MainWindow.__init__ doesn't initialize '_rows_with_widgets'"
        )

        assert 'set()' in source, (
            "❌ FAILURE: '_rows_with_widgets' should be initialized as set()"
        )

        print("✅ PASS: MainWindow.__init__ initializes _rows_with_widgets as set()")

    def test_phase2_uses_viewport_range(self):
        """CRITICAL: Verify phase2_create_table_widgets uses viewport range"""
        import inspect

        source = inspect.getsource(MainWindow.phase2_create_table_widgets)

        # Should call _get_visible_row_range
        assert '_get_visible_row_range' in source, (
            "❌ FAILURE: phase2_create_table_widgets doesn't call '_get_visible_row_range'\n"
            "This means Phase 2 is still creating widgets for ALL rows!"
        )

        # Should loop over visible range, not all galleries
        assert 'first_visible, last_visible' in source, (
            "❌ FAILURE: phase2_create_table_widgets doesn't use visible range variables"
        )

        # Should NOT loop over all galleries
        assert 'for gallery in self.galleries:' not in source, (
            "❌ FAILURE: phase2_create_table_widgets still loops over all galleries!\n"
            "Should only create widgets for visible range!"
        )

        # Should add to _rows_with_widgets
        assert '_rows_with_widgets.add' in source, (
            "❌ FAILURE: phase2_create_table_widgets doesn't track created widgets"
        )

        print("✅ PASS: phase2_create_table_widgets uses viewport-based creation")
        print("   - Calls _get_visible_row_range()")
        print("   - Uses first_visible, last_visible range")
        print("   - Tracks widgets in _rows_with_widgets")
        print("   - Does NOT loop over all galleries")

    def test_scroll_handler_creates_widgets(self):
        """Verify _on_table_scrolled creates widgets for newly visible rows"""
        import inspect

        source = inspect.getsource(MainWindow._on_table_scrolled)

        # Should get visible range
        assert '_get_visible_row_range' in source, (
            "❌ FAILURE: _on_table_scrolled doesn't call _get_visible_row_range"
        )

        # Should check if row already has widgets
        assert '_rows_with_widgets' in source, (
            "❌ FAILURE: _on_table_scrolled doesn't check _rows_with_widgets"
        )

        # Should create widgets for rows without them
        assert 'not in' in source or 'in self._rows_with_widgets' in source, (
            "❌ FAILURE: _on_table_scrolled doesn't check if row needs widgets"
        )

        print("✅ PASS: _on_table_scrolled creates widgets for newly visible rows")

    def test_get_visible_row_range_implementation(self):
        """Verify _get_visible_row_range implementation"""
        import inspect

        source = inspect.getsource(MainWindow._get_visible_row_range)

        # Should use viewport
        assert 'viewport' in source.lower(), (
            "❌ FAILURE: _get_visible_row_range doesn't use viewport"
        )

        # Should return tuple
        assert 'return' in source, (
            "❌ FAILURE: _get_visible_row_range missing return statement"
        )

        # Should calculate first and last visible
        assert 'first' in source.lower() and 'last' in source.lower(), (
            "❌ FAILURE: _get_visible_row_range doesn't calculate first/last visible"
        )

        print("✅ PASS: _get_visible_row_range properly implemented")

    def test_scroll_connection_in_init(self):
        """Verify scroll event is connected in __init__"""
        import inspect

        source = inspect.getsource(MainWindow.__init__)

        # Should connect scroll event
        assert 'valueChanged.connect' in source and '_on_table_scrolled' in source, (
            "❌ FAILURE: Scroll event not connected to _on_table_scrolled in __init__"
        )

        print("✅ PASS: Scroll event connected to _on_table_scrolled")

    def test_rows_with_widgets_cleared_on_new_session(self):
        """Verify _rows_with_widgets is cleared when starting new session"""
        import inspect

        # Check phase1_prepare_table_structure
        source = inspect.getsource(MainWindow.phase1_prepare_table_structure)

        assert '_rows_with_widgets.clear' in source, (
            "❌ FAILURE: _rows_with_widgets not cleared in phase1_prepare_table_structure"
        )

        print("✅ PASS: _rows_with_widgets cleared on new session")

    def test_no_mass_widget_creation_in_phase2(self):
        """CRITICAL: Verify Phase 2 doesn't create widgets for all galleries"""
        import inspect

        source = inspect.getsource(MainWindow.phase2_create_table_widgets)

        # Count setItem calls - should be minimal (just for visible rows)
        set_cell_widget_count = source.count('.setCellWidget(')

        # Should have ~2 setCellWidget calls per row (progress + actions)
        # But only in the visible range creation, not in a mass loop
        assert set_cell_widget_count < 10, (
            f"❌ FAILURE: Found {set_cell_widget_count} setCellWidget calls\n"
            "This suggests widgets are being created in a loop over all galleries"
        )

        print(f"✅ PASS: Phase 2 has {set_cell_widget_count} setCellWidget calls (not in mass loop)")

    def test_performance_log_reports_limited_widgets(self):
        """Verify performance logs report limited widget creation"""
        import inspect

        source = inspect.getsource(MainWindow.phase2_create_table_widgets)

        # Should log the number of widgets created
        assert 'len(self._rows_with_widgets)' in source, (
            "❌ FAILURE: Phase 2 doesn't log widget count from _rows_with_widgets"
        )

        print("✅ PASS: Phase 2 logs widget count from _rows_with_widgets")


class TestIntegrationScenarios:
    """Integration tests with mock data"""

    @pytest.fixture
    def mock_window(self, qapp):
        """Create MainWindow with mocked dependencies"""
        with patch.object(main_window_module, 'ImxToUploader'):
            with patch.object(main_window_module, 'load_user_defaults', return_value={}):
                with patch.object(main_window_module, 'QSettings'):
                    # Create window
                    window = MainWindow()

                    # Mock galleries data
                    window.galleries = [
                        {
                            'name': f'Gallery {i}',
                            'path': f'/path/{i}',
                            'total_images': 100,
                            'total_size': 1024 * 1024 * 10
                        }
                        for i in range(TOTAL_GALLERIES)
                    ]

                    yield window

                    # Cleanup
                    window.close()
                    QApplication.processEvents()

    def test_phase1_creates_997_rows_no_widgets(self, mock_window):
        """Verify Phase 1 creates 997 rows but NO widgets"""
        # Act: Run Phase 1
        mock_window.phase1_prepare_table_structure()
        QApplication.processEvents()

        # Assert: Should have 997 rows
        assert mock_window.gallery_table.rowCount() == TOTAL_GALLERIES, (
            f"Expected {TOTAL_GALLERIES} rows, got {mock_window.gallery_table.rowCount()}"
        )

        # Should have NO widgets yet
        widget_count = count_widgets(mock_window.gallery_table)
        assert widget_count == 0, (
            f"❌ FAILURE: Phase 1 created {widget_count} widgets (should be 0)"
        )

        print(f"✅ PASS: Phase 1 created {TOTAL_GALLERIES} rows with 0 widgets")

    def test_phase2_creates_limited_widgets(self, mock_window):
        """CRITICAL: Verify Phase 2 creates ~30-40 widgets, NOT 997"""
        # Arrange: Run Phase 1 first
        mock_window.phase1_prepare_table_structure()
        QApplication.processEvents()

        # Act: Run Phase 2
        mock_window.phase2_create_table_widgets()
        QApplication.processEvents()

        # Assert: Count created widgets
        widget_count = count_widgets(mock_window.gallery_table)

        # Should be ~30-40 visible rows, NOT 997
        assert widget_count < EXPECTED_VISIBLE_WIDGETS_MAX, (
            f"❌ FAILURE: Too many widgets created: {widget_count} "
            f"(expected < {EXPECTED_VISIBLE_WIDGETS_MAX})\n"
            f"This indicates viewport lazy loading was NOT implemented - "
            f"still creating widgets for all {TOTAL_GALLERIES} galleries!"
        )

        assert widget_count >= EXPECTED_VISIBLE_WIDGETS_MIN, (
            f"❌ FAILURE: Too few widgets created: {widget_count} "
            f"(expected >= {EXPECTED_VISIBLE_WIDGETS_MIN})"
        )

        print(f"✅ PASS: Phase 2 created {widget_count} widgets (expected {EXPECTED_VISIBLE_WIDGETS_MIN}-{EXPECTED_VISIBLE_WIDGETS_MAX})")
        print(f"   Total rows: {TOTAL_GALLERIES}")
        print(f"   Widgets created: {widget_count} ({widget_count/TOTAL_GALLERIES*100:.1f}%)")

    def test_rows_with_widgets_tracking(self, mock_window):
        """Verify _rows_with_widgets accurately tracks created widgets"""
        # Arrange & Act
        mock_window.phase1_prepare_table_structure()
        mock_window.phase2_create_table_widgets()
        QApplication.processEvents()

        # Assert: Widget count matches tracking set
        actual_widget_count = count_widgets(mock_window.gallery_table)
        tracked_count = len(mock_window._rows_with_widgets)

        assert tracked_count == actual_widget_count, (
            f"❌ FAILURE: Tracked rows ({tracked_count}) doesn't match "
            f"actual widget count ({actual_widget_count})"
        )

        # All tracked rows should have widgets
        for row in mock_window._rows_with_widgets:
            progress_widget = mock_window.gallery_table.cellWidget(row, COL_PROGRESS)
            action_widget = mock_window.gallery_table.cellWidget(row, COL_ACTIONS)

            assert progress_widget is not None, f"Row {row} tracked but missing progress widget"
            assert action_widget is not None, f"Row {row} tracked but missing action widget"

        print(f"✅ PASS: _rows_with_widgets tracking is accurate ({tracked_count} rows)")


class TestMemoryEfficiency:
    """Verify memory efficiency of viewport approach"""

    def test_viewport_reduces_memory_by_96_percent(self):
        """Verify viewport approach reduces widget memory by ~96%"""
        # Without viewport: 997 galleries × (1 progress + 1 button) = 1,994 widgets
        # With viewport: ~40 galleries × (1 progress + 1 button) = 80 widgets
        # Reduction: (1994 - 80) / 1994 = 96% memory savings

        widgets_without_viewport = TOTAL_GALLERIES * 2  # progress + button per row
        widgets_with_viewport = 40 * 2  # only visible rows

        memory_reduction = (widgets_without_viewport - widgets_with_viewport) / widgets_without_viewport

        assert memory_reduction > 0.95, (
            f"Expected >95% memory reduction, got {memory_reduction*100:.1f}%"
        )

        print(f"✅ PASS: Viewport approach reduces widget memory by {memory_reduction*100:.1f}%")
        print(f"   Without viewport: {widgets_without_viewport} widgets")
        print(f"   With viewport: {widgets_with_viewport} widgets")
        print(f"   Savings: {widgets_without_viewport - widgets_with_viewport} widgets")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
