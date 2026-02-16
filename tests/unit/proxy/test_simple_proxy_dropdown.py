"""Unit tests for simplified proxy UI dropdown functionality.

Tests cover the refactored proxy settings widget with radio button modes
and hierarchical proxy assignment using InheritableProxyControl.
"""

import pytest
from unittest.mock import MagicMock, patch, call
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    """Create QApplication instance for Qt widgets."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def mock_storage():
    """Create mock ProxyStorage instance."""
    storage = MagicMock()
    storage.list_pools.return_value = []
    storage.get_pool_assignment.return_value = None
    storage.get_global_default_pool.return_value = None
    storage.get_use_os_proxy.return_value = False
    return storage


@pytest.fixture
def mock_pools():
    """Create mock proxy pools for testing."""
    from src.proxy.models import ProxyPool, ProxyEntry, ProxyType, RotationStrategy

    pool1 = ProxyPool(
        id="pool-uuid-1",
        name="Main Pool",
        enabled=True,
        rotation_strategy=RotationStrategy.ROUND_ROBIN,
        proxies=[
            ProxyEntry(host="proxy1.example.com", port=8080, proxy_type=ProxyType.HTTP),
            ProxyEntry(host="proxy2.example.com", port=8080, proxy_type=ProxyType.HTTP),
        ]
    )

    pool2 = ProxyPool(
        id="pool-uuid-2",
        name="Backup Pool",
        enabled=True,
        rotation_strategy=RotationStrategy.RANDOM,
        proxies=[
            ProxyEntry(host="backup.example.com", port=3128, proxy_type=ProxyType.HTTPS),
        ]
    )

    pool3 = ProxyPool(
        id="pool-uuid-3",
        name="Disabled Pool",
        enabled=False,
        proxies=[
            ProxyEntry(host="disabled.example.com", port=8080, proxy_type=ProxyType.HTTP),
        ]
    )

    return [pool1, pool2, pool3]


class TestProxyModeRadioButtons:
    """Tests for proxy mode radio button selection."""

    def test_initial_mode_no_proxy(self, qapp, mock_storage):
        """Test that 'No proxy' is selected when no configuration exists."""
        from src.gui.settings.proxy_tab import ProxySettingsWidget

        with patch('src.gui.settings.proxy_tab.ProxyStorage', return_value=mock_storage):
            widget = ProxySettingsWidget()

            assert widget.no_proxy_radio.isChecked()
            assert not widget.system_proxy_radio.isChecked()
            assert not widget.custom_proxy_radio.isChecked()

    def test_initial_mode_system_proxy(self, qapp, mock_storage):
        """Test that 'System proxy' is selected when OS proxy is enabled."""
        mock_storage.get_use_os_proxy.return_value = True

        from src.gui.settings.proxy_tab import ProxySettingsWidget

        with patch('src.gui.settings.proxy_tab.ProxyStorage', return_value=mock_storage):
            widget = ProxySettingsWidget()

            assert not widget.no_proxy_radio.isChecked()
            assert widget.system_proxy_radio.isChecked()
            assert not widget.custom_proxy_radio.isChecked()

    def test_initial_mode_custom_proxy(self, qapp, mock_storage, mock_pools):
        """Test that 'Custom proxy' is selected when pools exist."""
        mock_storage.list_pools.return_value = mock_pools[:2]  # Only enabled pools
        mock_storage.get_global_default_pool.return_value = "pool-uuid-1"

        from src.gui.settings.proxy_tab import ProxySettingsWidget

        with patch('src.gui.settings.proxy_tab.ProxyStorage', return_value=mock_storage):
            widget = ProxySettingsWidget()

            assert not widget.no_proxy_radio.isChecked()
            assert not widget.system_proxy_radio.isChecked()
            assert widget.custom_proxy_radio.isChecked()

    def test_switching_to_no_proxy_saves_settings(self, qapp, mock_storage):
        """Test that switching to 'No proxy' clears proxy settings."""
        from src.gui.settings.proxy_tab import ProxySettingsWidget

        with patch('src.gui.settings.proxy_tab.ProxyStorage', return_value=mock_storage):
            widget = ProxySettingsWidget()

            # Switch to no proxy mode
            widget.no_proxy_radio.setChecked(True)
            widget._on_proxy_mode_changed()

            # Should clear global default and OS proxy
            mock_storage.set_global_default_pool.assert_called_with(None)
            mock_storage.set_use_os_proxy.assert_called_with(False)

    def test_switching_to_system_proxy_saves_settings(self, qapp, mock_storage):
        """Test that switching to 'System proxy' enables OS proxy."""
        from src.gui.settings.proxy_tab import ProxySettingsWidget

        with patch('src.gui.settings.proxy_tab.ProxyStorage', return_value=mock_storage):
            widget = ProxySettingsWidget()

            # Switch to system proxy mode
            widget.system_proxy_radio.setChecked(True)
            widget._on_proxy_mode_changed()

            # Should enable OS proxy and clear pool
            mock_storage.set_global_default_pool.assert_called_with(None)
            mock_storage.set_use_os_proxy.assert_called_with(True)

    def test_mode_change_emits_signal(self, qapp, mock_storage):
        """Test that changing proxy mode emits settings_changed signal."""
        from src.gui.settings.proxy_tab import ProxySettingsWidget

        with patch('src.gui.settings.proxy_tab.ProxyStorage', return_value=mock_storage):
            widget = ProxySettingsWidget()

            signal_spy = MagicMock()
            widget.settings_changed.connect(signal_spy)

            # Change mode
            widget.system_proxy_radio.setChecked(True)
            widget._on_proxy_mode_changed()

            signal_spy.assert_called_once()


class TestProxyUIStateManagement:
    """Tests for UI state enable/disable based on proxy mode."""

    def test_custom_mode_enables_configuration_sections(self, qapp, mock_storage):
        """Test that custom mode enables all proxy configuration sections."""
        from src.gui.settings.proxy_tab import ProxySettingsWidget

        with patch('src.gui.settings.proxy_tab.ProxyStorage', return_value=mock_storage):
            widget = ProxySettingsWidget()

            # Switch to custom mode
            widget.custom_proxy_radio.setChecked(True)
            widget._update_ui_state()

            assert widget.pools_group.isEnabled()
            assert widget.category_group.isEnabled()

    def test_no_proxy_mode_disables_configuration_sections(self, qapp, mock_storage):
        """Test that no proxy mode disables all configuration sections."""
        from src.gui.settings.proxy_tab import ProxySettingsWidget

        with patch('src.gui.settings.proxy_tab.ProxyStorage', return_value=mock_storage):
            widget = ProxySettingsWidget()

            # Switch to no proxy mode
            widget.no_proxy_radio.setChecked(True)
            widget._update_ui_state()

            assert not widget.pools_group.isEnabled()
            assert not widget.category_group.isEnabled()

    def test_system_proxy_mode_disables_configuration_sections(self, qapp, mock_storage):
        """Test that system proxy mode disables all configuration sections."""
        from src.gui.settings.proxy_tab import ProxySettingsWidget

        with patch('src.gui.settings.proxy_tab.ProxyStorage', return_value=mock_storage):
            widget = ProxySettingsWidget()

            # Switch to system proxy mode
            widget.system_proxy_radio.setChecked(True)
            widget._update_ui_state()

            assert not widget.pools_group.isEnabled()
            assert not widget.category_group.isEnabled()


class TestProxyPoolDropdownPopulation:
    """Tests for proxy pool dropdown population in InheritableProxyControl."""

    def test_dropdown_includes_special_options(self, qapp, mock_storage):
        """Test that dropdown includes Direct Connection and OS Proxy options."""
        from src.gui.widgets.inheritable_proxy_control import InheritableProxyControl

        with patch('src.gui.widgets.inheritable_proxy_control.ProxyStorage', return_value=mock_storage):
            control = InheritableProxyControl(level="global")

            # Check that special options exist
            items = [control.combo.itemData(i) for i in range(control.combo.count())]
            assert InheritableProxyControl.VALUE_DIRECT in items
            assert InheritableProxyControl.VALUE_OS_PROXY in items

    def test_dropdown_includes_enabled_pools(self, qapp, mock_storage, mock_pools):
        """Test that dropdown includes only enabled proxy pools."""
        mock_storage.list_pools.return_value = mock_pools

        from src.gui.widgets.inheritable_proxy_control import InheritableProxyControl

        with patch('src.gui.widgets.inheritable_proxy_control.ProxyStorage', return_value=mock_storage):
            control = InheritableProxyControl(level="global")

            # Get pool IDs from combo
            items = [control.combo.itemData(i) for i in range(control.combo.count())]

            # Should include enabled pools
            assert "pool-uuid-1" in items
            assert "pool-uuid-2" in items
            # Should NOT include disabled pool
            assert "pool-uuid-3" not in items

    def test_dropdown_excludes_disabled_pools(self, qapp, mock_storage, mock_pools):
        """Test that disabled pools are excluded from dropdown."""
        mock_storage.list_pools.return_value = mock_pools

        from src.gui.widgets.inheritable_proxy_control import InheritableProxyControl

        with patch('src.gui.widgets.inheritable_proxy_control.ProxyStorage', return_value=mock_storage):
            control = InheritableProxyControl(level="global")

            # Check combo box display text
            texts = [control.combo.itemText(i) for i in range(control.combo.count())]

            # Should show enabled pools with proxy count
            assert any("Main Pool" in text for text in texts)
            assert any("Backup Pool" in text for text in texts)
            # Should NOT show disabled pool
            assert not any("Disabled Pool" in text for text in texts)

    def test_dropdown_refresh_updates_pools(self, qapp, mock_storage, mock_pools):
        """Test that refresh() updates the pool list."""
        mock_storage.list_pools.return_value = []

        from src.gui.widgets.inheritable_proxy_control import InheritableProxyControl

        with patch('src.gui.widgets.inheritable_proxy_control.ProxyStorage', return_value=mock_storage):
            control = InheritableProxyControl(level="global")

            initial_count = control.combo.count()

            # Update storage to return pools
            mock_storage.list_pools.return_value = mock_pools[:2]
            control.refresh()

            # Count should increase (added 2 enabled pools)
            assert control.combo.count() > initial_count


class TestCategoryAssignmentPersistence:
    """Tests for category-level proxy assignment persistence."""

    def test_category_assignment_saves_to_storage(self, qapp, mock_storage):
        """Test that category proxy assignment is saved to storage."""
        from src.gui.widgets.inheritable_proxy_control import InheritableProxyControl

        with patch('src.gui.widgets.inheritable_proxy_control.ProxyStorage', return_value=mock_storage):
            control = InheritableProxyControl(
                level="category",
                category="file_hosts"
            )

            # Enable override and select a value
            control.set_override(True)
            control.combo.setCurrentIndex(0)  # Direct connection
            control._save_assignment()

            # Should save to category assignment
            mock_storage.set_pool_assignment.assert_called_with(
                InheritableProxyControl.VALUE_DIRECT,
                "file_hosts",
                None
            )

    def test_category_clear_override_removes_assignment(self, qapp, mock_storage):
        """Test that clearing category override removes the assignment."""
        from src.gui.widgets.inheritable_proxy_control import InheritableProxyControl

        with patch('src.gui.widgets.inheritable_proxy_control.ProxyStorage', return_value=mock_storage):
            control = InheritableProxyControl(
                level="category",
                category="forums"
            )

            # Set override then clear it
            control.set_override(True)
            control.set_override(False)

            # Should clear the assignment
            mock_storage.set_pool_assignment.assert_called_with(None, "forums", None)

    def test_category_inherits_from_global(self, qapp, mock_storage):
        """Test that category without override inherits from global."""
        mock_storage.get_global_default_pool.return_value = "pool-uuid-1"
        mock_storage.get_pool_assignment.return_value = None

        from src.gui.widgets.inheritable_proxy_control import InheritableProxyControl

        with patch('src.gui.widgets.inheritable_proxy_control.ProxyStorage', return_value=mock_storage):
            control = InheritableProxyControl(
                level="category",
                category="api"
            )

            # Should inherit global value
            assert control.get_effective_value() == "pool-uuid-1"
            assert not control.is_overriding()


class TestServiceLevelAssignment:
    """Tests for service-level proxy assignment."""

    def test_service_assignment_saves_to_storage(self, qapp, mock_storage, mock_pools):
        """Test that service proxy assignment is saved to storage."""
        mock_storage.list_pools.return_value = mock_pools[:2]

        from src.gui.widgets.inheritable_proxy_control import InheritableProxyControl

        with patch('src.gui.widgets.inheritable_proxy_control.ProxyStorage', return_value=mock_storage):
            control = InheritableProxyControl(
                level="service",
                category="file_hosts",
                service_id="rapidgator"
            )

            # Enable override and select a pool
            control.set_override(True)
            # Find pool in combo
            for i in range(control.combo.count()):
                if control.combo.itemData(i) == "pool-uuid-1":
                    control.combo.setCurrentIndex(i)
                    break
            control._save_assignment()

            # Should save to service assignment
            mock_storage.set_pool_assignment.assert_called_with(
                "pool-uuid-1",
                "file_hosts",
                "rapidgator"
            )

    def test_service_inherits_from_category(self, qapp, mock_storage):
        """Test that service without override inherits from category."""
        mock_storage.get_pool_assignment.side_effect = lambda cat, svc: "pool-uuid-2" if svc is None else None

        from src.gui.widgets.inheritable_proxy_control import InheritableProxyControl

        with patch('src.gui.widgets.inheritable_proxy_control.ProxyStorage', return_value=mock_storage):
            control = InheritableProxyControl(
                level="service",
                category="file_hosts",
                service_id="pixeldrain"
            )

            # Should inherit category value
            effective = control.get_effective_value()
            assert effective == "pool-uuid-2"
            assert not control.is_overriding()


class TestSignalEmissions:
    """Tests for signal emissions on proxy control changes."""

    def test_value_changed_signal_on_combo_change(self, qapp, mock_storage):
        """Test that value_changed signal is emitted when combo selection changes."""
        from src.gui.widgets.inheritable_proxy_control import InheritableProxyControl

        with patch('src.gui.widgets.inheritable_proxy_control.ProxyStorage', return_value=mock_storage):
            control = InheritableProxyControl(level="global")

            signal_spy = MagicMock()
            control.value_changed.connect(signal_spy)

            # Change combo selection
            control.combo.setCurrentIndex(1)

            signal_spy.assert_called_once()

    def test_value_changed_signal_on_override_toggle(self, qapp, mock_storage):
        """Test that value_changed signal is emitted when override is toggled."""
        from src.gui.widgets.inheritable_proxy_control import InheritableProxyControl

        with patch('src.gui.widgets.inheritable_proxy_control.ProxyStorage', return_value=mock_storage):
            control = InheritableProxyControl(
                level="category",
                category="file_hosts"
            )

            signal_spy = MagicMock()
            control.value_changed.connect(signal_spy)

            # Toggle override
            control.set_override(True)

            # Signal should be emitted (once from checkbox change)
            assert signal_spy.call_count >= 1

    def test_settings_changed_signal_propagates(self, qapp, mock_storage):
        """Test that settings_changed signal propagates from mode changes."""
        from src.gui.settings.proxy_tab import ProxySettingsWidget

        with patch('src.gui.settings.proxy_tab.ProxyStorage', return_value=mock_storage):
            widget = ProxySettingsWidget()

            signal_spy = MagicMock()
            widget.settings_changed.connect(signal_spy)

            # Trigger mode change via the handler directly
            widget.system_proxy_radio.setChecked(True)
            widget._on_proxy_mode_changed()

            # Should emit settings_changed from mode change
            assert signal_spy.call_count >= 1


class TestRefreshAfterPoolChanges:
    """Tests for UI refresh after pool creation/deletion."""

    def test_load_pools_refreshes_all_controls(self, qapp, mock_storage, mock_pools):
        """Test that load_pools() refreshes all dropdown widgets."""
        mock_storage.list_pools.return_value = mock_pools

        from src.gui.settings.proxy_tab import ProxySettingsWidget

        with patch('src.gui.settings.proxy_tab.ProxyStorage', return_value=mock_storage):
            widget = ProxySettingsWidget()

            # Spy on refresh methods
            with patch.object(widget.file_hosts_dropdown, 'refresh') as fh_spy, \
                 patch.object(widget.forums_dropdown, 'refresh') as forums_spy, \
                 patch.object(widget.api_dropdown, 'refresh') as api_spy:

                widget.load_pools()

                # All controls should be refreshed
                fh_spy.assert_called_once()
                forums_spy.assert_called_once()
                api_spy.assert_called_once()

    def test_pool_list_updates_after_pool_creation(self, qapp, mock_storage, mock_pools):
        """Test that pools list widget updates after creating a pool."""
        mock_storage.list_pools.return_value = []

        from src.gui.settings.proxy_tab import ProxySettingsWidget

        with patch('src.gui.settings.proxy_tab.ProxyStorage', return_value=mock_storage):
            widget = ProxySettingsWidget()

            initial_count = widget.pools_list.count()

            # Simulate pool creation
            mock_storage.list_pools.return_value = mock_pools[:1]
            widget.load_pools()

            # List should have one more item
            assert widget.pools_list.count() == initial_count + 1

    def test_dropdowns_reflect_new_pools(self, qapp, mock_storage, mock_pools):
        """Test that dropdowns include newly created pools."""
        mock_storage.list_pools.return_value = []

        from src.gui.settings.proxy_tab import ProxySettingsWidget

        with patch('src.gui.settings.proxy_tab.ProxyStorage', return_value=mock_storage):
            widget = ProxySettingsWidget()

            # Get initial list count
            initial_count = widget.pools_list.count()

            # Add pools and refresh
            mock_storage.list_pools.return_value = mock_pools[:2]
            widget.load_pools()

            # List should have more items
            assert widget.pools_list.count() > initial_count


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_no_pools_available(self, qapp, mock_storage):
        """Test behavior when no proxy pools are available."""
        mock_storage.list_pools.return_value = []

        from src.gui.widgets.inheritable_proxy_control import InheritableProxyControl

        with patch('src.gui.widgets.inheritable_proxy_control.ProxyStorage', return_value=mock_storage):
            control = InheritableProxyControl(level="global")

            # Should still have special options
            assert control.combo.count() >= 2  # Direct + OS Proxy

    def test_all_pools_disabled(self, qapp, mock_storage, mock_pools):
        """Test behavior when all pools are disabled."""
        # Return only disabled pool
        mock_storage.list_pools.return_value = [mock_pools[2]]

        from src.gui.widgets.inheritable_proxy_control import InheritableProxyControl

        with patch('src.gui.widgets.inheritable_proxy_control.ProxyStorage', return_value=mock_storage):
            control = InheritableProxyControl(level="global")

            # Should only have special options (no pools)
            items = [control.combo.itemData(i) for i in range(control.combo.count())]
            assert "pool-uuid-3" not in items

    def test_missing_category_assignment(self, qapp, mock_storage):
        """Test service inherits from global when category has no assignment."""
        mock_storage.get_pool_assignment.return_value = None
        mock_storage.get_global_default_pool.return_value = "pool-uuid-1"

        from src.gui.widgets.inheritable_proxy_control import InheritableProxyControl

        with patch('src.gui.widgets.inheritable_proxy_control.ProxyStorage', return_value=mock_storage):
            control = InheritableProxyControl(
                level="service",
                category="file_hosts",
                service_id="test_service"
            )

            # Should fall back to global
            assert control.get_effective_value() == "pool-uuid-1"

    def test_deleted_pool_assignment(self, qapp, mock_storage):
        """Test behavior when assigned pool is deleted."""
        # Pool assignment exists but pool is not in list
        mock_storage.get_pool_assignment.return_value = "deleted-pool-uuid"
        mock_storage.list_pools.return_value = []

        from src.gui.widgets.inheritable_proxy_control import InheritableProxyControl

        with patch('src.gui.widgets.inheritable_proxy_control.ProxyStorage', return_value=mock_storage):
            control = InheritableProxyControl(
                level="category",
                category="file_hosts"
            )

            # Should show "(Deleted pool)" in display
            display_name = control._get_display_name("deleted-pool-uuid")
            assert display_name == "(Deleted pool)"

    def test_none_combo_value_ignored(self, qapp, mock_storage):
        """Test that None combo value is handled gracefully in save."""
        from src.gui.widgets.inheritable_proxy_control import InheritableProxyControl

        with patch('src.gui.widgets.inheritable_proxy_control.ProxyStorage', return_value=mock_storage):
            control = InheritableProxyControl(level="global")

            # Set combo to return None
            with patch.object(control.combo, 'currentData', return_value=None):
                control._save_assignment()

                # Should not crash, storage methods should not be called
                mock_storage.set_global_default_pool.assert_not_called()


class TestPoolButtonStates:
    """Tests for pool management button enable/disable states."""

    def test_pool_buttons_disabled_initially(self, qapp, mock_storage):
        """Test that edit/delete/test buttons are disabled when no pool is selected."""
        from src.gui.settings.proxy_tab import ProxySettingsWidget

        with patch('src.gui.settings.proxy_tab.ProxyStorage', return_value=mock_storage):
            widget = ProxySettingsWidget()

            assert not widget.edit_pool_btn.isEnabled()
            assert not widget.delete_pool_btn.isEnabled()
            assert not widget.test_pool_btn.isEnabled()

    def test_pool_buttons_enabled_on_selection(self, qapp, mock_storage, mock_pools):
        """Test that buttons are enabled when a pool is selected."""
        mock_storage.list_pools.return_value = mock_pools[:1]

        from src.gui.settings.proxy_tab import ProxySettingsWidget

        with patch('src.gui.settings.proxy_tab.ProxyStorage', return_value=mock_storage):
            widget = ProxySettingsWidget()
            widget.load_pools()

            # Switch to custom mode to enable pool controls
            widget.custom_proxy_radio.setChecked(True)
            widget._update_ui_state()

            # Select first pool
            if widget.pools_list.count() > 0:
                item = widget.pools_list.item(0)
                widget.pools_list.setCurrentItem(item)
                # Manually call the handler to update button state
                widget._on_pool_selected()

                assert widget.edit_pool_btn.isEnabled()
                assert widget.delete_pool_btn.isEnabled()
                assert widget.test_pool_btn.isEnabled()
