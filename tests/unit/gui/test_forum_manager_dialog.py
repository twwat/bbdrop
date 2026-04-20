import os
import sqlite3
import tempfile

import pytest
from PyQt6.QtWidgets import QApplication

from src.gui.dialogs.forum_manager_dialog import ForumManagerDialog
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


def test_dialog_constructs(app, conn):
    dlg = ForumManagerDialog(conn=conn)
    assert dlg is not None
    assert dlg.forum_list.count() == 0


def test_dialog_lists_existing_forums(app, conn):
    fp.insert_forum(
        conn, name="VIP", software_id="vbulletin_4_2_0",
        base_url="https://x", default_cooldown_s=30,
    )
    dlg = ForumManagerDialog(conn=conn)
    assert dlg.forum_list.count() == 1
    assert dlg.forum_list.item(0).text() == "VIP"


def test_save_via_helper_inserts_new(app, conn):
    dlg = ForumManagerDialog(conn=conn)
    fid = dlg._save_forum(
        name="Test", software_id="vbulletin_4_2_0",
        base_url="https://t", default_cooldown_s=15,
        username="", password="",
    )
    assert fid is not None
    row = fp.get_forum(conn, fid)
    assert row["name"] == "Test"
    assert row["default_cooldown_s"] == 15


def test_save_via_helper_rejects_missing_name(app, conn):
    dlg = ForumManagerDialog(conn=conn)
    fid = dlg._save_forum(
        name="", software_id="vbulletin_4_2_0",
        base_url="https://t", default_cooldown_s=15,
        username="", password="",
    )
    assert fid is None


def test_software_combo_populated(app, conn):
    dlg = ForumManagerDialog(conn=conn)
    items = [
        dlg.software_combo.itemData(i)
        for i in range(dlg.software_combo.count())
    ]
    assert "vbulletin_4_2_0" in items
