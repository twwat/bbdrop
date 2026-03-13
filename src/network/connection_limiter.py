"""Shared per-host connection limiter using semaphores.

Ensures upload workers and the scanner share the same per-host connection pool.
If a host has max_connections=4 and 3 upload workers are active, the scanner
can only use 1 connection.
"""

import threading
from contextlib import contextmanager
from typing import Dict, Optional

from src.utils.logger import log


class ConnectionLimiter:
    """Registry of per-host semaphores for connection limiting.

    Thread-safe. Semaphores are created lazily on first access per host.
    """

    DEFAULT_LIMIT = 2

    def __init__(
        self,
        host_limits: Optional[Dict[str, int]] = None,
        default_limit: int = DEFAULT_LIMIT,
    ):
        self._limits: Dict[str, int] = dict(host_limits or {})
        self._default_limit = default_limit
        self._semaphores: Dict[str, threading.Semaphore] = {}
        self._lock = threading.Lock()

    def _get_semaphore(self, host_id: str) -> threading.Semaphore:
        """Get or create the semaphore for a host (thread-safe)."""
        with self._lock:
            if host_id not in self._semaphores:
                limit = self._limits.get(host_id, self._default_limit)
                self._semaphores[host_id] = threading.Semaphore(limit)
            return self._semaphores[host_id]

    def get_limit(self, host_id: str) -> int:
        """Get the max_connections limit for a host."""
        return self._limits.get(host_id, self._default_limit)

    def acquire(self, host_id: str, timeout: Optional[float] = None) -> bool:
        """Acquire a connection slot for a host.

        Args:
            host_id: Host identifier.
            timeout: Seconds to wait. None = block forever. 0 = non-blocking.

        Returns:
            True if slot acquired, False if timed out.
        """
        sem = self._get_semaphore(host_id)
        if timeout is not None:
            return sem.acquire(timeout=timeout)
        return sem.acquire()

    def release(self, host_id: str) -> None:
        """Release a connection slot for a host."""
        sem = self._get_semaphore(host_id)
        sem.release()

    def available(self, host_id: str) -> int:
        """Get approximate available slots for a host.

        Note: This is a snapshot and may be stale in concurrent scenarios.
        """
        sem = self._get_semaphore(host_id)
        # Semaphore._value is CPython-specific but reliable for diagnostics
        return sem._value

    @contextmanager
    def connection(self, host_id: str, timeout: Optional[float] = None):
        """Context manager for acquiring/releasing a connection slot.

        Args:
            host_id: Host identifier.
            timeout: Seconds to wait. None = block forever.

        Raises:
            TimeoutError: If timeout expires before slot is available.
        """
        if timeout is not None:
            acquired = self.acquire(host_id, timeout=timeout)
            if not acquired:
                raise TimeoutError(f"Timed out waiting for {host_id} connection slot")
        else:
            self.acquire(host_id)

        try:
            yield
        finally:
            self.release(host_id)

    def set_limit(self, host_id: str, limit: int) -> None:
        """Update the connection limit for a host.

        Creates a new semaphore with the new limit. Only safe to call
        when no connections are active for this host.
        """
        with self._lock:
            self._limits[host_id] = limit
            self._semaphores[host_id] = threading.Semaphore(limit)
