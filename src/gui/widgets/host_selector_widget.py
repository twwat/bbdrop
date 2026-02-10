"""
Host selector widget for choosing target image host.

Provides a dropdown selector populated from ImageHostConfigManager
with proper signal emission when selection changes.
"""

from typing import Optional

from PyQt6.QtWidgets import QWidget, QComboBox, QHBoxLayout, QLabel
from PyQt6.QtCore import pyqtSignal, Qt

from src.core.image_host_config import get_image_host_config_manager


class HostSelectorWidget(QWidget):
    """Dropdown widget to select target image host.

    Provides a labeled combo box populated with all enabled image hosts
    from the ImageHostConfigManager. Emits a signal when the selection
    changes.

    Usage:
        selector = HostSelectorWidget()
        selector.host_changed.connect(self._on_host_changed)

        # Get current selection
        host_id = selector.get_selected_host()

        # Set selection programmatically
        selector.set_selected_host("imx")
    """

    # Signal emitted when selection changes, passes host_id
    host_changed = pyqtSignal(str)

    # Preferred default host ID (used when available)
    PREFERRED_HOST = "imx"

    def __init__(self, parent: Optional[QWidget] = None, show_label: bool = True):
        """Initialize the host selector widget.

        Args:
            parent: Parent widget
            show_label: Whether to show the "Host:" label (default: True)
        """
        super().__init__(parent)
        self._show_label = show_label
        self._setup_ui()
        self._populate_hosts()

    def _setup_ui(self) -> None:
        """Set up the widget UI components."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        if self._show_label:
            self.label = QLabel("Host:")
            self.label.setToolTip("Select target image hosting service")
            layout.addWidget(self.label)
        else:
            self.label = None

        self.combo = QComboBox()
        self.combo.setMinimumWidth(150)
        self.combo.setToolTip("Select target image hosting service")
        self.combo.currentIndexChanged.connect(self._on_selection_changed)

        layout.addWidget(self.combo)
        layout.addStretch()

    def _populate_hosts(self) -> None:
        """Populate the combo box with available image hosts."""
        # Block signals during population to prevent spurious emissions
        self.combo.blockSignals(True)

        try:
            self.combo.clear()

            manager = get_image_host_config_manager()
            enabled_hosts = manager.get_enabled_hosts()

            if not enabled_hosts:
                # No hosts available - add placeholder
                self.combo.addItem("No hosts configured", None)
                self.combo.setEnabled(False)
                return

            # Add each enabled host
            for host_id, config in enabled_hosts.items():
                display_name = config.name or host_id.upper()
                self.combo.addItem(display_name, host_id)

                # Set tooltip with host details
                idx = self.combo.count() - 1
                tooltip = f"{display_name}"
                if config.requires_auth:
                    auth_type = config.auth_type or "authentication"
                    tooltip += f" (requires {auth_type})"
                self.combo.setItemData(idx, tooltip, role=Qt.ItemDataRole.ToolTipRole)

            # Select default host if available
            self._select_default_host()

        finally:
            self.combo.blockSignals(False)

    def _select_default_host(self) -> None:
        """Select the default host in the combo box."""
        # Try to select the preferred host
        for i in range(self.combo.count()):
            if self.combo.itemData(i) == self.PREFERRED_HOST:
                self.combo.setCurrentIndex(i)
                return

        # If preferred not found, select first available item
        if self.combo.count() > 0:
            self.combo.setCurrentIndex(0)

    def _on_selection_changed(self, index: int) -> None:
        """Handle combo box selection change.

        Args:
            index: New selected index
        """
        host_id = self.combo.currentData()
        if host_id:
            self.host_changed.emit(host_id)

    def get_selected_host(self) -> str:
        """Get the currently selected host ID.

        Returns:
            The host ID string, or the first enabled host if nothing valid is selected.
        """
        host_id = self.combo.currentData()
        if host_id:
            return host_id
        # Fallback: return the first enabled host instead of hardcoded "imx"
        manager = get_image_host_config_manager()
        enabled = manager.get_enabled_hosts()
        if enabled:
            return next(iter(enabled))
        return self.PREFERRED_HOST  # absolute last resort

    def set_selected_host(self, host_id: str) -> bool:
        """Set the selected host by ID.

        Args:
            host_id: The host ID to select (e.g., "imx", "turbo")

        Returns:
            True if the host was found and selected, False otherwise.
        """
        for i in range(self.combo.count()):
            if self.combo.itemData(i) == host_id:
                self.combo.setCurrentIndex(i)
                return True
        return False

    def refresh(self) -> None:
        """Refresh the host list from the config manager.

        This reloads the available hosts and tries to restore
        the current selection.
        """
        # Save current selection
        current_host = self.get_selected_host()

        # Repopulate
        self._populate_hosts()

        # Try to restore selection
        if not self.set_selected_host(current_host):
            # If previous selection not available, select default
            self._select_default_host()

    def get_selected_host_config(self):
        """Get the full config object for the selected host.

        Returns:
            ImageHostConfig for the selected host, or None if not found.
        """
        host_id = self.get_selected_host()
        manager = get_image_host_config_manager()
        return manager.get_host(host_id)

    def setEnabled(self, enabled: bool) -> None:
        """Enable or disable the widget.

        Args:
            enabled: Whether the widget should be enabled.
        """
        super().setEnabled(enabled)
        self.combo.setEnabled(enabled)
        if self.label:
            self.label.setEnabled(enabled)
