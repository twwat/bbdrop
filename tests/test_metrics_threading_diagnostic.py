"""
Diagnostic test to identify the exact cause of MetricsStore threading hang.

Tests each component in isolation:
1. PyQt6 QObject creation from threads
2. ThreadPoolExecutor in __init__
3. atexit registration
4. Database operations
"""

import threading
import time
import sys
from concurrent.futures import ThreadPoolExecutor


def test_1_pyqt_qobject_in_thread():
    """Test if creating PyQt6 QObject from thread causes hang."""
    print("\n=== Test 1: PyQt6 QObject creation from thread ===")

    try:
        from PyQt6.QtCore import QObject, pyqtSignal
    except ImportError:
        print("PyQt6 not available, skipping")
        return True

    result = {'success': False, 'error': None}

    def create_qobject():
        try:
            class TestSignals(QObject):
                test_signal = pyqtSignal(str)

            obj = TestSignals()
            print(f"  ✓ Created QObject in thread {threading.current_thread().name}")
            result['success'] = True
        except Exception as e:
            result['error'] = str(e)
            print(f"  ✗ Error creating QObject: {e}")

    thread = threading.Thread(target=create_qobject, name="QObjectTest")
    thread.start()
    thread.join(timeout=3.0)

    if thread.is_alive():
        print("  ✗ HANG DETECTED: Thread creating QObject hung!")
        return False

    if not result['success']:
        print(f"  ✗ Failed: {result['error']}")
        return False

    print("  ✓ PASSED: QObject can be created from thread")
    return True


def test_2_threadpool_executor_in_init():
    """Test if ThreadPoolExecutor creation hangs in __init__."""
    print("\n=== Test 2: ThreadPoolExecutor in __init__ ===")

    result = {'success': False, 'error': None, 'init_count': 0}

    class TestClass:
        _instance = None
        _lock = threading.Lock()

        def __new__(cls):
            if cls._instance is None:
                with cls._lock:
                    if cls._instance is None:
                        cls._instance = super().__new__(cls)
                        cls._instance._initialized = False
            return cls._instance

        def __init__(self):
            with self._lock:
                if self._initialized:
                    return
                self._initialized = True
                result['init_count'] += 1

                # Create executor like MetricsStore does
                self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="TestWorker")
                self._running = True

                # Start a worker
                self._executor.submit(self._worker)

        def _worker(self):
            while self._running:
                time.sleep(0.1)

    def create_instance():
        try:
            obj = TestClass()
            print(f"  ✓ Created instance in thread {threading.current_thread().name}")
            result['success'] = True
        except Exception as e:
            result['error'] = str(e)
            print(f"  ✗ Error: {e}")

    # Test from thread
    thread = threading.Thread(target=create_instance, name="ExecutorTest")
    thread.start()
    thread.join(timeout=3.0)

    if thread.is_alive():
        print("  ✗ HANG DETECTED: Thread with ThreadPoolExecutor hung!")
        return False

    if not result['success']:
        print(f"  ✗ Failed: {result['error']}")
        return False

    # Cleanup
    TestClass._instance._running = False
    TestClass._instance._executor.shutdown(wait=True)

    print(f"  ✓ PASSED: ThreadPoolExecutor works (init_count={result['init_count']})")
    return True


def test_3_pyqt_with_executor():
    """Test if combining PyQt QObject + ThreadPoolExecutor causes hang."""
    print("\n=== Test 3: PyQt QObject + ThreadPoolExecutor ===")

    try:
        from PyQt6.QtCore import QObject, pyqtSignal
    except ImportError:
        print("PyQt6 not available, skipping")
        return True

    result = {'success': False, 'error': None}

    class TestSignals(QObject):
        test_signal = pyqtSignal(str)

    class TestClass:
        _instance = None
        _lock = threading.Lock()

        def __new__(cls):
            if cls._instance is None:
                with cls._lock:
                    if cls._instance is None:
                        cls._instance = super().__new__(cls)
                        cls._instance._initialized = False
            return cls._instance

        def __init__(self):
            with self._lock:
                if self._initialized:
                    return
                self._initialized = True

                # Create both PyQt signals AND executor
                self.signals = TestSignals()
                self._executor = ThreadPoolExecutor(max_workers=1)
                self._running = True
                self._executor.submit(self._worker)

        def _worker(self):
            while self._running:
                time.sleep(0.1)

    def create_instance():
        try:
            obj = TestClass()
            print(f"  ✓ Created QObject+Executor in thread {threading.current_thread().name}")
            result['success'] = True
        except Exception as e:
            result['error'] = str(e)
            print(f"  ✗ Error: {e}")

    # Test from thread
    thread = threading.Thread(target=create_instance, name="ComboTest")
    thread.start()
    thread.join(timeout=3.0)

    if thread.is_alive():
        print("  ✗ HANG DETECTED: QObject + ThreadPoolExecutor hung!")
        print("  → This is likely the root cause!")
        return False

    if not result['success']:
        print(f"  ✗ Failed: {result['error']}")
        return False

    # Cleanup
    TestClass._instance._running = False
    TestClass._instance._executor.shutdown(wait=True)

    print("  ✓ PASSED: QObject + ThreadPoolExecutor works")
    return True


