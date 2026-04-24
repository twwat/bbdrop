"""DAO for forum-posting tables.

Schema lives in `database.py` (migration v15). All functions take an open
sqlite3 connection and use parameterized queries; caller manages transactions
beyond the per-function commit done here.

Spec: docs/superpowers/specs/2026-04-20-forum-posting-design.md §2 / §14.
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional


# Fields that exist on tab_posting_config and may be overridden per-gallery.
# Kept in sync with the schema.
_TAB_CFG_FIELDS = (
    "forum_fk", "kind", "target_id", "body_template_name",
    "title_template_name", "trigger_mode", "update_mode",
    "manual_edit_handling", "stale_triggers_json", "enabled",
)


# ---------------------------------------------------------------------------
# forums
# ---------------------------------------------------------------------------

def insert_forum(conn, *, name: str, software_id: str, base_url: str,
                 default_cooldown_s: int = 30) -> int:
    cur = conn.execute(
        "INSERT INTO forums(name, software_id, base_url, default_cooldown_s) "
        "VALUES (?,?,?,?)",
        (name, software_id, base_url, default_cooldown_s),
    )
    conn.commit()
    return cur.lastrowid


def update_forum(conn, forum_id: int, **fields: Any) -> None:
    if not fields:
        return
    allowed = {"name", "software_id", "base_url", "default_cooldown_s", "enabled"}
    bad = set(fields) - allowed
    if bad:
        raise ValueError(f"Unknown forum field(s): {sorted(bad)}")
    fields["updated_ts"] = int(time.time())
    cols = ", ".join(f"{k}=?" for k in fields)
    conn.execute(
        f"UPDATE forums SET {cols} WHERE id=?",
        (*fields.values(), forum_id),
    )
    conn.commit()


def delete_forum(conn, forum_id: int) -> None:
    conn.execute("DELETE FROM forums WHERE id=?", (forum_id,))
    conn.commit()


def get_forum(conn, forum_id: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM forums WHERE id=?", (forum_id,)
    ).fetchone()
    return dict(row) if row else None


def list_forums(conn, *, enabled_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM forums"
    if enabled_only:
        sql += " WHERE enabled=1"
    sql += " ORDER BY name"
    return [dict(r) for r in conn.execute(sql)]


# ---------------------------------------------------------------------------
# forum_targets
# ---------------------------------------------------------------------------

_TARGET_KINDS = ("subforum", "thread")


def insert_target(
    conn, *, forum_fk: int, name: str, kind: str, target_id: str,
) -> int:
    """Insert a new forum target. Raises sqlite3.IntegrityError on duplicate
    (forum_fk, kind, target_id). Callers that want upsert-on-duplicate
    behaviour should use ``upsert_target``."""
    if kind not in _TARGET_KINDS:
        raise ValueError(f"Invalid target kind: {kind!r}")
    cur = conn.execute(
        "INSERT INTO forum_targets(forum_fk, name, kind, target_id) "
        "VALUES (?,?,?,?)",
        (forum_fk, name, kind, str(target_id)),
    )
    conn.commit()
    return cur.lastrowid


def upsert_target(
    conn, *, forum_fk: int, name: str, kind: str, target_id: str,
) -> int:
    """Insert-or-touch a target. If the (forum, kind, target_id) tuple
    already exists, updates its name + updated_ts and returns the existing
    row id. Otherwise inserts a new row and returns its id."""
    if kind not in _TARGET_KINDS:
        raise ValueError(f"Invalid target kind: {kind!r}")
    row = conn.execute(
        "SELECT id FROM forum_targets "
        "WHERE forum_fk=? AND kind=? AND target_id=?",
        (forum_fk, kind, str(target_id)),
    ).fetchone()
    if row:
        target_pk = row[0]
        conn.execute(
            "UPDATE forum_targets SET name=?, updated_ts=? WHERE id=?",
            (name, int(time.time()), target_pk),
        )
        conn.commit()
        return target_pk
    return insert_target(
        conn, forum_fk=forum_fk, name=name, kind=kind, target_id=target_id,
    )


def update_target(conn, target_pk: int, **fields: Any) -> None:
    if not fields:
        return
    allowed = {"name", "kind", "target_id"}
    bad = set(fields) - allowed
    if bad:
        raise ValueError(f"Unknown target field(s): {sorted(bad)}")
    if "kind" in fields and fields["kind"] not in _TARGET_KINDS:
        raise ValueError(f"Invalid target kind: {fields['kind']!r}")
    if "target_id" in fields:
        fields["target_id"] = str(fields["target_id"])
    fields["updated_ts"] = int(time.time())
    cols = ", ".join(f"{k}=?" for k in fields)
    conn.execute(
        f"UPDATE forum_targets SET {cols} WHERE id=?",
        (*fields.values(), target_pk),
    )
    conn.commit()


def delete_target(conn, target_pk: int) -> None:
    conn.execute("DELETE FROM forum_targets WHERE id=?", (target_pk,))
    conn.commit()


def get_target(conn, target_pk: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM forum_targets WHERE id=?", (target_pk,),
    ).fetchone()
    return dict(row) if row else None


def list_targets(conn, forum_fk: int) -> list[dict]:
    return [
        dict(r) for r in conn.execute(
            "SELECT * FROM forum_targets WHERE forum_fk=? "
            "ORDER BY kind, name COLLATE NOCASE",
            (forum_fk,),
        )
    ]


# ---------------------------------------------------------------------------
# tab_posting_destinations  (v2 multi-destination model)
# ---------------------------------------------------------------------------


def add_tab_destination(
    conn, *,
    tab_id: int,
    forum_fk: int,
    target_id: str,
    kind: str,
    body_template_name: Optional[str] = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO tab_posting_destinations
            (tab_id, forum_fk, target_id, kind, body_template_name)
        VALUES (?,?,?,?,?)
        """,
        (tab_id, forum_fk, str(target_id), kind, body_template_name),
    )
    conn.commit()
    return cur.lastrowid


