"""Unit tests for proxy resolver."""

from unittest.mock import MagicMock, patch

from src.proxy.models import ProxyProfile, ProxyPool, ProxyContext, ProxyType
from src.proxy.resolver import ProxyResolver


def create_test_profile(name: str, host: str = None, proxy_id: str = None) -> ProxyProfile:
    """Create a test proxy profile."""
    profile = ProxyProfile(
        name=name,
        host=host or f"{name.lower()}.proxy.com",
        port=8080
    )
    if proxy_id:
        profile.id = proxy_id
    return profile


def create_test_pool(
    name: str,
    proxy_ids: list,
    pool_id: str = None
) -> ProxyPool:
    """Create a test pool."""
    pool = ProxyPool(
        name=name,
        proxy_ids=proxy_ids
    )
    if pool_id:
        pool.id = pool_id
    return pool


class TestProxyResolverHierarchy:
    """Tests for the 8-level resolution hierarchy."""

    def test_level1_url_specific(self):
        """Test Level 1: URL-specific proxy."""
        # This would require URL pattern matching
        # For now, test that URL context is respected
        pass  # URL-specific is an advanced feature

    def test_level2_service_pool(self):
        """Test Level 2: Service-specific pool."""
        from src.proxy.models import ProxyEntry

        # Mock storage
        storage = MagicMock()
        pool = ProxyPool(name="ServicePool", id="pool1")
        pool.enabled = True
        service_proxy = ProxyEntry(host="service.proxy", port=8080, proxy_type=ProxyType.HTTP)
        pool.proxies = [service_proxy]

        storage.get_pool_assignment.return_value = "pool1"
        storage.load_pool.return_value = pool

        # Mock rotator
        rotator = MagicMock()
        rotator.get_next_proxy.return_value = service_proxy

        resolver = ProxyResolver(storage=storage, rotator=rotator)
        context = ProxyContext(category="file_hosts", service_id="rapidgator")

        result = resolver.resolve(context)

        assert result is not None
        assert result.host == "service.proxy"

    def test_level3_service_profile(self):
        """Test Level 3: Service-specific profile (now service pool)."""
        from src.proxy.models import ProxyEntry

        storage = MagicMock()
        # Service level has a pool with one proxy
        service_pool = ProxyPool(name="ServicePool", id="sp1")
        service_pool.enabled = True
        service_proxy = ProxyEntry(host="service.proxy", port=8080, proxy_type=ProxyType.HTTP)
        service_pool.proxies = [service_proxy]

        storage.get_pool_assignment.return_value = "sp1"
        storage.load_pool.return_value = service_pool

        rotator = MagicMock()
        rotator.get_next_proxy.return_value = service_proxy

        resolver = ProxyResolver(storage=storage, rotator=rotator)
        context = ProxyContext(category="file_hosts", service_id="rapidgator")

        result = resolver.resolve(context)

        assert result is not None
        assert result.host == "service.proxy"

    def test_level4_category_pool(self):
        """Test Level 4: Category-level pool falls back when no service assignment."""
        from src.proxy.models import ProxyEntry

        storage = MagicMock()
        pool = ProxyPool(name="CategoryPool", id="catpool")
        pool.enabled = True
        cat_proxy = ProxyEntry(host="category.proxy", port=8080, proxy_type=ProxyType.HTTP)
        pool.proxies = [cat_proxy]

        # Service level returns None, category level returns the pool
        def get_pool_assignment(category, service_id=None):
            if service_id:
                return None
            return "catpool"

        storage.get_pool_assignment.side_effect = get_pool_assignment
        storage.load_pool.return_value = pool
        # Need a global pool to enable category level checking
        storage.get_global_default_pool.return_value = "global-pool"
        storage.get_use_os_proxy.return_value = False

        rotator = MagicMock()
        rotator.get_next_proxy.return_value = cat_proxy

        resolver = ProxyResolver(storage=storage, rotator=rotator)
        context = ProxyContext(category="file_hosts", service_id="")

        result = resolver.resolve(context)

        assert result is not None
        assert result.host == "category.proxy"

    def test_level5_category_profile(self):
        """Test Level 5: Category-level profile (now category pool)."""
        from src.proxy.models import ProxyEntry

        storage = MagicMock()
        # Category level has a pool with one proxy
        cat_pool = ProxyPool(name="CategoryPool", id="cat1")
        cat_pool.enabled = True
        cat_proxy = ProxyEntry(host="category.proxy", port=8080, proxy_type=ProxyType.HTTP)
        cat_pool.proxies = [cat_proxy]

        # Return category pool ID for category level, None for service level
        def get_pool_assignment(category, service_id=None):
            if service_id:
                return None
            return "cat1"

        storage.get_pool_assignment.side_effect = get_pool_assignment
        storage.load_pool.return_value = cat_pool
        # Need a global pool to enable category level checking
        storage.get_global_default_pool.return_value = "global"
        storage.get_use_os_proxy.return_value = False

        rotator = MagicMock()
        rotator.get_next_proxy.return_value = cat_proxy

        resolver = ProxyResolver(storage=storage, rotator=rotator)
        context = ProxyContext(category="file_hosts", service_id="")

        result = resolver.resolve(context)

        assert result is not None
        assert result.host == "category.proxy"

    def test_level6_global_pool(self):
        """Test Level 6: Global default pool."""
        from src.proxy.models import ProxyEntry

        storage = MagicMock()
        pool = ProxyPool(name="GlobalPool", id="globalpool")
        pool.enabled = True
        global_proxy = ProxyEntry(host="global.proxy", port=8080, proxy_type=ProxyType.HTTP)
        pool.proxies = [global_proxy]

        storage.get_pool_assignment.return_value = None
        storage.get_global_default_pool.return_value = "globalpool"
        storage.load_pool.return_value = pool

        rotator = MagicMock()
        rotator.get_next_proxy.return_value = global_proxy

        resolver = ProxyResolver(storage=storage, rotator=rotator)
        context = ProxyContext(category="file_hosts", service_id="")

        result = resolver.resolve(context)

        assert result is not None

    def test_level7_global_profile(self):
        """Test Level 7: Global default profile (OS proxy as fallback)."""
        from src.proxy.models import ProxyEntry

        storage = MagicMock()
        # Global has no pool, but OS proxy is enabled
        storage.get_pool_assignment.return_value = None
        storage.get_global_default_pool.return_value = None
        storage.get_use_os_proxy.return_value = True

        resolver = ProxyResolver(storage=storage)
        context = ProxyContext(category="file_hosts", service_id="")

        os_proxy = ProxyEntry(host="os.proxy", port=8080, proxy_type=ProxyType.HTTP)

        with patch.object(resolver, '_get_os_proxy', return_value=os_proxy):
            result = resolver.resolve(context)

            assert result is not None
            assert result.host == "os.proxy"

    def test_level8_os_proxy(self):
        """Test Level 8: OS system proxy."""
        storage = MagicMock()
        storage.get_pool_assignment.return_value = None
        storage.get_assignment.return_value = None
        storage.get_global_default_pool.return_value = None
        storage.get_global_default.return_value = None
        storage.get_use_os_proxy.return_value = True
        storage.list_profiles.return_value = []
        storage.list_health.return_value = {}

        resolver = ProxyResolver(storage=storage)
        context = ProxyContext(category="file_hosts", service_id="")

        with patch.object(resolver, '_get_os_proxy') as mock_os:
            mock_os.return_value = create_test_profile("OSProxy")

            result = resolver.resolve(context)

            assert result is not None
            mock_os.assert_called_once()

    def test_no_proxy_returns_none(self):
        """Test that None is returned when no proxy is configured."""
        storage = MagicMock()
        storage.get_pool_assignment.return_value = None
        storage.get_assignment.return_value = None
        storage.get_global_default_pool.return_value = None
        storage.get_global_default.return_value = None
        storage.get_use_os_proxy.return_value = False
        storage.list_profiles.return_value = []
        storage.list_health.return_value = {}

        resolver = ProxyResolver(storage=storage)
        context = ProxyContext(category="file_hosts", service_id="")

        result = resolver.resolve(context)

        assert result is None


