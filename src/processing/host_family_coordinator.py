"""Host family coordinator for cross-host dedup orchestration.

Watches `FileHostWorker.host_gallery_settled` events and flips DB state for
K2S-family rows: unblocking secondaries on primary success, promoting the
next-in-chain on primary failure, and flipping failed rows to dedup_only=1
after a family winner emerges.

All reactions are idempotent — re-running on the same event is safe.

### MD5 propagation

K2S-family backends rewrite uploaded files server-side (MP4 atom rewriting,
etc.), so the md5 that `createFileByHash` indexes is a post-rewrite md5 that
only the server knows. It takes a variable delay (~10-15s in practice) before
`getFilesInfo` returns it.

The primary worker does NOT poll for this md5 — it finishes with a NULL
md5_hash and moves on to the next gallery. Instead, the coordinator spawns a
single background `threading.Timer` when the primary settles: wait the
expected propagation window, do one `getFilesInfo` call, write the md5 to the
primary's row, then unblock siblings so they pick up the now-populated row and
run `createFileByHash` directly. On the rare miss, the poller backs off
exponentially; if it ever exhausts attempts, siblings are unblocked anyway and
fall through to full upload.

This collapses what used to be per-sibling independent polling loops into
exactly one shared poll per family upload.
"""
import threading
import time
from typing import Dict, Optional
from urllib.parse import urlparse

from PyQt6.QtCore import QObject, pyqtSlot

from src.core.constants import HOST_FAMILY_PRIORITY
from src.core.file_host_config import get_host_family, is_family_dedup_enabled
from src.network.file_host_client import FileHostClient
from src.storage.database import QueueStore
from src.utils.logger import log

# Timings for the post-upload md5 poll. The initial delay is tuned to the
# observed window after which K2S-family backends have finished rewriting;
# the happy path takes exactly one HTTP call. Backoff only kicks in for the
# rare miss where the backend is slow.
K2S_MD5_INITIAL_DELAY_SEC = 12
K2S_MD5_BACKOFF_BASE_SEC = 10
K2S_MD5_MAX_BACKOFF_SEC = 60
K2S_MD5_MAX_ATTEMPTS = 4  # total attempts (1 initial + 3 retries)


def _canonical_file_id_from_url(download_url: Optional[str]) -> Optional[str]:
    """Extract the canonical file id from a K2S-family download URL.

    K2S-family URLs have the form `https://<host>/file/{id}/{filename}`.
    `getFilesInfo` expects that `{id}` segment — NOT the user-facing file_id
    returned in the upload response (which, for K2S, is `user_file_id`).
    """
    if not download_url:
        return None
    try:
        path_segments = urlparse(download_url).path.strip('/').split('/')
    except Exception:
        return None
    for i, segment in enumerate(path_segments):
        if segment == 'file' and i + 1 < len(path_segments):
            return path_segments[i + 1] or None
    return None


def _unblock_family_waiters(
    queue_store: QueueStore, gallery_fk: int, family: str, primary_row_id: int
) -> None:
    """Flip every row blocked on the primary's row to `pending`.

    Used by both the sync path in `_handle_success` (when the primary already
    has an md5) and the async md5 poller thread (after the poll finishes,
    whether it landed an md5 or gave up).
    """
    members = HOST_FAMILY_PRIORITY.get(family, [])
    if not members:
        return
    rows = queue_store.get_family_head_rows(gallery_fk, members)
    for r in rows:
        if r["status"] == "blocked" and r["blocked_by_upload_id"] == primary_row_id:
            queue_store.update_file_host_upload(r["id"], status="pending")


def _md5_fetch_worker(
    queue_store: QueueStore,
    gallery_fk: int,
    family: str,
    primary_row_id: int,
    host_name: str,
    canonical_file_id: str,
) -> None:
    """Background task: poll primary's `getFilesInfo` until md5 lands.

    Runs on a `threading.Timer` thread. Does not touch Qt. All side effects
    go through `queue_store` (SQLite WAL, safe from any thread). On success,
    writes the md5 to the primary's row before unblocking siblings so they
    read the populated value via `get_family_completed_parts`. On permanent
    miss, unblocks siblings anyway — they will fall through to full upload.
    """
    tag = f"[family-md5-poll gallery_fk={gallery_fk} host={host_name}]"
    md5: Optional[str] = None
    for attempt in range(K2S_MD5_MAX_ATTEMPTS):
        try:
            md5 = FileHostClient.fetch_md5_for_host(
                host_name,
                canonical_file_id,
                log_callback=_make_poll_log_cb(tag),
            )
        except Exception as e:
            log(
                f"{tag} attempt {attempt + 1} raised: {e}",
                level="warning",
                category="file_hosts",
            )
            md5 = None

        if md5:
            break

        if attempt + 1 >= K2S_MD5_MAX_ATTEMPTS:
            break  # exhausted; don't sleep again

        delay = min(
            K2S_MD5_BACKOFF_BASE_SEC * (2 ** attempt),
            K2S_MD5_MAX_BACKOFF_SEC,
        )
        log(
            f"{tag} md5 not ready, retry in {delay}s "
            f"(attempt {attempt + 2}/{K2S_MD5_MAX_ATTEMPTS})",
            level="debug",
            category="file_hosts",
        )
        time.sleep(delay)

    if md5:
        queue_store.update_file_host_upload(primary_row_id, md5_hash=md5)
        log(
            f"{tag} md5 landed: {md5} — unblocking siblings",
            level="debug",
            category="file_hosts",
        )
    else:
        log(
            f"{tag} gave up after {K2S_MD5_MAX_ATTEMPTS} attempts — "
            f"siblings will fall through to full upload",
            level="warning",
            category="file_hosts",
        )

    _unblock_family_waiters(queue_store, gallery_fk, family, primary_row_id)


