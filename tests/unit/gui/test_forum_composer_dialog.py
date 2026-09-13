import os
import sqlite3
import tempfile
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication

from src.gui.dialogs.forum_composer_dialog import ForumComposerDialog
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


def _setup(conn) -> list[int]:
    fid = fp.insert_forum(
        conn, name="VIP", software_id="vbulletin_4_2_0",
        base_url="https://x", default_cooldown_s=0,
    )
    conn.execute(
        "INSERT INTO tabs(name, tab_type, display_order) "
        "VALUES('T','user',0)",
    )
    tab_id = conn.execute("SELECT id FROM tabs WHERE name='T'").fetchone()[0]
    # Use v2 multi-destination API (tab_posting_destinations table). kind is
    # forum_targets/destination vocabulary ("subforum"/"thread"); "reply"
    # (legacy tab_posting_config vocabulary) maps to "thread".
    fp.add_tab_destination(
        conn, tab_id=tab_id, forum_fk=fid, kind="thread",
        target_id="111", body_template_name="Default",
    )
    conn.execute(
        "INSERT INTO galleries(path, status, added_ts, tab_id) "
        "VALUES('/a','completed',0,?)",
        (tab_id,),
    )
    conn.execute(
        "INSERT INTO galleries(path, status, added_ts, tab_id) "
        "VALUES('/b','completed',0,?)",
        (tab_id,),
    )
    rows = conn.execute("SELECT id FROM galleries ORDER BY id").fetchall()
    return [r[0] for r in rows]


def _make_controller():
    controller = MagicMock()
    controller.post_now = MagicMock(return_value=999)
    return controller


def test_composer_lists_one_row_per_gallery(app, conn):
    gids = _setup(conn)
    controller = _make_controller()
    dlg = ForumComposerDialog(
        conn=conn, controller=controller, gallery_ids=gids,
    )
    assert dlg.row_count() == 2
    # Both rows have effective destinations so neither warns
    assert dlg.has_warning(0) is False
    assert dlg.has_warning(1) is False


def test_composer_post_enqueues_for_each_unskipped_row(app, conn):
    gids = _setup(conn)
    controller = _make_controller()
    dlg = ForumComposerDialog(
        conn=conn, controller=controller, gallery_ids=gids,
    )
    dlg.set_skipped(0, True)
    dlg.post_all()
    assert controller.post_now.call_count == 1  # only the unskipped row
    args, _ = controller.post_now.call_args
    assert args[0] == gids[1]


def test_composer_handles_gallery_with_no_config(app, conn):
    gids = _setup(conn)
    # Add a gallery in another tab that has no posting config
    conn.execute(
        "INSERT INTO tabs(name, tab_type, display_order) "
        "VALUES('Other','user',1)",
    )
    other_tab = conn.execute(
        "SELECT id FROM tabs WHERE name='Other'",
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO galleries(path, status, added_ts, tab_id) "
        "VALUES('/c','completed',0,?)",
        (other_tab,),
    )
    new_gid = conn.execute(
        "SELECT id FROM galleries WHERE path='/c'",
    ).fetchone()[0]
    controller = _make_controller()
    dlg = ForumComposerDialog(
        conn=conn, controller=controller,
        gallery_ids=[*gids, new_gid],
    )
    assert dlg.row_count() == 3
    assert dlg.has_warning(2) is True


def test_composer_passes_body_override_when_edited(app, conn):
    gids = _setup(conn)
    controller = _make_controller()
    dlg = ForumComposerDialog(
        conn=conn, controller=controller, gallery_ids=[gids[0]],
    )
    dlg._rows[0].body_edit.setPlainText("EDITED BODY")
    dlg.post_all()
    args, _ = controller.post_now.call_args
    dests = args[1]
    assert len(dests) > 0
    assert dests[0].get("_body_override") == "EDITED BODY"


def test_composer_skips_warning_rows_on_post(app, conn):
    gids = _setup(conn)
    conn.execute(
        "INSERT INTO tabs(name, tab_type, display_order) "
        "VALUES('Other','user',1)",
    )
    other_tab = conn.execute(
        "SELECT id FROM tabs WHERE name='Other'",
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO galleries(path, status, added_ts, tab_id) "
        "VALUES('/c','completed',0,?)",
        (other_tab,),
    )
    new_gid = conn.execute(
        "SELECT id FROM galleries WHERE path='/c'",
    ).fetchone()[0]
    controller = _make_controller()
    dlg = ForumComposerDialog(
        conn=conn, controller=controller,
        gallery_ids=[*gids, new_gid],
    )
    dlg.post_all()
    # Only the two configured galleries should be posted; the third has no destinations.
    assert controller.post_now.call_count == 2
