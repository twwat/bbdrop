"""Tests for v17 schema migration — multi-destination forum posting tables."""
from __future__ import annotations

import os
import sqlite3
import tempfile

import pytest

from src.storage.database import _ensure_schema, _schema_initialized_dbs


@pytest.fixture
def conn():
    """Real-file sqlite DB so the schema-cache early-return doesn't bite us."""
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


@pytest.mark.unit
def test_migration_creates_tab_posting_destinations(conn):
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert "tab_posting_destinations" in tables
    assert "tab_posting_settings" in tables
    assert "gallery_posting_destinations" in tables


def _make_tab(conn, name="T"):
    """Helper to create a tab and return its ID."""
    conn.execute("INSERT INTO tabs(name, tab_type, display_order) VALUES(?,'user',0)",
                 (name,))
    return conn.execute(
        "SELECT id FROM tabs WHERE name=? ORDER BY id DESC LIMIT 1", (name,)
    ).fetchone()[0]


def _make_forum(conn, name="F"):
    """Helper to create a forum and return its ID."""
    conn.execute(
        "INSERT INTO forums(name, software_id, base_url) VALUES(?, ?, ?)",
        (name, "vbulletin_4_2_0", "http://f.com")
    )
    return conn.execute(
        "SELECT id FROM forums WHERE name=? ORDER BY id DESC LIMIT 1", (name,)
    ).fetchone()[0]


@pytest.mark.unit
def test_tab_posting_destinations_unique_constraint(conn):
    tab_id = _make_tab(conn, "Tab1")
    forum_id = _make_forum(conn)
    conn.execute(
        "INSERT INTO tab_posting_destinations(tab_id,forum_fk,target_id,kind)"
        " VALUES(?,?,'99','thread')", (tab_id, forum_id)
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO tab_posting_destinations(tab_id,forum_fk,target_id,kind)"
            " VALUES(?,?,'99','thread')", (tab_id, forum_id)
        )
        conn.commit()


@pytest.mark.unit
def test_gallery_posting_destinations_action_constraint(conn):
    tab_id = _make_tab(conn, "Tab2")
    forum_id = _make_forum(conn, "Forum2")
    conn.execute(
        "INSERT INTO galleries(path, tab_id, status, added_ts)"
        " VALUES(?, ?, ?, ?)",
        ("/g", tab_id, "completed", 0)
    )
    gallery_id = conn.execute(
        "SELECT id FROM galleries WHERE path=?", ("/g",)
    ).fetchone()[0]
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO gallery_posting_destinations"
            "(gallery_fk,forum_fk,target_id,kind,action)"
            " VALUES(?,?,'10','reply','invalid_action')",
            (gallery_id, forum_id)
        )
        conn.commit()


@pytest.mark.unit
def test_gallery_posting_destinations_kind_constraint(conn):
    tab_id = _make_tab(conn, "Tab3")
    forum_id = _make_forum(conn, "Forum3")
    conn.execute(
        "INSERT INTO galleries(path, tab_id, status, added_ts)"
        " VALUES(?, ?, ?, ?)",
        ("/g", tab_id, "completed", 0)
    )
    gallery_id = conn.execute(
        "SELECT id FROM galleries WHERE path=?", ("/g",)
    ).fetchone()[0]
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO gallery_posting_destinations"
            "(gallery_fk,forum_fk,target_id,kind,action)"
            " VALUES(?,?,'10','invalid_kind','add')",
            (gallery_id, forum_id)
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Task 2: CRUD tests for v2 multi-destination model
# ---------------------------------------------------------------------------

import src.storage.forum_posting as fp


def _seed(conn):
    """Insert minimal tab + forum + gallery rows for CRUD tests."""
    conn.execute("INSERT INTO tabs(id,name,tab_type) VALUES(2,'T2','user')")
    conn.execute(
        "INSERT INTO forums(id,name,software_id,base_url)"
        " VALUES(2,'Forum2','vb','http://b.com')"
    )
    conn.execute(
        "INSERT INTO forum_targets(forum_fk,name,kind,target_id)"
        " VALUES(2,'Thread1','thread','42')"
    )
    conn.execute(
        "INSERT INTO galleries(id,path,tab_id,status,added_ts)"
        " VALUES(2,'/gal',2,'completed',0)"
    )
    conn.commit()


