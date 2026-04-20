"""Unit tests for ForumController.onboard_post (P3 Task 1)."""

import os
import sqlite3
import tempfile
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QCoreApplication

from src.gui.forum_controller import ForumController
from src.processing.forum_posting_worker import FetchJob
from src.storage import forum_posting as fp
from src.storage.database import _ensure_schema, _schema_initialized_dbs


@pytest.fixture
def app():
    return QCoreApplication.instance() or QCoreApplication([])


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


def _setup(conn):
    fid = fp.insert_forum(
        conn, name="VIP", software_id="vbulletin_4_2_0",
        base_url="https://vipergirls.to", default_cooldown_s=0,
    )
    conn.execute(
        "INSERT INTO tabs(name, tab_type, display_order) "
        "VALUES('T','user',0)",
    )
    tab_id = conn.execute(
        "SELECT id FROM tabs WHERE name='T'"
    ).fetchone()[0]
    fp.set_tab_posting_config(
        conn, tab_id=tab_id, forum_fk=fid, kind="reply",
        target_id="111", body_template_name="Default",
        title_template_name=None, trigger_mode="manual",
        update_mode="whole", manual_edit_handling="skip_alert",
        stale_triggers=["upload"], enabled=True,
    )
    conn.execute(
        "INSERT INTO galleries(path, status, added_ts, tab_id) "
        "VALUES('/x','completed',0,?)", (tab_id,),
    )
    gid = conn.execute("SELECT id FROM galleries").fetchone()[0]
    return tab_id, fid, gid


def _make_controller(conn):
    return ForumController(
        conn=conn,
        worker=MagicMock(),
        template_renderer=lambda *a, **kw: ("", ""),
        credential_loader=lambda fid: ("", ""),
    )


def test_onboard_bare_id_uses_tab_forum(app, conn):
    _, fid, gid = _setup(conn)
    ctrl = _make_controller(conn)
    pid = ctrl.onboard_post(gid, "999999")
    assert ctrl._worker.enqueue.called
    job = ctrl._worker.enqueue.call_args[0][0]
    assert isinstance(job, FetchJob)
    assert job.post_id == "999999"
    assert job.forum_id == fid
    row = fp.get_forum_post(conn, pid)
    assert row["source"] == "onboarded"
    assert row["status"] == "queued"


def test_onboard_full_url_uses_matching_forum(app, conn):
    _, fid, gid = _setup(conn)
    fid2 = fp.insert_forum(
        conn, name="Other", software_id="vbulletin_4_2_0",
        base_url="https://other.example", default_cooldown_s=0,
    )
    ctrl = _make_controller(conn)
    ctrl.onboard_post(gid, "https://other.example/showthread.php?p=42")
    job = ctrl._worker.enqueue.call_args[0][0]
    assert job.forum_id == fid2
    assert job.post_id == "42"


def test_onboard_rejects_when_no_tab_config(app, conn):
    conn.execute(
        "INSERT INTO tabs(name, tab_type, display_order) "
        "VALUES('Empty','user',0)",
    )
    tab_id = conn.execute(
        "SELECT id FROM tabs ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO galleries(path, status, added_ts, tab_id) "
        "VALUES('/y','completed',0,?)", (tab_id,),
    )
    gid = conn.execute(
        "SELECT id FROM galleries ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    ctrl = _make_controller(conn)
    with pytest.raises(ValueError):
        ctrl.onboard_post(gid, "999")
    assert not ctrl._worker.enqueue.called


def test_onboard_rejects_full_url_with_unknown_host(app, conn):
    _, _, gid = _setup(conn)
    ctrl = _make_controller(conn)
    with pytest.raises(ValueError):
        ctrl.onboard_post(gid, "https://unknown.example/showthread.php?p=42")


def test_onboard_rejects_unparseable_text(app, conn):
    _, _, gid = _setup(conn)
    ctrl = _make_controller(conn)
    with pytest.raises(ValueError):
        ctrl.onboard_post(gid, "not a url or id")