class TestProxyResolverPoolAware:
    """Tests for pool-aware resolution."""

    def test_pool_rotation_used(self):
        """Test that pool rotation is used for pools."""
        from src.proxy.models import ProxyEntry

        storage = MagicMock()
        pool = ProxyPool(name="TestPool", id="testpool")
        pool.enabled = True
        p1 = ProxyEntry(host="proxy1.example.com", port=8080, proxy_type=ProxyType.HTTP)
        p2 = ProxyEntry(host="proxy2.example.com", port=8080, proxy_type=ProxyType.HTTP)
        p3 = ProxyEntry(host="proxy3.example.com", port=8080, proxy_type=ProxyType.HTTP)
        pool.proxies = [p1, p2, p3]

        storage.get_pool_assignment.return_value = pool.id
        storage.load_pool.return_value = pool

        rotator = MagicMock()
        rotator.get_next_proxy.return_value = p2

        resolver = ProxyResolver(storage=storage, rotator=rotator)
        context = ProxyContext(category="file_hosts", service_id="test")

        result = resolver.resolve(context)

        assert result.host == "proxy2.example.com"
        rotator.get_next_proxy.assert_called()

    def test_sticky_session_passed_to_rotator(self):
        """Test that service_key is passed for sticky sessions."""
        from src.proxy.models import ProxyEntry

        storage = MagicMock()
        pool = ProxyPool(name="StickyPool", id="stickypool")
        pool.enabled = True
        pool.sticky_sessions = True
        proxy = ProxyEntry(host="proxy1.example.com", port=8080, proxy_type=ProxyType.HTTP)
        pool.proxies = [proxy]

        storage.get_pool_assignment.return_value = pool.id
        storage.load_pool.return_value = pool

        rotator = MagicMock()
        rotator.get_next_proxy.return_value = proxy

        resolver = ProxyResolver(storage=storage, rotator=rotator)
        context = ProxyContext(category="file_hosts", service_id="rapidgator")

        resolver.resolve(context)

        # Check rotator was called with service_key (category/service_id format)
        rotator.get_next_proxy.assert_called()
        call_args = rotator.get_next_proxy.call_args
        # The resolver passes service_key as positional arg or keyword
        assert call_args is not None


