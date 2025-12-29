#!/usr/bin/env python3
"""
Test that GUI window can be instantiated without hanging.
"""

import sys
import signal
sys.path.insert(0, '.')

# Set timeout
def timeout_handler(signum, frame):
    print("\n✗ TIMEOUT - GUI instantiation hung!", flush=True)
    sys.exit(124)

signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(10)  # 10 second timeout

print("=" * 60)
print("GUI LAUNCH TEST (Non-blocking)")
print("=" * 60)

print("\n1. Initializing QApplication...", flush=True)
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)
print("   ✓ QApplication created", flush=True)

print("\n2. Importing ImxUploadGUI...", flush=True)
from src.gui.main_window import ImxUploadGUI
print(f"   ✓ Imported: {ImxUploadGUI.__name__}", flush=True)

print("\n3. Instantiating GUI window (this is where hang occurred before)...", flush=True)
window = ImxUploadGUI()
print("   ✓ GUI window instantiated successfully!", flush=True)

print("\n4. Showing window...", flush=True)
window.show()
print("   ✓ Window shown", flush=True)

print("\n5. Closing window immediately (no event loop)...", flush=True)
window.close()
print("   ✓ Window closed", flush=True)

print("\n6. Quitting application...", flush=True)
app.quit()
print("   ✓ Application quit", flush=True)

print("\n" + "=" * 60)
print("✅ GUI LAUNCH SUCCESSFUL - NO HANG!")
print("=" * 60)
sys.exit(0)
