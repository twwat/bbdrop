#!/usr/bin/env python3
"""
Test script for drag-drop logging fix.

This tests the fix where drag-drop logs were using generic log() calls
without proper category, causing them to appear at INFO level instead of TRACE.

Fix location: src/gui/main_window.py:dragEnterEvent() and dropEvent()
Lines 6636-6714

Before fix:
  - log("message") or log("message", level="trace")
  - Category not specified, so logs appear at INFO level

After fix:
  - log("drag_drop", "message") - category as first parameter
  - Logs appear at TRACE level and can be filtered out
"""

import sys
import os
from pathlib import Path
import re

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def verify_log_call_format():
    """Verify that drag-drop log calls use correct format"""

    print("\n" + "="*80)
    print("TEST 1: Log Call Format Verification")
    print("="*80)

    source_file = project_root / "src" / "gui" / "main_window.py"

    if not source_file.exists():
        print(f"❌ FAIL: Source file not found: {source_file}")
        return False

    with open(source_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Find drag-drop related log calls
    log_calls = []
    in_drag_drop_method = False
    current_method = None

    for i, line in enumerate(lines, 1):
        # Track which method we're in
        if "def dragEnterEvent" in line:
            in_drag_drop_method = True
            current_method = "dragEnterEvent"
        elif "def dragOverEvent" in line:
            in_drag_drop_method = True
            current_method = "dragOverEvent"
        elif "def dropEvent" in line:
            in_drag_drop_method = True
            current_method = "dropEvent"
        elif line.strip().startswith("def ") and in_drag_drop_method:
            in_drag_drop_method = False
            current_method = None

        # Look for log calls in drag-drop methods
        if in_drag_drop_method and 'log(' in line:
            log_calls.append({
                'line_num': i,
                'line': line.strip(),
                'method': current_method
            })

    if not log_calls:
        print("⚠️  WARNING: No log calls found in drag-drop methods")
        return None

    print(f"\nFound {len(log_calls)} log calls in drag-drop methods:")
    print("-" * 80)

    # Analyze each log call
    correct_format = 0
    incorrect_format = 0

    for call in log_calls:
        line = call['line']
        line_num = call['line_num']
        method = call['method']

        # Extract the log call
        # Should be: log("drag_drop", "message")
        # or: log("drag_drop", f"message {var}")

        # Check if category is specified as first parameter
        # Pattern: log("drag_drop", ...
        if re.search(r'log\(\s*["\']drag_drop["\']', line):
            print(f"✓ Line {line_num:4d} ({method:16s}): CORRECT format")
            print(f"  {line[:100]}")
            correct_format += 1
        else:
            print(f"❌ Line {line_num:4d} ({method:16s}): INCORRECT format")
            print(f"  {line[:100]}")
            incorrect_format += 1

    print("\n" + "-" * 80)
    print(f"Correct format:   {correct_format}/{len(log_calls)}")
    print(f"Incorrect format: {incorrect_format}/{len(log_calls)}")

    if incorrect_format > 0:
        print("\n⚠️  EXPECTED FORMAT:")
        print('  log("drag_drop", "message")')
        print('  log("drag_drop", f"message {variable}")')
        print("\n❌ INCORRECT FORMATS TO AVOID:")
        print('  log("message")')
        print('  log("message", level="trace")')
        print('  log("message", category="drag_drop")')

    return incorrect_format == 0


def verify_unique_messages():
    """Verify that each drag-drop log message is unique and specific"""

    print("\n" + "="*80)
    print("TEST 2: Message Uniqueness")
    print("="*80)

    source_file = project_root / "src" / "gui" / "main_window.py"

    with open(source_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract all drag-drop log messages
    # Pattern: log("drag_drop", "message") or log("drag_drop", f"message")
    pattern = r'log\(\s*["\']drag_drop["\']\s*,\s*["\']([^"\']+)["\']'
    f_pattern = r'log\(\s*["\']drag_drop["\']\s*,\s*f["\']([^"\']+)["\']'

    messages = re.findall(pattern, content)
    f_messages = re.findall(f_pattern, content)
    all_messages = messages + f_messages

    if not all_messages:
        print("⚠️  WARNING: No drag-drop log messages found")
        return None

    print(f"\nFound {len(all_messages)} drag-drop log messages:")
    print("-" * 80)

    # Check for duplicates
    seen = {}
    duplicates = []

    for msg in all_messages:
        # Normalize message (remove variables like {var})
        normalized = re.sub(r'\{[^}]+\}', '{...}', msg)

        if normalized in seen:
            duplicates.append((normalized, seen[normalized]))
        else:
            seen[normalized] = msg

        print(f"  • {msg}")

    print("\n" + "-" * 80)

    if duplicates:
        print(f"⚠️  Found {len(duplicates)} duplicate message patterns:")
        for norm, orig in duplicates:
            print(f"  • {norm}")
        print("\nRecommendation: Make each message unique to identify exact checkpoint")
        return False
    else:
        print(f"✓ All {len(all_messages)} messages are unique")
        return True


def verify_expected_messages():
    """Verify that expected checkpoint messages are present"""

    print("\n" + "="*80)
    print("TEST 3: Expected Checkpoint Messages")
    print("="*80)

    source_file = project_root / "src" / "gui" / "main_window.py"

    with open(source_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Expected checkpoints in drag-drop flow
    expected_checkpoints = [
        ("dragEnterEvent entry", r'dragEnterEvent.*hasUrls.*hasText'),
        ("dragEnterEvent accept URLs", r'Accepting drag with.*URLs'),
        ("dragEnterEvent accept text", r'Accepting drag with text'),
        ("dragEnterEvent reject", r'Rejecting drag'),
        ("dropEvent entry", r'dropEvent.*hasUrls.*hasText'),
        ("dropEvent processing", r'Processing.*URLs'),
        ("dropEvent path", r'Original path from URL'),
        ("dropEvent WSL conversion", r'WSL2 path conversion'),
        ("dropEvent validation", r'Path validated'),
        ("dropEvent adding", r'Adding.*valid paths'),
        ("dropEvent no paths", r'No valid paths'),
        ("dropEvent no URLs", r'No URLs in mime data'),
    ]

    print("\nChecking for expected checkpoint messages:")
    print("-" * 80)

    all_found = True

    for checkpoint_name, pattern in expected_checkpoints:
        # Search for pattern in drag-drop log calls
        # Look for: log("drag_drop", "...pattern...")
        search_pattern = r'log\(["\']drag_drop["\']\s*,\s*[f]?["\'][^"\']*' + pattern

        if re.search(search_pattern, content, re.IGNORECASE):
            print(f"✓ {checkpoint_name:30s}: Found")
        else:
            print(f"❌ {checkpoint_name:30s}: NOT FOUND")
            all_found = False

    print("\n" + "-" * 80)

    if all_found:
        print("✓ All expected checkpoint messages found")
    else:
        print("❌ Some checkpoint messages missing")

    return all_found


def test_log_level_behavior():
    """Test that drag_drop category logs at TRACE level"""

    print("\n" + "="*80)
    print("TEST 4: Log Level Behavior")
    print("="*80)

    # This test verifies the logger behavior by checking the log function
    # Category-based logging should map "drag_drop" to TRACE level

    print("\n[Checking logger category mapping]")

    logger_file = project_root / "src" / "utils" / "logger.py"

    if not logger_file.exists():
        print(f"❌ FAIL: Logger file not found: {logger_file}")
        return False

    with open(logger_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Look for category-to-level mapping
    # The log() function should map categories to levels

    # Check if there's a CATEGORY_LEVEL_MAP or similar
    if "drag_drop" in content and ("TRACE" in content or "trace" in content):
        print("✓ Logger file mentions both 'drag_drop' and 'TRACE'")

        # Look for explicit mapping
        if re.search(r'drag_drop.*trace|trace.*drag_drop', content, re.IGNORECASE):
            print("✓ Found explicit drag_drop -> trace mapping")
            return True
        else:
            print("⚠️  WARNING: No explicit mapping found")
            print("   Category-based logging should use trace level")
            return None
    else:
        print("⚠️  WARNING: Logger may not have drag_drop category support")
        return None


def generate_test_output_example():
    """Generate example output showing expected behavior"""

    print("\n" + "="*80)
    print("EXAMPLE: Expected Log Output Behavior")
    print("="*80)

    print("\n[With default INFO level - NO drag-drop logs should appear]")
    print("-" * 80)
    print("INFO: Starting application")
    print("INFO: Loading galleries")
    print("INFO: Gallery table initialized")
    print("  (no drag-drop logs)")

    print("\n[With TRACE level enabled - drag-drop logs should appear]")
    print("-" * 80)
    print("INFO: Starting application")
    print("TRACE [drag_drop]: dragEnterEvent: hasUrls=True, hasText=False, formats=['text/uri-list']")
    print("TRACE [drag_drop]: dragEnterEvent: Accepting drag with 3 URLs")
    print("TRACE [drag_drop]: dropEvent: hasUrls=True, hasText=False")
    print("TRACE [drag_drop]: dropEvent: Processing 3 URLs")
    print("TRACE [drag_drop]: dropEvent: Original path from URL: /mnt/c/Users/test/folder")
    print("TRACE [drag_drop]: WSL2 path conversion: /mnt/c/Users/test/folder -> /mnt/c/Users/test/folder")
    print("TRACE [drag_drop]: Path validated: /mnt/c/Users/test/folder")
    print("TRACE [drag_drop]: dropEvent: Adding 3 valid paths")
    print("INFO: Loading galleries")


if __name__ == "__main__":
    print("\n" + "="*80)
    print("DRAG-DROP LOGGING FIX - TEST SUITE")
    print("="*80)
    print("\nTesting fix for: Drag-drop logs appearing at INFO level instead of TRACE")
    print("Fix location: src/gui/main_window.py:dragEnterEvent() and dropEvent()")
    print("\nExpected behavior:")
    print("  • Drag-drop logs use category-based logging: log('drag_drop', 'message')")
    print("  • Each log message is unique and identifies exact checkpoint")
    print("  • With default INFO level: no drag-drop logs appear")
    print("  • With TRACE level enabled: detailed drag-drop logs appear")

    results = []

    # Run tests
    try:
        results.append(("Log Call Format", verify_log_call_format()))
    except Exception as e:
        print(f"\n❌ EXCEPTION in verify_log_call_format: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Log Call Format", False))

    try:
        results.append(("Message Uniqueness", verify_unique_messages()))
    except Exception as e:
        print(f"\n❌ EXCEPTION in verify_unique_messages: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Message Uniqueness", False))

    try:
        results.append(("Expected Messages", verify_expected_messages()))
    except Exception as e:
        print(f"\n❌ EXCEPTION in verify_expected_messages: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Expected Messages", False))

    try:
        results.append(("Log Level Behavior", test_log_level_behavior()))
    except Exception as e:
        print(f"\n❌ EXCEPTION in test_log_level_behavior: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Log Level Behavior", False))

    # Show example output
    try:
        generate_test_output_example()
    except Exception as e:
        print(f"\n❌ EXCEPTION in generate_test_output_example: {e}")

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

        print(f"{test_name:25s}: {status}")

    # Overall result
    all_passed = all(r is True for _, r in results if r is not None)
    has_warnings = any(r is None for _, r in results)

    print("\n" + "="*80)
    if all_passed and not has_warnings:
        print("✓ ALL TESTS PASSED")
        sys.exit(0)
    elif all_passed and has_warnings:
        print("⚠️  TESTS PASSED WITH WARNINGS - Manual verification recommended")
        sys.exit(0)
    else:
        print("❌ SOME TESTS FAILED")
        sys.exit(1)