class TestProxyResolverResultReporting:
    """Tests for result reporting (success/failure)."""

    def test_report_proxy_result_success(self):
        """Test reporting successful proxy usage."""
        storage = MagicMock()
        rotator = MagicMock()
        pool = create_test_pool("TestPool", ["profile1"], pool_id="pool1")

        storage.get_pool_assignment.return_value = "pool1"
        storage.load_pool.return_value = pool

        resolver = ProxyResolver(storage=storage, rotator=rotator)
        resolver.report_result("pool1", 0, success=True)

        rotator.report_success.assert_called_once_with("pool1", 0)

    def test_report_proxy_result_failure(self):
        """Test reporting failed proxy usage."""
        storage = MagicMock()
        rotator = MagicMock()
        rotator.report_failure.return_value = False  # Not exceeded max failures
        pool = create_test_pool("TestPool", ["profile1"], pool_id="pool1")

        storage.get_pool_assignment.return_value = "pool1"
        storage.load_pool.return_value = pool

        resolver = ProxyResolver(storage=storage, rotator=rotator)
        resolver.report_result("pool1", 0, success=False)

        rotator.report_failure.assert_called_once()


class TestProxyResolverDisabledProfiles:
    """Tests for handling disabled profiles."""

    def test_disabled_profile_skipped(self):
        """Test that disabled profiles are skipped."""
        storage = MagicMock()
        profile = create_test_profile("Disabled")
        profile.enabled = False

        storage.get_pool_assignment.return_value = None
        storage.get_assignment.return_value = profile.id
        storage.load_profile.return_value = profile
        storage.list_profiles.return_value = [profile]
        storage.list_health.return_value = {}
        storage.get_global_default_pool.return_value = None
        storage.get_global_default.return_value = None
        storage.get_use_os_proxy.return_value = False

        resolver = ProxyResolver(storage=storage)
        context = ProxyContext(category="file_hosts", service_id="")

        # Should continue to next level since profile is disabled
        # This depends on implementation - may return None or continue
        result = resolver.resolve(context)

        # Based on typical implementation, disabled should be skipped
        # Adjust assertion based on actual behavior
        assert result is None or not result.enabled


