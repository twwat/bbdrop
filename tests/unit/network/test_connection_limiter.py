"""Tests for ConnectionLimiter — shared per-host connection semaphores."""

import pytest
import threading
import time

from src.network.connection_limiter import ConnectionLimiter


class TestConnectionLimiterBasic:
    """Test basic semaphore creation and acquisition."""

    def test_default_limit(self):
        """Default max_connections should be 2."""
        limiter = ConnectionLimiter()
        assert limiter.get_limit('turbo') == 2

    def test_custom_limit(self):
        """Custom max_connections should be respected."""
        limiter = ConnectionLimiter(host_limits={'turbo': 5})
        assert limiter.get_limit('turbo') == 5

    def test_acquire_release(self):
        """Should be able to acquire and release a connection slot."""
        limiter = ConnectionLimiter(host_limits={'turbo': 2})
        assert limiter.acquire('turbo', timeout=1.0) is True
        assert limiter.available('turbo') == 1
        limiter.release('turbo')
        assert limiter.available('turbo') == 2

    def test_acquire_blocks_at_limit(self):
        """Acquiring beyond limit should fail with timeout."""
        limiter = ConnectionLimiter(host_limits={'turbo': 1})
        assert limiter.acquire('turbo', timeout=0.1) is True
        # Second acquire should fail (timeout)
        assert limiter.acquire('turbo', timeout=0.1) is False
        limiter.release('turbo')

    def test_context_manager(self):
        """connection() context manager should acquire/release."""
        limiter = ConnectionLimiter(host_limits={'turbo': 2})
        with limiter.connection('turbo'):
            assert limiter.available('turbo') == 1
        assert limiter.available('turbo') == 2

    def test_context_manager_releases_on_exception(self):
        """connection() should release slot even on exception."""
        limiter = ConnectionLimiter(host_limits={'turbo': 1})
        with pytest.raises(ValueError):
            with limiter.connection('turbo'):
                raise ValueError("test error")
        # Should be released
        assert limiter.available('turbo') == 1


class TestConnectionLimiterConcurrency:
    """Test concurrent access patterns."""

    def test_multiple_hosts_independent(self):
        """Different hosts should have independent limits."""
        limiter = ConnectionLimiter(host_limits={'turbo': 1, 'rapidgator': 1})
        assert limiter.acquire('turbo', timeout=0.1) is True
        # Should still be able to acquire rapidgator
        assert limiter.acquire('rapidgator', timeout=0.1) is True
        limiter.release('turbo')
        limiter.release('rapidgator')

    def test_shared_between_upload_and_scan(self):
        """Upload acquiring a slot should reduce scanner availability."""
        limiter = ConnectionLimiter(host_limits={'turbo': 2})
        # Simulate uploader taking one slot
        limiter.acquire('turbo')
        assert limiter.available('turbo') == 1
        # Scanner can still get one slot
        assert limiter.acquire('turbo', timeout=0.1) is True
        # No more slots
        assert limiter.acquire('turbo', timeout=0.1) is False
        limiter.release('turbo')
        limiter.release('turbo')

    def test_thread_safety(self):
        """Multiple threads should safely acquire/release."""
        limiter = ConnectionLimiter(host_limits={'turbo': 3})
        errors = []
        acquired_count = 0
        lock = threading.Lock()

        def worker():
            nonlocal acquired_count
            try:
                if limiter.acquire('turbo', timeout=2.0):
                    with lock:
                        acquired_count += 1
                    time.sleep(0.01)
                    limiter.release('turbo')
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not errors
        assert limiter.available('turbo') == 3

    def test_unknown_host_uses_default(self):
        """Host without explicit limit should use default."""
        limiter = ConnectionLimiter(default_limit=3)
        assert limiter.get_limit('new_host') == 3


class TestConnectionLimiterUpdateLimits:
    """Test dynamic limit updates."""

    def test_update_limit(self):
        """Updating a host limit should take effect."""
        limiter = ConnectionLimiter(host_limits={'turbo': 2})
        limiter.set_limit('turbo', 4)
        assert limiter.get_limit('turbo') == 4
        assert limiter.available('turbo') == 4
