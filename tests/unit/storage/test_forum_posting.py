"""Tests for forum_posting DAO + v15 schema migration.

Schema: v15 adds 4 tables (forums, tab_posting_config, gallery_posting_override,
forum_posts) backing the forum-posting subsystem (spec
docs/superpowers/specs/2026-04-20-forum-posting-design.md §2 / §14).
"""

from __future__ import annotations

import os
import sqlite3
import tempfile

import pytest

from src.storage import forum_posting as fp
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


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

def test_migration_creates_all_four_tables(conn):
    tables = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {"forums", "tab_posting_config",
            "gallery_posting_override", "forum_posts"}.issubset(tables)


def test_migration_creates_forum_posts_indexes(conn):
    indexes = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
    }
    assert "idx_forum_posts_gallery" in indexes
    assert "idx_forum_posts_forum_status" in indexes
    assert "idx_forum_posts_status_attempt" in indexes


def test_schema_version_advances_to_15(conn):
    row = conn.execute(
        "SELECT value_text FROM settings WHERE key='schema_version'"
    ).fetchone()
    assert int(row[0]) >= 15


def test_migration_is_idempotent(conn):
    """Running schema setup again must not raise."""
    _schema_initialized_dbs.clear()  # force second pass through _ensure_schema
    _ensure_schema(conn)
    tables = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert "forums" in tables  # no DROP/CREATE side-effects, table still there


# ---------------------------------------------------------------------------
# forums
# ---------------------------------------------------------------------------

def test_insert_and_fetch_forum(conn):
    fid = fp.insert_forum(conn, name="VIP", software_id="vbulletin_4_2_0",
                          base_url="https://vipergirls.to",
                          default_cooldown_s=30)
    row = fp.get_forum(conn, fid)
    assert row["name"] == "VIP"
    assert row["software_id"] == "vbulletin_4_2_0"
    assert row["base_url"] == "https://vipergirls.to"
    assert row["default_cooldown_s"] == 30
    assert row["enabled"] == 1


def test_list_forums_orders_by_name(conn):
    fp.insert_forum(conn, name="ZForum", software_id="vbulletin_4_2_0",
                    base_url="https://z", default_cooldown_s=30)
    fp.insert_forum(conn, name="AForum", software_id="vbulletin_4_2_0",
                    base_url="https://a", default_cooldown_s=30)
    names = [f["name"] for f in fp.list_forums(conn)]
    assert names == ["AForum", "ZForum"]


def test_list_forums_enabled_only_filters(conn):
    f1 = fp.insert_forum(conn, name="On", software_id="vbulletin_4_2_0",
                         base_url="https://x", default_cooldown_s=30)
    f2 = fp.insert_forum(conn, name="Off", software_id="vbulletin_4_2_0",
                         base_url="https://y", default_cooldown_s=30)
    fp.update_forum(conn, f2, enabled=0)
    enabled = fp.list_forums(conn, enabled_only=True)
    assert len(enabled) == 1
    assert enabled[0]["id"] == f1


def test_update_forum_rejects_unknown_field(conn):
    fid = fp.insert_forum(conn, name="VIP", software_id="vbulletin_4_2_0",
                          base_url="https://x", default_cooldown_s=30)
    with pytest.raises(ValueError):
        fp.update_forum(conn, fid, bogus="value")


def test_delete_forum_cascades_to_dependents(conn):
    fid = fp.insert_forum(conn, name="VIP", software_id="vbulletin_4_2_0",
                          base_url="https://x", default_cooldown_s=30)
    conn.execute("INSERT INTO galleries(path, status, added_ts) VALUES('/x','completed',0)")
    gid = conn.execute("SELECT id FROM galleries").fetchone()[0]
    fp.insert_forum_post(conn, gallery_fk=gid, forum_fk=fid, kind="reply",
                          target_id="111", body_hash="h", link_map={})
    fp.delete_forum(conn, fid)
    assert fp.get_forum(conn, fid) is None
    assert conn.execute(
        "SELECT COUNT(*) FROM forum_posts WHERE forum_fk=?", (fid,)
    ).fetchone()[0] == 0


# ---------------------------------------------------------------------------
# tab_posting_config
# ---------------------------------------------------------------------------

def _make_tab(conn, name="T"):
    conn.execute("INSERT INTO tabs(name, tab_type, display_order) VALUES(?,'user',0)",
                 (name,))
    return conn.execute(
        "SELECT id FROM tabs WHERE name=? ORDER BY id DESC LIMIT 1", (name,)
    ).fetchone()[0]