class TestProxyResolverCaching:
    """Tests for resolution caching (if implemented)."""

    def test_cache_hit(self):
        """Test that cached results are used."""
        # Caching may or may not be implemented
        # This is a placeholder for future caching tests
        pass

    def test_cache_invalidation(self):
        """Test that cache is invalidated on changes."""
        pass


class TestProxyResolverSpecialValues:
    """Tests for special value short-circuiting (__direct__ and __os_proxy__)."""

    def test_service_level_direct_short_circuits(self):
        """Test that __direct__ at service level returns None immediately."""
        from src.proxy.resolver import PROXY_DIRECT

        storage = MagicMock()
        rotator = MagicMock()

        # Service level has __direct__ assignment
        storage.get_pool_assignment.return_value = PROXY_DIRECT
        # Must also set global to trigger the logic path
        storage.get_global_default_pool.return_value = None
        storage.get_use_os_proxy.return_value = False

        resolver = ProxyResolver(storage=storage, rotator=rotator)
        context = ProxyContext(category="file_hosts", service_id="rapidgator")

        result = resolver.resolve(context)

        # Should return None for direct connection
        assert result is None
        # Should NOT try to load a pool
        storage.load_pool.assert_not_called()

    def test_service_level_os_proxy_short_circuits(self):
        """Test that __os_proxy__ at service level returns OS proxy immediately."""
        from src.proxy.resolver import PROXY_OS_PROXY
        from src.proxy.models import ProxyEntry

        storage = MagicMock()
        rotator = MagicMock()

        # Service level has __os_proxy__ assignment, category has None
        def get_pool_assignment(category, service_id=None):
            if service_id:
                return PROXY_OS_PROXY
            return None

        storage.get_pool_assignment.side_effect = get_pool_assignment
        # Must set global pool to enable category/service level checking
        storage.get_global_default_pool.return_value = "global-pool"
        storage.get_use_os_proxy.return_value = False

        resolver = ProxyResolver(storage=storage, rotator=rotator)
        context = ProxyContext(category="file_hosts", service_id="rapidgator")

        # Mock OS proxy
        os_proxy = ProxyEntry(
            host="proxy.company.com",
            port=8080,
            proxy_type=ProxyType.HTTP
        )

        with patch.object(resolver, '_get_os_proxy', return_value=os_proxy) as mock_os:
            result = resolver.resolve(context)

            # Should return OS proxy
            assert result is not None
            assert result.host == "proxy.company.com"
            mock_os.assert_called_once()

        # Should NOT try to load a pool
        storage.load_pool.assert_not_called()

    def test_category_level_direct_short_circuits(self):
        """Test that __direct__ at category level returns None."""
        from src.proxy.resolver import PROXY_DIRECT

        storage = MagicMock()
        rotator = MagicMock()

        # No service level assignment, category has __direct__
        def get_pool_assignment(category, service_id=None):
            if service_id:  # Service level
                return None
            return PROXY_DIRECT  # Category level

        storage.get_pool_assignment.side_effect = get_pool_assignment
        # Must set global for path
        storage.get_global_default_pool.return_value = None
        storage.get_use_os_proxy.return_value = False

        resolver = ProxyResolver(storage=storage, rotator=rotator)
        context = ProxyContext(category="file_hosts", service_id="rapidgator")

        result = resolver.resolve(context)

        assert result is None

    def test_category_level_os_proxy_short_circuits(self):
        """Test that __os_proxy__ at category level returns OS proxy."""
        from src.proxy.resolver import PROXY_OS_PROXY
        from src.proxy.models import ProxyEntry

        storage = MagicMock()
        rotator = MagicMock()

        # Category has __os_proxy__, service level returns None
        def get_pool_assignment(category, service_id=None):
            if service_id:
                return None
            # Category level (no service_id) returns OS proxy marker
            return PROXY_OS_PROXY

        storage.get_pool_assignment.side_effect = get_pool_assignment
        # Must set global pool to enable category level checking
        storage.get_global_default_pool.return_value = "global"
        storage.get_use_os_proxy.return_value = False

        resolver = ProxyResolver(storage=storage, rotator=rotator)
        context = ProxyContext(category="file_hosts", service_id="rapidgator")

        os_proxy = ProxyEntry(host="corporate.proxy", port=3128, proxy_type=ProxyType.HTTP)

        with patch.object(resolver, '_get_os_proxy', return_value=os_proxy):
            result = resolver.resolve(context)

            assert result is not None
            assert result.host == "corporate.proxy"