@pytest.mark.unit
def test_add_and_list_tab_destinations(conn):
    _seed(conn)
    pk = fp.add_tab_destination(conn, tab_id=2, forum_fk=2,
                                target_id="42", kind="thread",
                                body_template_name="default")
    assert isinstance(pk, int) and pk > 0
    dests = fp.list_tab_destinations(conn, tab_id=2)
    assert len(dests) == 1
    assert dests[0]["target_id"] == "42"
    assert dests[0]["kind"] == "thread"


@pytest.mark.unit
def test_remove_tab_destination(conn):
    _seed(conn)
    pk = fp.add_tab_destination(conn, tab_id=2, forum_fk=2,
                                target_id="42", kind="thread",
                                body_template_name="default")
    fp.remove_tab_destination(conn, pk)
    assert fp.list_tab_destinations(conn, tab_id=2) == []


@pytest.mark.unit
def test_clear_tab_destinations(conn):
    _seed(conn)
    fp.add_tab_destination(conn, tab_id=2, forum_fk=2,
                           target_id="42", kind="thread")
    fp.clear_tab_destinations(conn, tab_id=2)
    assert fp.list_tab_destinations(conn, tab_id=2) == []


@pytest.mark.unit
def test_tab_posting_settings_roundtrip(conn):
    _seed(conn)
    fp.set_tab_posting_settings(conn, tab_id=2,
                                trigger_mode="auto_on_upload", enabled=True)
    s = fp.get_tab_posting_settings_for_tab(conn, tab_id=2)
    assert s is not None
    assert s["trigger_mode"] == "auto_on_upload"
    assert s["enabled"] == 1


@pytest.mark.unit
def test_tab_posting_settings_defaults_to_none_when_unset(conn):
    _seed(conn)
    assert fp.get_tab_posting_settings_for_tab(conn, tab_id=2) is None


@pytest.mark.unit
def test_get_effective_destinations_tab_only(conn):
    _seed(conn)
    fp.add_tab_destination(conn, tab_id=2, forum_fk=2,
                           target_id="42", kind="thread",
                           body_template_name="default")
    dests = fp.get_effective_destinations(conn, gallery_fk=2)
    assert len(dests) == 1
    assert dests[0]["target_id"] == "42"


@pytest.mark.unit
def test_get_effective_destinations_no_config_returns_empty(conn):
    _seed(conn)
    assert fp.get_effective_destinations(conn, gallery_fk=2) == []


@pytest.mark.unit
def test_get_effective_destinations_add_override(conn):
    _seed(conn)
    conn.execute(
        "INSERT INTO forum_targets(forum_fk,name,kind,target_id)"
        " VALUES(2,'Sub1','subforum','99')"
    )
    conn.commit()
    fp.add_tab_destination(conn, tab_id=2, forum_fk=2,
                           target_id="42", kind="thread",
                           body_template_name="default")
    fp.upsert_gallery_destination(conn, gallery_fk=2, forum_fk=2,
                                  target_id="99", kind="subforum",
                                  body_template_name="default", action="add")
    dests = fp.get_effective_destinations(conn, gallery_fk=2)
    assert len(dests) == 2
    assert {d["target_id"] for d in dests} == {"42", "99"}


@pytest.mark.unit
def test_get_effective_destinations_remove_override(conn):
    _seed(conn)
    fp.add_tab_destination(conn, tab_id=2, forum_fk=2,
                           target_id="42", kind="thread",
                           body_template_name="default")
    fp.upsert_gallery_destination(conn, gallery_fk=2, forum_fk=2,
                                  target_id="42", kind="thread",
                                  body_template_name="default", action="remove")
    assert fp.get_effective_destinations(conn, gallery_fk=2) == []


@pytest.mark.unit
def test_get_tab_posting_settings_for_gallery(conn):
    _seed(conn)
    fp.set_tab_posting_settings(conn, tab_id=2,
                                trigger_mode="auto_on_upload", enabled=True)
    s = fp.get_tab_posting_settings_for_gallery(conn, gallery_fk=2)
    assert s is not None
    assert s["trigger_mode"] == "auto_on_upload"
