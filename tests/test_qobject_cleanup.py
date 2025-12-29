#!/usr/bin/env python3
"""
Test if QObject cleanup without QApplication causes the hang.
"""

import sys
sys.path.insert(0, '.')

print("TEST 1: Create QObject WITHOUT QApplication")
print("=" * 60)

from PyQt6.QtCore import QObject, pyqtSignal

class TestSignals(QObject):
    test_signal = pyqtSignal(str)

print("1. Creating QObject with signals (NO QApplication)...", flush=True)
obj = TestSignals()
print(f"   ✓ Created: {obj}", flush=True)

print("\n2. Deleting object explicitly...", flush=True)
del obj
print("   ✓ Deleted successfully", flush=True)

print("\n3. Exiting...", flush=True)
sys.exit(0)
