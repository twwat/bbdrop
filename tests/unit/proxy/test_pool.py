"""Unit tests for proxy pool rotation."""

import pytest
from unittest.mock import MagicMock, patch
import time

from src.proxy.models import (
    ProxyProfile, ProxyPool, ProxyEntry, ProxyHealth, RotationStrategy, ProxyType
)
from src.proxy.pool import PoolRotator


def create_test_entry(name: str, weight: int = 1) -> ProxyEntry:
    """Create a test proxy entry."""
    return ProxyEntry(
        host=f"{name.lower()}.proxy.com",
        port=8080,
        proxy_type=ProxyType.HTTP,
        weight=weight
    )


def create_test_pool(
    proxy_names: list,
    strategy: RotationStrategy = RotationStrategy.ROUND_ROBIN,
    weights: dict = None,
    sticky: bool = False
) -> ProxyPool:
    """Create a test pool with proxy entries."""
    proxies = []
    for name in proxy_names:
        weight = (weights or {}).get(name, 1)
        proxies.append(create_test_entry(name, weight=weight))

    return ProxyPool(
        name="Test Pool",
        proxies=proxies,
        rotation_strategy=strategy,
        sticky_sessions=sticky,
        sticky_ttl_seconds=60
    )


class TestPoolRotatorRoundRobin:
    """Tests for round-robin rotation strategy."""

    def test_cycles_through_proxies(self):
        """Test that round-robin cycles through all proxies."""
        pool = create_test_pool(["p1", "p2", "p3"])
        rotator = PoolRotator()

        # Should cycle: p1 -> p2 -> p3 -> p1 -> ...
        results = [rotator.get_next_proxy(pool) for _ in range(6)]

        # Get the host names to compare
        result_hosts = [r.host if r else None for r in results]
        assert result_hosts[:3] == ["p1.proxy.com", "p2.proxy.com", "p3.proxy.com"]
        assert result_hosts[3:6] == ["p1.proxy.com", "p2.proxy.com", "p3.proxy.com"]

    def test_single_proxy(self):
        """Test round-robin with single proxy."""
        pool = create_test_pool(["only"])
        rotator = PoolRotator()

        for _ in range(5):
            result = rotator.get_next_proxy(pool)
            assert result is not None
            assert result.host == "only.proxy.com"


class TestPoolRotatorRandom:
    """Tests for random rotation strategy."""

    def test_returns_from_pool(self):
        """Test that random returns proxies from the pool."""
        pool = create_test_pool(["p1", "p2", "p3"], RotationStrategy.RANDOM)
        rotator = PoolRotator()

        valid_hosts = {"p1.proxy.com", "p2.proxy.com", "p3.proxy.com"}
        for _ in range(20):
            result = rotator.get_next_proxy(pool)
            assert result is not None
            assert result.host in valid_hosts

    def test_distribution(self):
        """Test that random has reasonable distribution."""
        pool = create_test_pool(["p1", "p2", "p3"], RotationStrategy.RANDOM)
        rotator = PoolRotator()

        results = [rotator.get_next_proxy(pool) for _ in range(300)]
        hosts = [r.host for r in results]
        counts = {
            "p1.proxy.com": hosts.count("p1.proxy.com"),
            "p2.proxy.com": hosts.count("p2.proxy.com"),
            "p3.proxy.com": hosts.count("p3.proxy.com"),
        }

        # Each should be roughly 100 (allow 30% variance)
        for count in counts.values():
            assert 50 < count < 150


class TestPoolRotatorLeastUsed:
    """Tests for least-used rotation strategy."""

    def test_prefers_less_used(self):
        """Test that least-used prefers proxies with fewer requests."""
        pool = create_test_pool(["p1", "p2", "p3"], RotationStrategy.LEAST_USED)
        rotator = PoolRotator()

        # Use p1 several times by getting and tracking
        for _ in range(5):
            rotator.get_next_proxy(pool)  # This increments use count

        # Reset to force p1 to have high count
        rotator._use_counts[pool.id] = {0: 10, 1: 0, 2: 0}

        # Next selection should prefer indices 1 or 2 (p2 or p3)
        result = rotator.get_next_proxy(pool)
        assert result is not None
        assert result.host in ["p2.proxy.com", "p3.proxy.com"]

    def test_balanced_distribution(self):
        """Test that least-used balances usage over time."""
        pool = create_test_pool(["p1", "p2", "p3"], RotationStrategy.LEAST_USED)
        rotator = PoolRotator()

        # Simulate 30 requests - get_next_proxy auto-increments use count
        for _ in range(30):
            rotator.get_next_proxy(pool)

        # Check usage counts are balanced
        counts = rotator._use_counts.get(pool.id, {})
        if counts:
            values = list(counts.values())
            assert max(values) - min(values) <= 2


class TestPoolRotatorWeighted:
    """Tests for weighted rotation strategy."""

    def test_respects_weights(self):
        """Test that weighted respects weight ratios."""
        pool = create_test_pool(
            ["p1", "p2"],
            RotationStrategy.WEIGHTED,
            weights={"p1": 3, "p2": 1}
        )
        rotator = PoolRotator()

        results = [rotator.get_next_proxy(pool) for _ in range(400)]
        p1_count = sum(1 for r in results if r.host == "p1.proxy.com")
        p2_count = sum(1 for r in results if r.host == "p2.proxy.com")

        # p1 should be roughly 3x more common than p2
        ratio = p1_count / p2_count if p2_count > 0 else 0
        assert 2.0 < ratio < 4.0  # Allow some variance

    def test_default_weight(self):
        """Test that missing weights default to 1."""
        pool = create_test_pool(
            ["p1", "p2", "p3"],
            RotationStrategy.WEIGHTED,
            weights={"p1": 2}  # p2 and p3 default to 1
        )
        rotator = PoolRotator()

        # Should not raise and should include all proxies
        results = [rotator.get_next_proxy(pool) for _ in range(100)]
        hosts = {r.host for r in results}
        assert "p1.proxy.com" in hosts
        assert "p2.proxy.com" in hosts
        assert "p3.proxy.com" in hosts


