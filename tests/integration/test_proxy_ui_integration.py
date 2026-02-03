"""Integration tests for proxy UI refactoring.

These tests verify the complete workflows and interactions between
ProxySettingsWidget, InheritableProxyControl, and ProxyStorage.
"""

import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSettings


@pytest.fixture(scope="module")
def qapp():
    """Create QApplication instance."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def clean_settings():
    """Create clean QSettings for testing."""
    settings = QSettings("bbdrop_test", "bbdrop_test")
    settings.clear()
    yield settings
    settings.clear()


@pytest.fixture
def proxy_storage(clean_settings):
    """Create ProxyStorage with clean settings."""
    from src.proxy.storage import ProxyStorage
    storage = ProxyStorage()
    storage._settings = clean_settings
    return storage


@pytest.fixture
def sample_pools():
    """Create sample proxy pools."""
    from src.proxy.models import ProxyPool, ProxyEntry, ProxyType, RotationStrategy

    pools = [
        ProxyPool(
            id="pool-1",
            name="Main Pool",
            enabled=True,
            rotation_strategy=RotationStrategy.ROUND_ROBIN,
            proxies=[
                ProxyEntry(host="proxy1.example.com", port=8080, proxy_type=ProxyType.HTTP),
                ProxyEntry(host="proxy2.example.com", port=8080, proxy_type=ProxyType.HTTP),
            ]
        ),
        ProxyPool(
            id="pool-2",
            name="Backup Pool",
            enabled=True,
            rotation_strategy=RotationStrategy.FAILOVER,
            proxies=[
                ProxyEntry(host="backup.example.com", port=3128, proxy_type=ProxyType.HTTPS),
            ]
        )
    ]
    return pools


class TestProxyModeIntegration:
    """Integration tests for proxy mode switching."""

    def test_mode_switch_persists_to_storage(self, qapp, proxy_storage):
        """Test that mode switches are persisted to storage."""
        from src.gui.widgets.proxy_settings_widget import ProxySettingsWidget

        with patch('src.gui.widgets.proxy_settings_widget.ProxyStorage', return_value=proxy_storage):
            widget = ProxySettingsWidget()

            # Switch to system proxy
            widget.system_proxy_radio.setChecked(True)
            widget._on_proxy_mode_changed()

            # Verify storage
            assert proxy_storage.get_use_os_proxy() is True
            assert proxy_storage.get_global_default_pool() is None

            # Switch to no proxy
            widget.no_proxy_radio.setChecked(True)
            widget._on_proxy_mode_changed()

            # Verify storage
            assert proxy_storage.get_use_os_proxy() is False
            assert proxy_storage.get_global_default_pool() is None

    def test_mode_restores_on_widget_creation(self, qapp, proxy_storage, sample_pools):
        """Test that proxy mode is correctly restored from storage."""
        # Set up storage state
        proxy_storage.set_use_os_proxy(True)

        from src.gui.widgets.proxy_settings_widget import ProxySettingsWidget

        with patch('src.gui.widgets.proxy_settings_widget.ProxyStorage', return_value=proxy_storage):
            widget = ProxySettingsWidget()

            # Should load system proxy mode
            assert widget.system_proxy_radio.isChecked()
            assert not widget.custom_proxy_radio.isChecked()

    def test_custom_mode_with_pools(self, qapp, proxy_storage, sample_pools):
        """Test that custom mode is selected when pools exist."""
        # Save pools to storage
        for pool in sample_pools:
            proxy_storage.save_pool(pool)
        proxy_storage.set_global_default_pool("pool-1")

        from src.gui.widgets.proxy_settings_widget import ProxySettingsWidget

        with patch('src.gui.widgets.proxy_settings_widget.ProxyStorage', return_value=proxy_storage):
            widget = ProxySettingsWidget()

            # Should load custom mode
            assert widget.custom_proxy_radio.isChecked()
            assert widget.pools_group.isEnabled()


class TestCategoryInheritanceIntegration:
    """Integration tests for category-level proxy inheritance."""

    def test_category_inherits_from_global_default(self, qapp, proxy_storage, sample_pools):
        """Test that category without override inherits from global."""
        # Set up storage
        for pool in sample_pools:
            proxy_storage.save_pool(pool)
        proxy_storage.set_global_default_pool("pool-1")

        from src.gui.widgets.inheritable_proxy_control import InheritableProxyControl

        with patch('src.gui.widgets.inheritable_proxy_control.ProxyStorage', return_value=proxy_storage):
            control = InheritableProxyControl(
                level="category",
                category="file_hosts"
            )

            # Should inherit global value
            assert control.get_effective_value() == "pool-1"
            assert not control.is_overriding()

    def test_category_override_saves_and_persists(self, qapp, proxy_storage, sample_pools):
        """Test that category override is saved and persists."""
        for pool in sample_pools:
            proxy_storage.save_pool(pool)
        proxy_storage.set_global_default_pool("pool-1")

        from src.gui.widgets.inheritable_proxy_control import InheritableProxyControl

        with patch('src.gui.widgets.inheritable_proxy_control.ProxyStorage', return_value=proxy_storage):
            # Create control and set override
            control = InheritableProxyControl(
                level="category",
                category="file_hosts"
            )
            control.set_override(True)

            # Find and select pool-2
            for i in range(control.combo.count()):
                if control.combo.itemData(i) == "pool-2":
                    control.combo.setCurrentIndex(i)
                    break

            # Verify storage
            assert proxy_storage.get_pool_assignment("file_hosts", None) == "pool-2"

            # Create new control (simulating reopen)
            control2 = InheritableProxyControl(
                level="category",
                category="file_hosts"
            )

            # Should restore override state
            assert control2.is_overriding()
            assert control2.get_effective_value() == "pool-2"

    def test_clearing_category_override_reverts_to_global(self, qapp, proxy_storage, sample_pools):
        """Test that clearing category override reverts to global value."""
        for pool in sample_pools:
            proxy_storage.save_pool(pool)
        proxy_storage.set_global_default_pool("pool-1")
        proxy_storage.set_pool_assignment("pool-2", "file_hosts", None)

        from src.gui.widgets.inheritable_proxy_control import InheritableProxyControl

        with patch('src.gui.widgets.inheritable_proxy_control.ProxyStorage', return_value=proxy_storage):
            control = InheritableProxyControl(
                level="category",
                category="file_hosts"
            )

            # Should start overriding
            assert control.is_overriding()
            assert control.get_effective_value() == "pool-2"

            # Clear override
            control.set_override(False)

            # Should revert to global
            assert not control.is_overriding()
            assert control.get_effective_value() == "pool-1"
            assert proxy_storage.get_pool_assignment("file_hosts", None) is None


class TestServiceInheritanceIntegration:
    """Integration tests for service-level proxy inheritance."""

    def test_service_inherits_from_category(self, qapp, proxy_storage, sample_pools):
        """Test service-level inheritance from category."""
        for pool in sample_pools:
            proxy_storage.save_pool(pool)
        proxy_storage.set_global_default_pool("pool-1")
        proxy_storage.set_pool_assignment("pool-2", "file_hosts", None)

        from src.gui.widgets.inheritable_proxy_control import InheritableProxyControl

        with patch('src.gui.widgets.inheritable_proxy_control.ProxyStorage', return_value=proxy_storage):
            control = InheritableProxyControl(
                level="service",
                category="file_hosts",
                service_id="rapidgator"
            )

            # Should inherit from category
            assert not control.is_overriding()
            assert control.get_effective_value() == "pool-2"

    def test_service_overrides_category(self, qapp, proxy_storage, sample_pools):
        """Test service-level override of category value."""
        for pool in sample_pools:
            proxy_storage.save_pool(pool)
        proxy_storage.set_pool_assignment("pool-1", "file_hosts", None)

        from src.gui.widgets.inheritable_proxy_control import InheritableProxyControl

        with patch('src.gui.widgets.inheritable_proxy_control.ProxyStorage', return_value=proxy_storage):
            control = InheritableProxyControl(
                level="service",
                category="file_hosts",
                service_id="pixeldrain"
            )

            # Set service-specific override
            control.set_override(True)
            for i in range(control.combo.count()):
                if control.combo.itemData(i) == "pool-2":
                    control.combo.setCurrentIndex(i)
                    break

            # Verify storage
            assert proxy_storage.get_pool_assignment("file_hosts", "pixeldrain") == "pool-2"
            assert control.is_overriding()

    def test_service_inherits_from_global_when_no_category_override(self, qapp, proxy_storage, sample_pools):
        """Test service falls back to global when category has no override."""
        for pool in sample_pools:
            proxy_storage.save_pool(pool)
        proxy_storage.set_global_default_pool("pool-1")

        from src.gui.widgets.inheritable_proxy_control import InheritableProxyControl

        with patch('src.gui.widgets.inheritable_proxy_control.ProxyStorage', return_value=proxy_storage):
            control = InheritableProxyControl(
                level="service",
                category="file_hosts",
                service_id="test_service"
            )

            # Should fall back to global (category has no override)
            assert not control.is_overriding()
            assert control.get_effective_value() == "pool-1"


class TestPoolManagementIntegration:
    """Integration tests for pool creation, deletion, and updates."""

    def test_pool_creation_updates_all_dropdowns(self, qapp, proxy_storage):
        """Test that creating a pool updates all dropdowns."""
        from src.gui.widgets.proxy_settings_widget import ProxySettingsWidget

        with patch('src.gui.widgets.proxy_settings_widget.ProxyStorage', return_value=proxy_storage):
            widget = ProxySettingsWidget()
            widget.custom_proxy_radio.setChecked(True)
            widget._update_ui_state()

            initial_count = widget.pools_list.count()

            # Create and save a pool
            from src.proxy.models import ProxyPool, ProxyEntry, ProxyType
            new_pool = ProxyPool(
                id="new-pool",
                name="New Pool",
                enabled=True,
                proxies=[
                    ProxyEntry(host="new.example.com", port=8080, proxy_type=ProxyType.HTTP)
                ]
            )
            proxy_storage.save_pool(new_pool)

            # Reload pools
            widget.load_pools()

            # Pools list should be updated
            assert widget.pools_list.count() > initial_count

    def test_pool_deletion_clears_assignments(self, qapp, proxy_storage, sample_pools):
        """Test that deleting a pool clears all assignments using it."""
        # Save pools
        for pool in sample_pools:
            proxy_storage.save_pool(pool)

        # Set assignments
        proxy_storage.set_pool_assignment("pool-1", "file_hosts", None)
        proxy_storage.set_pool_assignment("pool-1", "forums", None)

        # Delete pool
        proxy_storage.delete_pool("pool-1")

        # Assignments should be cleared
        assert proxy_storage.get_pool_assignment("file_hosts", None) is None
        assert proxy_storage.get_pool_assignment("forums", None) is None

    def test_pool_list_reflects_deletions(self, qapp, proxy_storage, sample_pools):
        """Test that pool list widget reflects deletions."""
        from src.gui.widgets.proxy_settings_widget import ProxySettingsWidget

        # Save pools
        for pool in sample_pools:
            proxy_storage.save_pool(pool)

        with patch('src.gui.widgets.proxy_settings_widget.ProxyStorage', return_value=proxy_storage):
            widget = ProxySettingsWidget()
            initial_count = widget.pools_list.count()

            # Delete a pool
            proxy_storage.delete_pool("pool-1")
            widget.load_pools()

            # List should have fewer items
            assert widget.pools_list.count() == initial_count - 1


class TestSpecialValuesIntegration:
    """Integration tests for special values (direct, os_proxy)."""

    def test_direct_connection_value_persists(self, qapp, proxy_storage):
        """Test that direct connection special value is stored correctly."""
        from src.gui.widgets.inheritable_proxy_control import InheritableProxyControl

        with patch('src.gui.widgets.inheritable_proxy_control.ProxyStorage', return_value=proxy_storage):
            control = InheritableProxyControl(
                level="category",
                category="file_hosts"
            )

            # Set to direct connection
            control.set_override(True)
            for i in range(control.combo.count()):
                if control.combo.itemData(i) == InheritableProxyControl.VALUE_DIRECT:
                    control.combo.setCurrentIndex(i)
                    break

            # Verify special value is stored (not None)
            stored_value = proxy_storage.get_pool_assignment("file_hosts", None)
            assert stored_value == "__direct__"

            # Create new control - should restore special value
            control2 = InheritableProxyControl(
                level="category",
                category="file_hosts"
            )
            assert control2.get_effective_value() == "__direct__"

    def test_os_proxy_value_persists(self, qapp, proxy_storage):
        """Test that OS proxy special value is stored correctly."""
        from src.gui.widgets.inheritable_proxy_control import InheritableProxyControl

        with patch('src.gui.widgets.inheritable_proxy_control.ProxyStorage', return_value=proxy_storage):
            control = InheritableProxyControl(
                level="category",
                category="api"
            )

            # Set to OS proxy
            control.set_override(True)
            for i in range(control.combo.count()):
                if control.combo.itemData(i) == InheritableProxyControl.VALUE_OS_PROXY:
                    control.combo.setCurrentIndex(i)
                    break

            # Verify special value is stored
            stored_value = proxy_storage.get_pool_assignment("api", None)
            assert stored_value == "__os_proxy__"


class TestUIRefreshIntegration:
    """Integration tests for UI refresh after storage changes."""

    def test_widget_refresh_after_external_storage_change(self, qapp, proxy_storage, sample_pools):
        """Test that widget refreshes correctly after external storage changes."""
        from src.gui.widgets.proxy_settings_widget import ProxySettingsWidget

        with patch('src.gui.widgets.proxy_settings_widget.ProxyStorage', return_value=proxy_storage):
            widget = ProxySettingsWidget()

            # Simulate external change (another process modifies storage)
            for pool in sample_pools:
                proxy_storage.save_pool(pool)

            # Refresh widget
            widget.load_pools()

            # Pools should appear in list
            assert widget.pools_list.count() == len(sample_pools)

    def test_all_controls_refresh_synchronously(self, qapp, proxy_storage, sample_pools):
        """Test that all dropdown widgets refresh together."""
        from src.gui.widgets.proxy_settings_widget import ProxySettingsWidget

        with patch('src.gui.widgets.proxy_settings_widget.ProxyStorage', return_value=proxy_storage):
            widget = ProxySettingsWidget()

            # Get initial list count
            initial_count = widget.pools_list.count()

            # Add pools
            for pool in sample_pools:
                proxy_storage.save_pool(pool)

            widget.load_pools()

            # Pools list should be updated with new pools
            new_count = widget.pools_list.count()
            assert new_count == initial_count + len(sample_pools)


class TestEdgeCasesIntegration:
    """Integration tests for edge cases and error conditions."""

    def test_deleted_pool_reference_handled_gracefully(self, qapp, proxy_storage, sample_pools):
        """Test that references to deleted pools are handled gracefully."""
        # Save pool and assign it
        proxy_storage.save_pool(sample_pools[0])
        proxy_storage.set_pool_assignment("pool-1", "file_hosts", None)

        # Delete the pool
        proxy_storage.delete_pool("pool-1")

        from src.gui.widgets.inheritable_proxy_control import InheritableProxyControl

        with patch('src.gui.widgets.inheritable_proxy_control.ProxyStorage', return_value=proxy_storage):
            # Create control - should handle deleted pool gracefully
            control = InheritableProxyControl(
                level="category",
                category="file_hosts"
            )

            # Assignment should be cleared (returns None after pool deletion)
            assert control.get_effective_value() in [None, "__direct__"]

    def test_disabled_pool_not_in_dropdown(self, qapp, proxy_storage):
        """Test that disabled pools don't appear in dropdowns."""
        from src.proxy.models import ProxyPool, ProxyEntry, ProxyType

        disabled_pool = ProxyPool(
            id="disabled-pool",
            name="Disabled Pool",
            enabled=False,
            proxies=[
                ProxyEntry(host="disabled.example.com", port=8080, proxy_type=ProxyType.HTTP)
            ]
        )
        proxy_storage.save_pool(disabled_pool)

        from src.gui.widgets.inheritable_proxy_control import InheritableProxyControl

        with patch('src.gui.widgets.inheritable_proxy_control.ProxyStorage', return_value=proxy_storage):
            control = InheritableProxyControl(level="global")

            # Get all pool IDs from combo
            pool_ids = [control.combo.itemData(i) for i in range(control.combo.count())]

            # Disabled pool should not be present
            assert "disabled-pool" not in pool_ids


@pytest.mark.slow
class TestPerformanceIntegration:
    """Performance-related integration tests."""

    def test_many_pools_performance(self, qapp, proxy_storage):
        """Test UI performance with many proxy pools."""
        from src.proxy.models import ProxyPool, ProxyEntry, ProxyType

        # Create 50 pools
        pools = [
            ProxyPool(
                id=f"pool-{i}",
                name=f"Pool {i}",
                enabled=True,
                proxies=[
                    ProxyEntry(host=f"proxy{i}.example.com", port=8080, proxy_type=ProxyType.HTTP)
                ]
            )
            for i in range(50)
        ]

        for pool in pools:
            proxy_storage.save_pool(pool)

        from src.gui.widgets.proxy_settings_widget import ProxySettingsWidget

        with patch('src.gui.widgets.proxy_settings_widget.ProxyStorage', return_value=proxy_storage):
            import time
            start = time.time()

            widget = ProxySettingsWidget()
            widget.load_pools()

            elapsed = time.time() - start

            # Should load quickly even with many pools (< 2 seconds)
            assert elapsed < 2.0
            assert widget.pools_list.count() == 50
