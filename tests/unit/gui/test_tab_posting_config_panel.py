import os
import sqlite3
import tempfile

import pytest
from PyQt6.QtWidgets import QApplication

from src.gui.widgets.tab_posting_config_panel import (
    TabPostingConfigPanel, _ADD_NEW,
)
from src.storage import forum_posting as fp
from src.storage.database import _ensure_schema, _schema_initialized_dbs


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def conn():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    _ensure_schema(c)
    yield c
    c.close()
    _schema_initialized_dbs.discard(path)
    try:
        os.unlink(path)
    except OSError:
        pass


def _make_tab(conn) -> int:
    conn.execute(
        "INSERT INTO tabs(name, tab_type, display_order) "
        "VALUES('T','user',0)",
    )
    return conn.execute("SELECT id FROM tabs WHERE name='T'").fetchone()[0]


def _select_target(panel, target_id: str, kind: str):
    """Helper: select a forum_target row by (kind, target_id) in the combo."""
    for i in range(panel.target_combo.count()):
        data = panel.target_combo.itemData(i)
        if isinstance(data, dict) and data.get("kind") == kind \
                and str(data.get("target_id")) == str(target_id):
            panel.target_combo.setCurrentIndex(i)
            return
    raise AssertionError(
        f"Target ({kind}, {target_id}) not found in combo"
    )


def _select_template(panel, name: str):
    idx = panel.template_combo.findData(name)
    assert idx >= 0, f"Template {name!r} not found in combo"
    panel.template_combo.setCurrentIndex(idx)


def test_panel_constructs(app, conn):
    fp.insert_forum(
        conn, name="VIP", software_id="vbulletin_4_2_0",
        base_url="https://x", default_cooldown_s=30,
    )
    tab_id = _make_tab(conn)
    panel = TabPostingConfigPanel(conn=conn, tab_id=tab_id)
    assert panel.forum_combo.count() == 1
    # Target combo always has the "+ Add new…" sentinel, even with no
    # targets saved for the forum yet.
    assert panel.target_combo.itemData(
        panel.target_combo.count() - 1,
    ) == _ADD_NEW


def test_panel_loads_existing_config_reselects_target(app, conn):
    fid = fp.insert_forum(
        conn, name="VIP", software_id="vbulletin_4_2_0",
        base_url="https://x", default_cooldown_s=30,
    )
    fp.insert_target(
        conn, forum_fk=fid, name="Daily Thread", kind="thread",
        target_id="999",
    )
    tab_id = _make_tab(conn)
    fp.set_tab_posting_config(
        conn, tab_id=tab_id, forum_fk=fid, kind="reply",
        target_id="999", body_template_name="default",
        title_template_name=None, trigger_mode="auto_on_upload",
        update_mode="whole", manual_edit_handling="skip_alert",
        stale_triggers=["upload"], enabled=True,
    )
    panel = TabPostingConfigPanel(conn=conn, tab_id=tab_id)
    data = panel.target_combo.currentData()
    assert isinstance(data, dict)
    assert data["kind"] == "thread" and str(data["target_id"]) == "999"
    assert panel.template_combo.currentData() == "default"
    assert panel.trigger_combo.currentData() == "auto_on_upload"
    assert panel.enabled_check.isChecked()
    assert panel.st_upload.isChecked()


def test_panel_loads_unknown_target_as_orphan_entry(app, conn):
    """A saved target_id with no matching forum_targets row still shows up
    selected in the combo (marked 'unknown') so loading is non-destructive."""
    fid = fp.insert_forum(
        conn, name="VIP", software_id="vbulletin_4_2_0",
        base_url="https://x", default_cooldown_s=30,
    )
    tab_id = _make_tab(conn)
    fp.set_tab_posting_config(
        conn, tab_id=tab_id, forum_fk=fid, kind="reply",
        target_id="42", body_template_name="default",
        title_template_name=None, trigger_mode="manual",
        update_mode="whole", manual_edit_handling="skip_alert",
        stale_triggers=["upload"], enabled=True,
    )
    panel = TabPostingConfigPanel(conn=conn, tab_id=tab_id)
    data = panel.target_combo.currentData()
    assert isinstance(data, dict)
    assert str(data["target_id"]) == "42"


def test_panel_save_persists_and_derives_kind_from_target(app, conn):
    fid = fp.insert_forum(
        conn, name="VIP", software_id="vbulletin_4_2_0",
        base_url="https://x", default_cooldown_s=30,
    )
    fp.insert_target(
        conn, forum_fk=fid, name="Celebs", kind="subforum",
        target_id="12",
    )
    tab_id = _make_tab(conn)
    panel = TabPostingConfigPanel(conn=conn, tab_id=tab_id)
    _select_target(panel, "12", "subforum")
    _select_template(panel, "default")
    panel.st_template.setChecked(True)
    panel.enabled_check.setChecked(True)
    assert panel.save() is True
    cfg = fp.get_tab_posting_config(conn, tab_id)
    assert cfg["forum_fk"] == fid
    # subforum → new_thread
    assert cfg["kind"] == "new_thread"
    assert cfg["target_id"] == "12"
    assert cfg["body_template_name"] == "default"
    # Single-template model: title_template_name is intentionally None.
    assert cfg["title_template_name"] is None
    assert "template_edit" in cfg["stale_triggers"]
    assert cfg["enabled"] == 1


def test_panel_save_rejects_missing_target(app, conn):
    fp.insert_forum(
        conn, name="VIP", software_id="vbulletin_4_2_0",
        base_url="https://x", default_cooldown_s=30,
    )
    tab_id = _make_tab(conn)
    panel = TabPostingConfigPanel(conn=conn, tab_id=tab_id)
    _select_template(panel, "default")
    # No target selected (combo is sitting on "+ Add new…" sentinel) —
    # save should refuse and leave the row absent.
    assert panel.save() is False


def test_thread_target_maps_to_reply_kind(app, conn):
    fid = fp.insert_forum(
        conn, name="VIP", software_id="vbulletin_4_2_0",
        base_url="https://x", default_cooldown_s=30,
    )
    fp.insert_target(
        conn, forum_fk=fid, name="Daily", kind="thread",
        target_id="9001",
    )
    tab_id = _make_tab(conn)
    panel = TabPostingConfigPanel(conn=conn, tab_id=tab_id)
    _select_target(panel, "9001", "thread")
    _select_template(panel, "default")
    assert panel.save() is True
    cfg = fp.get_tab_posting_config(conn, tab_id)
    assert cfg["kind"] == "reply"
    assert cfg["target_id"] == "9001"