def test_set_tab_posting_config_inserts_then_upserts(conn):
    tab_id = _make_tab(conn)
    fid = fp.insert_forum(conn, name="VIP", software_id="vbulletin_4_2_0",
                          base_url="https://x", default_cooldown_s=30)
    fp.set_tab_posting_config(conn, tab_id=tab_id, forum_fk=fid, kind="reply",
                              target_id="123", body_template_name="Default",
                              title_template_name=None,
                              trigger_mode="auto_on_upload",
                              update_mode="whole",
                              manual_edit_handling="skip_alert",
                              stale_triggers=["upload"], enabled=True)
    cfg = fp.get_tab_posting_config(conn, tab_id)
    assert cfg["target_id"] == "123"
    assert cfg["enabled"] == 1
    assert cfg["stale_triggers"] == ["upload"]

    fp.set_tab_posting_config(conn, tab_id=tab_id, forum_fk=fid, kind="reply",
                              target_id="456", body_template_name="Default",
                              title_template_name=None, trigger_mode="manual",
                              update_mode="surgical",
                              manual_edit_handling="skip_alert",
                              stale_triggers=["upload", "template_edit"],
                              enabled=False)
    cfg = fp.get_tab_posting_config(conn, tab_id)
    assert cfg["target_id"] == "456"
    assert cfg["trigger_mode"] == "manual"
    assert cfg["enabled"] == 0
    assert set(cfg["stale_triggers"]) == {"upload", "template_edit"}


def test_get_tab_posting_config_returns_none_when_missing(conn):
    tab_id = _make_tab(conn)
    assert fp.get_tab_posting_config(conn, tab_id) is None


def test_delete_tab_posting_config_removes_row(conn):
    tab_id = _make_tab(conn)
    fid = fp.insert_forum(conn, name="VIP", software_id="vbulletin_4_2_0",
                          base_url="https://x", default_cooldown_s=30)
    fp.set_tab_posting_config(conn, tab_id=tab_id, forum_fk=fid, kind="reply",
                              target_id="1", body_template_name="t",
                              title_template_name=None, trigger_mode="manual",
                              update_mode="whole",
                              manual_edit_handling="skip_alert",
                              stale_triggers=[], enabled=True)
    fp.delete_tab_posting_config(conn, tab_id)
    assert fp.get_tab_posting_config(conn, tab_id) is None


def test_kind_check_constraint_rejects_invalid(conn):
    tab_id = _make_tab(conn)
    fid = fp.insert_forum(conn, name="VIP", software_id="vbulletin_4_2_0",
                          base_url="https://x", default_cooldown_s=30)
    with pytest.raises(sqlite3.IntegrityError):
        fp.set_tab_posting_config(conn, tab_id=tab_id, forum_fk=fid,
                                   kind="bogus", target_id="1",
                                   body_template_name="t",
                                   title_template_name=None,
                                   trigger_mode="manual", update_mode="whole",
                                   manual_edit_handling="skip_alert",
                                   stale_triggers=[], enabled=True)


# ---------------------------------------------------------------------------
# gallery_posting_override + effective config
# ---------------------------------------------------------------------------

def _setup_tab_with_config(conn):
    tab_id = _make_tab(conn)
    fid = fp.insert_forum(conn, name="VIP", software_id="vbulletin_4_2_0",
                          base_url="https://x", default_cooldown_s=30)
    fp.set_tab_posting_config(conn, tab_id=tab_id, forum_fk=fid, kind="reply",
                              target_id="111", body_template_name="Default",
                              title_template_name=None,
                              trigger_mode="auto_on_upload",
                              update_mode="whole",
                              manual_edit_handling="skip_alert",
                              stale_triggers=["upload"], enabled=True)
    conn.execute(
        "INSERT INTO galleries(path, status, added_ts, tab_id) "
        "VALUES('/tmp/x','completed',0,?)", (tab_id,)
    )
    gid = conn.execute("SELECT id FROM galleries").fetchone()[0]
    return tab_id, fid, gid


def test_effective_config_inherits_from_tab_when_no_override(conn):
    _, fid, gid = _setup_tab_with_config(conn)
    eff = fp.get_effective_posting_config(conn, gid)
    assert eff["forum_fk"] == fid
    assert eff["target_id"] == "111"
    assert eff["update_mode"] == "whole"


def test_effective_config_override_takes_precedence(conn):
    _, _, gid = _setup_tab_with_config(conn)
    fp.set_gallery_override(conn, gallery_fk=gid, target_id="222",
                             update_mode="surgical")
    eff = fp.get_effective_posting_config(conn, gid)
    assert eff["target_id"] == "222"          # from override
    assert eff["update_mode"] == "surgical"   # from override
    assert eff["body_template_name"] == "Default"  # inherited


