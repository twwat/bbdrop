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


# Placeholder — implemented in Task 7.
def _file_list_result_from_json(text: str) -> FileListResult:
    raise NotImplementedError("Implemented in Task 7")
