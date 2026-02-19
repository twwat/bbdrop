"""Proxy health monitoring and testing."""

import asyncio
import time
import logging
from typing import Optional, Dict, List, Callable, Awaitable
from dataclasses import dataclass

from src.proxy.models import ProxyProfile, ProxyHealth
from src.proxy.credentials import get_proxy_password

logger = logging.getLogger(__name__)


@dataclass
class HealthCheckConfig:
    """Configuration for health checks."""
    test_url: str = "https://httpbin.org/ip"
    timeout_seconds: float = 10.0
    check_interval_seconds: float = 300.0  # 5 minutes
    max_consecutive_failures: int = 3
    auto_disable_on_failure: bool = True
    # Alternative test endpoints
    fallback_urls: List[str] = None

    def __post_init__(self):
        if self.fallback_urls is None:
            self.fallback_urls = [
                "https://api.ipify.org",
                "https://icanhazip.com",
            ]


class HealthMonitor:
    """
    Monitors proxy health with async testing.

    Usage:
        monitor = HealthMonitor()
        health = await monitor.check_proxy(profile)
        # Or check all proxies
        results = await monitor.check_all(profiles)
    """

    def __init__(self, config: Optional[HealthCheckConfig] = None):
        self.config = config or HealthCheckConfig()
        self._health_cache: Dict[str, ProxyHealth] = {}
        self._running_checks: Dict[str, asyncio.Task] = {}
        self._listeners: List[Callable[[str, ProxyHealth], Awaitable[None]]] = []

    async def check_proxy(
        self,
        profile: ProxyProfile,
        password: Optional[str] = None
    ) -> ProxyHealth:
        """
        Check health of a single proxy.

        Args:
            profile: ProxyProfile to test
            password: Optional password (will try keyring if not provided)

        Returns:
            ProxyHealth with test results
        """
        # Get or create health record
        health = self._health_cache.get(profile.id) or ProxyHealth(profile_id=profile.id)

        time.time()
        success = False
        latency = 0.0

        try:
            # Get password if needed
            if profile.auth_required and not password:
                password = get_proxy_password(profile.id)

            # Try main URL, then fallbacks
            urls_to_try = [self.config.test_url] + self.config.fallback_urls

            for test_url in urls_to_try:
                try:
                    latency = await self._test_proxy(profile, password, test_url)
                    success = True
                    break
                except Exception as e:
                    logger.debug(f"Test URL {test_url} failed for {profile.name}: {e}")
                    continue

        except Exception as e:
            logger.warning(f"Health check failed for {profile.name}: {e}")

        # Update health record
        health.last_check = time.time()
        health.total_requests += 1

        if success:
            health.is_alive = True
            health.last_success = time.time()
            health.latency_ms = latency
            health.consecutive_failures = 0
        else:
            health.failed_requests += 1
            health.consecutive_failures += 1

            # Auto-disable if configured
            if (self.config.auto_disable_on_failure and
                health.consecutive_failures >= self.config.max_consecutive_failures):
                health.is_alive = False
                logger.warning(
                    f"Proxy {profile.name} marked as dead after "
                    f"{health.consecutive_failures} consecutive failures"
                )

        # Cache and notify
        self._health_cache[profile.id] = health
        await self._notify_listeners(profile.id, health)

        return health

    async def check_all(
        self,
        profiles: List[ProxyProfile],
        concurrent_limit: int = 10
    ) -> Dict[str, ProxyHealth]:
        """
        Check health of multiple proxies concurrently.

        Args:
            profiles: List of profiles to check
            concurrent_limit: Max concurrent checks

        Returns:
            Dict of profile_id -> ProxyHealth
        """
        semaphore = asyncio.Semaphore(concurrent_limit)

        async def limited_check(profile: ProxyProfile) -> tuple:
            async with semaphore:
                health = await self.check_proxy(profile)
                return profile.id, health

        tasks = [limited_check(p) for p in profiles if p.enabled]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        health_map = {}
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Health check error: {result}")
            else:
                profile_id, health = result
                health_map[profile_id] = health

        return health_map

    def get_health(self, profile_id: str) -> Optional[ProxyHealth]:
        """Get cached health for a profile."""
        return self._health_cache.get(profile_id)

    def get_all_health(self) -> Dict[str, ProxyHealth]:
        """Get all cached health data."""
        return self._health_cache.copy()

    def clear_health(self, profile_id: Optional[str] = None) -> None:
        """Clear health cache for one or all profiles."""
        if profile_id:
            self._health_cache.pop(profile_id, None)
        else:
            self._health_cache.clear()

    def add_listener(self, callback: Callable[[str, ProxyHealth], Awaitable[None]]) -> None:
        """Add health change listener."""
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[str, ProxyHealth], Awaitable[None]]) -> None:
        """Remove health change listener."""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def is_alive(self, profile_id: str) -> bool:
        """Quick check if proxy is alive (from cache)."""
        health = self._health_cache.get(profile_id)
        return health.is_alive if health else True  # Assume alive if no data

    def get_latency(self, profile_id: str) -> float:
        """Get cached latency for a proxy."""
        health = self._health_cache.get(profile_id)
        return health.latency_ms if health else 0.0

    async def _test_proxy(
        self,
        profile: ProxyProfile,
        password: Optional[str],
        test_url: str
    ) -> float:
        """
        Test a proxy by making a request through it.

        Returns latency in milliseconds.
        """
        import aiohttp

        # Build proxy URL
        proxy_url = self._build_proxy_url(profile, password)

        start = time.time()

        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            async with session.get(test_url, proxy=proxy_url) as response:
                await response.text()

                if response.status != 200:
                    raise Exception(f"HTTP {response.status}")

        latency_ms = (time.time() - start) * 1000
        return latency_ms

    def _build_proxy_url(self, profile: ProxyProfile, password: Optional[str]) -> str:
        """Build proxy URL for aiohttp."""
        scheme = profile.proxy_type.value

        if profile.auth_required and profile.username and password:
            return f"{scheme}://{profile.username}:{password}@{profile.host}:{profile.port}"

        return f"{scheme}://{profile.host}:{profile.port}"

    async def _notify_listeners(self, profile_id: str, health: ProxyHealth) -> None:
        """Notify all listeners of health change."""
        for listener in self._listeners:
            try:
                await listener(profile_id, health)
            except Exception as e:
                logger.error(f"Health listener error: {e}")