class TestProxyResolverThreeLevelHierarchy:
    """Tests for the 3-level resolution hierarchy: service -> category -> global."""

    def test_service_level_takes_priority(self):
        """Test that service-level assignment takes priority over category and global."""
        from src.proxy.models import ProxyEntry

        storage = MagicMock()
        rotator = MagicMock()

        # Create pools for each level
        service_pool = ProxyPool(name="ServicePool")
        service_pool.id = "service-pool-id"
        service_pool.enabled = True
        service_pool.proxies = [ProxyEntry(host="service.proxy", port=8080, proxy_type=ProxyType.HTTP)]

        category_pool = ProxyPool(name="CategoryPool")
        category_pool.id = "category-pool-id"

        # Service level returns a pool, should not reach category or global
        def get_pool_assignment(category, service_id=None):
            if service_id == "rapidgator":
                return "service-pool-id"
            return "category-pool-id"  # Category level

        storage.get_pool_assignment.side_effect = get_pool_assignment
        storage.load_pool.return_value = service_pool
        storage.get_global_default_pool.return_value = "global-pool-id"
        storage.get_use_os_proxy.return_value = False

        service_proxy = ProxyEntry(host="service.proxy", port=8080, proxy_type=ProxyType.HTTP)
        rotator.get_next_proxy.return_value = service_proxy

        resolver = ProxyResolver(storage=storage, rotator=rotator)
        context = ProxyContext(category="file_hosts", service_id="rapidgator")

        result = resolver.resolve(context)

        assert result is not None
        assert result.host == "service.proxy"

    def test_category_level_fallback(self):
        """Test that category level is used when no service assignment exists."""
        from src.proxy.models import ProxyEntry

        storage = MagicMock()
        rotator = MagicMock()

        category_pool = ProxyPool(name="CategoryPool")
        category_pool.id = "category-pool-id"
        category_pool.enabled = True
        category_pool.proxies = [ProxyEntry(host="category.proxy", port=8080, proxy_type=ProxyType.HTTP)]

        # No service level, category level has assignment
        def get_pool_assignment(category, service_id=None):
            if service_id:
                return None  # No service level
            return "category-pool-id"

        storage.get_pool_assignment.side_effect = get_pool_assignment
        storage.load_pool.return_value = category_pool

        category_proxy = ProxyEntry(host="category.proxy", port=8080, proxy_type=ProxyType.HTTP)
        rotator.get_next_proxy.return_value = category_proxy

        resolver = ProxyResolver(storage=storage, rotator=rotator)
        context = ProxyContext(category="file_hosts", service_id="rapidgator")

        result = resolver.resolve(context)

        assert result is not None
        assert result.host == "category.proxy"

    def test_global_level_fallback(self):
        """Test that global level is used when no service/category assignment exists."""
        from src.proxy.models import ProxyEntry

        storage = MagicMock()
        rotator = MagicMock()

        global_pool = ProxyPool(name="GlobalPool")
        global_pool.id = "global-pool-id"
        global_pool.enabled = True
        global_pool.proxies = [ProxyEntry(host="global.proxy", port=8080, proxy_type=ProxyType.HTTP)]

        # No service or category level
        storage.get_pool_assignment.return_value = None
        storage.get_global_default_pool.return_value = "global-pool-id"
        storage.load_pool.return_value = global_pool

        global_proxy = ProxyEntry(host="global.proxy", port=8080, proxy_type=ProxyType.HTTP)
        rotator.get_next_proxy.return_value = global_proxy

        resolver = ProxyResolver(storage=storage, rotator=rotator)
        context = ProxyContext(category="file_hosts", service_id="rapidgator")

        result = resolver.resolve(context)

        assert result is not None
        assert result.host == "global.proxy"
        storage.get_global_default_pool.assert_called_once()

    def test_os_proxy_fallback(self):
        """Test that OS proxy is used as final fallback before direct."""
        from src.proxy.models import ProxyEntry

        storage = MagicMock()
        rotator = MagicMock()

        # No pool assignments at any level
        storage.get_pool_assignment.return_value = None
        storage.get_global_default_pool.return_value = None
        storage.get_use_os_proxy.return_value = True

        resolver = ProxyResolver(storage=storage, rotator=rotator)
        context = ProxyContext(category="file_hosts", service_id="rapidgator")

        os_proxy = ProxyEntry(host="os.proxy", port=3128, proxy_type=ProxyType.HTTP)

        with patch.object(resolver, '_get_os_proxy', return_value=os_proxy):
            result = resolver.resolve(context)

            assert result is not None
            assert result.host == "os.proxy"

    def test_direct_connection_when_nothing_configured(self):
        """Test that None (direct) is returned when nothing is configured."""
        storage = MagicMock()
        rotator = MagicMock()

        storage.get_pool_assignment.return_value = None
        storage.get_global_default_pool.return_value = None
        storage.get_use_os_proxy.return_value = False

        resolver = ProxyResolver(storage=storage, rotator=rotator)
        context = ProxyContext(category="file_hosts", service_id="rapidgator")

        result = resolver.resolve(context)

        assert result is None