def remove_tab_destination(conn, destination_id: int) -> None:
    conn.execute(
        "DELETE FROM tab_posting_destinations WHERE id=?", (destination_id,)
    )
    conn.commit()


def list_tab_destinations(conn, tab_id: int) -> list[dict]:
    return [
        dict(r) for r in conn.execute(
            "SELECT d.*, f.name AS forum_name, t.name AS target_name "
            "FROM tab_posting_destinations d "
            "JOIN forums f ON f.id = d.forum_fk "
            "LEFT JOIN forum_targets t "
            "  ON t.forum_fk = d.forum_fk AND t.target_id = d.target_id "
            "WHERE d.tab_id=? ORDER BY d.id",
            (tab_id,),
        )
    ]


def clear_tab_destinations(conn, tab_id: int) -> None:
    conn.execute(
        "DELETE FROM tab_posting_destinations WHERE tab_id=?", (tab_id,)
    )
    conn.commit()


# ---------------------------------------------------------------------------
# tab_posting_settings  (v2 behavioral: trigger_mode, enabled)
# ---------------------------------------------------------------------------


def get_tab_posting_settings_for_tab(conn, tab_id: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM tab_posting_settings WHERE tab_id=?", (tab_id,)
    ).fetchone()
    return dict(row) if row else None


def get_tab_posting_settings_for_gallery(conn, gallery_fk: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT s.* FROM tab_posting_settings s "
        "JOIN galleries g ON g.tab_id = s.tab_id "
        "WHERE g.id=?",
        (gallery_fk,),
    ).fetchone()
    return dict(row) if row else None


