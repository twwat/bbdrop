"""Signals and state the unified Hosts tab must expose."""
import os

# Ensure Qt uses offscreen platform for headless testing
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import pyqtBoundSignal

from src.gui.settings.file_hosts_tab import FileHostsSettingsWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    # Icon manager is normally initialized by the main window; tests need it too.
    from src.gui.icon_manager import get_icon_manager, init_icon_manager
    from src.utils.paths import get_project_root
    if get_icon_manager() is None:
        init_icon_manager(os.path.join(get_project_root(), "assets"))
    yield app


def test_widget_exposes_primary_and_cover_signals(qapp):
    widget = FileHostsSettingsWidget(parent=None, worker_manager=None)
    assert isinstance(widget.primary_host_changed, pyqtBoundSignal)
    assert isinstance(widget.cover_host_changed, pyqtBoundSignal)
    assert isinstance(widget.cover_gallery_changed, pyqtBoundSignal)


def test_widget_tracks_active_image_host(qapp):
    widget = FileHostsSettingsWidget(parent=None, worker_manager=None)
    widget.set_active_image_host('pixhost')
    assert widget._active_image_host == 'pixhost'


def test_set_covers_enabled_is_callable(qapp):
    widget = FileHostsSettingsWidget(parent=None, worker_manager=None)
    widget.set_covers_enabled(True)
    widget.set_covers_enabled(False)
