"""
Test MetricsStore integration with actual worker threads.

This simulates the actual pattern used in file_host_workers.py where
worker threads call get_metrics_store() and record_transfer().
"""

import threading
import time
from queue import Queue


def test_worker_pattern_integration():
    """Test the exact pattern used in file_host_workers."""
    print("\n=== Testing Worker Pattern Integration ===")

    # Import after path setup
    import sys
    sys.path.insert(0, '/home/jimbo/imxup')
    from src.utils.metrics_store import get_metrics_store, MetricsStore

    # Reset singleton
    MetricsStore._instance = None

    # Create store in main thread (like the app does)
    print("1. Creating MetricsStore in main thread...")
    main_store = get_metrics_store()
    print(f"   → Created: {id(main_store)}")

    results = []
    exceptions = []

    def worker_thread(worker_id: int, task_queue: Queue):
        """Simulate a file host worker thread."""
        try:
            while True:
                task = task_queue.get(timeout=0.5)
                if task is None:
                    break

                # This is the EXACT pattern in file_host_workers.py line 603-610
                from src.utils.metrics_store import get_metrics_store
                metrics_store = get_metrics_store()

                if metrics_store:
                    print(f"   Worker-{worker_id}: Recording transfer {task}...")
                    metrics_store.record_transfer(
                        host_name=f"host_{worker_id % 3}",
                        bytes_uploaded=1024 * 1024,  # 1 MB
                        transfer_time=1.0,
                        success=True
                    )
                    results.append({
                        'worker': worker_id,
                        'task': task,
                        'store_id': id(metrics_store)
                    })

                task_queue.task_done()

        except Exception as e:
            exceptions.append({
                'worker': worker_id,
                'error': str(e),
                'type': type(e).__name__
            })

    # Create task queue and spawn workers (like FileHostWorkerManager does)
    print("\n2. Spawning 5 worker threads...")
    task_queue = Queue()
    workers = []

    for i in range(5):
        worker = threading.Thread(
            target=worker_thread,
            args=(i, task_queue),
            name=f"FileHostWorker-{i}",
            daemon=True
        )
        workers.append(worker)
        worker.start()
        print(f"   → Started Worker-{i}")

    # Queue tasks
    print("\n3. Queueing 25 tasks...")
    for task_id in range(25):
        task_queue.put(task_id)

    # Wait for all tasks to complete
    print("\n4. Waiting for task completion...")
    start = time.time()
    task_queue.join()
    elapsed = time.time() - start
    print(f"   ✓ All tasks completed in {elapsed:.3f}s")

    # Signal workers to exit
    for _ in workers:
        task_queue.put(None)

    # Wait for workers to finish
    print("\n5. Waiting for workers to exit...")
    for worker in workers:
        worker.join(timeout=2.0)
        if worker.is_alive():
            print(f"   ✗ {worker.name} did not exit!")
            return False

    print(f"   ✓ All workers exited")

    # Check results
    print("\n6. Verifying results...")
    if exceptions:
        print(f"   ✗ Exceptions occurred: {exceptions}")
        return False

    print(f"   ✓ Processed {len(results)} tasks")
    print(f"   ✓ No exceptions")

    # Verify all workers got same singleton instance
    store_ids = set(r['store_id'] for r in results)
    if len(store_ids) != 1:
        print(f"   ✗ Multiple MetricsStore instances: {store_ids}")
        return False

    if list(store_ids)[0] != id(main_store):
        print(f"   ✗ Worker store ID doesn't match main: {list(store_ids)[0]} != {id(main_store)}")
        return False

    print(f"   ✓ All workers used same singleton instance")

    # Verify metrics were recorded
    metrics = main_store.get_all_host_stats()
    print(f"   ✓ Recorded metrics for {len(metrics)} hosts")

    total_files = sum(m['files_uploaded'] for m in metrics.values())
    if total_files != 25:
        print(f"   ✗ Expected 25 files, got {total_files}")
        return False

    print(f"   ✓ All 25 transfers recorded")

    # Cleanup
    main_store.close()
    MetricsStore._instance = None

    print("\n✓ WORKER PATTERN INTEGRATION TEST PASSED")
    return True


def test_rapid_worker_creation():
    """Test rapid creation and destruction of worker threads."""
    print("\n=== Testing Rapid Worker Creation ===")

    import sys
    sys.path.insert(0, '/home/jimbo/imxup')
    from src.utils.metrics_store import get_metrics_store, MetricsStore

    # Reset singleton
    MetricsStore._instance = None

    # Create store
    store = get_metrics_store()

    completed = 0
    lock = threading.Lock()

    def rapid_worker(worker_id: int):
        """Worker that quickly accesses store and exits."""
        try:
            from src.utils.metrics_store import get_metrics_store
            ms = get_metrics_store()
            ms.record_transfer(f"host_{worker_id % 2}", 1024, 0.1, True)

            nonlocal completed
            with lock:
                completed += 1
        except Exception as e:
            print(f"   ✗ Worker-{worker_id} error: {e}")

    # Rapidly create and destroy 50 workers
    print("1. Spawning 50 rapid workers...")
    workers = []
    for i in range(50):
        w = threading.Thread(target=rapid_worker, args=(i,))
        workers.append(w)
        w.start()

    # Wait for all
    print("2. Waiting for completion...")
    start = time.time()
    for w in workers:
        w.join(timeout=1.0)
        if w.is_alive():
            print(f"   ✗ Worker hung!")
            return False

    elapsed = time.time() - start
    print(f"   ✓ All workers completed in {elapsed:.3f}s")

    if completed != 50:
        print(f"   ✗ Only {completed}/50 workers completed")
        return False

    print(f"   ✓ All 50 workers completed successfully")

    # Cleanup
    store.close()
    MetricsStore._instance = None

    print("\n✓ RAPID WORKER CREATION TEST PASSED")
    return True


if __name__ == '__main__':
    print("=" * 60)
    print("MetricsStore Worker Integration Tests")
    print("=" * 60)

    tests = [
        test_worker_pattern_integration,
        test_rapid_worker_creation,
    ]

    all_passed = True
    for test_func in tests:
        try:
            if not test_func():
                all_passed = False
                break
        except Exception as e:
            print(f"\n✗ Test crashed: {e}")
            import traceback
            traceback.print_exc()
            all_passed = False
            break

    print("\n" + "=" * 60)
    if all_passed:
        print("✓ ALL INTEGRATION TESTS PASSED")
    else:
        print("✗ INTEGRATION TESTS FAILED")
