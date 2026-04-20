import os
import sqlite3
import tempfile
import time
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QCoreApplication

from src.gui.forum_controller import ForumController
from src.storage import forum_posting as fp
from src.storage.database import _ensure_schema, _schema_initialized_dbs
from src.utils.forum_signals import bbcode_regenerated_signal_hub


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


def _setup_tab_with_config(conn, *, trigger_mode="auto_on_upload",
                           stale_triggers=None):
    conn.execute(
        "INSERT INTO tabs(name, tab_type, display_order) "
        "VALUES('T','user',?)", (time.time_ns(),),
    )
    tab_id = conn.execute(
        "SELECT id FROM tabs WHERE name='T' ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    fid = fp.insert_forum(
        conn, name="VIP", software_id="vbulletin_4_2_0",
        base_url="https://x", default_cooldown_s=0,
    )
    fp.set_tab_posting_config(
        conn, tab_id=tab_id, forum_fk=fid, kind="reply",
        target_id="999", body_template_name="Default",
        title_template_name=None, trigger_mode=trigger_mode,
        update_mode="whole", manual_edit_handling="skip_alert",
        stale_triggers=stale_triggers or ["upload"], enabled=True,
    )
    conn.execute(
        "INSERT INTO galleries(path, status, added_ts, tab_id) "
        "VALUES('/x','completed',0,?)", (tab_id,),
    )
    gid = conn.execute(
        "SELECT id FROM galleries ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    return tab_id, fid, gid


def test_auto_post_enqueues_job_when_tab_configured_for_auto(app, conn):
    _, fid, gid = _setup_tab_with_config(conn)
    worker = MagicMock()
    template_renderer = MagicMock(return_value=("rendered body", ""))
    ctrl = ForumController(
        conn=conn, worker=worker, template_renderer=template_renderer,
    )
    ctrl.handle_gallery_uploaded(gid)
    assert worker.enqueue.called
    job = worker.enqueue.call_args[0][0]
    assert job.body == "rendered body"
    assert job.target_id == "999"
    assert job.forum_id == fid


def test_auto_post_skipped_when_trigger_is_manual(app, conn):
    _setup_tab_with_config(conn, trigger_mode="manual")
    gid = conn.execute("SELECT id FROM galleries").fetchone()[0]
    worker = MagicMock()
    ctrl = ForumController(
        conn=conn, worker=worker,
        template_renderer=lambda *a, **kw: ("", ""),
    )
    ctrl.handle_gallery_uploaded(gid)
    assert not worker.enqueue.called


def test_auto_post_skipped_when_disabled(app, conn):
    tab_id, fid, gid = _setup_tab_with_config(conn)
    fp.set_tab_posting_config(
        conn, tab_id=tab_id, forum_fk=fid, kind="reply",
        target_id="999", body_template_name="Default",
        title_template_name=None, trigger_mode="auto_on_upload",
        update_mode="whole", manual_edit_handling="skip_alert",
        stale_triggers=["upload"], enabled=False,
    )
    worker = MagicMock()
    ctrl = ForumController(
        conn=conn, worker=worker,
        template_renderer=lambda *a, **kw: ("b", ""),
    )
    ctrl.handle_gallery_uploaded(gid)
    assert not worker.enqueue.called


def test_auto_post_skipped_if_already_posted(app, conn):
    _, fid, gid = _setup_tab_with_config(conn)
    pid = fp.insert_forum_post(
        conn, gallery_fk=gid, forum_fk=fid, kind="reply",
        target_id="999", body_hash="h", link_map={},
    )
    fp.update_forum_post(conn, pid, status="posted", posted_post_id="1")
    worker = MagicMock()
    ctrl = ForumController(
        conn=conn, worker=worker,
        template_renderer=lambda *a, **kw: ("b", ""),
    )
    ctrl.handle_gallery_uploaded(gid)
    assert not worker.enqueue.called


def test_post_now_enqueues_regardless_of_trigger_mode(app, conn):
    _setup_tab_with_config(conn, trigger_mode="manual")
    gid = conn.execute("SELECT id FROM galleries").fetchone()[0]
    worker = MagicMock()
    ctrl = ForumController(
        conn=conn, worker=worker,
        template_renderer=lambda *a, **kw: ("body", ""),
    )
    pid = ctrl.post_now(gid)
    assert worker.enqueue.called
    assert fp.get_forum_post(conn, pid)["status"] == "queued"


def test_bbcode_regenerated_marks_posts_stale(app, conn):
    _, fid, gid = _setup_tab_with_config(
        conn, stale_triggers=["upload", "template_edit"],
    )
    pid = fp.insert_forum_post(
        conn, gallery_fk=gid, forum_fk=fid, kind="reply",
        target_id="999", body_hash="h", link_map={},
    )
    fp.update_forum_post(conn, pid, status="posted", posted_post_id="555")
    worker = MagicMock()
    ctrl = ForumController(
        conn=conn, worker=worker,
        template_renderer=lambda *a, **kw: ("", ""),
    )
    bbcode_regenerated_signal_hub.bbcode_regenerated.emit(gid, "template_edit")
    app.processEvents()
    assert fp.get_forum_post(conn, pid)["status"] == "stale"


def test_bbcode_regenerated_ignores_unrelated_cause(app, conn):
    _, fid, gid = _setup_tab_with_config(conn, stale_triggers=["upload"])
    pid = fp.insert_forum_post(
        conn, gallery_fk=gid, forum_fk=fid, kind="reply",
        target_id="999", body_hash="h", link_map={},
    )
    fp.update_forum_post(conn, pid, status="posted")
    worker = MagicMock()
    ctrl = ForumController(
        conn=conn, worker=worker,
        template_renderer=lambda *a, **kw: ("", ""),
    )
    bbcode_regenerated_signal_hub.bbcode_regenerated.emit(gid, "template_edit")
    app.processEvents()
    assert fp.get_forum_post(conn, pid)["status"] == "posted"


def test_post_result_payload_persists_to_db(app, conn):
    _, fid, gid = _setup_tab_with_config(conn)
    pid = fp.insert_forum_post(
        conn, gallery_fk=gid, forum_fk=fid, kind="reply",
        target_id="999", body_hash="h", link_map={},
    )
    worker = MagicMock()
    ctrl = ForumController(
        conn=conn, worker=worker,
        template_renderer=lambda *a, **kw: ("", ""),
    )
    ctrl._on_post_result_payload(pid, {
        "posted_post_id": "777",
        "posted_thread_id": "999",
        "posted_url": "https://x/showthread.php?p=777",
    })
    row = fp.get_forum_post(conn, pid)
    assert row["status"] == "posted"
    assert row["posted_post_id"] == "777"
    assert row["posted_url"] == "https://x/showthread.php?p=777"


def test_post_completed_failure_marks_failed(app, conn):
    _, fid, gid = _setup_tab_with_config(conn)
    pid = fp.insert_forum_post(
        conn, gallery_fk=gid, forum_fk=fid, kind="reply",
        target_id="999", body_hash="h", link_map={},
    )
    worker = MagicMock()
    ctrl = ForumController(
        conn=conn, worker=worker,
        template_renderer=lambda *a, **kw: ("", ""),
    )
    ctrl._on_post_completed(pid, False, "NETWORK:boom")
    row = fp.get_forum_post(conn, pid)
    assert row["status"] == "failed"
    assert row["last_error"] == "NETWORK:boom"
