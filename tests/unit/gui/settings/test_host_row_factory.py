"""Shared row factory produces the right widget set per host kind."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton

from src.gui.settings.file_hosts_tab import FileHostsSettingsWidget
from src.gui.widgets.custom_widgets import StorageTrafficBar


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from src.gui.icon_manager import get_icon_manager, init_icon_manager
    from src.utils.paths import get_project_root
    if get_icon_manager() is None:
        init_icon_manager(os.path.join(get_project_root(), "assets"))
    yield app


def test_file_host_with_storage_gets_progress_bar(qapp):
    widget = FileHostsSettingsWidget(parent=None, worker_manager=None)
    entry = widget.host_widgets.get('rapidgator')
    assert entry is not None
    # File hosts with storage support use QProgressBar (not StorageTrafficBar)
    # This is by design per commit e15bf0a for visual unification with image hosts
    from PyQt6.QtWidgets import QProgressBar
    assert isinstance(entry['storage_bar'], QProgressBar)


def test_image_host_row_omits_storage_slot(qapp):
    """Image hosts now have a StorageTrafficBar in unlimited mode for visual parity."""
    widget = FileHostsSettingsWidget(parent=None, worker_manager=None)
    entry = widget.host_widgets.get('imx')
    assert entry is not None, "Image host 'imx' should appear in host_widgets"
    assert entry.get('kind') == 'image'
    # Image hosts have storage_bar with unlimited state (no quota) per commit e71a91f
    assert isinstance(entry['storage_bar'], StorageTrafficBar)
    assert entry['unlimited_label'] is None  # unlimited_label deprecated in favor of StorageTrafficBar.set_unlimited()
    assert isinstance(entry['status_label'], QLabel)


def test_every_row_has_configure_button(qapp):
    widget = FileHostsSettingsWidget(parent=None, worker_manager=None)
    for host_id, entry in widget.host_widgets.items():
        assert isinstance(entry['configure_btn'], QPushButton), f"{host_id} missing Configure"
