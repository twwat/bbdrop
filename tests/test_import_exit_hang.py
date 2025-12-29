#!/usr/bin/env python3
"""
Test if the hang occurs during Python exit cleanup, not during import.
This tests if there's a threading/cleanup issue with MetricsStore.
"""

import sys
import time
import atexit
sys.path.insert(0, '.')

print("=" * 60)
print("EXIT CLEANUP DIAGNOSTIC")
print("=" * 60)

# Register exit handler to detect if we reach normal exit
exit_reached = False
def on_exit():
    global exit_reached
    exit_reached = True
    print("\n✓ atexit handler called - normal exit sequence started", flush=True)

atexit.register(on_exit)

print("\n1. Initializing MetricsStore...", flush=True)
from src.utils.metrics_store import get_metrics_store
ms = get_metrics_store()
print(f"   ✓ MetricsStore ready: {ms}", flush=True)

print("\n2. Importing main_window...", flush=True)
from src.gui.main_window import ImxUploadGUI
print(f"   ✓ main_window imported: {ImxUploadGUI.__name__}", flush=True)

print("\n3. Checking MetricsStore state...", flush=True)
print(f"   - DB connection: {ms.db_manager}", flush=True)
print(f"   - Thread pool: {hasattr(ms, '_thread_pool')}", flush=True)

print("\n4. Starting clean shutdown sequence...", flush=True)

# Explicitly close MetricsStore before exit
try:
    print("   - Calling ms.close()...", flush=True)
    if hasattr(ms, 'close'):
        ms.close()
        print("   ✓ MetricsStore.close() completed", flush=True)
    else:
        print("   ! MetricsStore has no close() method", flush=True)
except Exception as e:
    print(f"   ✗ Error during close: {e}", flush=True)

print("\n5. Exiting Python interpreter now...", flush=True)
sys.exit(0)
