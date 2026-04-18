"""Tests that the controller wires load/save through to the cache store."""
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QObject
from src.network.file_manager.client import FileInfo, FileListResult


def _make_controller(monkeypatch=None):
    """Construct a FileManagerController with fully mocked dialog and worker.

    ``super().__init__(dialog)`` passes the dialog as a Qt parent, which
    rejects a plain MagicMock.  We sidestep this by patching QObject.__init__
    to a no-op for the duration of construction.
    """
    from src.gui.file_manager_controller import FileManagerController

    dialog = MagicMock()
    dialog.file_list = MagicMock()
    dialog.folder_tree = MagicMock()
    dialog.toolbar = MagicMock()
    dialog.parent.return_value = None
    dialog.reapply_filter = MagicMock()

    with patch("src.gui.file_manager_controller.FileManagerWorker"), \
         patch.object(QObject, "__init__", lambda self, *a, **kw: None):
        c = FileManagerController.__new__(FileManagerController)
        FileManagerController.__init__(c, dialog)

    return c


def test_on_files_loaded_calls_cache_store_save(qtbot, monkeypatch):
    """When the worker emits files_loaded, the controller writes through to SQLite."""
    c = _make_controller()

    c._current_host = "rapidgator"
    c._current_folder = "/"
    c._in_trash = False

    # Register a pending request so _on_files_loaded knows where the
    # response belongs.
    op_id = "op1"
    c._pending_file_folders[op_id] = ("rapidgator", "/")

    result = FileListResult(files=[], total=0, page=1, per_page=100)

    save_spy = MagicMock()
    monkeypatch.setattr("src.gui.file_manager_cache_store.save", save_spy)

    c._on_files_loaded(op_id, result)

    assert save_spy.called, "cache_store.save should be called after files_loaded"
    called_host, called_folder, called_result, called_ts = save_spy.call_args[0]
    assert called_host == "rapidgator"
    assert called_folder == "/"
    assert called_result is result
    assert isinstance(called_ts, float)


def test_set_host_warms_file_cache_from_store(qtbot, monkeypatch):
    """set_host should pre-fill _file_cache from persistent storage."""
    from src.network.file_manager.client import FileManagerCapabilities

    c = _make_controller()

    # Stub out the probe so set_host reaches the warm-then-load stage.
    monkeypatch.setattr(c, "_probe_host",
                        lambda h: (FileManagerCapabilities(), None))
    monkeypatch.setattr(c, "_load_files", lambda: None)
    monkeypatch.setattr(c, "_load_folder_tree", lambda p: None)
    monkeypatch.setattr(c, "_load_account_info", lambda: None)

    cached_result = FileListResult(files=[], total=0, page=1, per_page=100)
    load_all_spy = MagicMock(return_value={"/": (cached_result, 1234.0)})
    monkeypatch.setattr("src.gui.file_manager_cache_store.load_all", load_all_spy)

    c.set_host("rapidgator")

    load_all_spy.assert_called_once_with("rapidgator")
    assert ("rapidgator", "/") in c._file_cache
    result, ts = c._file_cache[("rapidgator", "/")]
    assert result is cached_result
    assert ts == 1234.0