class PeriodicHealthChecker:
    """
    Runs periodic health checks in the background.

    Usage:
        checker = PeriodicHealthChecker(monitor, storage)
        await checker.start()
        # ... later
        await checker.stop()
    """

    def __init__(
        self,
        monitor: HealthMonitor,
        get_profiles: Callable[[], List[ProxyProfile]],
        interval_seconds: float = 300.0
    ):
        """
        Args:
            monitor: HealthMonitor instance
            get_profiles: Callback to get current profile list
            interval_seconds: Check interval
        """
        self.monitor = monitor
        self.get_profiles = get_profiles
        self.interval_seconds = interval_seconds
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """Start periodic health checking."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._check_loop())

    async def stop(self) -> None:
        """Stop periodic health checking."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    @property
    def is_running(self) -> bool:
        """Check if periodic checker is running."""
        return self._running

    async def _check_loop(self) -> None:
        """Main check loop."""
        while self._running:
            try:
                profiles = self.get_profiles()
                if profiles:
                    logger.log(5, f"Running periodic health check on {len(profiles)} proxies")
                    await self.monitor.check_all(profiles)

            except Exception as e:
                logger.error(f"Periodic health check error: {e}")

            await asyncio.sleep(self.interval_seconds)


def sync_check_proxy(profile: ProxyProfile, password: Optional[str] = None) -> ProxyHealth:
    """
    Synchronous wrapper for checking a single proxy.

    For use in non-async contexts.
    """
    monitor = HealthMonitor()
    return asyncio.run(monitor.check_proxy(profile, password))
