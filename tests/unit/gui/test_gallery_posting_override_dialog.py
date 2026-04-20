import os
import sqlite3
import tempfile

import pytest
from PyQt6.QtWidgets import QApplication

from src.gui.dialogs.gallery_posting_override_dialog import (
    GalleryPostingOverrideDialog,
)
from src.gui.widgets.tab_posting_config_panel import (
    TabPostingConfigPanel, _INHERIT,
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


def _setup_tab_with_config(conn) -> tuple[int, int]:
    fid = fp.insert_forum(
        conn, name="VIP", software_id="vbulletin_4_2_0",
        base_url="https://x", default_cooldown_s=30,
    )
    # Seed a couple of targets so the override panel has something to
    # pick from.
    fp.insert_target(
        conn, forum_fk=fid, name="Thread 111", kind="thread",
        target_id="111",
    )
    fp.insert_target(
        conn, forum_fk=fid, name="Thread 999", kind="thread",
        target_id="999",
    )
    conn.execute(
        "INSERT INTO tabs(name, tab_type, display_order) "
        "VALUES('T','user',0)",
    )
    tab_id = conn.execute("SELECT id FROM tabs WHERE name='T'").fetchone()[0]
    fp.set_tab_posting_config(
        conn, tab_id=tab_id, forum_fk=fid, kind="reply",
        target_id="111", body_template_name="default",
        title_template_name=None, trigger_mode="auto_on_upload",
        update_mode="whole", manual_edit_handling="skip_alert",
        stale_triggers=["upload"], enabled=True,
    )
    conn.execute(
        "INSERT INTO galleries(path, status, added_ts, tab_id) "
        "VALUES('/x','completed',0,?)",
        (tab_id,),
    )
    gid = conn.execute("SELECT id FROM galleries WHERE path='/x'").fetchone()[0]
    return tab_id, gid


def _select_target(panel, target_id: str, kind: str):
    for i in range(panel.target_combo.count()):
        data = panel.target_combo.itemData(i)
        if isinstance(data, dict) and data.get("kind") == kind \
                and str(data.get("target_id")) == str(target_id):
            panel.target_combo.setCurrentIndex(i)
            return
    raise AssertionError(
        f"Target ({kind}, {target_id}) not found in combo"
    )


def test_override_dialog_constructs(app, conn):
    _, gid = _setup_tab_with_config(conn)
    dlg = GalleryPostingOverrideDialog(conn=conn, gallery_id=gid)
    assert dlg is not None
    assert dlg.panel._override_mode is True


def test_override_panel_has_inherit_sentinel(app, conn):
    _, gid = _setup_tab_with_config(conn)
    panel = TabPostingConfigPanel(conn=conn, gallery_id=gid)
    # Override-mode combos should have an "(Inherit)" sentinel at
    # index 0. Forum combo, Target combo, and Template combo all use
    # _INHERIT as the sentinel data; the behaviour combos use None.
    assert panel.forum_combo.itemData(0) == _INHERIT
    assert panel.target_combo.itemData(0) == _INHERIT
    assert panel.template_combo.itemData(0) == _INHERIT
    assert panel.trigger_combo.itemData(0) is None
    assert panel.update_mode_combo.itemData(0) is None
    assert panel.manual_edit_combo.itemData(0) is None


def test_override_dialog_partial_save(app, conn):
    _, gid = _setup_tab_with_config(conn)
    dlg = GalleryPostingOverrideDialog(conn=conn, gallery_id=gid)
    # Override just the target: pick the other seeded thread. Forum +
    # template stay on "(Inherit)".
    # First we need to move forum off "(Inherit)" so targets load,
    # then remember to reset to "(Inherit)" before save.
    # Simpler: find the target directly by iterating current items.
    # The forum combo needs a real forum id selected to populate
    # targets — select it, pick target, then reset to inherit.
    idx_vip = dlg.panel.forum_combo.findText("VIP")
    dlg.panel.forum_combo.setCurrentIndex(idx_vip)
    _select_target(dlg.panel, "999", "thread")
    # Reset forum to "(Inherit)" so only target_id is overridden — but
    # override mode stores kind alongside target, so setting just
    # target also sets kind. That's fine; the test below asserts both
    # the override target and inherited update_mode.
    assert dlg.panel.save() is True
    eff = fp.get_effective_posting_config(conn, gid)
    assert eff["target_id"] == "999"
    assert eff["update_mode"] == "whole"  # inherited from tab


def test_override_dialog_clear_returns_to_inheritance(app, conn):
    _, gid = _setup_tab_with_config(conn)
    fp.set_gallery_override(
        conn, gallery_fk=gid, target_id="999", kind="reply",
    )
    dlg = GalleryPostingOverrideDialog(conn=conn, gallery_id=gid)
    # Existing override loaded into the panel
    data = dlg.panel.target_combo.currentData()
    assert isinstance(data, dict) and str(data["target_id"]) == "999"
    # Switch target combo back to "(Inherit)" and clear forum too.
    dlg.panel.forum_combo.setCurrentIndex(0)  # "(Inherit)"
    dlg.panel.target_combo.setCurrentIndex(0)
    assert dlg.panel.save() is True
    eff = fp.get_effective_posting_config(conn, gid)
    # With nothing overridden, the effective config falls back to the
    # tab row (target 111).
    assert eff["target_id"] == "111"


def test_override_dialog_save_then_load_roundtrip(app, conn):
    _, gid = _setup_tab_with_config(conn)
    panel = TabPostingConfigPanel(conn=conn, gallery_id=gid)
    # Pick a concrete forum + target + template, plus an update_mode.
    panel.forum_combo.setCurrentIndex(panel.forum_combo.findText("VIP"))
    _select_target(panel, "999", "thread")
    tidx = panel.template_combo.findData("default")
    panel.template_combo.setCurrentIndex(tidx)
    idx = panel.update_mode_combo.findData("surgical")
    panel.update_mode_combo.setCurrentIndex(idx)
    assert panel.save() is True
    panel2 = TabPostingConfigPanel(conn=conn, gallery_id=gid)
    data = panel2.target_combo.currentData()
    assert isinstance(data, dict) and str(data["target_id"]) == "999"
    assert panel2.template_combo.currentData() == "default"
    assert panel2.update_mode_combo.currentData() == "surgical"
