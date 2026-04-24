"""Unit tests for ForumTargetPicker widget."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile

import pytest
from PyQt6.QtWidgets import QApplication

from src.storage.database import _ensure_schema, _schema_initialized_dbs

_app = QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def conn():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    _ensure_schema(db)
    yield db
    db.close()
    _schema_initialized_dbs.discard(path)
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def conn_with_targets(conn):
    conn.execute(
        "INSERT INTO forums(id,name,software_id,base_url)"
        " VALUES(1,'Forum A','vb','http://a.com')"
    )
    conn.execute(
        "INSERT INTO forum_targets(forum_fk,name,kind,target_id)"
        " VALUES(1,'Thread 1','thread','10')"
    )
    conn.execute(
        "INSERT INTO forum_targets(forum_fk,name,kind,target_id)"
        " VALUES(1,'Sub 1','subforum','20')"
    )
    conn.commit()
    return conn


@pytest.mark.unit
def test_picker_starts_empty(conn_with_targets):
    from src.gui.widgets.forum_target_picker import ForumTargetPicker
    picker = ForumTargetPicker(conn_with_targets)
    assert picker.get_targets() == []


@pytest.mark.unit
def test_picker_set_targets_reflected_in_get(conn_with_targets):
    from src.gui.widgets.forum_target_picker import ForumTargetPicker
    picker = ForumTargetPicker(conn_with_targets)
    targets = [{"forum_fk": 1, "forum_name": "Forum A",
                "target_id": "10", "kind": "thread", "name": "Thread 1"}]
    picker.set_targets(targets)
    result = picker.get_targets()
    assert len(result) == 1
    assert result[0]["target_id"] == "10"


@pytest.mark.unit
def test_picker_emits_signal_on_remove(conn_with_targets):
    from src.gui.widgets.forum_target_picker import ForumTargetPicker
    picker = ForumTargetPicker(conn_with_targets)
    t = {"forum_fk": 1, "forum_name": "Forum A",
         "target_id": "10", "kind": "thread", "name": "Thread 1"}
    picker.set_targets([t])
    emitted = []
    picker.targets_changed.connect(emitted.append)
    picker._remove_target(t)
    assert len(emitted) == 1
    assert emitted[0] == []


@pytest.mark.unit
def test_picker_remove_specific_target_keeps_others(conn_with_targets):
    from src.gui.widgets.forum_target_picker import ForumTargetPicker
    picker = ForumTargetPicker(conn_with_targets)
    t1 = {"forum_fk": 1, "forum_name": "Forum A",
          "target_id": "10", "kind": "thread", "name": "Thread 1"}
    t2 = {"forum_fk": 1, "forum_name": "Forum A",
          "target_id": "20", "kind": "subforum", "name": "Sub 1"}
    picker.set_targets([t1, t2])
    picker._remove_target(t1)
    remaining = picker.get_targets()
    assert len(remaining) == 1
    assert remaining[0]["target_id"] == "20"


@pytest.mark.unit
def test_picker_set_targets_twice_replaces(conn_with_targets):
    from src.gui.widgets.forum_target_picker import ForumTargetPicker
    picker = ForumTargetPicker(conn_with_targets)
    t1 = {"forum_fk": 1, "forum_name": "Forum A",
          "target_id": "10", "kind": "thread", "name": "Thread 1"}
    picker.set_targets([t1])
    t2 = {"forum_fk": 1, "forum_name": "Forum A",
          "target_id": "20", "kind": "subforum", "name": "Sub 1"}
    picker.set_targets([t2])
    result = picker.get_targets()
    assert len(result) == 1
    assert result[0]["target_id"] == "20"


@pytest.mark.unit
def test_picker_panel_loads_targets(conn_with_targets):
    from src.gui.widgets.forum_target_picker import _TargetPickerPanel
    panel = _TargetPickerPanel(conn_with_targets, current=[])
    # Panel should have loaded the 2 targets + 1 header = 3 items
    assert panel._list.count() == 3  # 1 forum header + 2 targets


@pytest.mark.unit
def test_picker_panel_premarks_current(conn_with_targets):
    from src.gui.widgets.forum_target_picker import _TargetPickerPanel
    from PyQt6.QtCore import Qt
    current = [{"forum_fk": 1, "target_id": "10"}]
    panel = _TargetPickerPanel(conn_with_targets, current=current)
    # Find the item with target_id "10" and confirm it's checked
    for i in range(panel._list.count()):
        item = panel._list.item(i)
        data = item.data(Qt.ItemDataRole.UserRole)
        if data and data.get("target_id") == "10":
            assert item.checkState() == Qt.CheckState.Checked
            break


@pytest.mark.unit
def test_picker_panel_checked_keys_survive_filter(conn_with_targets):
    """Checkbox state should persist across search/filter cycles."""
    from src.gui.widgets.forum_target_picker import _TargetPickerPanel
    from PyQt6.QtCore import Qt
    panel = _TargetPickerPanel(conn_with_targets, current=[])
    # Find and check "Thread 1"
    for i in range(panel._list.count()):
        item = panel._list.item(i)
        data = item.data(Qt.ItemDataRole.UserRole)
        if data and data.get("target_id") == "10":
            item.setCheckState(Qt.CheckState.Checked)
            break
    # Filter list (Thread 1 disappears)
    panel._filter("Sub")
    # Clear filter (Thread 1 reappears)
    panel._filter("")
    # Thread 1 should still be checked
    found = False
    for i in range(panel._list.count()):
        item = panel._list.item(i)
        data = item.data(Qt.ItemDataRole.UserRole)
        if data and data.get("target_id") == "10":
            assert item.checkState() == Qt.CheckState.Checked, "Checked state lost after filter cycle"
            found = True
            break
    assert found, "Thread 1 not found after filter cleared"
