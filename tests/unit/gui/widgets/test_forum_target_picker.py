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


@pytest.fixture
def conn_with_collision(conn):
    """A subforum and a thread sharing target_id '10' in the same forum.

    vBulletin id namespaces are separate per kind, so this is a legitimate,
    non-corrupt state: forum_targets is UNIQUE(forum_fk, kind, target_id),
    not UNIQUE(forum_fk, target_id).
    """
    conn.execute(
        "INSERT INTO forums(id,name,software_id,base_url)"
        " VALUES(1,'Forum A','vb','http://a.com')"
    )
    conn.execute(
        "INSERT INTO forum_targets(forum_fk,name,kind,target_id)"
        " VALUES(1,'Thread 10','thread','10')"
    )
    conn.execute(
        "INSERT INTO forum_targets(forum_fk,name,kind,target_id)"
        " VALUES(1,'Subforum 10','subforum','10')"
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


_THREAD_1 = {"forum_fk": 1, "forum_name": "Forum A",
             "target_id": "10", "kind": "thread", "name": "Thread 1"}


def _item_for(panel, target_id):
    """The visible list row for target_id, or None if filtered out."""
    from PyQt6.QtCore import Qt
    for i in range(panel._list.count()):
        item = panel._list.item(i)
        data = item.data(Qt.ItemDataRole.UserRole)
        if data and data.get("target_id") == target_id:
            return item
    return None


def _item_for_kind(panel, target_id, kind):
    """The visible list row for (target_id, kind), or None if filtered out.

    Needed once a subforum and a thread can share a target_id in the same
    forum — _item_for's target_id-only match can't disambiguate them.
    """
    from PyQt6.QtCore import Qt
    for i in range(panel._list.count()):
        item = panel._list.item(i)
        data = item.data(Qt.ItemDataRole.UserRole)
        if data and data.get("target_id") == target_id and data.get("kind") == kind:
            return item
    return None


def _accepted_ids(panel):
    """Click 'Add selected' and return the emitted target_ids."""
    emitted = []
    panel.targets_selected.connect(emitted.append)
    panel._accept()
    assert len(emitted) == 1
    return [t["target_id"] for t in emitted[0]]


@pytest.mark.unit
def test_picker_panel_premarks_current(conn_with_targets):
    from src.gui.widgets.forum_target_picker import _TargetPickerPanel
    panel = _TargetPickerPanel(conn_with_targets, current=[_THREAD_1])
    item = _item_for(panel, "10")
    assert item is not None
    assert item.isSelected()


@pytest.mark.unit
def test_picker_panel_selection_survives_filter(conn_with_targets):
    """A row the user selects stays selected across a search/clear cycle."""
    from src.gui.widgets.forum_target_picker import _TargetPickerPanel
    panel = _TargetPickerPanel(conn_with_targets, current=[])
    _item_for(panel, "10").setSelected(True)

    panel._filter("Sub")
    assert _item_for(panel, "10") is None  # hidden by the search
    panel._filter("")

    item = _item_for(panel, "10")
    assert item is not None
    assert item.isSelected(), "Selection lost after filter cycle"


@pytest.mark.unit
def test_picker_panel_accept_includes_selection_hidden_by_filter(conn_with_targets):
    from src.gui.widgets.forum_target_picker import _TargetPickerPanel
    panel = _TargetPickerPanel(conn_with_targets, current=[])
    _item_for(panel, "10").setSelected(True)
    panel._filter("Sub")                     # Thread 1 now hidden
    _item_for(panel, "20").setSelected(True)

    # Library order = fp.list_targets' ORDER BY kind, name: subforum first.
    assert _accepted_ids(panel) == ["20", "10"]


@pytest.mark.unit
def test_picker_panel_accept_keeps_current_target_hidden_by_filter(conn_with_targets):
    """The data-loss case: an already-configured target must survive a
    search that hides it, then 'Add selected'."""
    from src.gui.widgets.forum_target_picker import _TargetPickerPanel
    panel = _TargetPickerPanel(conn_with_targets, current=[_THREAD_1])
    panel._filter("Sub")

    assert _accepted_ids(panel) == ["10"]


@pytest.mark.unit
def test_picker_panel_deselect_removes_target(conn_with_targets):
    from src.gui.widgets.forum_target_picker import _TargetPickerPanel
    panel = _TargetPickerPanel(conn_with_targets, current=[_THREAD_1])
    _item_for(panel, "10").setSelected(False)

    assert _accepted_ids(panel) == []


@pytest.mark.unit
def test_picker_panel_accept_keeps_current_target_missing_from_library(conn_with_targets):
    """A configured target no longer in the library is never shown, so the
    user can't have deselected it — it must not be silently dropped."""
    from src.gui.widgets.forum_target_picker import _TargetPickerPanel
    gone = {"forum_fk": 1, "forum_name": "Forum A",
            "target_id": "99", "kind": "thread", "name": "Gone"}
    panel = _TargetPickerPanel(conn_with_targets, current=[gone])

    assert _accepted_ids(panel) == ["99"]


@pytest.mark.unit
def test_picker_panel_accept_current_plus_selection_hidden_by_filter(conn_with_targets):
    """Documented behaviour change (plan's "Behaviour change" note): current
    pre-selects Thread 1; a filter hides it while the user also picks Sub 1.
    Accept emits both, in library order (subforum sorts before thread)."""
    from src.gui.widgets.forum_target_picker import _TargetPickerPanel
    panel = _TargetPickerPanel(conn_with_targets, current=[_THREAD_1])
    panel._filter("Sub")                     # Thread 1 now hidden
    _item_for(panel, "20").setSelected(True)

    assert _accepted_ids(panel) == ["20", "10"]


# ---------------------------------------------------------------------------
# (forum_fk, kind, target_id) key collision regression
#
# The picker used to key targets on (forum_fk, target_id) only, but
# forum_targets is UNIQUE(forum_fk, kind, target_id): a subforum and a
# thread can legitimately share a target_id in the same forum (vBulletin id
# namespaces are separate per kind). With the 2-part key, checking one of a
# colliding pair marked both as selected/deselected together, so _accept
# either silently dropped a selection or emitted the wrong kind.
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_picker_panel_collision_select_thread_only(conn_with_collision):
    from src.gui.widgets.forum_target_picker import _TargetPickerPanel
    panel = _TargetPickerPanel(conn_with_collision, current=[])
    _item_for_kind(panel, "10", "thread").setSelected(True)

    emitted = []
    panel.targets_selected.connect(emitted.append)
    panel._accept()
    assert len(emitted) == 1
    assert [(t["kind"], t["target_id"]) for t in emitted[0]] == [("thread", "10")]


@pytest.mark.unit
def test_picker_panel_collision_select_subforum_only(conn_with_collision):
    from src.gui.widgets.forum_target_picker import _TargetPickerPanel
    panel = _TargetPickerPanel(conn_with_collision, current=[])
    _item_for_kind(panel, "10", "subforum").setSelected(True)

    emitted = []
    panel.targets_selected.connect(emitted.append)
    panel._accept()
    assert len(emitted) == 1
    assert [(t["kind"], t["target_id"]) for t in emitted[0]] == [("subforum", "10")]


@pytest.mark.unit
def test_picker_panel_collision_survive_filter_independently(conn_with_collision):
    """Selecting one of a colliding pair must not affect the other, and both
    must be able to hold independent selection states across a filter cycle."""
    from src.gui.widgets.forum_target_picker import _TargetPickerPanel
    panel = _TargetPickerPanel(conn_with_collision, current=[])
    _item_for_kind(panel, "10", "thread").setSelected(True)

    panel._filter("Sub")
    sub_item = _item_for_kind(panel, "10", "subforum")
    assert sub_item is not None
    assert not sub_item.isSelected()  # selecting the thread didn't select this
    panel._filter("")

    thread_item = _item_for_kind(panel, "10", "thread")
    sub_item = _item_for_kind(panel, "10", "subforum")
    assert thread_item.isSelected(), "Thread selection lost after filter cycle"
    assert not sub_item.isSelected()

    sub_item.setSelected(True)
    emitted = []
    panel.targets_selected.connect(emitted.append)
    panel._accept()
    assert len(emitted) == 1
    kinds = sorted(t["kind"] for t in emitted[0])
    assert kinds == ["subforum", "thread"]


@pytest.mark.unit
def test_remove_target_collision_keeps_same_id_other_kind(conn_with_collision):
    """Removing the thread pill must not remove the subforum pill that
    shares the same target_id in the same forum."""
    from src.gui.widgets.forum_target_picker import ForumTargetPicker
    picker = ForumTargetPicker(conn_with_collision)
    thread = {"forum_fk": 1, "forum_name": "Forum A",
              "target_id": "10", "kind": "thread", "name": "Thread 10"}
    subforum = {"forum_fk": 1, "forum_name": "Forum A",
                "target_id": "10", "kind": "subforum", "name": "Subforum 10"}
    picker.set_targets([thread, subforum])
    picker._remove_target(thread)

    remaining = picker.get_targets()
    assert len(remaining) == 1
    assert remaining[0]["kind"] == "subforum"
