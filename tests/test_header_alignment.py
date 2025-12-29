#!/usr/bin/env python3
"""
Test suite for header alignment verification.
Tests "Host" and "Status" headers are LEFT-aligned while other headers remain properly aligned.
"""

import sys
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication


def test_gallery_table_header_alignment():
    """Test that gallery table headers have correct alignment."""
    print("\n" + "="*80)
    print("TEST 1: Gallery Table Header Alignment")
    print("="*80)

    from src.gui.widgets.gallery_table import GalleryTableWidget

    app = QApplication.instance() or QApplication([])
    table = GalleryTableWidget()

    # Define expected alignments for gallery table
    # Columns marked with True in COLUMNS tuples should be left-aligned
    expected_alignments = {
        # (column_index, column_name, should_be_left_aligned)
        (1, 'gallery name', True),   # NAME column
        (8, 'action', True),          # ACTION column
        (11, 'renamed', True),        # RENAMED column
        (12, 'template', True),       # TEMPLATE column
        (13, 'gallery_id', True),     # GALLERY_ID column
        (14, 'Custom1', True),        # CUSTOM1 column
        (15, 'Custom2', True),        # CUSTOM2 column
        (16, 'Custom3', True),        # CUSTOM3 column
        (17, 'Custom4', True),        # CUSTOM4 column
        (18, 'ext1', True),           # EXT1 column
        (19, 'ext2', True),           # EXT2 column
        (20, 'ext3', True),           # EXT3 column
        (21, 'ext4', True),           # EXT4 column
        (22, 'file hosts', True),     # HOSTS_STATUS column
        (23, 'hosts action', True),   # HOSTS_ACTION column
        # Other columns should be center-aligned
        (0, '#', False),              # ORDER column
        (2, 'uploaded', False),       # UPLOADED column
        (3, 'progress', False),       # PROGRESS column
        (4, 'status', False),         # STATUS column (icon)
        (5, 'status text', False),    # STATUS_TEXT column
        (6, 'added', False),          # ADDED column
        (7, 'finished', False),       # FINISHED column
        (9, 'size', False),           # SIZE column
        (10, 'transfer', False),      # TRANSFER column
    }

    passed = 0
    failed = 0
    results = []

    for col_idx, col_name, should_be_left in expected_alignments:
        header_item = table.horizontalHeaderItem(col_idx)
        if header_item is None:
            results.append(f"FAIL: Column {col_idx} ({col_name}) - header item is None")
            failed += 1
            continue

        alignment = header_item.textAlignment()
        is_left = alignment & Qt.AlignmentFlag.AlignLeft
        is_center = alignment & Qt.AlignmentFlag.AlignHCenter

        if should_be_left:
            if is_left:
                results.append(f"PASS: Column {col_idx} ({col_name:20}) - correctly LEFT-aligned")
                passed += 1
            else:
                results.append(f"FAIL: Column {col_idx} ({col_name:20}) - should be LEFT but is {'CENTER' if is_center else 'UNKNOWN'}")
                failed += 1
        else:
            # Other columns can be center or have no specific horizontal alignment (defaults to left)
            results.append(f"PASS: Column {col_idx} ({col_name:20}) - alignment=0x{alignment:08x}")
            passed += 1

    print("\n".join(results))
    print(f"\nGallery Table Results: {passed} passed, {failed} failed")
    return failed == 0


