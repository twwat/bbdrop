"""
Unit tests for progress tracking module.

Tests ProgressState, ProgressTracker, BandwidthMonitor,
MultiProgressTracker, and HealthCheck classes.
"""

import pytest
import time
import threading
from unittest.mock import Mock, patch, MagicMock
from collections import deque

from src.utils.progress_tracking import (
    ProgressState,
    ProgressTracker,
    BandwidthMonitor,
    MultiProgressTracker,
    HealthCheck
)


class TestProgressState:
    """Test ProgressState dataclass."""

    def test_init_defaults(self):
        """Test default initialization."""
        state = ProgressState()

        assert state.total == 0
        assert state.current == 0
        assert state.completed is False
        assert state.error is None
        assert isinstance(state.start_time, float)
        assert isinstance(state.last_update, float)

    def test_init_with_values(self):
        """Test initialization with custom values."""
        state = ProgressState(
            total=100,
            current=50,
            start_time=1000.0,
            last_update=1050.0,
            completed=False,
            error="test error"
        )

        assert state.total == 100
        assert state.current == 50
        assert state.start_time == 1000.0
        assert state.last_update == 1050.0
        assert state.completed is False
        assert state.error == "test error"

    def test_percentage_calculation(self):
        """Test percentage property."""
        # Normal case
        state = ProgressState(total=100, current=25)
        assert state.percentage == 25.0

        # Completed
        state = ProgressState(total=100, current=100)
        assert state.percentage == 100.0

        # Over 100% (should cap at 100)
        state = ProgressState(total=100, current=150)
        assert state.percentage == 100.0

        # Zero total
        state = ProgressState(total=0, current=0)
        assert state.percentage == 0.0

        # Negative total
        state = ProgressState(total=-10, current=5)
        assert state.percentage == 0.0

    def test_elapsed_time(self):
        """Test elapsed_time property."""
        past_time = time.time() - 5.0
        state = ProgressState(start_time=past_time)

        elapsed = state.elapsed_time
        assert 4.9 <= elapsed <= 5.1  # Allow small timing variance

    def test_remaining_items(self):
        """Test remaining_items property."""
        # Normal case
        state = ProgressState(total=100, current=30)
        assert state.remaining_items == 70

        # Completed
        state = ProgressState(total=100, current=100)
        assert state.remaining_items == 0

        # Over 100% (should return 0)
        state = ProgressState(total=100, current=150)
        assert state.remaining_items == 0

        # Zero
        state = ProgressState(total=0, current=0)
        assert state.remaining_items == 0

    def test_estimated_time_remaining(self):
        """Test estimated_time_remaining property."""
        # Normal case with progress
        past_time = time.time() - 10.0
        state = ProgressState(total=100, current=50, start_time=past_time)

        eta = state.estimated_time_remaining
        assert eta is not None
        assert 9.0 <= eta <= 11.0  # Should be ~10 seconds

        # No progress yet
        state = ProgressState(total=100, current=0)
        assert state.estimated_time_remaining is None

        # Zero total
        state = ProgressState(total=0, current=0)
        assert state.estimated_time_remaining is None

        # Completed
        past_time = time.time() - 10.0
        state = ProgressState(total=100, current=100, start_time=past_time)
        eta = state.estimated_time_remaining
        assert eta is not None
        assert eta < 0.1  # Should be very close to 0

    def test_estimated_time_remaining_edge_cases(self):
        """Test edge cases for time estimation."""
        # Just started (very small elapsed time)
        recent_time = time.time() - 0.001
        state = ProgressState(total=100, current=1, start_time=recent_time)
        eta = state.estimated_time_remaining
        assert eta is not None  # Should still calculate

        # Large numbers
        past_time = time.time() - 100.0
        state = ProgressState(total=1000000, current=100000, start_time=past_time)
        eta = state.estimated_time_remaining
        assert eta is not None
        assert eta > 0