def set_tab_posting_settings(
    conn, *,
    tab_id: int,
    trigger_mode: str = "manual",
    enabled: bool = True,
) -> None:
    conn.execute(
        """
        INSERT INTO tab_posting_settings(tab_id, trigger_mode, enabled, updated_ts)
        VALUES (?,?,?,?)
        ON CONFLICT(tab_id) DO UPDATE SET
            trigger_mode=excluded.trigger_mode,
            enabled=excluded.enabled,
            updated_ts=excluded.updated_ts
        """,
        (tab_id, trigger_mode, 1 if enabled else 0, int(time.time())),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# gallery_posting_destinations  (v2 per-gallery overrides)
# ---------------------------------------------------------------------------


def upsert_gallery_destination(
    conn, *,
    gallery_fk: int,
    forum_fk: int,
    target_id: str,
    kind: str,
    body_template_name: Optional[str] = None,
    action: str = "add",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO gallery_posting_destinations
            (gallery_fk, forum_fk, target_id, kind, body_template_name, action, updated_ts)
        VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(gallery_fk, forum_fk, target_id) DO UPDATE SET
            kind=excluded.kind,
            body_template_name=excluded.body_template_name,
            action=excluded.action,
            updated_ts=excluded.updated_ts
        """,
        (gallery_fk, forum_fk, str(target_id), kind,
         body_template_name, action, int(time.time())),
    )
    conn.commit()
    return cur.lastrowid


def remove_gallery_destination(conn, destination_id: int) -> None:
    conn.execute(
        "DELETE FROM gallery_posting_destinations WHERE id=?", (destination_id,)
    )
    conn.commit()


def list_gallery_destination_overrides(conn, gallery_fk: int) -> list[dict]:
    return [
        dict(r) for r in conn.execute(
            "SELECT * FROM gallery_posting_destinations WHERE gallery_fk=? ORDER BY id",
            (gallery_fk,),
        )
    ]


def get_effective_destinations(conn, gallery_fk: int) -> list[dict]:
    """Return the resolved posting destinations for a gallery.

    Merges tab defaults with gallery-level add/replace/remove overrides.
    Returns [] when no destinations are configured anywhere.
    """
    row = conn.execute(
        "SELECT tab_id FROM galleries WHERE id=?", (gallery_fk,)
    ).fetchone()
    if not row or not row[0]:
        return []
    tab_id = row[0]

    result: dict[tuple, dict] = {}
    for d in list_tab_destinations(conn, tab_id):
        key = (d["forum_fk"], d["target_id"])
        result[key] = {
            "forum_fk": d["forum_fk"],
            "forum_name": d.get("forum_name", ""),
            "target_id": d["target_id"],
            "kind": d["kind"],
            "body_template_name": d.get("body_template_name"),
            "target_name": d.get("target_name"),
        }

    for o in list_gallery_destination_overrides(conn, gallery_fk):
        key = (o["forum_fk"], o["target_id"])
        if o["action"] == "remove":
            result.pop(key, None)
        elif o["action"] in ("add", "replace"):
            f_row = conn.execute(
                "SELECT name FROM forums WHERE id=?", (o["forum_fk"],)
            ).fetchone()
            result[key] = {
                "forum_fk": o["forum_fk"],
                "forum_name": f_row[0] if f_row else "",
                "target_id": o["target_id"],
                "kind": o["kind"],
                "body_template_name": o.get("body_template_name"),
                "target_name": None,
            }

    return list(result.values())


# ---------------------------------------------------------------------------
# tab_posting_config
# ---------------------------------------------------------------------------

def set_tab_posting_config(
    conn, *,
    tab_id: int,
    forum_fk: int,
    kind: str,
    target_id: str,
    body_template_name: str,
    title_template_name: Optional[str],
    trigger_mode: str,
    update_mode: str,
    manual_edit_handling: str,
    stale_triggers: list[str],
    enabled: bool,
) -> None:
    """Insert-or-update the config for one tab. Tab is the PK so this upserts."""
    conn.execute(
        """
        INSERT INTO tab_posting_config(
            tab_id, forum_fk, kind, target_id,
            body_template_name, title_template_name,
            trigger_mode, update_mode, manual_edit_handling,
            stale_triggers_json, enabled, updated_ts
        )
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(tab_id) DO UPDATE SET
            forum_fk=excluded.forum_fk,
            kind=excluded.kind,
            target_id=excluded.target_id,
            body_template_name=excluded.body_template_name,
            title_template_name=excluded.title_template_name,
            trigger_mode=excluded.trigger_mode,
            update_mode=excluded.update_mode,
            manual_edit_handling=excluded.manual_edit_handling,
            stale_triggers_json=excluded.stale_triggers_json,
            enabled=excluded.enabled,
            updated_ts=excluded.updated_ts
        """,
        (tab_id, forum_fk, kind, target_id, body_template_name,
         title_template_name, trigger_mode, update_mode, manual_edit_handling,
         json.dumps(stale_triggers), 1 if enabled else 0, int(time.time())),
    )
    conn.commit()


def get_tab_posting_config(conn, tab_id: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM tab_posting_config WHERE tab_id=?", (tab_id,)
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["stale_triggers"] = json.loads(d.pop("stale_triggers_json") or "[]")
    return d


def delete_tab_posting_config(conn, tab_id: int) -> None:
    conn.execute("DELETE FROM tab_posting_config WHERE tab_id=?", (tab_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# gallery_posting_override
# ---------------------------------------------------------------------------

def set_gallery_override(conn, *, gallery_fk: int, **fields: Any) -> None:
    """Upsert override row. Pass any subset of overridable fields; omitted = no
    change (existing override values preserved). Pass field=None to clear that
    field back to inheriting from the tab.

    `stale_triggers` is accepted as a list and serialised to JSON.
    `enabled` is accepted as a bool and stored as 0/1.
    """
    allowed = set(_TAB_CFG_FIELDS) | {"stale_triggers"}
    bad = set(fields) - allowed
    if bad:
        raise ValueError(f"Unknown override field(s): {sorted(bad)}")

    if "stale_triggers" in fields:
        st = fields.pop("stale_triggers")
        fields["stale_triggers_json"] = (
            json.dumps(st) if st is not None else None
        )
    if "enabled" in fields and fields["enabled"] is not None:
        fields["enabled"] = 1 if fields["enabled"] else 0

    fields["updated_ts"] = int(time.time())
    cols = ", ".join(fields.keys())
    qs = ", ".join("?" for _ in fields)
    updates = ", ".join(f"{k}=excluded.{k}" for k in fields)
    conn.execute(
        f"INSERT INTO gallery_posting_override(gallery_fk, {cols}) "
        f"VALUES (?, {qs}) "
        f"ON CONFLICT(gallery_fk) DO UPDATE SET {updates}",
        (gallery_fk, *fields.values()),
    )
    conn.commit()


def clear_gallery_override(conn, gallery_fk: int) -> None:
    conn.execute(
        "DELETE FROM gallery_posting_override WHERE gallery_fk=?",
        (gallery_fk,),
    )
    conn.commit()


def get_effective_posting_config(conn, gallery_fk: int) -> Optional[dict]:
    """Resolve override → tab fallback. Returns the merged config dict, or
    None if no tab posting config exists for the gallery's tab."""
    row = conn.execute(
        """
        SELECT g.tab_id, o.*
        FROM galleries g
        LEFT JOIN gallery_posting_override o ON o.gallery_fk = g.id
        WHERE g.id = ?
        """,
        (gallery_fk,),
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    tab_id = d.pop("tab_id", None)
    if tab_id is None:
        return None
    tab_cfg = get_tab_posting_config(conn, tab_id)
    if not tab_cfg:
        return None

    eff = dict(tab_cfg)
    # Strip the override row's own bookkeeping columns before merging.
    for k in ("gallery_fk", "created_ts", "updated_ts"):
        d.pop(k, None)

    for k in _TAB_CFG_FIELDS:
        v = d.get(k)
        if v is not None:
            eff[k] = v
    if d.get("stale_triggers_json") is not None:
        eff["stale_triggers"] = json.loads(d["stale_triggers_json"])
    return eff


# ---------------------------------------------------------------------------
# forum_posts
# ---------------------------------------------------------------------------

def insert_forum_post(
    conn, *,
    gallery_fk: int,
    forum_fk: int,
    kind: str,
    target_id: str,
    body_hash: str,
    link_map: dict,
    source: str = "app",
    update_mode_at_post: Optional[str] = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO forum_posts(
            gallery_fk, forum_fk, kind, target_id,
            status, source, body_hash, link_map_json, update_mode_at_post
        )
        VALUES (?,?,?,?, 'queued', ?, ?, ?, ?)
        """,
        (gallery_fk, forum_fk, kind, target_id, source, body_hash,
         json.dumps(link_map), update_mode_at_post),
    )
    conn.commit()
    return cur.lastrowid


def update_forum_post(conn, post_id: int, **fields: Any) -> None:
    if not fields:
        return
    allowed = {
        "posted_post_id", "posted_thread_id", "posted_url", "posted_ts",
        "status", "body_hash", "link_map_json", "last_attempt_ts",
        "last_error", "raw_response", "update_mode_at_post",
    }
    bad = set(fields) - allowed
    if bad:
        raise ValueError(f"Unknown forum_post field(s): {sorted(bad)}")
    fields["updated_ts"] = int(time.time())
    cols = ", ".join(f"{k}=?" for k in fields)
    conn.execute(
        f"UPDATE forum_posts SET {cols} WHERE id=?",
        (*fields.values(), post_id),
    )
    conn.commit()


def get_forum_post(conn, post_id: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM forum_posts WHERE id=?", (post_id,)
    ).fetchone()
    return dict(row) if row else None


def list_forum_posts_for_gallery(conn, gallery_fk: int) -> list[dict]:
    return [
        dict(r) for r in conn.execute(
            "SELECT * FROM forum_posts WHERE gallery_fk=? "
            "ORDER BY created_ts DESC, id DESC",
            (gallery_fk,),
        )
    ]


def mark_posts_stale_for_gallery(conn, gallery_fk: int) -> list[int]:
    """Flip every 'posted' row for this gallery to 'stale'. Returns the IDs
    that were updated (caller can fan-out per-row UI refresh signals)."""
    rows = conn.execute(
        "SELECT id FROM forum_posts WHERE gallery_fk=? AND status='posted'",
        (gallery_fk,),
    ).fetchall()
    ids = [r[0] for r in rows]
    if ids:
        placeholders = ",".join("?" for _ in ids)
        conn.execute(
            f"UPDATE forum_posts SET status='stale', updated_ts=? "
            f"WHERE id IN ({placeholders})",
            (int(time.time()), *ids),
        )
        conn.commit()
    return ids
