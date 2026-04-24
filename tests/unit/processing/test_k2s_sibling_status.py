"""Tests for K2S sibling host status message logic."""
import time
from unittest.mock import MagicMock, patch


# ── DB helper tests ──────────────────────────────────────────────────────────

def test_has_blocked_uploads_for_host_returns_false_when_empty(tmp_path):
    from src.storage.database import QueueStore
    db = QueueStore(tmp_path / "test.db")
    assert db.has_blocked_uploads_for_host("keep2share") is False


def test_has_blocked_uploads_for_host_returns_true_when_blocked_row_exists(tmp_path):
    """Insert a blocked row directly and verify the helper sees it."""
    import sqlite3
    db_path = tmp_path / "test.db"
    from src.storage.database import QueueStore, _ensure_schema
    store = QueueStore(db_path)

    with sqlite3.connect(db_path) as conn:
        _ensure_schema(conn)
        conn.execute(
            """INSERT INTO galleries (path, name, status, added_ts)
               VALUES ('x', 'x', 'ready', 0)"""
        )
        gal_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            """INSERT INTO file_host_uploads
               (gallery_fk, host_name, status, part_number)
               VALUES (?, 'fileboom', 'blocked', 0)""",
            (gal_id,),
        )

    assert store.has_blocked_uploads_for_host("fileboom") is True
    assert store.has_blocked_uploads_for_host("keep2share") is False


# ── Worker main-loop status emission tests ───────────────────────────────────

def _make_worker(tmp_path):
    """Build a minimal stub with the _update_family_idle_status method bound.

    Avoids constructing a real FileHostWorker (QThread subclass) which requires
    a running Qt event loop and a fully configured host. Instead we copy the
    unbound method onto a plain Python object that has exactly the attributes
    the method touches.
    """
    from src.storage.database import QueueStore
    from src.processing.file_host_workers import FileHostWorker

    queue_store = QueueStore(tmp_path / "test.db")
    status_emit = MagicMock()

    class _Stub:
        host_id = "fileboom"
        _family_status = ""
        _hash_created_ts = 0.0
        log_prefix = "FileBoom Worker"

        def __init__(self, qs):
            self.queue_store = qs
            self.status_updated = MagicMock()
            self.status_updated.emit = status_emit

        _update_family_idle_status = FileHostWorker._update_family_idle_status

    return _Stub(queue_store), queue_store


def test_emits_waiting_md5_when_blocked_rows_exist(tmp_path):
    import sqlite3
    from src.storage.database import _ensure_schema
    worker, store = _make_worker(tmp_path)

    with sqlite3.connect(store.db_path) as conn:
        _ensure_schema(conn)
        conn.execute("INSERT INTO galleries (path, name, status, added_ts) VALUES ('x','x','ready',0)")
        gal_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO file_host_uploads (gallery_fk, host_name, status, part_number) VALUES (?, 'fileboom', 'blocked', 0)",
            (gal_id,)
        )

    worker._update_family_idle_status()
    worker.status_updated.emit.assert_called_once_with("fileboom", "waiting_md5")
    assert worker._family_status == "waiting_md5"


def test_reverts_to_idle_when_no_blocked_rows(tmp_path):
    worker, _ = _make_worker(tmp_path)
    worker._family_status = "waiting_md5"

    worker._update_family_idle_status()
    worker.status_updated.emit.assert_called_once_with("fileboom", "idle")
    assert worker._family_status == ""


def test_holds_hash_created_for_3_seconds(tmp_path):
    worker, _ = _make_worker(tmp_path)
    worker._family_status = "hash_created"
    worker._hash_created_ts = time.time()

    worker._update_family_idle_status()
    worker.status_updated.emit.assert_not_called()


def test_clears_hash_created_after_hold_expires(tmp_path):
    worker, _ = _make_worker(tmp_path)
    worker._family_status = "hash_created"
    worker._hash_created_ts = time.time() - 4.0

    worker._update_family_idle_status()
    worker.status_updated.emit.assert_called_once_with("fileboom", "idle")
    assert worker._family_status == ""


def test_emits_creating_from_hash_before_mirror_loop(tmp_path):
    """_try_family_mirror emits creating_from_hash when sibling parts are present."""
    from src.processing.file_host_workers import FileHostWorker

    worker, store = _make_worker(tmp_path)
    # Bind _try_family_mirror onto the stub
    worker._try_family_mirror = FileHostWorker._try_family_mirror.__get__(worker)
    worker._should_stop_current = False
    worker._stop_event = MagicMock(is_set=MagicMock(return_value=False))

    sibling_parts = [{"host_name": "keep2share", "md5_hash": "abc123", "file_name": "a.zip", "part_number": 0}]

    with patch.object(store, "get_family_completed_parts", return_value=sibling_parts):
        worker.queue_store = store
        mock_client = MagicMock()
        mock_client.try_create_by_hash.return_value = None  # mirror fails
        row = {"id": 1, "gallery_fk": 1, "host_name": "fileboom", "gallery_path": "/x"}
        worker._try_family_mirror(row, mock_client, "k2s")

    worker.status_updated.emit.assert_any_call("fileboom", "creating_from_hash")
    assert worker._family_status == "creating_from_hash"


def test_emits_hash_created_after_mirror_success(tmp_path):
    """_process_single_pending_row emits hash_created when mirror succeeds."""
    from src.processing.file_host_workers import FileHostWorker
    import src.processing.file_host_workers as fhw_mod

    worker, store = _make_worker(tmp_path)
    worker._process_single_pending_row = \
        FileHostWorker._process_single_pending_row.__get__(worker)
    worker.host_id = "fileboom"
    worker.config_manager = MagicMock()
    worker.config_manager.get_host.return_value = MagicMock()
    worker._create_client = MagicMock(return_value=MagicMock())
    worker._try_family_mirror = MagicMock(return_value=True)
    worker.upload_completed = MagicMock()
    worker.upload_completed.emit = MagicMock()
    worker.host_gallery_settled = MagicMock()
    worker.host_gallery_settled.emit = MagicMock()

    row = {
        "id": 1, "gallery_fk": 1, "host_name": "fileboom",
        "gallery_path": "/x", "gallery_name": "gallery",
        "dedup_only": 0,
    }

    with patch.object(fhw_mod, "is_family_dedup_enabled", return_value=True), \
         patch.object(fhw_mod, "get_host_family", return_value="k2s"):
        worker._process_single_pending_row(row)

    worker.status_updated.emit.assert_any_call("fileboom", "hash_created")
    assert worker._family_status == "hash_created"
    assert worker._hash_created_ts > 0