class TestPoolRotatorFailover:
    """Tests for failover rotation strategy."""

    def test_uses_first_proxy(self):
        """Test that failover always uses first proxy when healthy."""
        pool = create_test_pool(["primary", "backup1", "backup2"], RotationStrategy.FAILOVER)
        rotator = PoolRotator()

        for _ in range(10):
            result = rotator.get_next_proxy(pool)
            assert result is not None
            assert result.host == "primary.proxy.com"

    def test_failover_to_backup(self):
        """Test failover when primary fails."""
        pool = create_test_pool(["primary", "backup1", "backup2"], RotationStrategy.FAILOVER)
        pool.max_consecutive_failures = 3
        rotator = PoolRotator()

        # Record failures for primary (index 0)
        for _ in range(3):
            rotator.report_failure(pool.id, 0)

        # Should now use backup1 (index 1)
        result = rotator.get_next_proxy(pool)
        assert result is not None
        assert result.host == "backup1.proxy.com"

    def test_recovery_after_success(self):
        """Test that proxy recovers after success."""
        pool = create_test_pool(["primary", "backup"], RotationStrategy.FAILOVER)
        pool.max_consecutive_failures = 2
        rotator = PoolRotator()

        # Fail primary (index 0)
        rotator.report_failure(pool.id, 0)
        rotator.report_failure(pool.id, 0)

        # Now using backup (index 1)
        result = rotator.get_next_proxy(pool)
        assert result is not None
        assert result.host == "backup.proxy.com"

        # Record success for primary (index 0)
        rotator.report_success(pool.id, 0)

        # Should return to primary
        result = rotator.get_next_proxy(pool)
        assert result is not None
        assert result.host == "primary.proxy.com"


class TestPoolRotatorStickySession:
    """Tests for sticky session functionality."""

    def test_sticky_returns_same_proxy(self):
        """Test that sticky session returns same proxy for same service."""
        pool = create_test_pool(["p1", "p2", "p3"], sticky=True)
        rotator = PoolRotator()

        # Get proxy for a service
        first = rotator.get_next_proxy(pool, service_key="rapidgator")

        # Should get same proxy for same service
        for _ in range(10):
            result = rotator.get_next_proxy(pool, service_key="rapidgator")
            assert result is not None
            assert result.host == first.host

    def test_different_services_different_proxies(self):
        """Test that different services can get different proxies."""
        pool = create_test_pool(["p1", "p2", "p3"], sticky=True)
        pool.rotation_strategy = RotationStrategy.ROUND_ROBIN
        rotator = PoolRotator()

        proxy1 = rotator.get_next_proxy(pool, service_key="service1")
        proxy2 = rotator.get_next_proxy(pool, service_key="service2")

        # They may be same or different, but should be consistent
        assert rotator.get_next_proxy(pool, service_key="service1").host == proxy1.host
        assert rotator.get_next_proxy(pool, service_key="service2").host == proxy2.host

    def test_sticky_expires(self):
        """Test that sticky session expires after TTL."""
        pool = create_test_pool(["p1", "p2", "p3"], sticky=True)
        pool.sticky_ttl_seconds = 1  # 1 second TTL
        rotator = PoolRotator()

        first = rotator.get_next_proxy(pool, service_key="test")

        # Wait for TTL to expire
        time.sleep(1.1)

        # May get different proxy now (depends on rotation)
        # At minimum, should not error
        rotator.get_next_proxy(pool, service_key="test")


class TestPoolRotatorHealthIntegration:
    """Tests for health-aware rotation."""

    def test_disabled_proxies_skipped(self):
        """Test that disabled proxies are skipped."""
        pool = create_test_pool(["p1", "p2", "p3"])
        # Disable the middle proxy
        pool.proxies[1].enabled = False
        rotator = PoolRotator()

        # Should only return enabled proxies
        results = set(
            rotator.get_next_proxy(pool).host
            for _ in range(20)
        )
        assert "p2.proxy.com" not in results
        assert "p1.proxy.com" in results
        assert "p3.proxy.com" in results

    def test_all_disabled_returns_none(self):
        """Test behavior when all proxies are disabled."""
        pool = create_test_pool(["p1", "p2"])
        # Disable all proxies
        for proxy in pool.proxies:
            proxy.enabled = False
        rotator = PoolRotator()

        # Should return None when all are disabled
        result = rotator.get_next_proxy(pool)
        assert result is None


class TestPoolRotatorRecording:
    """Tests for usage recording."""

    def test_report_success(self):
        """Test recording success clears failure count."""
        pool = create_test_pool(["p1"])
        rotator = PoolRotator()

        # Report failures for proxy index 0
        rotator.report_failure(pool.id, 0)
        rotator.report_failure(pool.id, 0)
        rotator.report_success(pool.id, 0)

        tracker = rotator._failure_trackers.get(pool.id, {}).get(0)
        assert tracker is None or tracker.consecutive_failures == 0

    def test_report_failure(self):
        """Test recording failures."""
        pool = create_test_pool(["p1"])
        rotator = PoolRotator()

        # Report failures for proxy index 0
        rotator.report_failure(pool.id, 0)
        rotator.report_failure(pool.id, 0)

        tracker = rotator._failure_trackers.get(pool.id, {}).get(0)
        assert tracker is not None
        assert tracker.consecutive_failures == 2