def test_4_actual_metricsstore():
    """Test actual MetricsStore creation from thread."""
    print("\n=== Test 4: Actual MetricsStore from thread ===")

    # Import sys properly
    import sys as system
    system.path.insert(0, '/home/jimbo/imxup')

    from src.utils.metrics_store import MetricsStore

    # Reset singleton
    MetricsStore._instance = None

    result = {'success': False, 'error': None}

    def create_store():
        try:
            print("  → Attempting MetricsStore creation...")
            start = time.time()
            store = MetricsStore()
            elapsed = time.time() - start
            print(f"  ✓ Created MetricsStore in {elapsed:.3f}s")
            result['success'] = True
        except Exception as e:
            result['error'] = str(e)
            print(f"  ✗ Error: {e}")

    # Test from thread
    thread = threading.Thread(target=create_store, name="MetricsTest")
    thread.start()
    thread.join(timeout=5.0)

    if thread.is_alive():
        print("  ✗ HANG DETECTED: MetricsStore hung!")
        print("\n  Thread stack trace:")
        import traceback
        import sys
        for thread_id, frame in sys._current_frames().items():
            if thread_id == thread.ident:
                print(''.join(traceback.format_stack(frame)))
        return False

    if not result['success']:
        print(f"  ✗ Failed: {result['error']}")
        return False

    # Cleanup
    MetricsStore._instance.close()
    MetricsStore._instance = None

    print("  ✓ PASSED: MetricsStore works from thread")
    return True


def test_5_get_hosts_with_history_from_thread():
    """Test get_hosts_with_history() from thread."""
    print("\n=== Test 5: get_hosts_with_history() from thread ===")

    import sys as system
    system.path.insert(0, '/home/jimbo/imxup')
    from src.utils.metrics_store import MetricsStore

    # Reset and create in main thread
    MetricsStore._instance = None
    store = MetricsStore()

    result = {'success': False, 'error': None, 'data': None}

    def call_method():
        try:
            print("  → Calling get_hosts_with_history()...")
            start = time.time()
            data = store.get_hosts_with_history()
            elapsed = time.time() - start
            print(f"  ✓ Completed in {elapsed:.3f}s, got {len(data)} hosts")
            result['success'] = True
            result['data'] = data
        except Exception as e:
            result['error'] = str(e)
            print(f"  ✗ Error: {e}")

    # Call from thread
    thread = threading.Thread(target=call_method, name="MethodTest")
    thread.start()
    thread.join(timeout=5.0)

    if thread.is_alive():
        print("  ✗ HANG DETECTED: get_hosts_with_history() hung from thread!")
        return False

    if not result['success']:
        print(f"  ✗ Failed: {result['error']}")
        return False

    # Cleanup
    store.close()
    MetricsStore._instance = None

    print("  ✓ PASSED: get_hosts_with_history() works from thread")
    return True


if __name__ == '__main__':
    print("=" * 60)
    print("MetricsStore Threading Diagnostic")
    print("=" * 60)

    tests = [
        ("PyQt QObject in thread", test_1_pyqt_qobject_in_thread),
        ("ThreadPoolExecutor in __init__", test_2_threadpool_executor_in_init),
        ("PyQt + Executor combo", test_3_pyqt_with_executor),
        ("Actual MetricsStore", test_4_actual_metricsstore),
        ("get_hosts_with_history()", test_5_get_hosts_with_history_from_thread),
    ]

    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
            if not passed:
                print(f"\n⚠️  Stopping at first failure: {name}")
                break
        except Exception as e:
            print(f"\n✗ Test crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
            break

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")

    print("\n" + "=" * 60)
    if all(passed for _, passed in results):
        print("✓ ALL TESTS PASSED")
    else:
        print("✗ FAILURES DETECTED")
        failed = [name for name, passed in results if not passed]
        print(f"\nRoot cause likely in: {failed[0]}")
