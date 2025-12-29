#!/usr/bin/env python3
"""
Test the order of atexit handlers and identify which one hangs.
"""

import sys
import atexit
import time
sys.path.insert(0, '.')

print("=" * 60)
print("ATEXIT HANDLER ORDER TEST")
print("=" * 60)

# Register our own handlers to track execution order
def handler_1():
    print("  [1] atexit handler_1 called", flush=True)

def handler_2():
    print("  [2] atexit handler_2 called", flush=True)

def handler_3():
    print("  [3] atexit handler_3 called (should run BEFORE MetricsStore)", flush=True)

atexit.register(handler_1)

print("\n1. Initializing MetricsStore (registers atexit handler)...", flush=True)
from src.utils.metrics_store import get_metrics_store
ms = get_metrics_store()
print(f"   ✓ MetricsStore initialized", flush=True)

atexit.register(handler_2)

print("\n2. Importing main_window...", flush=True)
from src.gui.main_window import ImxUploadGUI
print(f"   ✓ main_window imported", flush=True)

atexit.register(handler_3)

print("\n3. Checking registered atexit handlers...", flush=True)
# atexit._exithandlers is internal but useful for debugging
if hasattr(atexit, '_exithandlers'):
    print(f"   - Number of atexit handlers: {len(atexit._exithandlers)}", flush=True)
    for i, (func, args, kwargs) in enumerate(atexit._exithandlers):
        print(f"   - Handler {i}: {func.__name__} from {func.__module__}", flush=True)

print("\n4. Exiting now... watch for atexit handler execution order:", flush=True)
print("   Expected order: handler_3, handler_2, MetricsStore.close, handler_1", flush=True)
print("-" * 60, flush=True)

sys.exit(0)