def test_effective_config_clear_returns_to_tab(conn):
    _, _, gid = _setup_tab_with_config(conn)
    fp.set_gallery_override(conn, gallery_fk=gid, target_id="999")
    fp.clear_gallery_override(conn, gid)
    eff = fp.get_effective_posting_config(conn, gid)
    assert eff["target_id"] == "111"   # tab default


def test_effective_config_returns_none_when_no_tab_config(conn):
    tab_id = _make_tab(conn)
    conn.execute(
        "INSERT INTO galleries(path, status, added_ts, tab_id) "
        "VALUES('/y','completed',0,?)", (tab_id,)
    )
    gid = conn.execute(
        "SELECT id FROM galleries ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    assert fp.get_effective_posting_config(conn, gid) is None


def test_set_gallery_override_rejects_unknown_field(conn):
    _, _, gid = _setup_tab_with_config(conn)
    with pytest.raises(ValueError):
        fp.set_gallery_override(conn, gallery_fk=gid, bogus="x")


def test_set_gallery_override_serializes_stale_triggers(conn):
    _, _, gid = _setup_tab_with_config(conn)
    fp.set_gallery_override(conn, gallery_fk=gid,
                             stale_triggers=["template_edit"])
    eff = fp.get_effective_posting_config(conn, gid)
    assert eff["stale_triggers"] == ["template_edit"]


# ---------------------------------------------------------------------------
# forum_posts
# ---------------------------------------------------------------------------

def test_insert_forum_post_starts_queued_with_app_source(conn):
    _, fid, gid = _setup_tab_with_config(conn)
    pid = fp.insert_forum_post(conn, gallery_fk=gid, forum_fk=fid,
                                kind="reply", target_id="111",
                                body_hash="abc", link_map={"x": 1})
    row = fp.get_forum_post(conn, pid)
    assert row["status"] == "queued"
    assert row["source"] == "app"
    assert row["body_hash"] == "abc"


def test_insert_forum_post_supports_onboarded_source(conn):
    _, fid, gid = _setup_tab_with_config(conn)
    pid = fp.insert_forum_post(conn, gallery_fk=gid, forum_fk=fid,
                                kind="reply", target_id="111",
                                body_hash="", link_map={},
                                source="onboarded")
    assert fp.get_forum_post(conn, pid)["source"] == "onboarded"


def test_update_forum_post_sets_status_and_post_ids(conn):
    _, fid, gid = _setup_tab_with_config(conn)
    pid = fp.insert_forum_post(conn, gallery_fk=gid, forum_fk=fid,
                                kind="reply", target_id="111",
                                body_hash="h", link_map={})
    fp.update_forum_post(conn, pid, status="posted",
                          posted_post_id="999",
                          posted_thread_id="111",
                          posted_url="https://x/showthread.php?p=999")
    row = fp.get_forum_post(conn, pid)
    assert row["status"] == "posted"
    assert row["posted_post_id"] == "999"
    assert row["posted_url"] == "https://x/showthread.php?p=999"


def test_update_forum_post_rejects_unknown_field(conn):
    _, fid, gid = _setup_tab_with_config(conn)
    pid = fp.insert_forum_post(conn, gallery_fk=gid, forum_fk=fid,
                                kind="reply", target_id="1",
                                body_hash="h", link_map={})
    with pytest.raises(ValueError):
        fp.update_forum_post(conn, pid, bogus="x")


def test_list_forum_posts_for_gallery_orders_newest_first(conn):
    _, fid, gid = _setup_tab_with_config(conn)
    p1 = fp.insert_forum_post(conn, gallery_fk=gid, forum_fk=fid,
                                kind="reply", target_id="1",
                                body_hash="h", link_map={})
    p2 = fp.insert_forum_post(conn, gallery_fk=gid, forum_fk=fid,
                                kind="reply", target_id="2",
                                body_hash="h", link_map={})
    rows = fp.list_forum_posts_for_gallery(conn, gid)
    assert [r["id"] for r in rows][0] == p2  # newest first


def test_mark_posts_stale_for_gallery_only_marks_posted(conn):
    _, fid, gid = _setup_tab_with_config(conn)
    p_posted = fp.insert_forum_post(conn, gallery_fk=gid, forum_fk=fid,
                                      kind="reply", target_id="1",
                                      body_hash="h", link_map={})
    fp.update_forum_post(conn, p_posted, status="posted")
    p_failed = fp.insert_forum_post(conn, gallery_fk=gid, forum_fk=fid,
                                      kind="reply", target_id="2",
                                      body_hash="h", link_map={})
    fp.update_forum_post(conn, p_failed, status="failed")
    p_queued = fp.insert_forum_post(conn, gallery_fk=gid, forum_fk=fid,
                                      kind="reply", target_id="3",
                                      body_hash="h", link_map={})

    marked = fp.mark_posts_stale_for_gallery(conn, gid)
    assert marked == [p_posted]
    assert fp.get_forum_post(conn, p_posted)["status"] == "stale"
    assert fp.get_forum_post(conn, p_failed)["status"] == "failed"
    assert fp.get_forum_post(conn, p_queued)["status"] == "queued"


def test_mark_posts_stale_for_gallery_returns_empty_when_none_posted(conn):
    _, _, gid = _setup_tab_with_config(conn)
    assert fp.mark_posts_stale_for_gallery(conn, gid) == []


# ---------------------------------------------------------------------------
# forum_targets
# ---------------------------------------------------------------------------

def test_insert_target_and_list(conn):
    fid = fp.insert_forum(
        conn, name="VIP", software_id="vbulletin_4_2_0",
        base_url="https://x", default_cooldown_s=30,
    )
    t1 = fp.insert_target(
        conn, forum_fk=fid, name="Celebs", kind="subforum", target_id="12",
    )
    t2 = fp.insert_target(
        conn, forum_fk=fid, name="Daily", kind="thread", target_id="9001",
    )
    rows = fp.list_targets(conn, fid)
    assert {r["id"] for r in rows} == {t1, t2}
    # Ordered by kind, then name COLLATE NOCASE — subforum before thread.
    assert [r["kind"] for r in rows] == ["subforum", "thread"]


def test_insert_target_rejects_bad_kind(conn):
    fid = fp.insert_forum(
        conn, name="VIP", software_id="vbulletin_4_2_0", base_url="x",
    )
    with pytest.raises(ValueError):
        fp.insert_target(
            conn, forum_fk=fid, name="Bad", kind="forum", target_id="1",
        )


def test_insert_target_rejects_duplicate_kind_and_target_id(conn):
    fid = fp.insert_forum(
        conn, name="VIP", software_id="vbulletin_4_2_0", base_url="x",
    )
    fp.insert_target(
        conn, forum_fk=fid, name="Celebs", kind="subforum", target_id="12",
    )
    with pytest.raises(sqlite3.IntegrityError):
        fp.insert_target(
            conn, forum_fk=fid, name="Dupe", kind="subforum", target_id="12",
        )


def test_upsert_target_returns_existing_id_and_updates_name(conn):
    fid = fp.insert_forum(
        conn, name="VIP", software_id="vbulletin_4_2_0", base_url="x",
    )
    t1 = fp.upsert_target(
        conn, forum_fk=fid, name="Celebs", kind="subforum", target_id="12",
    )
    t2 = fp.upsert_target(
        conn, forum_fk=fid, name="Celeb Photos", kind="subforum",
        target_id="12",
    )
    assert t1 == t2
    row = fp.get_target(conn, t1)
    assert row["name"] == "Celeb Photos"


def test_update_target_changes_name(conn):
    fid = fp.insert_forum(
        conn, name="VIP", software_id="vbulletin_4_2_0", base_url="x",
    )
    t = fp.insert_target(
        conn, forum_fk=fid, name="Old", kind="thread", target_id="1",
    )
    fp.update_target(conn, t, name="New")
    assert fp.get_target(conn, t)["name"] == "New"


def test_update_target_rejects_unknown_field(conn):
    fid = fp.insert_forum(
        conn, name="VIP", software_id="vbulletin_4_2_0", base_url="x",
    )
    t = fp.insert_target(
        conn, forum_fk=fid, name="X", kind="thread", target_id="1",
    )
    with pytest.raises(ValueError):
        fp.update_target(conn, t, forum_fk=99)


def test_delete_target_removes_row(conn):
    fid = fp.insert_forum(
        conn, name="VIP", software_id="vbulletin_4_2_0", base_url="x",
    )
    t = fp.insert_target(
        conn, forum_fk=fid, name="X", kind="thread", target_id="1",
    )
    fp.delete_target(conn, t)
    assert fp.get_target(conn, t) is None


def test_delete_forum_cascades_to_targets(conn):
    fid = fp.insert_forum(
        conn, name="VIP", software_id="vbulletin_4_2_0", base_url="x",
    )
    fp.insert_target(
        conn, forum_fk=fid, name="X", kind="thread", target_id="1",
    )
    fp.delete_forum(conn, fid)
    assert fp.list_targets(conn, fid) == []