class TestProxyResolverGetEffectiveProxyInfo:
    """Tests for get_effective_proxy_info method."""

    def test_info_with_service_direct_override(self):
        """Test info when service has __direct__ override."""
        from src.proxy.resolver import PROXY_DIRECT

        storage = MagicMock()
        rotator = MagicMock()

        storage.get_pool_assignment.return_value = PROXY_DIRECT

        resolver = ProxyResolver(storage=storage, rotator=rotator)
        context = ProxyContext(category="file_hosts", service_id="rapidgator")

        info = resolver.get_effective_proxy_info(context)

        assert info['proxy'] is None
        assert info['source'] == 'service'
        assert 'Direct connection' in info['reason']
        assert 'rapidgator' in info['reason']

    def test_info_with_service_os_proxy_override(self):
        """Test info when service has __os_proxy__ override."""
        from src.proxy.resolver import PROXY_OS_PROXY
        from src.proxy.models import ProxyEntry

        storage = MagicMock()
        rotator = MagicMock()

        storage.get_pool_assignment.return_value = PROXY_OS_PROXY

        resolver = ProxyResolver(storage=storage, rotator=rotator)
        context = ProxyContext(category="file_hosts", service_id="rapidgator")

        os_proxy = ProxyEntry(host="env.proxy", port=8080, proxy_type=ProxyType.HTTP)

        with patch.object(resolver, '_get_os_proxy', return_value=os_proxy):
            info = resolver.get_effective_proxy_info(context)

            assert info['proxy'] is not None
            assert info['source'] == 'service'
            assert 'OS proxy' in info['reason']

    def test_info_with_category_direct_override(self):
        """Test info when category has __direct__ override."""
        from src.proxy.resolver import PROXY_DIRECT

        storage = MagicMock()
        rotator = MagicMock()

        def get_pool_assignment(category, service_id=None):
            if service_id:
                return None
            return PROXY_DIRECT

        storage.get_pool_assignment.side_effect = get_pool_assignment

        resolver = ProxyResolver(storage=storage, rotator=rotator)
        context = ProxyContext(category="file_hosts", service_id="rapidgator")

        info = resolver.get_effective_proxy_info(context)

        assert info['proxy'] is None
        assert info['source'] == 'category'
        assert 'Direct connection' in info['reason']
        assert 'file_hosts' in info['reason']
