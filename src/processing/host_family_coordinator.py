"""Host family coordinator for cross-host dedup orchestration.

Watches `FileHostWorker.host_gallery_settled` events and flips DB state for
K2S-family rows: unblocking secondaries on primary success, promoting the
next-in-chain on primary failure, and flipping failed rows to dedup_only=1
after a family winner emerges.

All reactions are idempotent — re-running on the same event is safe.
"""
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSlot

from src.core.constants import HOST_FAMILY_PRIORITY
from src.core.file_host_config import get_host_family, is_family_dedup_enabled
from src.storage.database import QueueStore
from src.utils.logger import log


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
        """Unblock siblings waiting on the row that just succeeded."""
        rows = self._family_rows(gallery_fk, family)
        done_row = next((r for r in rows if r["host_name"] == host_name), None)
        if done_row is None:
            return

        for r in rows:
            if r["status"] == "blocked" and r["blocked_by_upload_id"] == done_row["id"]:
                self.queue_store.update_file_host_upload(
                    r["id"],
                    status="pending",
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
        """Flip failed head rows to dedup_only=1 when a family winner exists."""
        rows = self._family_rows(gallery_fk, family)
        has_winner = any(r["status"] == "completed" for r in rows)
        if not has_winner:
            return

        for r in rows:
            if r["status"] == "failed" and r.get("dedup_only", 0) == 0:
                self.queue_store.update_file_host_upload(
                    r["id"],
                    status="pending",
                    dedup_only=1,
                    blocked_by_upload_id=None,
                )
