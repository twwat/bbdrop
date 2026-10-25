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


def test_connection_limit_spinboxes_round_trip(qapp):
    widget = FileHostsSettingsWidget(parent=None, worker_manager=None)
    assert widget.get_settings()["global_limit"] == 3
    widget.load_settings({"global_limit": 6, "per_host_limit": 4})
    settings = widget.get_settings()
    assert (settings["global_limit"], settings["per_host_limit"]) == (6, 4)


def test_save_writes_limits_and_applies_them_to_the_coordinator(qapp, tmp_path, monkeypatch):
    from src.processing.file_host_coordinator import FileHostCoordinator
    ini = tmp_path / "bbdrop.ini"
    monkeypatch.setattr("src.utils.paths.get_config_path", lambda: str(ini))
    coordinator = FileHostCoordinator()
    monkeypatch.setattr("src.gui.settings.file_hosts_tab.get_coordinator", lambda: coordinator)

    widget = FileHostsSettingsWidget(parent=None, worker_manager=None)
    widget.global_limit_spin.setValue(7)
    widget.per_host_limit_spin.setValue(3)
    widget.save_to_config()

    import configparser
    cfg = configparser.ConfigParser()
    cfg.read(ini, encoding="utf-8")
    assert cfg.getint("FILE_HOSTS", "global_limit") == 7
    assert cfg.getint("FILE_HOSTS", "per_host_limit") == 3
    assert (coordinator.global_limit, coordinator.per_host_limit) == (7, 3)


def test_changing_a_limit_marks_the_tab_dirty(qapp):
    widget = FileHostsSettingsWidget(parent=None, worker_manager=None)
    seen = []
    widget.settings_changed.connect(lambda: seen.append(1))
    widget.global_limit_spin.setValue(5)
    assert seen


def test_failed_host_load_still_shows_saved_limits(qapp, tmp_path, monkeypatch):
    ini = tmp_path / "bbdrop.ini"
    ini.write_text("[FILE_HOSTS]\nglobal_limit = 6\nper_host_limit = 4\n", encoding="utf-8")
    monkeypatch.setattr("src.utils.paths.get_config_path", lambda: str(ini))
    widget = FileHostsSettingsWidget(parent=None, worker_manager=None)

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("src.core.file_host_config.get_file_host_setting", boom)
    widget.load_from_config()
    assert (widget.global_limit_spin.value(), widget.per_host_limit_spin.value()) == (6, 4)
