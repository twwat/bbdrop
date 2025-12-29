"""
Test concurrent initialization of MetricsStore to verify deadlock fix.

This test verifies that the singleton pattern with proper lock protection
prevents race conditions when multiple threads attempt to initialize
MetricsStore simultaneously.
"""

import threading
import time
import pytest
from src.utils.metrics_store import MetricsStore


def test_concurrent_initialization():
    """Test that concurrent MetricsStore() calls don't cause deadlock or double-init."""
    # Reset singleton for this test
    MetricsStore._instance = None

    results = []
    exceptions = []

    def create_instance(thread_id):
        """Thread worker that creates MetricsStore instance."""
        try:
            start = time.time()
            store = MetricsStore()
            elapsed = time.time() - start

            results.append({
                'thread_id': thread_id,
                'instance_id': id(store),
                'elapsed': elapsed,
                'has_db_lock': hasattr(store, '_db_lock'),
                'has_executor': hasattr(store, '_executor'),
                'initialized': getattr(store, '_initialized', False)
            })
        except Exception as e:
            exceptions.append({
                'thread_id': thread_id,
                'error': str(e),
                'type': type(e).__name__
            })

    # Create 10 threads that all try to get MetricsStore simultaneously
    threads = []
    for i in range(10):
        t = threading.Thread(target=create_instance, args=(i,), name=f"Worker-{i}")
        threads.append(t)

    # Start all threads at roughly the same time
    for t in threads:
        t.start()

    # Wait for all threads to complete (with timeout to detect deadlock)
    timeout = 10.0
    start_time = time.time()
    for t in threads:
        remaining = timeout - (time.time() - start_time)
        t.join(timeout=max(0.1, remaining))

        if t.is_alive():
            pytest.fail(f"Thread {t.name} did not complete within {timeout}s - possible deadlock!")

    # Verify no exceptions occurred
    if exceptions:
        pytest.fail(f"Exceptions occurred during concurrent initialization: {exceptions}")

    # Verify all threads got results
    assert len(results) == 10, f"Expected 10 results, got {len(results)}"

    # Verify all threads got the SAME instance (singleton)
    instance_ids = [r['instance_id'] for r in results]
    assert len(set(instance_ids)) == 1, f"Multiple instances created: {set(instance_ids)}"

    # Verify all instances are properly initialized
    for result in results:
        assert result['initialized'], f"Thread {result['thread_id']} got uninitialized instance"
        assert result['has_db_lock'], f"Thread {result['thread_id']} instance missing _db_lock"
        assert result['has_executor'], f"Thread {result['thread_id']} instance missing _executor"

    # Verify first thread took longer (did initialization) and others returned quickly
    sorted_results = sorted(results, key=lambda x: x['elapsed'])
    first_elapsed = sorted_results[0]['elapsed']

    # First thread should have done initialization (takes >0.01s)
    # Subsequent threads should return almost immediately (<0.01s typical)
    fast_count = sum(1 for r in sorted_results[1:] if r['elapsed'] < 0.1)
    assert fast_count >= 7, f"Expected at least 7 threads to return quickly, got {fast_count}"

    # Cleanup
    store = MetricsStore.instance()
    store.close()
    MetricsStore._instance = None


def test_concurrent_record_transfer():
    """Test that concurrent record_transfer calls don't cause deadlock."""
    # Reset and create instance
    MetricsStore._instance = None
    store = MetricsStore()

    exceptions = []
    completion_count = threading.Event()
    completed = 0
    lock = threading.Lock()

    def record_transfers(thread_id):
        """Thread worker that records multiple transfers."""
        nonlocal completed
        try:
            for i in range(5):
                store.record_transfer(
                    host_name=f"host_{thread_id % 3}",  # Use 3 different hosts
                    bytes_uploaded=1024 * 1024,  # 1 MB
                    transfer_time=1.0 + (i * 0.1),
                    success=True
                )
                time.sleep(0.001)  # Small delay

            with lock:
                completed += 1
                if completed == 10:
                    completion_count.set()
        except Exception as e:
            exceptions.append({
                'thread_id': thread_id,
                'error': str(e),
                'type': type(e).__name__
            })

    # Create 10 threads that record transfers concurrently
    threads = []
    for i in range(10):
        t = threading.Thread(target=record_transfers, args=(i,), name=f"Recorder-{i}")
        threads.append(t)
        t.start()

    # Wait for completion with timeout
    if not completion_count.wait(timeout=10.0):
        pytest.fail("Concurrent record_transfer calls did not complete within 10s - possible deadlock!")

    # Wait for all threads
    for t in threads:
        t.join(timeout=1.0)
        assert not t.is_alive(), f"Thread {t.name} still alive after completion"

    # Verify no exceptions
    if exceptions:
        pytest.fail(f"Exceptions during concurrent transfers: {exceptions}")

    # Verify metrics were recorded correctly
    metrics = store.get_all_host_stats()
    assert len(metrics) == 3, f"Expected 3 hosts, got {len(metrics)}"

    # Each host should have received transfers from multiple threads
    for host_name, host_metrics in metrics.items():
        files = host_metrics['files_uploaded']
        # Each of 10 threads does 5 uploads, distributed across 3 hosts
        # So each host gets ~16-17 uploads
        assert files >= 10, f"Host {host_name} only received {files} uploads"

    # Cleanup
    store.close()
    MetricsStore._instance = None


def test_no_double_initialization():
    """Test that __init__ only runs once even with concurrent access."""
    # Reset singleton
    MetricsStore._instance = None

    init_count = 0
    lock = threading.Lock()

    # Monkey-patch to count initializations
    original_ensure_schema = MetricsStore._ensure_schema

    def counting_ensure_schema(self):
        nonlocal init_count
        with lock:
            init_count += 1
        return original_ensure_schema(self)

    MetricsStore._ensure_schema = counting_ensure_schema

    try:
        # Create 20 threads
        threads = []
        for i in range(20):
            t = threading.Thread(target=lambda: MetricsStore(), name=f"Init-{i}")
            threads.append(t)
            t.start()

        # Wait for all
        for t in threads:
            t.join(timeout=5.0)
            assert not t.is_alive()

        # Verify _ensure_schema was called exactly once
        assert init_count == 1, f"Expected 1 initialization, got {init_count}"

    finally:
        # Restore original method
        MetricsStore._ensure_schema = original_ensure_schema

        # Cleanup
        store = MetricsStore.instance()
        store.close()
        MetricsStore._instance = None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
