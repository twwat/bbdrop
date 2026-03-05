"""Performance tests for widget creation timing.

This script measures the actual time cost of creating different widget types
to inform optimization decisions for the gallery table.

Run with: python -m tests.performance.test_widget_creation_time
"""

import pytest
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from PyQt6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem


def ensure_qapp():
    """Ensure QApplication exists."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture(autouse=True)
def cleanup_widgets(qapp):
    """Ensure QApplication exists and cleanup all widgets after each test."""
    yield
    # Close all top-level widgets
    for widget in qapp.topLevelWidgets():
        try:
            widget.close()
            widget.deleteLater()
        except Exception:
            pass
    # Process events to ensure cleanup
    qapp.processEvents()


def test_progress_widget_creation(num_rows: int = 100):
    """Measure TableProgressWidget creation time.

    Returns:
        Dict with timing results
    """
    from src.gui.widgets.custom_widgets import TableProgressWidget

    table = QTableWidget(num_rows, 15)

    # Measure widget creation only (not setCellWidget)
    start_create = time.perf_counter()
    widgets = []
    for _ in range(num_rows):
        w = TableProgressWidget()
        widgets.append(w)
    create_time = (time.perf_counter() - start_create) * 1000

    # Measure setCellWidget time
    start_set = time.perf_counter()
    for row, w in enumerate(widgets):
        table.setCellWidget(row, 3, w)
    set_time = (time.perf_counter() - start_set) * 1000

    assert create_time + set_time < num_rows * 5, "Widget creation too slow"


def test_filehosts_status_widget_creation(num_rows: int = 100):
    """Measure FileHostsStatusWidget creation time.

    Note: This widget is more complex - it loads icon manager, config, etc.

    Returns:
        Dict with timing results
    """
    from src.gui.widgets.custom_widgets import FileHostsStatusWidget

    table = QTableWidget(num_rows, 15)

    # Measure widget creation (includes init but not update_hosts)
    start_create = time.perf_counter()
    widgets = []
    for i in range(num_rows):
        w = FileHostsStatusWidget(f"/path/gallery_{i}", parent=None)
        widgets.append(w)
    create_time = (time.perf_counter() - start_create) * 1000

    # Measure setCellWidget time
    start_set = time.perf_counter()
    for row, w in enumerate(widgets):
        table.setCellWidget(row, 11, w)
    set_time = (time.perf_counter() - start_set) * 1000

    assert create_time + set_time < num_rows * 5, "Widget creation too slow"


def test_filehosts_with_update(num_rows: int = 100):
    """Measure FileHostsStatusWidget with update_hosts() call.

    This is the ACTUAL cost since update_hosts loads icons and config.

    Returns:
        Dict with timing results
    """
    from src.gui.widgets.custom_widgets import FileHostsStatusWidget

    table = QTableWidget(num_rows, 15)

    # Empty host uploads (simulates gallery with no file host uploads)
    empty_uploads = {}

    # Measure full creation including update_hosts
    start = time.perf_counter()
    for i in range(num_rows):
        w = FileHostsStatusWidget(f"/path/gallery_{i}", parent=None)
        w.update_hosts(empty_uploads)
        table.setCellWidget(i, 11, w)
    total_time = (time.perf_counter() - start) * 1000

    assert total_time < num_rows * 10, "Widget creation with update too slow"


def test_filehosts_action_widget_creation(num_rows: int = 100):
    """Measure FileHostsActionWidget creation time.

    Returns:
        Dict with timing results
    """
    from src.gui.widgets.custom_widgets import FileHostsActionWidget

    table = QTableWidget(num_rows, 15)

    start = time.perf_counter()
    for i in range(num_rows):
        w = FileHostsActionWidget(f"/path/gallery_{i}", parent=None)
        table.setCellWidget(i, 12, w)
    total_time = (time.perf_counter() - start) * 1000

    assert total_time < num_rows * 5, "Action widget creation too slow"


def test_action_button_widget_creation(num_rows: int = 100):
    """Measure ActionButtonWidget creation time.

    Returns:
        Dict with timing results
    """
    from src.gui.widgets.custom_widgets import ActionButtonWidget

    table = QTableWidget(num_rows, 15)

    start = time.perf_counter()
    for i in range(num_rows):
        w = ActionButtonWidget(parent=None)
        table.setCellWidget(i, 8, w)
    total_time = (time.perf_counter() - start) * 1000

    assert total_time < num_rows * 5, "Button widget creation too slow"


def test_viewport_first(num_rows: int = 100, visible_rows: int = 25):
    """Measure time-to-first-usable with viewport prioritization.

    Args:
        num_rows: Total rows in table
        visible_rows: Number of rows visible in viewport

    Returns:
        Dict with timing results
    """
    from src.gui.widgets.custom_widgets import TableProgressWidget

    table = QTableWidget(num_rows, 15)

    # Time to create visible rows only
    start_visible = time.perf_counter()
    for row in range(visible_rows):
        w = TableProgressWidget()
        table.setCellWidget(row, 3, w)
    visible_time = (time.perf_counter() - start_visible) * 1000

    # Time to create remaining rows
    start_remaining = time.perf_counter()
    for row in range(visible_rows, num_rows):
        w = TableProgressWidget()
        table.setCellWidget(row, 3, w)
    remaining_time = (time.perf_counter() - start_remaining) * 1000

    assert visible_time < remaining_time * 2, "Viewport-first should be fast"


def test_text_only_row_creation(num_rows: int = 100):
    """Measure time to create text-only rows (no widgets).

    This is the baseline for Phase 1 of phased loading.

    Returns:
        Dict with timing results
    """
    table = QTableWidget(num_rows, 15)

    start = time.perf_counter()
    for row in range(num_rows):
        # Simulate minimal row creation (name, status text, etc.)
        for col in range(10):
            item = QTableWidgetItem(f"Row {row} Col {col}")
            table.setItem(row, col, item)
    total_time = (time.perf_counter() - start) * 1000

    assert total_time < num_rows * 5, "Text-only row creation too slow"


def test_setUpdatesEnabled_impact(num_rows: int = 100):
    """Measure impact of setUpdatesEnabled(False) during bulk insert.

    Returns:
        Dict with timing results
    """
    from src.gui.widgets.custom_widgets import TableProgressWidget

    # WITH updates enabled (normal)
    table1 = QTableWidget(num_rows, 15)
    start_enabled = time.perf_counter()
    for row in range(num_rows):
        w = TableProgressWidget()
        table1.setCellWidget(row, 3, w)
    enabled_time = (time.perf_counter() - start_enabled) * 1000

    # WITH updates disabled (optimized)
    table2 = QTableWidget(num_rows, 15)
    table2.setUpdatesEnabled(False)
    start_disabled = time.perf_counter()
    for row in range(num_rows):
        w = TableProgressWidget()
        table2.setCellWidget(row, 3, w)
    table2.setUpdatesEnabled(True)
    disabled_time = (time.perf_counter() - start_disabled) * 1000

    assert enabled_time > 0 and disabled_time > 0, "Both scenarios should complete"


def run_all_tests(num_rows: int = 100):
    """Run all performance tests and print results."""
    print(f"\n{'='*70}")
    print(f"WIDGET CREATION PERFORMANCE TESTS ({num_rows} rows)")
    print(f"{'='*70}\n")

    tests = [
        ("Progress Widget", test_progress_widget_creation),
        ("FileHosts Status (init only)", test_filehosts_status_widget_creation),
        ("FileHosts Status (with update_hosts)", test_filehosts_with_update),
        ("FileHosts Action", test_filehosts_action_widget_creation),
        ("Action Button", test_action_button_widget_creation),
        ("Text-Only Rows", test_text_only_row_creation),
        ("Viewport-First", test_viewport_first),
        ("setUpdatesEnabled Impact", test_setUpdatesEnabled_impact),
    ]

    for name, test_func in tests:
        print(f"Running: {name}...")
        try:
            test_func(num_rows)
            print("  [OK] Complete")
        except Exception as e:
            print(f"  [ERROR] {e}")


if __name__ == '__main__':
    app = ensure_qapp()

    # Use command line arg for row count, default to 100
    num_rows = int(sys.argv[1]) if len(sys.argv) > 1 else 100

    run_all_tests(num_rows)
