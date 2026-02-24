"""Proxy Settings Widget - Manage proxy pools and assignments."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QMessageBox, QListWidget, QListWidgetItem, QLineEdit,
)
from PyQt6.QtCore import pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QColor
from typing import Optional, List
import logging
import re
import threading

from src.proxy.models import ProxyPool
from src.proxy.storage import ProxyStorage
from src.gui.widgets.simple_proxy_dropdown import SimpleProxyDropdown
from src.gui.widgets.info_button import InfoButton

logger = logging.getLogger(__name__)


class ProxySettingsWidget(QWidget):
    """Widget for configuring proxy settings - pools and assignments."""

    settings_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.storage = ProxyStorage()

        self.setup_ui()
        self.load_pools()

    def setup_ui(self):
        """Setup the proxy settings UI."""
        layout = QVBoxLayout(self)

        desc = QLabel("Configure proxy pools and per-category overrides for network requests.")
        desc.setWordWrap(True)
        desc.setProperty("class", "tab-description")
        layout.addWidget(desc)

        # Default Connection Group
        default_group = QGroupBox("Default Connection")
        default_layout = QVBoxLayout(default_group)

        default_info = QLabel(
            "Choose the default proxy for all network traffic. "
            "Category overrides below can use a different proxy for specific traffic types."
        )
        default_info.setWordWrap(True)
        default_layout.addWidget(default_info)

        global_row = QHBoxLayout()
        global_row.addWidget(QLabel("Default:"))
        self.global_dropdown = SimpleProxyDropdown(category="__global__", is_global=True)
        self.global_dropdown.value_changed.connect(self._on_settings_changed)
        global_row.addWidget(self.global_dropdown, 1)
        default_layout.addLayout(global_row)

        layout.addWidget(default_group)

        # Proxy Pools Group
        self.pools_group = QGroupBox("Proxy Pools")
        pools_layout = QVBoxLayout(self.pools_group)

        pools_info = QLabel(
            "Each pool contains your proxy servers. Create a pool, paste your proxies, done."
        )
        pools_info.setWordWrap(True)
        pools_layout.addWidget(pools_info)

        # Pools list
        self.pools_list = QListWidget()
        self.pools_list.setMinimumHeight(150)
        self.pools_list.itemSelectionChanged.connect(self._on_pool_selected)
        self.pools_list.itemDoubleClicked.connect(self._on_pool_edit)
        pools_layout.addWidget(self.pools_list)

        # Pool buttons
        pool_btn_layout = QHBoxLayout()

        self.add_pool_btn = QPushButton("New Pool")
        self.add_pool_btn.setToolTip("Create a new proxy pool")
        self.add_pool_btn.clicked.connect(self._on_add_pool)
        pool_btn_layout.addWidget(self.add_pool_btn)

        self.edit_pool_btn = QPushButton("Edit")
        self.edit_pool_btn.setToolTip("Edit the selected proxy pool")
        self.edit_pool_btn.setEnabled(False)
        self.edit_pool_btn.clicked.connect(self._on_edit_pool)
        pool_btn_layout.addWidget(self.edit_pool_btn)

        self.delete_pool_btn = QPushButton("Delete")
        self.delete_pool_btn.setToolTip("Delete the selected proxy pool")
        self.delete_pool_btn.setEnabled(False)
        self.delete_pool_btn.clicked.connect(self._on_delete_pool)
        pool_btn_layout.addWidget(self.delete_pool_btn)

        self.test_pool_btn = QPushButton("Test")
        self.test_pool_btn.setEnabled(False)
        self.test_pool_btn.setToolTip("Test first proxy in pool")
        self.test_pool_btn.clicked.connect(self._on_test_pool)
        pool_btn_layout.addWidget(self.test_pool_btn)

        pool_btn_layout.addStretch()
        pools_layout.addLayout(pool_btn_layout)

        layout.addWidget(self.pools_group)

        # Category Overrides Group
        self.category_group = QGroupBox("Category Overrides")
        category_layout = QVBoxLayout(self.category_group)

        category_info_row = QHBoxLayout()
        category_info = QLabel(
            "Override the default proxy for specific categories."
        )
        category_info.setWordWrap(True)
        category_info_row.addWidget(category_info)
        category_info_row.addWidget(InfoButton(
            "Override the default proxy for specific traffic types. Useful if "
            "you want file host traffic through one proxy but API calls "
            "direct, or forums through a different region.<br><br>"
            "'Use default' means this category inherits the global default above."
        ))
        category_layout.addLayout(category_info_row)

        # File Hosts category
        fh_layout = QHBoxLayout()
        fh_layout.addWidget(QLabel("File Hosts:"))
        self.file_hosts_dropdown = SimpleProxyDropdown(category="file_hosts")
        self.file_hosts_dropdown.value_changed.connect(self._on_settings_changed)
        fh_layout.addWidget(self.file_hosts_dropdown, 1)
        category_layout.addLayout(fh_layout)

        # Forums category
        forums_layout = QHBoxLayout()
        forums_layout.addWidget(QLabel("Forums:"))
        self.forums_dropdown = SimpleProxyDropdown(category="forums")
        self.forums_dropdown.value_changed.connect(self._on_settings_changed)
        forums_layout.addWidget(self.forums_dropdown, 1)
        category_layout.addLayout(forums_layout)

        # API category
        api_layout = QHBoxLayout()
        api_layout.addWidget(QLabel("API:"))
        self.api_dropdown = SimpleProxyDropdown(category="api")
        self.api_dropdown.value_changed.connect(self._on_settings_changed)
        api_layout.addWidget(self.api_dropdown, 1)
        category_layout.addLayout(api_layout)

        # Image Hosts category
        ih_layout = QHBoxLayout()
        ih_layout.addWidget(QLabel("Image Hosts:"))
        self.image_hosts_dropdown = SimpleProxyDropdown(category="image_hosts")
        self.image_hosts_dropdown.value_changed.connect(self._on_settings_changed)
        ih_layout.addWidget(self.image_hosts_dropdown, 1)
        category_layout.addLayout(ih_layout)

        layout.addWidget(self.category_group)

        # Tor Circuit Renewal Group
        tor_group = QGroupBox("Tor Circuit Renewal")
        tor_layout = QVBoxLayout(tor_group)

        tor_circuit_layout = QHBoxLayout()
        self.tor_newnym_btn = QPushButton("New Circuit")
        self.tor_newnym_btn.setToolTip("Request a new Tor circuit (new exit node IP)")
        self.tor_newnym_btn.clicked.connect(self._on_new_circuit)
        tor_circuit_layout.addWidget(self.tor_newnym_btn)

        tor_circuit_layout.addWidget(QLabel("Control password:"))
        self.tor_control_password = QLineEdit()
        self.tor_control_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.tor_control_password.setPlaceholderText("(leave blank if no auth)")
        self.tor_control_password.setMaximumWidth(200)
        tor_circuit_layout.addWidget(self.tor_control_password)

        self.tor_circuit_status = QLabel("")
        tor_circuit_layout.addWidget(self.tor_circuit_status)
        tor_circuit_layout.addStretch()
        tor_layout.addLayout(tor_circuit_layout)

        layout.addWidget(tor_group)
        layout.addStretch()

    def load_pools(self):
        """Load proxy pools from storage."""
        try:
            pools = self.storage.list_pools()

            self.pools_list.clear()
            for pool in pools:
                self._add_pool_to_list(pool)

            # Refresh all dropdowns
            self.global_dropdown.refresh()
            self.file_hosts_dropdown.refresh()
            self.forums_dropdown.refresh()
            self.api_dropdown.refresh()
            self.image_hosts_dropdown.refresh()
        except Exception as e:
            logger.error(f"Failed to load proxy pools: {e}")
            QMessageBox.critical(
                self,
                "Error Loading Pools",
                f"Failed to load proxy pools from storage.\n\nError: {e}"
            )

    def _add_pool_to_list(self, pool: ProxyPool):
        """Add a pool to the list widget."""
        proxy_count = len(pool.proxies)
        display = f"{pool.name} ({proxy_count} proxies, {pool.rotation_strategy.value})"
        if pool.sticky_sessions:
            display += " [Sticky]"
        if not pool.enabled:
            display += " [Disabled]"

        item = QListWidgetItem(display)
        item.setData(Qt.ItemDataRole.UserRole, pool.id)

        if not pool.enabled:
            item.setForeground(QColor(128, 128, 128))

        self.pools_list.addItem(item)

    def _on_settings_changed(self):
        """Handle any settings change."""
        self.settings_changed.emit()

    def _on_pool_selected(self):
        """Handle pool selection change."""
        has_selection = len(self.pools_list.selectedItems()) > 0
        self.edit_pool_btn.setEnabled(has_selection)
        self.delete_pool_btn.setEnabled(has_selection)
        self.test_pool_btn.setEnabled(has_selection)

    def _on_pool_edit(self, item: QListWidgetItem):
        """Handle double-click to edit pool."""
        self._on_edit_pool()

    def _on_add_pool(self):
        """Show dialog to create new pool."""
        from src.gui.dialogs.proxy_pool_dialog import ProxyPoolDialog

        dialog = ProxyPoolDialog(self)
        if dialog.exec():
            pool = dialog.get_pool()
            self.storage.save_pool(pool)
            self.load_pools()
            self.settings_changed.emit()

    def _on_edit_pool(self):
        """Show dialog to edit selected pool."""
        items = self.pools_list.selectedItems()
        if not items:
            return

        pool_id = items[0].data(Qt.ItemDataRole.UserRole)
        pool = self.storage.load_pool(pool_id)
        if not pool:
            QMessageBox.warning(self, "Error", "Could not load pool.")
            return

        from src.gui.dialogs.proxy_pool_dialog import ProxyPoolDialog

        dialog = ProxyPoolDialog(self, pool=pool)
        if dialog.exec():
            updated = dialog.get_pool()
            self.storage.save_pool(updated)
            self.load_pools()
            self.settings_changed.emit()

    def _on_delete_pool(self):
        """Delete selected pool."""
        items = self.pools_list.selectedItems()
        if not items:
            return

        pool_id = items[0].data(Qt.ItemDataRole.UserRole)
        pool = self.storage.load_pool(pool_id)
        if not pool:
            return

        reply = QMessageBox.question(
            self,
            "Delete Pool",
            f"Delete proxy pool '{pool.name}' with {len(pool.proxies)} proxies?\n\n"
            "This will clear any assignments using this pool.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.storage.delete_pool(pool_id)
            self.load_pools()
            self.settings_changed.emit()

    def _validate_proxy_host(self, host: str) -> bool:
        """Validate proxy host to prevent injection attacks."""
        hostname_pattern = r'^[a-zA-Z0-9._-]+$'
        ipv4_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'

        if not host or len(host) > 253:
            return False

        return bool(re.match(hostname_pattern, host) or re.match(ipv4_pattern, host))

    def _on_test_pool(self):
        """Test first proxy in selected pool."""
        items = self.pools_list.selectedItems()
        if not items:
            return

        pool_id = items[0].data(Qt.ItemDataRole.UserRole)
        pool = self.storage.load_pool(pool_id)
        if not pool or not pool.proxies:
            QMessageBox.warning(self, "Error", "Pool has no proxies.")
            return

        proxy = pool.proxies[0]

        if not self._validate_proxy_host(proxy.host):
            logger.error(f"Invalid proxy host detected: {proxy.host}")
            QMessageBox.critical(
                self,
                "Security Error",
                "Invalid proxy host configuration. Please check proxy settings."
            )
            return

        try:
            import pycurl
            from io import BytesIO

            buffer = BytesIO()
            curl = pycurl.Curl()
            curl.setopt(pycurl.URL, "https://httpbin.org/ip")
            curl.setopt(pycurl.WRITEDATA, buffer)
            curl.setopt(pycurl.TIMEOUT, 10)
            curl.setopt(pycurl.CONNECTTIMEOUT, 5)

            curl.setopt(pycurl.PROXY, f"{proxy.host}:{proxy.port}")

            if proxy.proxy_type.value in ('socks4', 'socks5'):
                curl.setopt(pycurl.PROXYTYPE,
                    pycurl.PROXYTYPE_SOCKS5 if proxy.proxy_type.value == 'socks5'
                    else pycurl.PROXYTYPE_SOCKS4)

            if proxy.username:
                curl.setopt(pycurl.PROXYUSERPWD, f"{proxy.username}:{proxy.password}")

            curl.perform()
            status_code = curl.getinfo(pycurl.RESPONSE_CODE)
            curl.close()

            if status_code == 200:
                response = buffer.getvalue().decode('utf-8')
                QMessageBox.information(
                    self,
                    "Proxy Test Successful",
                    f"Connection through pool '{pool.name}' successful!\n\n"
                    f"Tested: {proxy.get_display_url()}\n"
                    f"Response:\n{response}"
                )
            else:
                QMessageBox.warning(
                    self,
                    "Proxy Test Failed",
                    f"Connection returned status {status_code}"
                )

        except Exception as e:
            logger.error(f"Proxy test failed for pool {pool.name}: {e}")
            QMessageBox.critical(
                self,
                "Proxy Test Failed",
                f"Connection error: {e}"
            )

    def _on_new_circuit(self):
        """Request a new Tor circuit."""
        from src.proxy.tor import request_new_circuit
        password = self.tor_control_password.text()
        success, message = request_new_circuit(password=password)

        if success:
            self.tor_circuit_status.setText("New circuit requested")
            self.tor_circuit_status.setStyleSheet("color: green;")
        else:
            self.tor_circuit_status.setText(message)
            self.tor_circuit_status.setStyleSheet("color: red;")

    def load_settings(self, settings: dict):
        """Load settings - called by parent settings dialog."""
        self.load_pools()

    def get_settings(self) -> dict:
        """Get settings - called by parent settings dialog."""
        return {}
