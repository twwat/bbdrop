import os
import sqlite3
import tempfile

import pytest
from PyQt6.QtWidgets import QApplication

from src.gui.dialogs.gallery_posting_override_dialog import (
    GalleryPostingOverrideDialog,
)
from src.gui.widgets.tab_posting_config_panel import TabPostingConfigPanel
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
    conn.execute(
        "INSERT INTO tabs(name, tab_type, display_order) "
        "VALUES('T','user',0)",
    )
    tab_id = conn.execute("SELECT id FROM tabs WHERE name='T'").fetchone()[0]
    fp.set_tab_posting_config(
        conn, tab_id=tab_id, forum_fk=fid, kind="reply",
        target_id="111", body_template_name="Default",
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


def test_override_dialog_constructs(app, conn):
    _, gid = _setup_tab_with_config(conn)
    dlg = GalleryPostingOverrideDialog(conn=conn, gallery_id=gid)
    assert dlg is not None
    assert dlg.panel._override_mode is True


def test_override_panel_has_inherit_sentinel(app, conn):
    _, gid = _setup_tab_with_config(conn)
    panel = TabPostingConfigPanel(conn=conn, gallery_id=gid)
    # Override-mode combos should have an "(Inherit)" sentinel at index 0.
    assert panel.kind_combo.itemData(0) is None
    assert panel.trigger_combo.itemData(0) is None
    assert panel.update_mode_combo.itemData(0) is None
    assert panel.manual_edit_combo.itemData(0) is None


def test_override_dialog_partial_save(app, conn):
    _, gid = _setup_tab_with_config(conn)
    dlg = GalleryPostingOverrideDialog(conn=conn, gallery_id=gid)
    dlg.panel.target_id_input.setText("999")
    assert dlg.panel.save() is True
    eff = fp.get_effective_posting_config(conn, gid)
    assert eff["target_id"] == "999"
    assert eff["update_mode"] == "whole"  # inherited


def test_override_dialog_clear_returns_to_inheritance(app, conn):
    _, gid = _setup_tab_with_config(conn)
    fp.set_gallery_override(conn, gallery_fk=gid, target_id="888")
    dlg = GalleryPostingOverrideDialog(conn=conn, gallery_id=gid)
    # Existing override loaded into the panel
    assert dlg.panel.target_id_input.text() == "888"
    dlg.panel.target_id_input.setText("")  # empty = inherit in override mode
    assert dlg.panel.save() is True
    eff = fp.get_effective_posting_config(conn, gid)
    assert eff["target_id"] == "111"


def test_override_dialog_save_then_load_roundtrip(app, conn):
    _, gid = _setup_tab_with_config(conn)
    panel = TabPostingConfigPanel(conn=conn, gallery_id=gid)
    panel.target_id_input.setText("555")
    panel.body_template_input.setText("OverrideTpl")
    idx = panel.update_mode_combo.findData("surgical")
    panel.update_mode_combo.setCurrentIndex(idx)
    assert panel.save() is True
    # Reopen — values should persist
    panel2 = TabPostingConfigPanel(conn=conn, gallery_id=gid)
    assert panel2.target_id_input.text() == "555"
    assert panel2.body_template_input.text() == "OverrideTpl"
    assert panel2.update_mode_combo.currentData() == "surgical"
