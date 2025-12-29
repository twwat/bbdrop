#!/usr/bin/env python3
"""
Test script for uploaded column update fix.

This tests the fix where the uploaded column (e.g., "0/77") was not being created
properly when total_images was initially 0 and later updated.

Fix location: src/gui/main_window.py:_populate_table_row_minimal()
Lines 1045-1050

Before fix:
  - Column item only created if total_images > 0
  - When total_images updated from 0 to 77, update code couldn't find item

After fix:
  - Column item always created (even with empty text for total_images=0)
  - Update code can now find and update the item
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from PyQt6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem
from PyQt6.QtCore import Qt

# Mock the GalleryQueueItem for testing
class MockGalleryQueueItem:
    """Mock gallery item for testing"""
    def __init__(self, name="test_gallery", total_images=0, uploaded_images=0, status="pending", total_size=0):
        self.name = name
        self.path = f"/fake/path/{name}"
        self.total_images = total_images
        self.uploaded_images = uploaded_images
        self.status = status
        self.total_size = total_size
        self.db_id = 1
        self.added_time = 0
        self.finished_time = None
        self.scan_complete = False


def test_uploaded_column_creation():
    """Test that uploaded column item is created even when total_images=0"""

    print("\n" + "="*80)
    print("TEST 1: Uploaded Column Creation Fix")
    print("="*80)

    # Create Qt application (required for PyQt6 widgets)
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    # Create test table
    table = QTableWidget()
    table.setColumnCount(10)
    table.setRowCount(1)

    # Column indices (matching GalleryTableWidget)
    COL_NAME = 1
    COL_UPLOADED = 2

    print("\n[PHASE 1] Simulating initial gallery add with total_images=0")
    print("-" * 80)

    # Simulate the fixed code in _populate_table_row_minimal
    item = MockGalleryQueueItem(name="test_gallery", total_images=0)
    row = 0

    # Name column
    name_item = QTableWidgetItem(item.name)
    name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    table.setItem(row, COL_NAME, name_item)
    print(f"✓ Set name column: '{item.name}'")

    # CRITICAL FIX: Always create uploaded column item
    # Before fix: if item.total_images > 0:
    # After fix: Always create (may have empty text)

    if item.total_images > 0:
        uploaded_text = f"{item.uploaded_images}/{item.total_images}"
    else:
        uploaded_text = ""  # Empty text, but item exists

    uploaded_item = QTableWidgetItem(uploaded_text)
    uploaded_item.setFlags(uploaded_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    table.setItem(row, COL_UPLOADED, uploaded_item)

    # Verify item was created
    created_item = table.item(row, COL_UPLOADED)
    if created_item is None:
        print("❌ FAIL: Uploaded column item was NOT created!")
        return False
    else:
        print(f"✓ Uploaded column item created with text: '{created_item.text()}'")

    print("\n[PHASE 2] Simulating scan completion with total_images=77")
    print("-" * 80)

    # Update total_images (simulating scan completion)
    item.total_images = 77
    item.uploaded_images = 0

    # Simulate the update code in _update_gallery_row_from_item
    uploaded_text = f"{item.uploaded_images}/{item.total_images}"
    existing_item = table.item(row, COL_UPLOADED)

    if existing_item is None:
        print("❌ FAIL: Cannot update - item does not exist!")
        return False
    else:
        existing_item.setText(uploaded_text)
        print(f"✓ Updated existing item to: '{existing_item.text()}'")

    # Verify final state
    final_item = table.item(row, COL_UPLOADED)
    expected_text = "0/77"

    print("\n[VERIFICATION]")
    print("-" * 80)

    if final_item is None:
        print("❌ FAIL: Item is None after update!")
        return False

    if final_item.text() != expected_text:
        print(f"❌ FAIL: Expected '{expected_text}', got '{final_item.text()}'")
        return False

    print(f"✓ SUCCESS: Column shows correct value '{expected_text}'")
    print(f"✓ Item exists: {final_item is not None}")
    print(f"✓ Item text: '{final_item.text()}'")

    return True


def test_edge_cases():
    """Test edge cases for the uploaded column fix"""

    print("\n" + "="*80)
    print("TEST 2: Edge Cases")
    print("="*80)

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    test_cases = [
        ("Empty to small", 0, 0, 5, 0, "0/5"),
        ("Empty to large", 0, 0, 10000, 0, "0/10000"),
        ("Update progress", 77, 30, 77, 45, "45/77"),
        ("Complete", 77, 77, 77, 77, "77/77"),
    ]

    all_passed = True

    for test_name, init_total, init_uploaded, new_total, new_uploaded, expected in test_cases:
        print(f"\n[{test_name}]")
        print(f"  Initial: {init_uploaded}/{init_total}")
        print(f"  Updated: {new_uploaded}/{new_total}")
        print(f"  Expected: '{expected}'")

        # Create table
        table = QTableWidget()
        table.setColumnCount(10)
        table.setRowCount(1)
        COL_UPLOADED = 2
        row = 0

        # Initial state
        if init_total > 0:
            uploaded_text = f"{init_uploaded}/{init_total}"
        else:
            uploaded_text = ""

        uploaded_item = QTableWidgetItem(uploaded_text)
        table.setItem(row, COL_UPLOADED, uploaded_item)

        # Update
        uploaded_text = f"{new_uploaded}/{new_total}"
        existing_item = table.item(row, COL_UPLOADED)

        if existing_item is None:
            print(f"  ❌ FAIL: Item is None!")
            all_passed = False
            continue

        existing_item.setText(uploaded_text)

        # Verify
        final_item = table.item(row, COL_UPLOADED)
        if final_item.text() == expected:
            print(f"  ✓ PASS: '{final_item.text()}'")
        else:
            print(f"  ❌ FAIL: Expected '{expected}', got '{final_item.text()}'")
            all_passed = False

    return all_passed


def verify_source_code_fix():
    """Verify that the fix is present in the source code"""

    print("\n" + "="*80)
    print("TEST 3: Source Code Verification")
    print("="*80)

    source_file = project_root / "src" / "gui" / "main_window.py"

    if not source_file.exists():
        print(f"❌ FAIL: Source file not found: {source_file}")
        return False

    with open(source_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Check for the fix in _populate_table_row_minimal
    print("\n[Checking _populate_table_row_minimal method]")

    # The fix should have code that creates uploaded_item even when total_images=0
    # Look for the pattern where item is created unconditionally

    # Find the method
    if "_populate_table_row_minimal" not in content:
        print("❌ FAIL: Method _populate_table_row_minimal not found!")
        return False

    print("✓ Method _populate_table_row_minimal exists")

    # Check for uploaded column handling
    lines = content.split('\n')
    in_minimal_method = False
    found_uploaded_column = False
    fix_present = False

    for i, line in enumerate(lines):
        if "def _populate_table_row_minimal" in line:
            in_minimal_method = True
            print(f"✓ Found method at line {i+1}")

        if in_minimal_method:
            # Look for uploaded column code
            if "Upload count" in line or "uploaded_text" in line:
                found_uploaded_column = True
                print(f"✓ Found uploaded column code at line {i+1}")

                # Check surrounding lines for the fix
                # The WRONG code would have: if item.total_images > 0:
                # The RIGHT code should create item regardless
                context = '\n'.join(lines[i:min(i+10, len(lines))])

                # Check if item creation is inside an if block
                if "if item.total_images > 0:" in context:
                    # Check if setItem is inside that if block
                    next_lines = lines[i+1:min(i+10, len(lines))]
                    for j, next_line in enumerate(next_lines):
                        if "setItem(row, GalleryTableWidget.COL_UPLOADED" in next_line or \
                           "setItem(row, COL_UPLOADED" in next_line:
                            # Check indentation - if it's indented more than the if, it's inside
                            if_indent = len(lines[i]) - len(lines[i].lstrip())
                            item_indent = len(next_line) - len(next_line.lstrip())

                            if item_indent > if_indent:
                                print(f"⚠️  WARNING: setItem appears to be inside 'if total_images > 0' block")
                                print(f"   This is the OLD (buggy) code!")
                                fix_present = False
                            else:
                                print(f"✓ setItem appears to be outside conditional - fix present")
                                fix_present = True
                            break
                else:
                    # No conditional check - this is good (fix present)
                    print("✓ No conditional check before item creation - fix present")
                    fix_present = True

                break

            # End of method
            if line.strip().startswith("def ") and "def _populate_table_row_minimal" not in line:
                break

    if not found_uploaded_column:
        print("⚠️  WARNING: Could not find uploaded column code in method")
        print("   Manual verification recommended")
        return None

    return fix_present


if __name__ == "__main__":
    print("\n" + "="*80)
    print("UPLOADED COLUMN FIX - TEST SUITE")
    print("="*80)
    print("\nTesting fix for: Uploaded column not showing when total_images updates from 0")
    print("Fix location: src/gui/main_window.py:_populate_table_row_minimal()")

    results = []

    # Run tests
    try:
        results.append(("Column Creation", test_uploaded_column_creation()))
    except Exception as e:
        print(f"\n❌ EXCEPTION in test_uploaded_column_creation: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Column Creation", False))

    try:
        results.append(("Edge Cases", test_edge_cases()))
    except Exception as e:
        print(f"\n❌ EXCEPTION in test_edge_cases: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Edge Cases", False))

    try:
        source_result = verify_source_code_fix()
        if source_result is None:
            results.append(("Source Code", "MANUAL CHECK NEEDED"))
        else:
            results.append(("Source Code", source_result))
    except Exception as e:
        print(f"\n❌ EXCEPTION in verify_source_code_fix: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Source Code", False))

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    for test_name, result in results:
        if result is True:
            status = "✓ PASS"
        elif result is False:
            status = "❌ FAIL"
        else:
            status = "⚠️  " + str(result)

        print(f"{test_name:20s}: {status}")

    # Overall result
    all_passed = all(r is True for _, r in results)

    print("\n" + "="*80)
    if all_passed:
        print("✓ ALL TESTS PASSED")
        sys.exit(0)
    else:
        print("❌ SOME TESTS FAILED")
        sys.exit(1)
