import os
import sqlite3
import tempfile

import pytest
from PyQt6.QtWidgets import QApplication

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


def _make_tab(conn) -> int:
    conn.execute(
        "INSERT INTO tabs(name, tab_type, display_order) "
        "VALUES('T','user',0)",
    )
    return conn.execute("SELECT id FROM tabs WHERE name='T'").fetchone()[0]


def test_panel_constructs(app, conn):
    fp.insert_forum(
        conn, name="VIP", software_id="vbulletin_4_2_0",
        base_url="https://x", default_cooldown_s=30,
    )
    tab_id = _make_tab(conn)
    panel = TabPostingConfigPanel(conn=conn, tab_id=tab_id)
    assert panel.forum_combo.count() == 1


def test_panel_loads_existing_config(app, conn):
    fid = fp.insert_forum(
        conn, name="VIP", software_id="vbulletin_4_2_0",
        base_url="https://x", default_cooldown_s=30,
    )
    tab_id = _make_tab(conn)
    fp.set_tab_posting_config(
        conn, tab_id=tab_id, forum_fk=fid, kind="reply",
        target_id="999", body_template_name="Default",
        title_template_name=None, trigger_mode="auto_on_upload",
        update_mode="whole", manual_edit_handling="skip_alert",
        stale_triggers=["upload"], enabled=True,
    )
    panel = TabPostingConfigPanel(conn=conn, tab_id=tab_id)
    assert panel.target_id_input.text() == "999"
    assert panel.trigger_combo.currentData() == "auto_on_upload"
    assert panel.enabled_check.isChecked()
    assert panel.st_upload.isChecked()


def test_panel_save_persists(app, conn):
    fp.insert_forum(
        conn, name="VIP", software_id="vbulletin_4_2_0",
        base_url="https://x", default_cooldown_s=30,
    )
    tab_id = _make_tab(conn)
    panel = TabPostingConfigPanel(conn=conn, tab_id=tab_id)
    panel.target_id_input.setText("777")
    panel.body_template_input.setText("MyTpl")
    panel.st_template.setChecked(True)
    panel.enabled_check.setChecked(True)
    assert panel.save() is True
    cfg = fp.get_tab_posting_config(conn, tab_id)
    assert cfg["target_id"] == "777"
    assert cfg["body_template_name"] == "MyTpl"
    assert "template_edit" in cfg["stale_triggers"]
    assert cfg["enabled"] == 1


def test_panel_save_rejects_empty_target(app, conn, monkeypatch):
    fp.insert_forum(
        conn, name="VIP", software_id="vbulletin_4_2_0",
        base_url="https://x", default_cooldown_s=30,
    )
    tab_id = _make_tab(conn)
    panel = TabPostingConfigPanel(conn=conn, tab_id=tab_id)
    panel.target_id_input.setText("")
    panel.body_template_input.setText("MyTpl")
    assert panel.save() is False


def test_panel_kind_visibility_toggles_label(app, conn):
    fp.insert_forum(
        conn, name="VIP", software_id="vbulletin_4_2_0",
        base_url="https://x", default_cooldown_s=30,
    )
    tab_id = _make_tab(conn)
    panel = TabPostingConfigPanel(conn=conn, tab_id=tab_id)
    panel.kind_combo.setCurrentIndex(
        panel.kind_combo.findData("new_thread"),
    )
    assert "Forum" in panel.target_label.text()
    panel.kind_combo.setCurrentIndex(
        panel.kind_combo.findData("reply"),
    )
    assert "Thread" in panel.target_label.text()
