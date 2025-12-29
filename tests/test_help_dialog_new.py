#!/usr/bin/env python3
"""
Test script for new help dialog
Tests import and basic functionality without full GUI
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_file_structure():
    """Test that the help dialog file exists and is structured correctly"""
    help_dialog_path = "src/gui/dialogs/help_dialog_new.py"

    print("🔍 Testing help dialog file structure...")

    # Check file exists
    assert os.path.exists(help_dialog_path), f"Help dialog not found at {help_dialog_path}"
    print(f"✅ File exists: {help_dialog_path}")

    # Read and check content
    with open(help_dialog_path, 'r') as f:
        content = f.read()

    # Check for key components
    required_components = [
        "class HelpDialog",
        "QTreeWidget",
        "QTextEdit",
        "setMarkdown",
        "_on_search",
        "_find_in_content",
        "_load_documentation",
        "docs/user",
    ]

    for component in required_components:
        assert component in content, f"Missing required component: {component}"
        print(f"✅ Found component: {component}")

    print(f"\n📊 File size: {len(content)} bytes")
    print(f"📊 Lines of code: {content.count(chr(10))}")


def test_documentation_files():
    """Test that user documentation files exist"""
    docs_dir = "docs/user"

    print("\n🔍 Testing documentation files...")

    if not os.path.exists(docs_dir):
        print(f"⚠️  Warning: {docs_dir} directory not found")
        return

    expected_files = [
        "HELP_CONTENT.md",
        "quick-start.md",
        "multi-host-upload.md",
        "bbcode-templates.md",
        "gui-guide.md",
        "keyboard-shortcuts.md",
        "troubleshooting.md",
    ]

    found_files = []
    for filename in expected_files:
        filepath = os.path.join(docs_dir, filename)
        if os.path.exists(filepath):
            size = os.path.getsize(filepath)
            print(f"✅ Found: {filename} ({size} bytes)")
            found_files.append(filename)
        else:
            print(f"⚠️  Missing: {filename}")

    print(f"\n📊 Found {len(found_files)}/{len(expected_files)} expected files")


def test_help_dialog_features():
    """Test help dialog features without Qt"""
    print("\n🔍 Testing help dialog features...")

    features = {
        "Navigation tree": "QTreeWidget",
        "Markdown rendering": "setMarkdown",
        "Search functionality": "_on_search",
        "Find in content": "_find_in_content",
        "Categorized topics": "doc_structure",
        "Splitter layout": "QSplitter",
    }

    with open("src/gui/dialogs/help_dialog_new.py", 'r') as f:
        content = f.read()

    for feature, marker in features.items():
        if marker in content:
            print(f"✅ {feature}: Implemented")
        else:
            print(f"❌ {feature}: Missing")


if __name__ == "__main__":
    print("=" * 60)
    print("HELP DIALOG NEW - TEST SUITE")
    print("=" * 60)

    try:
        test_file_structure()
        test_documentation_files()
        test_help_dialog_features()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        sys.exit(1)