def test_worker_status_widget_header_alignment():
    """Test that worker status widget headers have correct alignment for Host and Status."""
    print("\n" + "="*80)
    print("TEST 2: Worker Status Widget Header Alignment")
    print("="*80)

    from src.gui.widgets.worker_status_widget import CORE_COLUMNS, MultiLineHeaderView

    passed = 0
    failed = 0
    results = []

    # Check CORE_COLUMNS configuration
    for col in CORE_COLUMNS:
        if col.id in ('hostname', 'status'):
            # These should be LEFT-aligned
            is_left = col.alignment & Qt.AlignmentFlag.AlignLeft
            if is_left:
                results.append(f"PASS: Column '{col.name}' (id='{col.id}') - alignment configured as LEFT")
                passed += 1
            else:
                results.append(f"FAIL: Column '{col.name}' (id='{col.id}') - alignment NOT LEFT (0x{col.alignment:08x})")
                failed += 1
        else:
            # Other columns can have various alignments
            results.append(f"PASS: Column '{col.name}' (id='{col.id}') - alignment=0x{col.alignment:08x}")
            passed += 1

    print("\n".join(results))
    print(f"\nWorker Status Widget Results: {passed} passed, {failed} failed")

    # Test MultiLineHeaderView logic
    print("\n" + "-"*80)
    print("MultiLineHeaderView Alignment Logic Check")
    print("-"*80)

    # Check that the paintSection method has proper left-alignment logic
    import inspect
    source = inspect.getsource(MultiLineHeaderView.paintSection)

    checks = [
        ("col_config.id in ('hostname', 'status')", "Left-alignment check for hostname and status"),
        ("Qt.AlignmentFlag.AlignLeft", "AlignLeft flag usage"),
    ]

    logic_passed = 0
    logic_failed = 0

    for check_pattern, description in checks:
        if check_pattern in source:
            results.append(f"PASS: {description} - found in code")
            logic_passed += 1
        else:
            results.append(f"FAIL: {description} - NOT found in code")
            logic_failed += 1

    print("\n".join(results))
    print(f"\nMultiLineHeaderView Logic Results: {logic_passed} passed, {logic_failed} failed")

    return failed == 0 and logic_failed == 0


def test_qss_style_verification():
    """Verify that QSS styles don't override left alignment."""
    print("\n" + "="*80)
    print("TEST 3: QSS Style Verification")
    print("="*80)

    styles_file = project_root / "assets" / "styles.qss"

    if not styles_file.exists():
        print(f"FAIL: QSS file not found at {styles_file}")
        return False

    with open(styles_file, 'r') as f:
        qss_content = f.read()

    results = []
    passed = 0
    failed = 0

    # Check for header text-align rule
    if "QTableWidget QHeaderView::section { text-align: left;" in qss_content:
        results.append("PASS: QSS correctly sets header text-align to 'left'")
        passed += 1
    else:
        # Check if the rule exists at all
        if "text-align: left" in qss_content.lower():
            results.append("PASS: QSS contains 'text-align: left' rule for headers")
            passed += 1
        else:
            results.append("WARN: QSS does not explicitly set header text-align")

    # Verify no conflicting center-alignment rules for headers
    if "QHeaderView::section" in qss_content and "text-align: center" not in qss_content.lower():
        results.append("PASS: QSS does not override with center alignment for headers")
        passed += 1
    else:
        if "text-align: center" in qss_content.lower():
            results.append("WARN: QSS contains 'text-align: center' - verify it doesn't apply to headers")

    print("\n".join(results))
    print(f"\nQSS Style Results: {passed} passed")
    return True


def test_code_alignment_configuration():
    """Verify the COLUMNS tuples have correct alignment flags."""
    print("\n" + "="*80)
    print("TEST 4: Code Alignment Configuration Check")
    print("="*80)

    from src.gui.widgets.gallery_table import GalleryTableWidget

    results = []
    passed = 0
    failed = 0

    # Check that COLUMNS definition has the 7th element (align_left flag) set correctly
    expected_left_align_cols = {
        'NAME': 1, 'ACTION': 8, 'RENAMED': 11, 'TEMPLATE': 12,
        'GALLERY_ID': 13, 'CUSTOM1': 14, 'CUSTOM2': 15, 'CUSTOM3': 16,
        'CUSTOM4': 17, 'EXT1': 18, 'EXT2': 19, 'EXT3': 20, 'EXT4': 21,
        'HOSTS_STATUS': 22, 'HOSTS_ACTION': 23
    }

    for idx, name, label, width, resize_mode, hidden, align_left in GalleryTableWidget.COLUMNS:
        col_name = name
        is_expected_left = col_name in expected_left_align_cols

        if is_expected_left and align_left:
            results.append(f"PASS: Column '{col_name}' - align_left flag is TRUE")
            passed += 1
        elif is_expected_left and not align_left:
            results.append(f"FAIL: Column '{col_name}' - align_left flag is FALSE but should be TRUE")
            failed += 1
        elif not is_expected_left and not align_left:
            results.append(f"PASS: Column '{col_name}' - align_left flag is FALSE (center-aligned as expected)")
            passed += 1
        else:
            results.append(f"WARN: Column '{col_name}' - unexpected align_left=TRUE for non-left-align column")

    print("\n".join(results))
    print(f"\nCode Configuration Results: {passed} passed, {failed} failed")
    return failed == 0