def _make_poll_log_cb(tag: str):
    """Build a log_callback with a frozen `tag` prefix for the poller."""
    def _cb(msg: str, level: str = "info") -> None:
        log(f"{tag} {msg}", level=level, category="file_hosts")
    return _cb


class HostFamilyCoordinator(QObject):
    """Single-responsibility coordinator for backend-family upload dedup.

    Owned by FileHostWorkerManager. The manager connects every worker's
    host_gallery_settled signal to `on_host_gallery_settled` — this class
    reacts by mutating DB state; it never touches workers or clients directly.

    Follows the same shape as the existing FileHostCoordinator, ArchiveCoordinator,
    and ScanCoordinator — single-purpose, owned by a manager, no UI concerns.
    """

    def __init__(self, queue_store: QueueStore):
        super().__init__()
        self.queue_store = queue_store
        # primary_row_id → active poller Timer. Entries are removed when
        # the Timer finishes (via the callback wrapper in _schedule_md5_fetch)
        # or when shutdown() cancels all pending pollers.
        self._pending_timers: Dict[int, threading.Timer] = {}
        self._pending_timers_lock = threading.Lock()

    def shutdown(self) -> None:
        """Cancel any in-flight md5 pollers.

        Called from `FileHostWorkerManager.shutdown_all` so we don't leak
        background threads past app exit or race the DB during teardown.
        Cancels Timers that haven't fired yet; pollers already running get
        to finish (their DB writes are idempotent — see _md5_fetch_worker).
        """
        with self._pending_timers_lock:
            timers = list(self._pending_timers.values())
            self._pending_timers.clear()
        for t in timers:
            t.cancel()

    @pyqtSlot(int, str, bool)
    def on_host_gallery_settled(
        self, gallery_fk: int, host_name: str, success: bool
    ) -> None:
        """React to a worker finishing processing a gallery for a host."""
        if not is_family_dedup_enabled():
            return

        family = get_host_family(host_name)
        if not family:
            return

        try:
            if success:
                self._handle_success(gallery_fk, host_name, family)
            else:
                self._handle_failure(gallery_fk, host_name, family)
            # Always run the retry scan — it's a no-op unless state changed.
            self._run_family_retry_scan(gallery_fk, family)
        except Exception as e:
            log(
                f"HostFamilyCoordinator error handling {host_name}/{gallery_fk}: {e}",
                level="warning",
                category="file_hosts",
            )

    def _family_rows(self, gallery_fk: int, family: str) -> list:
        """Return all head rows (part_number=0) for this gallery in the family."""
        members = HOST_FAMILY_PRIORITY.get(family, [])
        if not members:
            return []
        all_rows = self.queue_store.get_family_head_rows(gallery_fk, members)
        return all_rows

    def _handle_success(self, gallery_fk: int, host_name: str, family: str) -> None:
        """Unblock siblings waiting on the row that just succeeded.

        For K2S-family primaries the row may have a NULL md5 (the worker
        doesn't poll the backend itself). If there are siblings waiting and
        md5 is missing, defer the unblock: spawn the background md5 poller,
        which will populate the md5 and unblock siblings when it's done.

        In any other case — no waiters, md5 already populated, or no usable
        download URL to derive a canonical id from — unblock immediately,
        preserving the pre-poller behavior.
        """
        rows = self._family_rows(gallery_fk, family)
        done_row = next((r for r in rows if r["host_name"] == host_name), None)
        if done_row is None:
            return

        waiters = [
            r for r in rows
            if r["status"] == "blocked" and r["blocked_by_upload_id"] == done_row["id"]
        ]
        if not waiters:
            return

        if done_row.get("md5_hash"):
            _unblock_family_waiters(
                self.queue_store, gallery_fk, family, done_row["id"]
            )
            return

        canonical_id = _canonical_file_id_from_url(done_row.get("download_url"))
        if not canonical_id:
            log(
                f"HostFamilyCoordinator: {host_name} gallery_fk={gallery_fk} "
                f"has no canonical file id — unblocking siblings without md5, "
                f"they will fall through to full upload",
                level="debug",
                category="file_hosts",
            )
            _unblock_family_waiters(
                self.queue_store, gallery_fk, family, done_row["id"]
            )
            return

        self._schedule_md5_fetch(
            gallery_fk=gallery_fk,
            family=family,
            primary_row_id=done_row["id"],
            host_name=host_name,
            canonical_file_id=canonical_id,
        )

    def _schedule_md5_fetch(
        self,
        gallery_fk: int,
        family: str,
        primary_row_id: int,
        host_name: str,
        canonical_file_id: str,
    ) -> None:
        """Start a background `threading.Timer` for the md5 poll.

        Registers the Timer in `_pending_timers` so shutdown can cancel it
        and duplicate schedules on the same primary row replace (rather
        than stack) the pending poller. Overridable by tests that want to
        run the poller synchronously or replace the thread model entirely.
        """
        # Replace any in-flight Timer for this same primary row — second
        # schedules are idempotent at the DB level, but stacking them wastes
        # HTTP calls and log lines.
        with self._pending_timers_lock:
            existing = self._pending_timers.pop(primary_row_id, None)
        if existing is not None:
            existing.cancel()

        def _run_and_cleanup():
            try:
                _md5_fetch_worker(
                    self.queue_store,
                    gallery_fk,
                    family,
                    primary_row_id,
                    host_name,
                    canonical_file_id,
                )
            finally:
                with self._pending_timers_lock:
                    self._pending_timers.pop(primary_row_id, None)

        t = threading.Timer(K2S_MD5_INITIAL_DELAY_SEC, _run_and_cleanup)
        t.daemon = True
        with self._pending_timers_lock:
            self._pending_timers[primary_row_id] = t
        t.start()
        log(
            f"HostFamilyCoordinator: scheduled md5 poll for {host_name} "
            f"gallery_fk={gallery_fk} in {K2S_MD5_INITIAL_DELAY_SEC}s",
            level="debug",
            category="file_hosts",
        )

    def _handle_failure(self, gallery_fk: int, host_name: str, family: str) -> None:
        """Promote the next eligible blocked sibling to primary."""
        rows = self._family_rows(gallery_fk, family)
        failed_row = next((r for r in rows if r["host_name"] == host_name), None)
        if failed_row is None:
            return

        # Only promote if the failed row WAS the primary (no blocked_by pointer).
        if failed_row.get("blocked_by_upload_id") is not None:
            return

        # Walk priority order to find the first still-blocked sibling.
        members = HOST_FAMILY_PRIORITY.get(family, [])
        rows_by_host = {r["host_name"]: r for r in rows}
        new_primary = None
        for candidate in members:
            if candidate == host_name:
                continue
            r = rows_by_host.get(candidate)
            if r and r["status"] == "blocked":
                new_primary = r
                break

        if new_primary is None:
            return  # No eligible successor; family is stuck failed.

        # Promote: flip to pending, clear blocked_by pointer.
        self.queue_store.update_file_host_upload(
            new_primary["id"],
            status="pending",
            blocked_by_upload_id=None,
        )

        # Reassign remaining blocked siblings to point at the new primary.
        for r in rows:
            if (
                r["status"] == "blocked"
                and r["id"] != new_primary["id"]
                and r.get("blocked_by_upload_id") == failed_row["id"]
            ):
                self.queue_store.update_file_host_upload(
                    r["id"],
                    blocked_by_upload_id=new_primary["id"],
                )

    def _run_family_retry_scan(self, gallery_fk: int, family: str) -> None:
        """Flip failed head rows to dedup_only=1 when a family winner exists.

        If the winner's md5 isn't populated yet (the coordinator's poller is
        still running), the dedup_only retry row must not be flipped to
        `pending` — its `_try_family_mirror` call would see a NULL-md5
        sibling and fail terminally. Block it on the winner instead; the
        poller will flip it to `pending` alongside any other waiters once
        md5 lands.
        """
        rows = self._family_rows(gallery_fk, family)
        winner = next((r for r in rows if r["status"] == "completed"), None)
        if winner is None:
            return

        winner_has_md5 = bool(winner.get("md5_hash"))
        new_status = "pending" if winner_has_md5 else "blocked"
        new_blocked_by = None if winner_has_md5 else winner["id"]

        for r in rows:
            if r["status"] == "failed" and r.get("dedup_only", 0) == 0:
                self.queue_store.update_file_host_upload(
                    r["id"],
                    status=new_status,
                    dedup_only=1,
                    blocked_by_upload_id=new_blocked_by,
                )
