"""Proxy pool rotation and management."""

import random
import time
import threading
from typing import Optional, Dict, List
from dataclasses import dataclass

from src.proxy.models import ProxyPool, ProxyEntry, RotationStrategy


@dataclass
class StickySession:
    """Tracks sticky session binding."""
    proxy_index: int
    service_key: str
    created_at: float
    ttl_seconds: int


@dataclass
class FailureTracker:
    """Tracks proxy failures for rotation decisions."""
    proxy_index: int
    consecutive_failures: int = 0
    last_failure_time: Optional[float] = None
    total_failures: int = 0


class PoolRotator:
    """Manages proxy rotation within a pool.

    Thread-safe implementation using a lock for all state mutations.
    """

    def __init__(self):
        self._lock = threading.Lock()
        # pool_id -> current index for round-robin
        self._round_robin_indices: Dict[str, int] = {}
        # pool_id -> {proxy_index -> use_count} for least-used
        self._use_counts: Dict[str, Dict[int, int]] = {}
        # pool_id -> {service_key -> StickySession}
        self._sticky_sessions: Dict[str, Dict[str, StickySession]] = {}
        # pool_id -> {proxy_index -> FailureTracker}
        self._failure_trackers: Dict[str, Dict[int, FailureTracker]] = {}

    def get_next_proxy(
        self,
        pool: ProxyPool,
        service_key: Optional[str] = None,
    ) -> Optional[ProxyEntry]:
        """
        Get next proxy from pool using configured rotation strategy.

        Args:
            pool: The proxy pool
            service_key: Optional service key for sticky sessions

        Returns:
            ProxyEntry to use, or None if no healthy proxies available
        """
        if not pool.enabled or not pool.proxies:
            return None

        with self._lock:
            # Check sticky session first
            if pool.sticky_sessions and service_key:
                sticky_idx = self._get_sticky_index(pool.id, service_key, pool.sticky_ttl_seconds)
                if sticky_idx is not None and self._is_proxy_available(sticky_idx, pool):
                    return pool.proxies[sticky_idx]

            # Get available proxy indices
            available = self._get_available_indices(pool)
            if not available:
                return None

            # Select based on strategy
            selected_idx = self._select_by_strategy(pool, available)
            if selected_idx is None:
                return None

            # Update sticky session if enabled
            if pool.sticky_sessions and service_key:
                self._set_sticky_index(pool.id, service_key, selected_idx, pool.sticky_ttl_seconds)

            # Track usage for least-used strategy
            self._increment_use_count(pool.id, selected_idx)

            return pool.proxies[selected_idx]

    def report_success(self, pool_id: str, proxy_index: int) -> None:
        """Report successful proxy use."""
        with self._lock:
            if pool_id not in self._failure_trackers:
                self._failure_trackers[pool_id] = {}

            tracker = self._failure_trackers[pool_id].get(proxy_index)
            if tracker:
                tracker.consecutive_failures = 0

    def report_failure(self, pool_id: str, proxy_index: int, max_failures: int = 3) -> bool:
        """
        Report proxy failure.

        Returns:
            True if proxy should be disabled (exceeded max failures)
        """
        with self._lock:
            if pool_id not in self._failure_trackers:
                self._failure_trackers[pool_id] = {}

            if proxy_index not in self._failure_trackers[pool_id]:
                self._failure_trackers[pool_id][proxy_index] = FailureTracker(proxy_index=proxy_index)

            tracker = self._failure_trackers[pool_id][proxy_index]
            tracker.consecutive_failures += 1
            tracker.total_failures += 1
            tracker.last_failure_time = time.time()

            return tracker.consecutive_failures >= max_failures

    def clear_sticky_session(self, pool_id: str, service_key: str) -> None:
        """Clear sticky session for a service."""
        with self._lock:
            if pool_id in self._sticky_sessions:
                self._sticky_sessions[pool_id].pop(service_key, None)

    def clear_all_sticky_sessions(self, pool_id: str) -> None:
        """Clear all sticky sessions for a pool."""
        with self._lock:
            self._sticky_sessions.pop(pool_id, None)

    def reset_pool_state(self, pool_id: str) -> None:
        """Reset all rotation state for a pool."""
        with self._lock:
            self._round_robin_indices.pop(pool_id, None)
            self._use_counts.pop(pool_id, None)
            self._sticky_sessions.pop(pool_id, None)
            self._failure_trackers.pop(pool_id, None)

    def get_pool_stats(self, pool_id: str) -> Dict:
        """Get rotation statistics for a pool."""
        return {
            'round_robin_index': self._round_robin_indices.get(pool_id, 0),
            'use_counts': self._use_counts.get(pool_id, {}),
            'sticky_sessions': len(self._sticky_sessions.get(pool_id, {})),
            'failure_trackers': {
                idx: {
                    'consecutive': t.consecutive_failures,
                    'total': t.total_failures
                }
                for idx, t in self._failure_trackers.get(pool_id, {}).items()
            }
        }

    # === Private Methods ===

    def _get_available_indices(self, pool: ProxyPool) -> List[int]:
        """Get list of available proxy indices."""
        available = []
        failure_trackers = self._failure_trackers.get(pool.id, {})

        for idx, proxy in enumerate(pool.proxies):
            if not proxy.enabled:
                continue

            # Check failure count
            tracker = failure_trackers.get(idx)
            if tracker and tracker.consecutive_failures >= pool.max_consecutive_failures:
                continue

            available.append(idx)

        return available

    def _is_proxy_available(self, proxy_index: int, pool: ProxyPool) -> bool:
        """Check if a specific proxy is available."""
        if proxy_index >= len(pool.proxies):
            return False

        proxy = pool.proxies[proxy_index]
        if not proxy.enabled:
            return False

        tracker = self._failure_trackers.get(pool.id, {}).get(proxy_index)
        if tracker and tracker.consecutive_failures >= pool.max_consecutive_failures:
            return False

        return True

    def _select_by_strategy(self, pool: ProxyPool, available: List[int]) -> Optional[int]:
        """Select proxy index based on rotation strategy."""
        if not available:
            return None

        strategy = pool.rotation_strategy

        if strategy == RotationStrategy.ROUND_ROBIN:
            return self._select_round_robin(pool.id, available)

        elif strategy == RotationStrategy.RANDOM:
            return random.choice(available)

        elif strategy == RotationStrategy.LEAST_USED:
            return self._select_least_used(pool.id, available)

        elif strategy == RotationStrategy.WEIGHTED:
            return self._select_weighted(pool, available)

        elif strategy == RotationStrategy.FAILOVER:
            return self._select_failover(available)

        return self._select_round_robin(pool.id, available)

    def _select_round_robin(self, pool_id: str, available: List[int]) -> int:
        """Select next proxy in round-robin order."""
        if pool_id not in self._round_robin_indices:
            self._round_robin_indices[pool_id] = 0

        index = self._round_robin_indices[pool_id] % len(available)
        self._round_robin_indices[pool_id] = index + 1

        return available[index]

    def _select_least_used(self, pool_id: str, available: List[int]) -> int:
        """Select proxy with lowest use count."""
        if pool_id not in self._use_counts:
            self._use_counts[pool_id] = {}

        counts = self._use_counts[pool_id]

        min_count = float('inf')
        min_idx = available[0]

        for idx in available:
            count = counts.get(idx, 0)
            if count < min_count:
                min_count = count
                min_idx = idx

        return min_idx

    def _select_weighted(self, pool: ProxyPool, available: List[int]) -> int:
        """Select proxy based on configured weights."""
        weights = []
        for idx in available:
            proxy = pool.proxies[idx]
            weights.append(proxy.weight)

        if sum(weights) == 0:
            return random.choice(available)

        return random.choices(available, weights=weights, k=1)[0]

    def _select_failover(self, available: List[int]) -> int:
        """Select first available proxy (failover mode)."""
        return available[0]

    def _get_sticky_index(self, pool_id: str, service_key: str, ttl: int) -> Optional[int]:
        """Get sticky proxy index for a service if still valid."""
        if pool_id not in self._sticky_sessions:
            return None

        session = self._sticky_sessions[pool_id].get(service_key)
        if not session:
            return None

        if time.time() - session.created_at > ttl:
            del self._sticky_sessions[pool_id][service_key]
            return None

        return session.proxy_index

    def _set_sticky_index(self, pool_id: str, service_key: str, proxy_index: int, ttl: int) -> None:
        """Set sticky proxy for a service."""
        if pool_id not in self._sticky_sessions:
            self._sticky_sessions[pool_id] = {}

        self._sticky_sessions[pool_id][service_key] = StickySession(
            proxy_index=proxy_index,
            service_key=service_key,
            created_at=time.time(),
            ttl_seconds=ttl
        )

    def _increment_use_count(self, pool_id: str, proxy_index: int) -> None:
        """Increment use count for a proxy."""
        if pool_id not in self._use_counts:
            self._use_counts[pool_id] = {}

        self._use_counts[pool_id][proxy_index] = self._use_counts[pool_id].get(proxy_index, 0) + 1
