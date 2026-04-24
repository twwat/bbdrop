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
        " VALUES(?,?,'99','reply')", (tab_id, forum_id)
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO tab_posting_destinations(tab_id,forum_fk,target_id,kind)"
            " VALUES(?,?,'99','reply')", (tab_id, forum_id)
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
