#!/usr/bin/env python3
"""
Test if ThreadPoolExecutor + QObject + atexit causes the hang.
This replicates MetricsStore's exact pattern.
"""

import sys
import atexit
import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue, Empty
from threading import Lock
sys.path.insert(0, '.')

from PyQt6.QtCore import QObject, pyqtSignal

print("THREADPOOL + QOBJECT + ATEXIT TEST")
print("=" * 60)

class TestSignals(QObject):
    """Mirrors MetricsSignals."""
    test_signal = pyqtSignal(str, dict)

class TestStore:
    """Mirrors MetricsStore pattern."""

    def __init__(self):
        print("  Initializing TestStore...", flush=True)
        self._running = True
        self._write_queue = Queue()
        self._lock = Lock()

        # This is the critical combo: QObject + ThreadPoolExecutor
        self.signals = TestSignals()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="TestWorker")

        # Start worker thread (like MetricsStore)
        self._executor.submit(self._write_worker)

        # Register atexit cleanup (like MetricsStore)
        atexit.register(self.close)

        print("  ✓ TestStore initialized", flush=True)

    def _write_worker(self):
        """Background worker (mirrors MetricsStore._write_worker)."""
        print("    [Worker thread started]", flush=True)
        while self._running:
            try:
                item = self._write_queue.get(timeout=1.0)
                if item is None:
                    break
                # Process item
                self._write_queue.task_done()
            except Empty:
                continue
        print("    [Worker thread exiting]", flush=True)

    def close(self):
        """Shutdown (mirrors MetricsStore.close)."""
        print("  close() called - shutting down worker...", flush=True)
        if not self._running:
            return

        self._running = False
        self._write_queue.put(None)  # Stop signal

        # This is where it might hang
        print("  Calling executor.shutdown(wait=True)...", flush=True)
        self._executor.shutdown(wait=True, cancel_futures=False)
        print("  ✓ close() completed", flush=True)

print("\n1. Creating TestStore (ThreadPool + QObject + atexit)...", flush=True)
store = TestStore()

print("\n2. Importing main_window (heavy PyQt6 usage)...", flush=True)
from src.gui.main_window import ImxUploadGUI
print(f"   ✓ Imported: {ImxUploadGUI.__name__}", flush=True)

print("\n3. Exiting WITHOUT manual close (relies on atexit)...", flush=True)
sys.exit(0)