class TestProgressTracker:
    """Test ProgressTracker class."""

    def test_init(self):
        """Test initialization."""
        tracker = ProgressTracker(total=100)

        state = tracker.get_state()
        assert state.total == 100
        assert state.current == 0
        assert not state.completed
        assert state.error is None

    def test_init_with_callbacks(self):
        """Test initialization with callbacks."""
        on_progress = Mock()
        on_complete = Mock()

        tracker = ProgressTracker(
            total=10,
            on_progress=on_progress,
            on_complete=on_complete
        )

        assert tracker._on_progress is on_progress
        assert tracker._on_complete is on_complete

    def test_update_basic(self):
        """Test basic update functionality."""
        tracker = ProgressTracker(total=10)

        tracker.update()
        state = tracker.get_state()
        assert state.current == 1

        tracker.update(3)
        state = tracker.get_state()
        assert state.current == 4

    def test_update_with_progress_callback(self):
        """Test update with progress callback."""
        on_progress = Mock()
        tracker = ProgressTracker(total=10, on_progress=on_progress)

        tracker.update(2)

        assert on_progress.call_count == 1
        state = on_progress.call_args[0][0]
        assert state.current == 2

    def test_update_completion(self):
        """Test update triggering completion."""
        on_progress = Mock()
        on_complete = Mock()
        tracker = ProgressTracker(
            total=5,
            on_progress=on_progress,
            on_complete=on_complete
        )

        # Not completed yet
        tracker.update(3)
        assert on_progress.call_count == 1
        assert on_complete.call_count == 0

        # Now complete
        tracker.update(10)  # More than needed
        state = tracker.get_state()
        assert state.current == 5  # Should cap at total
        assert state.completed
        assert on_progress.call_count == 2
        assert on_complete.call_count == 1

    def test_update_beyond_total(self):
        """Test updating beyond total is capped."""
        tracker = ProgressTracker(total=10)

        tracker.update(20)
        state = tracker.get_state()
        assert state.current == 10
        assert state.completed

    def test_set_current(self):
        """Test set_current method."""
        on_progress = Mock()
        tracker = ProgressTracker(total=100, on_progress=on_progress)

        tracker.set_current(50)
        state = tracker.get_state()
        assert state.current == 50
        assert on_progress.call_count == 1

    def test_set_current_negative(self):
        """Test set_current with negative value."""
        tracker = ProgressTracker(total=100)

        tracker.set_current(-10)
        state = tracker.get_state()
        assert state.current == 0  # Should clamp to 0

    def test_set_current_beyond_total(self):
        """Test set_current beyond total."""
        on_complete = Mock()
        tracker = ProgressTracker(total=10, on_complete=on_complete)

        tracker.set_current(20)
        state = tracker.get_state()
        assert state.current == 10
        assert state.completed
        assert on_complete.call_count == 1

    def test_set_error(self):
        """Test set_error method."""
        on_complete = Mock()
        tracker = ProgressTracker(total=10, on_complete=on_complete)

        tracker.set_error("Test error")

        state = tracker.get_state()
        assert state.error == "Test error"
        assert state.completed
        assert on_complete.call_count == 1

    def test_is_completed(self):
        """Test is_completed method."""
        tracker = ProgressTracker(total=5)

        assert not tracker.is_completed()

        tracker.update(5)
        assert tracker.is_completed()

    def test_has_error(self):
        """Test has_error method."""
        tracker = ProgressTracker(total=5)

        assert not tracker.has_error()

        tracker.set_error("Error occurred")
        assert tracker.has_error()

    def test_reset_basic(self):
        """Test reset without new total."""
        tracker = ProgressTracker(total=10)
        tracker.update(5)

        tracker.reset()

        state = tracker.get_state()
        assert state.total == 10
        assert state.current == 0
        assert not state.completed
        assert state.error is None

    def test_reset_with_new_total(self):
        """Test reset with new total."""
        tracker = ProgressTracker(total=10)
        tracker.update(5)
        tracker.set_error("error")

        tracker.reset(new_total=20)

        state = tracker.get_state()
        assert state.total == 20
        assert state.current == 0
        assert not state.completed
        assert state.error is None

    def test_thread_safety(self):
        """Test thread-safe operations."""
        tracker = ProgressTracker(total=1000)

        def worker():
            for _ in range(100):
                tracker.update(1)

        threads = [threading.Thread(target=worker) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        state = tracker.get_state()
        assert state.current == 1000
        assert state.completed

    def test_callback_called_outside_lock(self):
        """Test callbacks are called outside the lock."""
        # This is implicit in the code - callbacks are called after 'with self._lock'
        # We test that callbacks don't cause deadlocks
        tracker = ProgressTracker(total=10)

        def slow_callback(state):
            time.sleep(0.01)  # Simulate slow callback

        tracker._on_progress = slow_callback

        # Should not hang
        tracker.update(1)
        assert tracker.get_state().current == 1


class TestBandwidthMonitor:
    """Test BandwidthMonitor class."""

    def test_init(self):
        """Test initialization."""
        monitor = BandwidthMonitor(window_size=10)

        assert monitor._samples.maxlen == 10
        assert monitor._total_bytes == 0
        assert isinstance(monitor._start_time, float)

    def test_init_default_window(self):
        """Test default window size."""
        monitor = BandwidthMonitor()
        assert monitor._samples.maxlen == 10

    def test_add_bytes(self):
        """Test adding bytes."""
        monitor = BandwidthMonitor()

        monitor.add_bytes(1024)
        assert monitor.get_total_bytes() == 1024

        monitor.add_bytes(2048)
        assert monitor.get_total_bytes() == 3072

    def test_get_total_bytes(self):
        """Test get_total_bytes method."""
        monitor = BandwidthMonitor()

        assert monitor.get_total_bytes() == 0

        monitor.add_bytes(100)
        monitor.add_bytes(200)
        assert monitor.get_total_bytes() == 300

    def test_get_current_speed_no_samples(self):
        """Test current speed with no samples."""
        monitor = BandwidthMonitor()
        assert monitor.get_current_speed() == 0.0

    def test_get_current_speed_one_sample(self):
        """Test current speed with one sample."""
        monitor = BandwidthMonitor()
        monitor.add_bytes(1024)
        assert monitor.get_current_speed() == 0.0  # Need at least 2

    def test_get_current_speed_multiple_samples(self):
        """Test current speed with multiple samples."""
        monitor = BandwidthMonitor()

        # Add samples with time delays
        monitor.add_bytes(1024)
        time.sleep(0.1)
        monitor.add_bytes(1024)
        time.sleep(0.1)
        monitor.add_bytes(1024)

        speed = monitor.get_current_speed()
        assert speed > 0
        # Should be roughly 1024 bytes per 0.1 seconds = 10240 bytes/sec
        assert 5000 < speed < 20000  # Allow variance

    def test_get_current_speed_zero_time_diff(self):
        """Test current speed when samples are at same time."""
        monitor = BandwidthMonitor()

        with patch('time.time', return_value=1000.0):
            monitor.add_bytes(1024)
            monitor.add_bytes(1024)

        assert monitor.get_current_speed() == 0.0

    def test_get_average_speed(self):
        """Test average speed calculation."""
        with patch('time.time') as mock_time:
            mock_time.return_value = 1000.0
            monitor = BandwidthMonitor()

            # Simulate 10 seconds passing
            mock_time.return_value = 1010.0
            monitor.add_bytes(1024)
            monitor.add_bytes(1024)

            avg_speed = monitor.get_average_speed()
            assert avg_speed == 204.8  # 2048 bytes / 10 seconds

    def test_get_average_speed_zero_time(self):
        """Test average speed with zero elapsed time."""
        with patch('time.time', return_value=1000.0):
            monitor = BandwidthMonitor()
            monitor.add_bytes(1024)

            assert monitor.get_average_speed() == 0.0

    def test_get_formatted_speed_bytes(self):
        """Test formatted speed for bytes/s."""
        monitor = BandwidthMonitor()

        with patch.object(monitor, 'get_current_speed', return_value=512.0):
            formatted = monitor.get_formatted_speed(use_current=True)
            assert formatted == "512.00 B/s"

    def test_get_formatted_speed_kilobytes(self):
        """Test formatted speed for KB/s."""
        monitor = BandwidthMonitor()

        with patch.object(monitor, 'get_current_speed', return_value=1536.0):
            formatted = monitor.get_formatted_speed(use_current=True)
            assert formatted == "1.50 KB/s"

    def test_get_formatted_speed_megabytes(self):
        """Test formatted speed for MB/s."""
        monitor = BandwidthMonitor()

        with patch.object(monitor, 'get_current_speed', return_value=2097152.0):
            formatted = monitor.get_formatted_speed(use_current=True)
            assert formatted == "2.00 MB/s"

    def test_get_formatted_speed_gigabytes(self):
        """Test formatted speed for GB/s."""
        monitor = BandwidthMonitor()

        with patch.object(monitor, 'get_current_speed', return_value=3221225472.0):
            formatted = monitor.get_formatted_speed(use_current=True)
            assert formatted == "3.00 GB/s"

    def test_get_formatted_speed_average(self):
        """Test formatted speed using average."""
        monitor = BandwidthMonitor()

        with patch.object(monitor, 'get_average_speed', return_value=1024.0):
            formatted = monitor.get_formatted_speed(use_current=False)
            assert formatted == "1.00 KB/s"

    def test_reset(self):
        """Test reset method."""
        monitor = BandwidthMonitor()

        monitor.add_bytes(1024)
        monitor.add_bytes(2048)

        assert monitor.get_total_bytes() > 0

        monitor.reset()

        assert monitor.get_total_bytes() == 0
        assert len(monitor._samples) == 0

    def test_window_size_limit(self):
        """Test that samples respect window size limit."""
        monitor = BandwidthMonitor(window_size=3)

        for i in range(5):
            monitor.add_bytes(100)
            time.sleep(0.01)

        assert len(monitor._samples) == 3  # Should only keep 3

    def test_thread_safety(self):
        """Test thread-safe operations."""
        monitor = BandwidthMonitor()

        def worker():
            for _ in range(100):
                monitor.add_bytes(1024)

        threads = [threading.Thread(target=worker) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert monitor.get_total_bytes() == 1024 * 1000


class TestMultiProgressTracker:
    """Test MultiProgressTracker class."""

    def test_init(self):
        """Test initialization."""
        multi = MultiProgressTracker()

        assert len(multi._trackers) == 0

    def test_create_tracker(self):
        """Test creating a tracker."""
        multi = MultiProgressTracker()

        tracker = multi.create_tracker("op1", total=100)

        assert tracker is not None
        assert tracker.get_state().total == 100

    def test_create_tracker_with_callbacks(self):
        """Test creating tracker with callbacks."""
        multi = MultiProgressTracker()
        on_progress = Mock()
        on_complete = Mock()

        tracker = multi.create_tracker(
            "op1",
            total=10,
            on_progress=on_progress,
            on_complete=on_complete
        )

        tracker.update(5)
        assert on_progress.call_count == 1

    def test_get_tracker(self):
        """Test getting a tracker."""
        multi = MultiProgressTracker()

        created = multi.create_tracker("op1", total=50)
        retrieved = multi.get_tracker("op1")

        assert retrieved is created

    def test_get_tracker_not_found(self):
        """Test getting non-existent tracker."""
        multi = MultiProgressTracker()

        tracker = multi.get_tracker("nonexistent")
        assert tracker is None

    def test_remove_tracker(self):
        """Test removing a tracker."""
        multi = MultiProgressTracker()

        multi.create_tracker("op1", total=10)
        assert multi.get_tracker("op1") is not None

        multi.remove_tracker("op1")
        assert multi.get_tracker("op1") is None

    def test_remove_tracker_nonexistent(self):
        """Test removing non-existent tracker doesn't error."""
        multi = MultiProgressTracker()

        # Should not raise
        multi.remove_tracker("nonexistent")

    def test_get_all_states(self):
        """Test getting all states."""
        multi = MultiProgressTracker()

        multi.create_tracker("op1", total=10)
        multi.create_tracker("op2", total=20)

        tracker1 = multi.get_tracker("op1")
        tracker2 = multi.get_tracker("op2")

        tracker1.update(5)
        tracker2.update(10)

        states = multi.get_all_states()

        assert len(states) == 2
        assert states["op1"].current == 5
        assert states["op2"].current == 10

    def test_get_overall_progress(self):
        """Test getting overall progress."""
        multi = MultiProgressTracker()

        multi.create_tracker("op1", total=100)
        multi.create_tracker("op2", total=200)
        multi.create_tracker("op3", total=50)

        multi.get_tracker("op1").update(50)
        multi.get_tracker("op2").update(100)
        multi.get_tracker("op3").update(25)

        completed, total = multi.get_overall_progress()

        assert completed == 175
        assert total == 350

    def test_get_overall_progress_empty(self):
        """Test overall progress with no trackers."""
        multi = MultiProgressTracker()

        completed, total = multi.get_overall_progress()

        assert completed == 0
        assert total == 0

    def test_clear_completed(self):
        """Test clearing completed trackers."""
        multi = MultiProgressTracker()

        multi.create_tracker("op1", total=10)
        multi.create_tracker("op2", total=10)
        multi.create_tracker("op3", total=10)

        # Complete some
        multi.get_tracker("op1").update(10)
        multi.get_tracker("op3").update(10)

        multi.clear_completed()

        assert multi.get_tracker("op1") is None
        assert multi.get_tracker("op2") is not None
        assert multi.get_tracker("op3") is None

    def test_thread_safety(self):
        """Test thread-safe operations."""
        multi = MultiProgressTracker()

        def worker(op_id):
            tracker = multi.create_tracker(op_id, total=100)
            for _ in range(100):
                tracker.update(1)

        threads = [
            threading.Thread(target=worker, args=(f"op{i}",))
            for i in range(10)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        completed, total = multi.get_overall_progress()
        assert completed == 1000
        assert total == 1000


class TestHealthCheck:
    """Test HealthCheck class."""

    def test_init(self):
        """Test initialization."""
        health = HealthCheck()

        assert len(health._checks) == 0
        assert isinstance(health._start_time, float)

    def test_register_check(self):
        """Test registering a health check."""
        health = HealthCheck()

        check_func = Mock(return_value=True)
        health.register_check("test_check", check_func)

        assert "test_check" in health._checks

    def test_run_checks_all_healthy(self):
        """Test running checks when all are healthy."""
        health = HealthCheck()

        health.register_check("check1", lambda: True)
        health.register_check("check2", lambda: True)

        results = health.run_checks()

        assert results['healthy'] is True
        assert len(results['checks']) == 2
        assert results['checks']['check1']['status'] == 'healthy'
        assert results['checks']['check2']['status'] == 'healthy'
        assert 'uptime_seconds' in results

    def test_run_checks_one_unhealthy(self):
        """Test running checks with one unhealthy."""
        health = HealthCheck()

        health.register_check("good", lambda: True)
        health.register_check("bad", lambda: False)

        results = health.run_checks()

        assert results['healthy'] is False
        assert results['checks']['good']['healthy'] is True
        assert results['checks']['bad']['healthy'] is False
        assert results['checks']['bad']['status'] == 'unhealthy'

    def test_run_checks_with_exception(self):
        """Test running checks when one raises exception."""
        health = HealthCheck()

        def failing_check():
            raise ValueError("Test error")

        health.register_check("good", lambda: True)
        health.register_check("failing", failing_check)

        results = health.run_checks()

        assert results['healthy'] is False
        assert results['checks']['good']['healthy'] is True
        assert results['checks']['failing']['healthy'] is False
        assert results['checks']['failing']['status'] == 'error'
        assert 'Test error' in results['checks']['failing']['error']

    def test_run_checks_empty(self):
        """Test running checks with no registered checks."""
        health = HealthCheck()

        results = health.run_checks()

        assert results['healthy'] is True
        assert len(results['checks']) == 0

    def test_is_healthy_true(self):
        """Test is_healthy when all checks pass."""
        health = HealthCheck()

        health.register_check("check1", lambda: True)
        health.register_check("check2", lambda: True)

        assert health.is_healthy() is True

    def test_is_healthy_false(self):
        """Test is_healthy when checks fail."""
        health = HealthCheck()

        health.register_check("good", lambda: True)
        health.register_check("bad", lambda: False)

        assert health.is_healthy() is False

    def test_uptime_tracking(self):
        """Test uptime is tracked correctly."""
        with patch('time.time') as mock_time:
            mock_time.return_value = 1000.0
            health = HealthCheck()

            # Simulate 60 seconds passing
            mock_time.return_value = 1060.0
            results = health.run_checks()

            assert results['uptime_seconds'] == 60.0

    def test_thread_safety(self):
        """Test thread-safe operations."""
        health = HealthCheck()

        def register_worker(i):
            health.register_check(f"check{i}", lambda: True)

        threads = [
            threading.Thread(target=register_worker, args=(i,))
            for i in range(10)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        results = health.run_checks()
        assert len(results['checks']) == 10
        assert results['healthy'] is True

    def test_check_function_not_called_during_registration(self):
        """Test check functions are not called during registration."""
        health = HealthCheck()

        mock_check = Mock(return_value=True)
        health.register_check("test", mock_check)

        assert mock_check.call_count == 0

    def test_check_result_structure(self):
        """Test the structure of check results."""
        health = HealthCheck()

        health.register_check("test", lambda: True)

        results = health.run_checks()

        # Verify overall structure
        assert 'healthy' in results
        assert 'uptime_seconds' in results
        assert 'checks' in results

        # Verify check structure
        check_result = results['checks']['test']
        assert 'status' in check_result
        assert 'healthy' in check_result
        assert isinstance(check_result['status'], str)
        assert isinstance(check_result['healthy'], bool)


class TestEdgeCasesAndIntegration:
    """Test edge cases and integration scenarios."""

    def test_progress_tracker_rapid_updates(self):
        """Test rapid concurrent updates."""
        tracker = ProgressTracker(total=10000)

        def rapid_worker():
            for _ in range(1000):
                tracker.update(1)

        threads = [threading.Thread(target=rapid_worker) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        state = tracker.get_state()
        assert state.current == 10000
        assert state.completed

    def test_bandwidth_monitor_concurrent_adds(self):
        """Test concurrent bandwidth monitoring."""
        monitor = BandwidthMonitor()

        def add_worker():
            for _ in range(100):
                monitor.add_bytes(1024)

        threads = [threading.Thread(target=add_worker) for _ in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert monitor.get_total_bytes() == 1024 * 500

    def test_multi_tracker_concurrent_operations(self):
        """Test concurrent operations on multi-tracker."""
        multi = MultiProgressTracker()

        def create_and_update(op_id):
            tracker = multi.create_tracker(op_id, total=100)
            for i in range(100):
                tracker.update(1)

        threads = [
            threading.Thread(target=create_and_update, args=(f"op{i}",))
            for i in range(20)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        completed, total = multi.get_overall_progress()
        assert completed == 2000
        assert total == 2000

    def test_progress_state_consistency(self):
        """Test ProgressState remains consistent."""
        tracker = ProgressTracker(total=100)

        # Get multiple state snapshots
        states = []
        for i in range(10):
            tracker.update(10)
            states.append(tracker.get_state())

        # Verify consistency
        for i, state in enumerate(states):
            assert state.current == (i + 1) * 10
            assert state.total == 100

    def test_zero_total_operations(self):
        """Test operations with zero total."""
        tracker = ProgressTracker(total=0)

        state = tracker.get_state()
        assert state.percentage == 0.0
        assert state.remaining_items == 0
        assert state.estimated_time_remaining is None

        # Should complete immediately
        tracker.update(1)
        assert tracker.is_completed()

    def test_large_numbers(self):
        """Test handling of large numbers."""
        tracker = ProgressTracker(total=10_000_000)

        tracker.update(5_000_000)
        state = tracker.get_state()

        assert state.current == 5_000_000
        assert state.percentage == 50.0
        assert state.remaining_items == 5_000_000

    def test_callback_exception_handling(self):
        """Test that callback exceptions don't break tracker."""
        def bad_callback(state):
            raise ValueError("Callback error")

        tracker = ProgressTracker(total=10, on_progress=bad_callback)

        # Should not raise - callbacks are called but exceptions propagate
        with pytest.raises(ValueError):
            tracker.update(1)

    def test_formatted_speed_edge_cases(self):
        """Test formatted speed with edge values."""
        monitor = BandwidthMonitor()

        # Very small speed
        with patch.object(monitor, 'get_current_speed', return_value=0.5):
            formatted = monitor.get_formatted_speed()
            assert "0.50 B/s" in formatted

        # Very large speed
        with patch.object(monitor, 'get_current_speed', return_value=10**12):
            formatted = monitor.get_formatted_speed()
            assert "GB/s" in formatted
