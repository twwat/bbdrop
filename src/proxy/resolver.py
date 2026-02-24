"""Proxy resolution engine."""

import os
from typing import Optional

from src.proxy.models import ProxyEntry, ProxyContext, ProxyType
from src.proxy.storage import ProxyStorage
from src.proxy.pool import PoolRotator


# Special values for proxy assignments
PROXY_DIRECT = "__direct__"
PROXY_OS_PROXY = "__os_proxy__"
PROXY_TOR = "__tor__"

_SPECIAL_VALUES = (PROXY_DIRECT, PROXY_OS_PROXY, PROXY_TOR)


class ProxyResolver:
    """Resolves proxy for a given context.

    Now pool-centric: pools contain proxies directly, no separate profiles needed.

    Resolution hierarchy (3 levels, most specific wins):
    1. Service-level (e.g., file_hosts/rapidgator)
    2. Category-level (e.g., file_hosts)
    3. Global-level

    Special values:
    - "__direct__" - Direct connection (no proxy)
    - "__os_proxy__" - Use OS system proxy
    - "__tor__" - Use Tor SOCKS5 proxy (127.0.0.1:9050)
    """

    def __init__(
        self,
        storage: Optional[ProxyStorage] = None,
        rotator: Optional[PoolRotator] = None
    ):
        self._storage = storage or ProxyStorage()
        self._rotator = rotator or PoolRotator()

    def _resolve_special_value(self, value: str) -> Optional[ProxyEntry]:
        """Resolve a special value to a ProxyEntry or None."""
        if value == PROXY_DIRECT:
            return None
        if value == PROXY_OS_PROXY:
            return self._get_os_proxy()
        if value == PROXY_TOR:
            return self._get_tor_proxy()
        return None

    def _get_tor_proxy(self) -> Optional[ProxyEntry]:
        """Create ephemeral Tor proxy entry."""
        from src.proxy.tor import TOR_HOST, TOR_SOCKS_PORT
        return ProxyEntry(
            host=TOR_HOST,
            port=TOR_SOCKS_PORT,
            proxy_type=ProxyType.SOCKS5,
            resolve_dns_through_proxy=True,
        )

    def resolve(self, context: ProxyContext) -> Optional[ProxyEntry]:
        """
        Resolve proxy for a given context.

        Resolution hierarchy:
        0. Legacy guard: global_default_pool unset → direct (old radio-button state)
        1. Category special values (__direct__, __os_proxy__, __tor__)
        2. Service pool assignment (e.g., file_hosts/rapidgator -> pool or special)
        3. Category pool assignment (e.g., file_hosts -> "Main Pool")
        4. Global default (pool or special value)
        5. Legacy fallback: use_os_proxy boolean
        6. None (direct connection)

        Args:
            context: ProxyContext with category and service_id

        Returns:
            ProxyEntry if proxy should be used, None for direct connection
        """
        service_key = f"{context.category}/{context.service_id}" if context.service_id else context.category

        # 0. Legacy guard: if global default was never set (None), no proxy is
        #    configured at all.  Return direct immediately.  This matches the old
        #    radio-button "No proxy" behavior and prevents stale service/category
        #    assignments from leaking through.
        global_pool = self._storage.get_global_default_pool()
        if not global_pool and not self._storage.get_use_os_proxy():
            return None

        # 1. Check category-level assignment (special values short-circuit)
        cat_pool_id = self._storage.get_pool_assignment(context.category)
        if cat_pool_id and cat_pool_id in _SPECIAL_VALUES:
            return self._resolve_special_value(cat_pool_id)

        # 2. Check service-level pool assignment
        if context.service_id:
            pool_id = self._storage.get_pool_assignment(context.category, context.service_id)
            if pool_id:
                if pool_id in _SPECIAL_VALUES:
                    return self._resolve_special_value(pool_id)
                pool = self._storage.load_pool(pool_id)
                if pool and pool.enabled and pool.proxies:
                    proxy = self._rotator.get_next_proxy(pool, service_key)
                    if proxy:
                        return proxy

        # 3. Check category pool (if it's an actual pool ID, not special value)
        if cat_pool_id and cat_pool_id not in _SPECIAL_VALUES:
            pool = self._storage.load_pool(cat_pool_id)
            if pool and pool.enabled and pool.proxies:
                proxy = self._rotator.get_next_proxy(pool, service_key)
                if proxy:
                    return proxy

        # 4. Check global default
        if global_pool:
            if global_pool in _SPECIAL_VALUES:
                return self._resolve_special_value(global_pool)
            pool = self._storage.load_pool(global_pool)
            if pool and pool.enabled and pool.proxies:
                proxy = self._rotator.get_next_proxy(pool, service_key)
                if proxy:
                    return proxy

        # 5. Legacy fallback: check use_os_proxy boolean
        if self._storage.get_use_os_proxy():
            return self._get_os_proxy()

        # 6. Direct connection
        return None

    def report_result(self, pool_id: str, proxy_index: int, success: bool) -> None:
        """Report proxy usage result."""
        pool = self._storage.load_pool(pool_id)
        if not pool:
            return

        if success:
            self._rotator.report_success(pool_id, proxy_index)
        else:
            self._rotator.report_failure(pool_id, proxy_index, pool.max_consecutive_failures)

    def _get_os_proxy(self) -> Optional[ProxyEntry]:
        """Get OS proxy settings from environment."""
        for var in ['HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy']:
            proxy_url = os.environ.get(var)
            if proxy_url:
                return self._parse_proxy_url(proxy_url)
        return None

    def _parse_proxy_url(self, url: str) -> Optional[ProxyEntry]:
        """Parse proxy URL into ProxyEntry."""
        from urllib.parse import urlparse, unquote

        try:
            parsed = urlparse(url)

            scheme = parsed.scheme.lower()
            if scheme in ('socks5', 'socks5h'):
                proxy_type = ProxyType.SOCKS5
            elif scheme == 'socks4':
                proxy_type = ProxyType.SOCKS4
            elif scheme == 'https':
                proxy_type = ProxyType.HTTPS
            else:
                proxy_type = ProxyType.HTTP

            return ProxyEntry(
                host=parsed.hostname or '',
                port=parsed.port or 8080,
                proxy_type=proxy_type,
                username=unquote(parsed.username) if parsed.username else '',
                password=unquote(parsed.password) if parsed.password else '',
            )
        except Exception:
            return None

    def get_effective_proxy_info(self, context: ProxyContext) -> dict:
        """Get information about which proxy will be used and why."""
        info = {
            'proxy': None,
            'pool': None,
            'source': 'direct',
            'reason': 'No proxy configured'
        }

        service_key = f"{context.category}/{context.service_id}" if context.service_id else context.category

        # Check service-level pool (if service_id provided)
        if context.service_id:
            pool_id = self._storage.get_pool_assignment(context.category, context.service_id)
            if pool_id:
                if pool_id == PROXY_DIRECT:
                    info['source'] = 'service'
                    info['reason'] = f"Service override: Direct connection ({context.service_id})"
                    return info
                if pool_id == PROXY_OS_PROXY:
                    proxy = self._get_os_proxy()
                    if proxy:
                        info['proxy'] = proxy
                        info['source'] = 'service'
                        info['reason'] = f"Service override: OS proxy ({context.service_id})"
                        return info
                if pool_id == PROXY_TOR:
                    info['proxy'] = self._get_tor_proxy()
                    info['source'] = 'service'
                    info['reason'] = f"Service override: Tor ({context.service_id})"
                    return info

                pool = self._storage.load_pool(pool_id)
                if pool and pool.enabled and pool.proxies:
                    info['pool'] = pool
                    info['source'] = 'service'
                    info['reason'] = f"Service pool: {pool.name} ({context.service_id})"
                    info['proxy'] = self._rotator.get_next_proxy(pool, service_key)
                    return info

        # Check category pool
        pool_id = self._storage.get_pool_assignment(context.category)
        if pool_id:
            if pool_id == PROXY_DIRECT:
                info['source'] = 'category'
                info['reason'] = f"Category override: Direct connection ({context.category})"
                return info
            if pool_id == PROXY_OS_PROXY:
                proxy = self._get_os_proxy()
                if proxy:
                    info['proxy'] = proxy
                    info['source'] = 'category'
                    info['reason'] = f"Category override: OS proxy ({context.category})"
                    return info
            if pool_id == PROXY_TOR:
                info['proxy'] = self._get_tor_proxy()
                info['source'] = 'category'
                info['reason'] = f"Category override: Tor ({context.category})"
                return info

            pool = self._storage.load_pool(pool_id)
            if pool and pool.enabled and pool.proxies:
                info['pool'] = pool
                info['source'] = 'category'
                info['reason'] = f"Category pool: {pool.name} ({context.category})"
                info['proxy'] = self._rotator.get_next_proxy(pool, service_key)
                return info

        # Check global pool
        pool_id = self._storage.get_global_default_pool()
        if pool_id:
            if pool_id == PROXY_TOR:
                info['proxy'] = self._get_tor_proxy()
                info['source'] = 'global'
                info['reason'] = 'Global: Tor'
                return info
            pool = self._storage.load_pool(pool_id)
            if pool and pool.enabled and pool.proxies:
                info['pool'] = pool
                info['source'] = 'global'
                info['reason'] = f"Global pool: {pool.name}"
                info['proxy'] = self._rotator.get_next_proxy(pool, service_key)
                return info

        # Check OS proxy
        if self._storage.get_use_os_proxy():
            proxy = self._get_os_proxy()
            if proxy:
                info['proxy'] = proxy
                info['source'] = 'os'
                info['reason'] = 'OS environment proxy'
                return info

        return info