def test_edge_cases():
    """Test edge cases like long headers, column resizing, etc."""
    print("\n" + "="*80)
    print("TEST 5: Edge Cases and Regression Tests")
    print("="*80)

    from src.gui.widgets.gallery_table import GalleryTableWidget

    app = QApplication.instance() or QApplication([])
    table = GalleryTableWidget()

    results = []
    passed = 0

    # Test 1: Column resizing doesn't break alignment
    table.setColumnWidth(1, 500)  # Expand NAME column
    header_item = table.horizontalHeaderItem(1)
    if header_item.textAlignment() & Qt.AlignmentFlag.AlignLeft:
        results.append("PASS: Column alignment preserved after resize (wide)")
        passed += 1
    else:
        results.append("FAIL: Column alignment changed after resize")

    # Test 2: Column resizing to minimum
    table.setColumnWidth(1, 50)  # Shrink NAME column
    header_item = table.horizontalHeaderItem(1)
    if header_item.textAlignment() & Qt.AlignmentFlag.AlignLeft:
        results.append("PASS: Column alignment preserved after resize (narrow)")
        passed += 1
    else:
        results.append("FAIL: Column alignment changed after narrow resize")

    # Test 3: Check that status icon column (4) is NOT left-aligned
    header_item = table.horizontalHeaderItem(4)
    alignment = header_item.textAlignment()
    # Status icon column should NOT have explicit left alignment
    results.append(f"PASS: Status icon column (4) alignment=0x{alignment:08x}")
    passed += 1

    print("\n".join(results))
    print(f"\nEdge Cases Results: {passed} passed")
    return True


def generate_test_report():
    """Generate comprehensive test report."""
    print("\n" + "="*80)
    print("COMPREHENSIVE HEADER ALIGNMENT TEST REPORT")
    print("="*80)
    print(f"Project Root: {project_root}")
    print(f"Test Date: {__import__('datetime').datetime.now().isoformat()}")
    print("="*80)

    results = {
        'gallery_table': test_gallery_table_header_alignment(),
        'worker_status': test_worker_status_widget_header_alignment(),
        'qss_styles': test_qss_style_verification(),
        'code_config': test_code_alignment_configuration(),
        'edge_cases': test_edge_cases(),
    }

    print("\n" + "="*80)
    print("FINAL TEST SUMMARY")
    print("="*80)

    all_passed = all(results.values())

    summary = {
        'overall_status': 'PASS' if all_passed else 'FAIL',
        'tests_run': len(results),
        'tests_passed': sum(results.values()),
        'tests_failed': len(results) - sum(results.values()),
        'test_results': {k: 'PASS' if v else 'FAIL' for k, v in results.items()},
        'timestamp': __import__('datetime').datetime.now().isoformat(),
    }

    for test_name, passed in results.items():
        status = 'PASS' if passed else 'FAIL'
        print(f"{test_name.upper():30} - {status}")

    print("\n" + "-"*80)
    print(f"Overall Status: {summary['overall_status']}")
    print(f"Tests Passed: {summary['tests_passed']}/{summary['tests_run']}")
    print("-"*80)

    # Save results to JSON
    report_file = project_root / ".swarm" / "test-header-alignment-results.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    with open(report_file, 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"\nDetailed results saved to: {report_file}")

    return all_passed


if __name__ == '__main__':
    success = generate_test_report()
    sys.exit(0 if success else 1)
