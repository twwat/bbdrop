"""Settings dialog package — one module per tab."""

from src.gui.settings.settings_dialog import ComprehensiveSettingsDialog
from src.gui.settings.tab_index import TabIndex
from src.gui.settings.host_test_dialog import HostTestDialog  # noqa: F401
from src.gui.widgets.icon_drop_frame import IconDropFrame  # noqa: F401

__all__ = [
    "ComprehensiveSettingsDialog",
    "TabIndex",
    "HostTestDialog",
    "IconDropFrame",
]
