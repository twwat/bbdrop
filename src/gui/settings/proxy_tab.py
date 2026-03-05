"""Proxies & Tor Settings Widget - Manage proxy pools, assignments, and Tor."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QMessageBox, QListWidget, QListWidgetItem,
)
from PyQt6.QtCore import pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QColor
import logging
import re
import threading

from src.proxy.models import ProxyPool
from src.proxy.storage import ProxyStorage
from src.gui.widgets.simple_proxy_dropdown import SimpleProxyDropdown
from src.gui.widgets.info_button import InfoButton

logger = logging.getLogger(__name__)


def _group_desc(text: str) -> QLabel:
    """Create a styled description label for use inside QGroupBox sections."""
    label = QLabel(text)
    label.setWordWrap(True)
    label.setProperty("class", "group-description")
    return label


class ProxySettingsWidget(QWidget):
    """Widget for configuring proxy settings - pools, assignments, and Tor."""

    settings_changed = pyqtSignal()
    _tor_status_ready = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.storage = ProxyStorage()

        self.setup_ui()
        self.load_pools()

    def setup_ui(self):
        """Setup the proxy settings UI."""
        from PyQt6.QtWidgets import QGridLayout, QFormLayout

        layout = QVBoxLayout(self)

        desc = QLabel(
            "Route traffic through proxy servers or Tor. Set a global default, "
            "then optionally override it per-category."
        )
        desc.setWordWrap(True)
        desc.setProperty("class", "tab-description")
        layout.addWidget(desc)

        # ── 2-column grid ─────────────────────────────────────────────
        grid = QGridLayout()
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(0, 50)
        grid.setColumnStretch(1, 50)

        # ── Top-left: Default Connection ──────────────────────────────
        default_group = QGroupBox("Default Connection")
        default_layout = QVBoxLayout(default_group)

        default_desc_row = QHBoxLayout()
        default_desc_row.addWidget(_group_desc(
            "All traffic uses this unless a category override says otherwise."
        ))
        default_desc_row.addWidget(InfoButton(
            "<b>No proxy (direct connection)</b> &mdash; connect straight to the "
            "internet, no proxy.<br><br>"
            "<b>Use system proxy settings</b> &mdash; use whatever proxy your "
            "operating system is configured with.<br><br>"
            "<b>Use Tor network</b> &mdash; route traffic through the Tor "
            "anonymity network (see Tor section).<br><br>"
            "<b>Pool name</b> &mdash; use a custom proxy pool you have created."
        ))
        default_layout.addLayout(default_desc_row)

        global_row = QHBoxLayout()
        global_row.addWidget(QLabel("Global Default:"))
        self.global_dropdown = SimpleProxyDropdown(category="__global__", is_global=True)
        self.global_dropdown.setToolTip("Default proxy for all network traffic")
        self.global_dropdown.value_changed.connect(self._on_settings_changed)
        self.global_dropdown.value_changed.connect(self._refresh_category_dropdowns)
        global_row.addWidget(self.global_dropdown, 1)
        default_layout.addLayout(global_row)

        grid.addWidget(default_group, 0, 0)

        # ── Bottom-right: Proxy Pools ─────────────────────────────────
        self.pools_group = QGroupBox("Proxy Pools")
        pools_layout = QVBoxLayout(self.pools_group)

        pools_desc_row = QHBoxLayout()
        pools_desc_row.addWidget(_group_desc(
            "Named groups of proxy servers. Assign a pool as the global "
            "default or to a specific category."
        ))
        pools_desc_row.addWidget(InfoButton(
            "<b>What is a pool?</b><br>"
            "A named collection of one or more proxy servers. When a pool "
            "is assigned, BBDrop picks a proxy from it according to the "
            "rotation strategy you choose when creating the pool.<br><br>"
            "<b>Adding proxies</b><br>"
            "Click <b>New Pool</b>, give it a name, choose a rotation "
            "strategy, and paste your proxies &mdash; one per line in "
            "<code>host:port</code> format. Use "
            "<code>user:pass@host:port</code> for authenticated proxies."
        ))
        pools_layout.addLayout(pools_desc_row)

        self.pools_list = QListWidget()
        self.pools_list.setMinimumHeight(100)
        self.pools_list.itemSelectionChanged.connect(self._on_pool_selected)
        self.pools_list.itemDoubleClicked.connect(self._on_pool_edit)
        pools_layout.addWidget(self.pools_list)

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
        self.delete_pool_btn.setToolTip("Delete the selected proxy pool and clear its assignments")
        self.delete_pool_btn.setEnabled(False)
        self.delete_pool_btn.clicked.connect(self._on_delete_pool)
        pool_btn_layout.addWidget(self.delete_pool_btn)

        self.test_pool_btn = QPushButton("Test")
        self.test_pool_btn.setEnabled(False)
        self.test_pool_btn.setToolTip("Test connectivity through the first proxy in the selected pool")
        self.test_pool_btn.clicked.connect(self._on_test_pool)
        pool_btn_layout.addWidget(self.test_pool_btn)

        pool_btn_layout.addStretch()
        pools_layout.addLayout(pool_btn_layout)

        grid.addWidget(self.pools_group, 1, 1)

        # ── Top-right: Tor Network ────────────────────────────────────
        tor_group = QGroupBox("Tor Network")
        tor_layout = QVBoxLayout(tor_group)

        tor_layout.addWidget(_group_desc(
            "Route traffic through the Tor anonymity network. "
            "Significantly slower than a direct connection."
        ))

        status_row = QHBoxLayout()
        status_row.addWidget(QLabel("Status:"))
        self.tor_status_label = QLabel("Checking...")
        status_row.addWidget(self.tor_status_label)
        status_row.addStretch()
        self.tor_configure_btn = QPushButton("Configure...")
        self.tor_configure_btn.setToolTip(
            "Connection settings, circuit control, and download info"
        )
        self.tor_configure_btn.clicked.connect(self._on_tor_configure)
        status_row.addWidget(self.tor_configure_btn)
        tor_layout.addLayout(status_row)

        grid.addWidget(tor_group, 0, 1)

        # ── Bottom-left: Category Overrides ───────────────────────────
        self.category_group = QGroupBox("Category Overrides")
        category_layout = QVBoxLayout(self.category_group)

        cat_desc_row = QHBoxLayout()
        cat_desc_row.addWidget(_group_desc(
            "Override the global default for specific traffic types."
        ))
        cat_desc_row.addWidget(InfoButton(
            "Each category can use a different proxy setting. For example, "
            "route file host traffic through a fast proxy and image uploads "
            "through Tor.<br><br>"
            "<b>Use global default</b> &mdash; no override; inherits the "
            "global default connection above.<br><br>"
            "All other options work the same as the global default dropdown."
        ))
        category_layout.addLayout(cat_desc_row)

        cat_form = QFormLayout()
        cat_form.setHorizontalSpacing(8)

        self.file_hosts_dropdown = SimpleProxyDropdown(category="file_hosts")
        self.file_hosts_dropdown.setToolTip("RapidGator, FileBoom, Keep2Share, TezFiles, Filedot, Filespace")
        self.file_hosts_dropdown.value_changed.connect(self._on_settings_changed)
        cat_form.addRow("File Hosts:", self.file_hosts_dropdown)

        self.image_hosts_dropdown = SimpleProxyDropdown(category="image_hosts")
        self.image_hosts_dropdown.setToolTip("IMX.to, TurboImageHost")
        self.image_hosts_dropdown.value_changed.connect(self._on_settings_changed)
        cat_form.addRow("Image Hosts:", self.image_hosts_dropdown)

        self.forums_dropdown = SimpleProxyDropdown(category="forums")
        self.forums_dropdown.setToolTip("Forum posting and scraping requests")
        self.forums_dropdown.value_changed.connect(self._on_settings_changed)
        cat_form.addRow("Forums:", self.forums_dropdown)

        self.api_dropdown = SimpleProxyDropdown(category="api")
        self.api_dropdown.setToolTip("API calls to host services (login, status checks)")
        self.api_dropdown.value_changed.connect(self._on_settings_changed)
        cat_form.addRow("API:", self.api_dropdown)

        category_layout.addLayout(cat_form)

        grid.addWidget(self.category_group, 1, 0)

        layout.addLayout(grid)
        layout.addStretch()

        # Check Tor status after UI is built (non-blocking)
        self._tor_status_ready.connect(self._update_tor_status)
        QTimer.singleShot(0, self._check_tor_status)

    # ── Tor status ────────────────────────────────────────────────────

    def _check_tor_status(self):
        """Check if Tor is running, in a background thread to avoid UI freeze."""
        self.tor_status_label.setText("Checking...")
        self.tor_status_label.setStyleSheet("")

        def _probe():
            from src.proxy.tor import is_tor_running
            running = is_tor_running(timeout=1.5)
            try:
                self._tor_status_ready.emit(running)
            except RuntimeError:
                pass  # Widget deleted before probe finished

        threading.Thread(target=_probe, daemon=True).start()

    def _update_tor_status(self, running: bool):
        """Update Tor status label on the main thread."""
        if running:
            self.tor_status_label.setText("Running (127.0.0.1:9050)")
            self.tor_status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.tor_status_label.setText("Not detected (127.0.0.1:9050)")
            self.tor_status_label.setStyleSheet("color: red;")

    # ── Pool management ───────────────────────────────────────────────

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

    def _refresh_category_dropdowns(self):
        """Refresh category dropdowns so 'Use global default: ...' text stays current."""
        self.file_hosts_dropdown.refresh()
        self.image_hosts_dropdown.refresh()
        self.forums_dropdown.refresh()
        self.api_dropdown.refresh()

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

    def _on_tor_configure(self):
        """Open the Tor configuration dialog."""
        from src.gui.dialogs.tor_config_dialog import TorConfigDialog

        dialog = TorConfigDialog(self)
        dialog.exec()
        # Refresh status on the tab after dialog closes
        self._check_tor_status()

    def load_settings(self, settings: dict):
        """Load settings - called by parent settings dialog."""
        self.load_pools()
        self._check_tor_status()

    def get_settings(self) -> dict:
        """Get settings - called by parent settings dialog."""
        return {}
