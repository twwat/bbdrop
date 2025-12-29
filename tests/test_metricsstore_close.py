#!/usr/bin/env python3
"""
Test MetricsStore cleanup to identify the blocking point.
"""

import sys
import signal
import time
sys.path.insert(0, '.')

# Set alarm to force-kill if we hang
def timeout_handler(signum, frame):
    print("\n✗ TIMEOUT - Process hung during cleanup!", flush=True)
    sys.exit(124)

signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(5)  # 5 second timeout

print("1. Initializing MetricsStore...", flush=True)
from src.utils.metrics_store import get_metrics_store
ms = get_metrics_store()
print(f"   ✓ MetricsStore: {ms}", flush=True)

print("\n2. Checking thread state...", flush=True)
print(f"   - _running: {ms._running}", flush=True)
print(f"   - _executor: {ms._executor}", flush=True)
print(f"   - signals: {ms.signals}", flush=True)

print("\n3. Importing main_window (starts PyQt6 event loop)...", flush=True)
from src.gui.main_window import ImxUploadGUI
print(f"   ✓ Imported: {ImxUploadGUI.__name__}", flush=True)

print("\n4. Manually closing MetricsStore...", flush=True)
start = time.time()
ms.close()
elapsed = (time.time() - start) * 1000
print(f"   ✓ close() completed in {elapsed:.1f}ms", flush=True)

print("\n5. Checking post-close state...", flush=True)
print(f"   - _running: {ms._running}", flush=True)
print(f"   - _executor: {ms._executor}", flush=True)

print("\n6. Exiting (should be instant)...", flush=True)
sys.exit(0)
