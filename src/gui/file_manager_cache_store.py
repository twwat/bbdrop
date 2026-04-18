"""Persistent tier for the file manager's in-memory folder-listing cache.

Stores serialized ``FileListResult`` rows in a separate SQLite file at
``~/.bbdrop/file_manager_cache.db`` so the file manager's cache survives
app restarts. The in-memory stale-while-revalidate flow in
``FileManagerController`` is unchanged; this module warms that cache on
host switch and writes through on each worker response.

Separate DB (not ``bbdrop.db``) by design: this is a cache. If the
schema ever needs to change, delete the file — next session repopulates
it. No migrations, no coordination with the queue DB schema version.
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Dict, Optional, Tuple

from src.network.file_manager.client import FileListResult
from src.utils.logger import log
from src.utils.paths import get_central_store_base_path

_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS cache (
    host_name   TEXT NOT NULL,
    folder_id   TEXT NOT NULL,
    data_json   TEXT NOT NULL,
    fetched_at  INTEGER NOT NULL,
    PRIMARY KEY (host_name, folder_id)
)
"""


def _db_path() -> str:
    """Return the cache DB path. Overridable in tests via monkeypatch."""
    return os.path.join(get_central_store_base_path(), "file_manager_cache.db")


def _connect() -> sqlite3.Connection:
    """Open the cache DB, ensuring schema and WAL mode."""
    path = _db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=5, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute(_TABLE_DDL)
    return conn


def load_all(host_name: str) -> Dict[str, Tuple[FileListResult, float]]:
    """Return {folder_id: (FileListResult, fetched_at)} for this host.

    Returns an empty dict for unknown hosts or if the DB is unreadable.
    Corrupt rows are deleted and skipped; the rest of the rows still load.
    """
    try:
        conn = _connect()
    except sqlite3.Error as e:
        log(f"file manager cache: cannot open DB: {e}", level="warning", category="file_manager")
        return {}

    try:
        rows = conn.execute(
            "SELECT folder_id, data_json, fetched_at FROM cache WHERE host_name = ?",
            (host_name,),
        ).fetchall()
    except sqlite3.Error as e:
        log(f"file manager cache: read failed: {e}", level="warning", category="file_manager")
        conn.close()
        return {}

    out: Dict[str, Tuple[FileListResult, float]] = {}
    corrupt_folder_ids = []
    for folder_id, data_json, fetched_at in rows:
        try:
            result = _file_list_result_from_json(data_json)
        except (ValueError, KeyError, TypeError) as e:
            log(f"file manager cache: corrupt row for {host_name}/{folder_id}: {e}",
                level="debug", category="file_manager")
            corrupt_folder_ids.append(folder_id)
            continue
        out[folder_id] = (result, float(fetched_at))

    # Delete corrupt rows so they don't keep getting logged.
    for fid in corrupt_folder_ids:
        try:
            conn.execute(
                "DELETE FROM cache WHERE host_name = ? AND folder_id = ?",
                (host_name, fid),
            )
        except sqlite3.Error:
            pass

    conn.close()
    return out


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _file_info_to_dict(fi) -> dict:
    """FileInfo -> JSON-friendly dict. created goes out as ISO string."""
    return {
        "id": fi.id,
        "name": fi.name,
        "is_folder": fi.is_folder,
        "size": fi.size,
        "created": fi.created.isoformat() if fi.created else None,
        "access": fi.access,
        "is_available": fi.is_available,
        "md5": fi.md5,
        "download_count": fi.download_count,
        "content_type": fi.content_type,
        "parent_id": fi.parent_id,
        "metadata": fi.metadata,
    }


def _file_info_from_dict(d: dict):
    """Inverse of _file_info_to_dict. Isolated import to avoid circularity."""
    from datetime import datetime
    from src.network.file_manager.client import FileInfo

    created_raw = d.get("created")
    created = None
    if created_raw:
        try:
            created = datetime.fromisoformat(created_raw)
        except (ValueError, TypeError):
            created = None

    return FileInfo(
        id=d.get("id", ""),
        name=d.get("name", ""),
        is_folder=bool(d.get("is_folder", False)),
        size=int(d.get("size", 0) or 0),
        created=created,
        access=d.get("access", "public"),
        is_available=bool(d.get("is_available", True)),
        md5=d.get("md5"),
        download_count=d.get("download_count"),
        content_type=d.get("content_type"),
        parent_id=d.get("parent_id"),
        metadata=dict(d.get("metadata") or {}),
    )


