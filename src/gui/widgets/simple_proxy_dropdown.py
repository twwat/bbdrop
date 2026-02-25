"""Simple Proxy Dropdown Widget - Streamlined proxy pool selection."""

from typing import Optional
from PyQt6.QtWidgets import QComboBox
from PyQt6.QtCore import pyqtSignal, Qt

from src.proxy.storage import ProxyStorage
from src.utils.logger import log


class SimpleProxyDropdown(QComboBox):
    """
    Dropdown for proxy pool selection.

    Two modes:
    - Global (is_global=True): No "Use default" option. Saves to global default pool.
    - Category/service (is_global=False): Has "Use default" first, clears assignment
      so resolver falls through to global.

    Options: No proxy (direct) | System proxy | Tor | separator | pools

    Usage:
        # Global default dropdown
        global_dd = SimpleProxyDropdown(category="__global__", is_global=True)

        # Category override dropdown
        cat_dd = SimpleProxyDropdown(category="file_hosts")

        # Service-level dropdown
        svc_dd = SimpleProxyDropdown(category="file_hosts", service_id="rapidgator")
    """

    value_changed = pyqtSignal()

    # Special constants
    VALUE_DIRECT = "__direct__"
    VALUE_OS_PROXY = "__os_proxy__"
    VALUE_TOR = "__tor__"
    VALUE_USE_DEFAULT = "__use_default__"

    def __init__(self, category: str, service_id: Optional[str] = None,
                 is_global: bool = False, parent=None):
        super().__init__(parent)

        self.category = category
        self.service_id = service_id
        self.is_global = is_global
        self.storage = ProxyStorage()

        self.setMinimumWidth(200)
        self.currentIndexChanged.connect(self._on_changed)

        self._populate()
        self._load_value()

    def _populate(self):
        """Populate dropdown with available options."""
        self.blockSignals(True)
        try:
            self.clear()

            # "Use Global Default" for non-global dropdowns
            if not self.is_global:
                self.addItem("Use Global Default", self.VALUE_USE_DEFAULT)
                self.insertSeparator(self.count())

            self.addItem("No proxy (direct connection)", self.VALUE_DIRECT)
            self.addItem("Use system proxy settings", self.VALUE_OS_PROXY)
            self.addItem("Use Tor network", self.VALUE_TOR)

            self.insertSeparator(self.count())

            pools = self.storage.list_pools()
            for pool in pools:
                if pool.enabled:
                    # Hide auto-created Tor pool from manual selection
                    from src.proxy.tor import TOR_POOL_NAME
                    if pool.name == TOR_POOL_NAME:
                        continue
                    count = len(pool.proxies)
                    display = f"{pool.name} ({count} proxies)"
                    self.addItem(display, pool.id)

        except Exception as e:
            self.addItem(f"Error loading pools: {e}", None)
        finally:
            self.blockSignals(False)

    def _load_value(self):
        """Load current assignment from storage."""
        self.blockSignals(True)
        try:
            if self.is_global:
                value = self.storage.get_global_default_pool()
                if not value:
                    # Legacy: check use_os_proxy
                    if self.storage.get_use_os_proxy():
                        value = self.VALUE_OS_PROXY
                    else:
                        value = self.VALUE_DIRECT
            else:
                value = self.storage.get_pool_assignment(self.category, self.service_id)
                if not value:
                    value = self.VALUE_USE_DEFAULT

            for i in range(self.count()):
                if self.itemData(i) == value:
                    self.setCurrentIndex(i)
                    return

            # Fallback
            self.setCurrentIndex(0)
        except Exception:
            if self.count() > 0:
                self.setCurrentIndex(0)
        finally:
            self.blockSignals(False)

    def _on_changed(self):
        """Handle selection change."""
        try:
            value = self.currentData()
            if value is None:
                return

            # Tor validation: check if running before allowing selection
            if value == self.VALUE_TOR:
                from src.proxy.tor import is_tor_running
                if not is_tor_running(timeout=1.0):
                    from PyQt6.QtWidgets import QMessageBox
                    QMessageBox.warning(
                        self, "Tor Not Running",
                        "Tor is not detected on port 9050.\n\n"
                        "Start the Tor service and try again."
                    )
                    self._load_value()
                    return

            if self.is_global:
                if value == self.VALUE_DIRECT:
                    self.storage.set_global_default_pool(self.VALUE_DIRECT)
                    self.storage.set_use_os_proxy(False)
                elif value == self.VALUE_OS_PROXY:
                    self.storage.set_global_default_pool(self.VALUE_OS_PROXY)
                    self.storage.set_use_os_proxy(True)
                elif value == self.VALUE_TOR:
                    self.storage.set_global_default_pool(self.VALUE_TOR)
                    self.storage.set_use_os_proxy(False)
                else:
                    # Pool ID
                    self.storage.set_global_default_pool(value)
                    self.storage.set_use_os_proxy(False)
            else:
                if value == self.VALUE_USE_DEFAULT:
                    self.storage.clear_pool_assignment(self.category, self.service_id)
                    self.storage.set_assignment(None, self.category, self.service_id)
                else:
                    self.storage.set_pool_assignment(value, self.category, self.service_id)
                    self.storage.set_assignment(None, self.category, self.service_id)

            self.value_changed.emit()

        except Exception as e:
            log(f"Error saving proxy selection: {e}", level="error")

    def refresh(self):
        """Refresh dropdown options from storage."""
        current_value = self.currentData()
        self._populate()

        if current_value is not None:
            self.blockSignals(True)
            for i in range(self.count()):
                if self.itemData(i) == current_value:
                    self.setCurrentIndex(i)
                    break
            self.blockSignals(False)
        else:
            self._load_value()

    def get_display_text(self) -> str:
        """Get human-readable text for the current selection."""
        current_text = self.currentText()
        value = self.currentData()

        if value is None:
            return "Unknown"

        if value not in (self.VALUE_DIRECT, self.VALUE_OS_PROXY, self.VALUE_TOR, self.VALUE_USE_DEFAULT):
            if ' (' in current_text:
                return current_text.split(' (')[0]

        return current_text
