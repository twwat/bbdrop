"""Simple Proxy Dropdown Widget - Streamlined proxy pool selection."""

from typing import Optional
from PyQt6.QtWidgets import QComboBox
from PyQt6.QtCore import pyqtSignal, Qt

from src.proxy.storage import ProxyStorage


class SimpleProxyDropdown(QComboBox):
    """
    Simplified dropdown for proxy pool selection.

    Provides three basic options:
    - Direct Connection (no proxy)
    - OS System Proxy (use system settings)
    - Enabled proxy pools

    Usage:
        dropdown = SimpleProxyDropdown(category="file_hosts", service_id="rapidgator")
        dropdown.value_changed.connect(self._on_proxy_changed)
    """

    # Signal emitted when selection changes
    value_changed = pyqtSignal()

    # Special constants for non-pool selections
    VALUE_DIRECT = "__direct__"
    VALUE_OS_PROXY = "__os_proxy__"

    def __init__(self, category: str, service_id: Optional[str] = None, parent=None):
        """Initialize the dropdown.

        Args:
            category: Category for this assignment (e.g., "file_hosts")
            service_id: Optional service ID for service-specific assignment
            parent: Parent widget
        """
        super().__init__(parent)

        self.category = category
        self.service_id = service_id
        self.storage = ProxyStorage()

        # Setup UI
        self.setMinimumWidth(200)

        # Connect signal
        self.currentIndexChanged.connect(self._on_changed)

        # Populate and load current value
        self._populate()
        self._load_value()

    def _populate(self):
        """Populate dropdown with available options."""
        # Block signals during population to avoid triggering saves
        self.blockSignals(True)

        try:
            self.clear()

            # Add Direct Connection
            self.addItem("Direct Connection", self.VALUE_DIRECT)
            self.setItemData(0, "Connect directly without proxy", role=Qt.ItemDataRole.ToolTipRole)

            # Add OS System Proxy
            self.addItem("OS System Proxy", self.VALUE_OS_PROXY)
            self.setItemData(1, "Use system proxy settings from OS", role=Qt.ItemDataRole.ToolTipRole)

            # Add separator
            self.insertSeparator(self.count())

            # Add enabled pools
            pools = self.storage.list_pools()
            for pool in pools:
                if pool.enabled:
                    count = len(pool.proxies)
                    display = f"{pool.name} ({count} proxies)"
                    idx = self.count()
                    self.addItem(display, pool.id)
                    tooltip = f"Use proxy pool: {pool.name}"
                    self.setItemData(idx, tooltip, role=Qt.ItemDataRole.ToolTipRole)

        except Exception as e:
            # Add error item if population fails
            self.addItem(f"Error loading pools: {e}", None)

        finally:
            # Always restore signals
            self.blockSignals(False)

    def _load_value(self):
        """Load current assignment from storage."""
        self.blockSignals(True)

        try:
            # Check for pool assignment (includes special values and pool IDs)
            pool_id = self.storage.get_pool_assignment(self.category, self.service_id)
            if pool_id:
                # Find and select the matching item (pool or special value)
                for i in range(self.count()):
                    if self.itemData(i) == pool_id:
                        self.setCurrentIndex(i)
                        return

            # Fallback: Check for profile assignment (legacy special values)
            profile_id = self.storage.get_assignment(self.category, self.service_id)

            if profile_id == self.VALUE_DIRECT:
                # Direct connection (legacy)
                for i in range(self.count()):
                    if self.itemData(i) == self.VALUE_DIRECT:
                        self.setCurrentIndex(i)
                        return

            elif profile_id == self.VALUE_OS_PROXY:
                # OS System Proxy (legacy)
                for i in range(self.count()):
                    if self.itemData(i) == self.VALUE_OS_PROXY:
                        self.setCurrentIndex(i)
                        return

            # Default to Direct Connection if nothing is set
            for i in range(self.count()):
                if self.itemData(i) == self.VALUE_DIRECT:
                    self.setCurrentIndex(i)
                    return

        except Exception as e:
            # On error, default to first item
            if self.count() > 0:
                self.setCurrentIndex(0)

        finally:
            self.blockSignals(False)

    def _on_changed(self):
        """Handle selection change - save to storage and update tooltip."""
        try:
            value = self.currentData()

            if value is None:
                # Separator or invalid item selected
                return

            if value == self.VALUE_DIRECT:
                # Save direct connection - store special value in pool assignment
                # Resolver checks pool assignment for special values
                self.storage.set_pool_assignment(self.VALUE_DIRECT, self.category, self.service_id)
                self.storage.set_assignment(None, self.category, self.service_id)
                self.setToolTip("Connect directly without proxy")

            elif value == self.VALUE_OS_PROXY:
                # Save OS proxy selection - store special value in pool assignment
                # Resolver checks pool assignment for special values
                self.storage.set_pool_assignment(self.VALUE_OS_PROXY, self.category, self.service_id)
                self.storage.set_assignment(None, self.category, self.service_id)
                self.setToolTip("Use system proxy settings from OS")

            else:
                # Pool ID - save as pool assignment
                self.storage.set_pool_assignment(value, self.category, self.service_id)
                # Clear any profile assignment
                self.storage.set_assignment(None, self.category, self.service_id)
                # Update tooltip with pool info
                current_text = self.currentText()
                tooltip = f"Use proxy pool: {current_text.split(' (')[0]}" if ' (' in current_text else f"Use proxy pool: {current_text}"
                self.setToolTip(tooltip)

            # Emit signal
            self.value_changed.emit()

        except Exception as e:
            # Log error but don't crash
            print(f"Error saving proxy selection: {e}")

    def refresh(self):
        """Refresh dropdown options from storage.

        This reloads the pools and restores the current selection.
        """
        # Save current selection
        current_value = self.currentData()

        # Repopulate
        self._populate()

        # Try to restore selection
        if current_value is not None:
            self.blockSignals(True)
            for i in range(self.count()):
                if self.itemData(i) == current_value:
                    self.setCurrentIndex(i)
                    break
            self.blockSignals(False)
        else:
            # If no valid selection, reload from storage
            self._load_value()

    def get_display_text(self) -> str:
        """Get human-readable text for the current selection.

        Returns the display text of the currently selected item.
        For pool items, extracts just the pool name without the proxy count.

        Returns:
            str: Human-readable text describing the current selection.
                 Examples: "Direct Connection", "OS System Proxy", "MyPool"
        """
        current_text = self.currentText()
        value = self.currentData()

        if value is None:
            return "Unknown"

        # For pool items, extract just the pool name without proxy count
        if value not in (self.VALUE_DIRECT, self.VALUE_OS_PROXY):
            # Remove the "(N proxies)" suffix if present
            if ' (' in current_text:
                return current_text.split(' (')[0]

        return current_text