def _file_list_result_to_json(result: FileListResult) -> str:
    payload = {
        "files": [_file_info_to_dict(fi) for fi in result.files],
        "total": int(result.total),
        "page": int(result.page),
        "per_page": int(result.per_page),
    }
    return json.dumps(payload, separators=(",", ":"))


def _file_list_result_from_json(text: str) -> FileListResult:
    payload = json.loads(text)
    return FileListResult(
        files=[_file_info_from_dict(d) for d in payload.get("files", [])],
        total=int(payload.get("total", 0)),
        page=int(payload.get("page", 1)),
        per_page=int(payload.get("per_page", 100)),
    )


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def save(host_name: str, folder_id: str, result: FileListResult, fetched_at: float) -> None:
    """Upsert one cache row. Errors are logged and swallowed — cache writes
    must never block the file manager."""
    try:
        conn = _connect()
    except sqlite3.Error as e:
        log(f"file manager cache: cannot open DB for write: {e}",
            level="warning", category="file_manager")
        return

    try:
        data_json = _file_list_result_to_json(result)
    except (TypeError, ValueError) as e:
        log(f"file manager cache: serialize failed for {host_name}/{folder_id}: {e}",
            level="warning", category="file_manager")
        conn.close()
        return

    try:
        conn.execute(
            "INSERT OR REPLACE INTO cache (host_name, folder_id, data_json, fetched_at) "
            "VALUES (?, ?, ?, ?)",
            (host_name, folder_id, data_json, int(fetched_at)),
        )
    except sqlite3.Error as e:
        log(f"file manager cache: write failed: {e}",
            level="warning", category="file_manager")
    finally:
        conn.close()


def clear(host_name: Optional[str] = None) -> None:
    """Wipe the cache — by host if host_name is given, otherwise everything.

    Exposed for tests and future UI (e.g. a 'Clear Cache' debug menu item).
    Failures are logged and swallowed.
    """
    try:
        conn = _connect()
    except sqlite3.Error as e:
        log(f"file manager cache: cannot open DB for clear: {e}",
            level="warning", category="file_manager")
        return
    try:
        if host_name is None:
            conn.execute("DELETE FROM cache")
        else:
            conn.execute("DELETE FROM cache WHERE host_name = ?", (host_name,))
    except sqlite3.Error as e:
        log(f"file manager cache: clear failed: {e}",
            level="warning", category="file_manager")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Gallery cross-reference lookup
# ---------------------------------------------------------------------------

def _queue_db_path() -> str:
    """Return the queue DB path. Overridable in tests via monkeypatch."""
    return os.path.join(get_central_store_base_path(), "bbdrop.db")


def lookup_galleries(host_name: str, file_ids) -> Dict[str, str]:
    """Map each file_id to its source gallery name, for files originally
    uploaded through BBDrop.

    Returns a dict of {file_id: gallery_name}. file_ids without a matching
    row in bbdrop.db's ``file_host_uploads`` table are simply absent from
    the result (no 'Unknown' sentinels). Errors return an empty dict.
    """
    ids = [str(x) for x in file_ids if x]
    if not ids:
        return {}

    path = _queue_db_path()
    if not os.path.exists(path):
        return {}

    try:
        conn = sqlite3.connect(path, timeout=5)
    except sqlite3.Error as e:
        log(f"file manager cache: cannot open queue DB: {e}",
            level="warning", category="file_manager")
        return {}

    try:
        placeholders = ",".join("?" for _ in ids)
        sql = (
            "SELECT fhu.file_id, g.name "
            "FROM file_host_uploads fhu "
            "JOIN galleries g ON g.id = fhu.gallery_fk "
            f"WHERE fhu.host_name = ? AND fhu.file_id IN ({placeholders})"
        )
        rows = conn.execute(sql, (host_name, *ids)).fetchall()
    except sqlite3.Error as e:
        log(f"file manager cache: lookup_galleries failed: {e}",
            level="warning", category="file_manager")
        conn.close()
        return {}

    conn.close()
    return {fid: name for (fid, name) in rows if fid}
