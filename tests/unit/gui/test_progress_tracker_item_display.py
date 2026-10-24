"""Unit tests for ProgressTracker byte-weighted per-item display helpers.

Covers _compute_item_work_bytes and compute_item_display -- the helpers that
power both the overall progress bar and the per-row progress bars / status
cells so they reflect total work (image host + file host bytes) instead of
image-count ratio.
"""

import os

import pytest
from unittest.mock import MagicMock

from src.gui.progress_tracker import ProgressTracker
from src.storage.queue_manager import GalleryQueueItem


def _make_main_window(file_host_rows=None):
    """Build a mock main window that returns the given file host rows."""
    mw = MagicMock()
    mw.queue_manager = MagicMock()
    mw.queue_manager.store = MagicMock()
    mw.queue_manager.store.get_file_host_uploads = MagicMock(
        return_value=file_host_rows or []
    )
    return mw


@pytest.fixture
def tracker():
    """ProgressTracker bound to a mock main window with no file host rows."""
    mw = _make_main_window()
    return ProgressTracker(mw)


class TestComputeItemWorkBytes:
    def test_image_gallery_uploading_mid_progress(self, tracker):
        item = GalleryQueueItem(path="/g")
        item.status = "uploading"
        item.total_size = 10_000_000  # 10 MB
        item.total_images = 10
        item.uploaded_images = 5
        total, uploaded = tracker._compute_item_work_bytes(item, file_host_rows=[])
        assert total == 10_000_000
        assert uploaded == 5_000_000  # 5/10 ratio

    def test_image_gallery_completed_no_file_hosts(self, tracker):
        item = GalleryQueueItem(path="/g")
        item.status = "completed"
        item.total_size = 2_000_000
        total, uploaded = tracker._compute_item_work_bytes(item, file_host_rows=[])
        assert total == uploaded == 2_000_000

    def test_video_gallery_image_host_is_sheet_size_fallback(self, tracker):
        # No real sheet file on disk -> uses 1% fallback of total_size
        item = GalleryQueueItem(path="/v")
        item.status = "uploading"
        item.media_type = "video"
        item.screenshot_sheet_path = ""  # no sheet path
        item.total_size = 100_000_000  # 100 MB video
        item.total_images = 1
        item.uploaded_images = 0
        total, uploaded = tracker._compute_item_work_bytes(item, file_host_rows=[])
        # Without a sheet path the function uses `image_host_total = item_total_size`
        # for non-sheet videos -- that's the current behavior: only the fallback
        # 1% kicks in when a sheet path is set but unreadable.
        assert total == 100_000_000
        assert uploaded == 0

    def test_image_host_done_file_host_halfway(self, tracker):
        item = GalleryQueueItem(path="/g")
        item.status = "completed"
        item.total_size = 1_000_000  # 1 MB image gallery
        file_host_rows = [
            {
                "status": "uploading",
                "total_bytes": 100_000_000,  # 100 MB archive
                "uploaded_bytes": 50_000_000,
                "file_size": 100_000_000,
                "deduped": False,
            },
        ]
        total, uploaded = tracker._compute_item_work_bytes(item, file_host_rows)
        # Image host: 1 MB done + file host: 100 MB total, 50 MB done
        assert total == 101_000_000
        assert uploaded == 51_000_000

    def test_file_host_completed_counts_full(self, tracker):
        item = GalleryQueueItem(path="/g")
        item.status = "completed"
        item.total_size = 1_000_000
        file_host_rows = [
            {
                "status": "completed",
                "total_bytes": 50_000_000,
                "uploaded_bytes": 50_000_000,
                "file_size": 50_000_000,
                "deduped": False,
            },
        ]
        total, uploaded = tracker._compute_item_work_bytes(item, file_host_rows)
        assert total == uploaded == 51_000_000

    def test_deduped_row_counts_full(self, tracker):
        item = GalleryQueueItem(path="/g")
        item.status = "completed"
        item.total_size = 1_000_000
        file_host_rows = [
            {
                "status": "pending",
                "total_bytes": 0,
                "uploaded_bytes": 0,
                "file_size": 50_000_000,
                "deduped": True,
            },
        ]
        total, uploaded = tracker._compute_item_work_bytes(item, file_host_rows)
        assert total == uploaded == 51_000_000

    def test_pending_row_counts_toward_total_but_zero_uploaded(self, tracker):
        item = GalleryQueueItem(path="/g")
        item.status = "completed"
        item.total_size = 1_000_000
        file_host_rows = [
            {
                "status": "pending",
                "total_bytes": 0,
                "uploaded_bytes": 0,
                "file_size": 80_000_000,
                "deduped": False,
            },
        ]
        total, uploaded = tracker._compute_item_work_bytes(item, file_host_rows)
        assert total == 81_000_000
        assert uploaded == 1_000_000  # image host contribution only

    def test_cancelled_row_excluded_from_work(self, tracker):
        """Cancelled rows are user-abandoned -- they should not pull the
        gallery's percent below 100 forever."""
        item = GalleryQueueItem(path="/g")
        item.status = "completed"
        item.total_size = 1_000_000
        file_host_rows = [
            {
                "status": "cancelled",
                "total_bytes": 80_000_000,
                "uploaded_bytes": 30_000_000,
                "file_size": 80_000_000,
                "deduped": False,
            },
        ]
        total, uploaded = tracker._compute_item_work_bytes(item, file_host_rows)
        # Only the image host contribution counts.
        assert total == 1_000_000
        assert uploaded == 1_000_000

    def test_blocked_row_excluded_from_work(self, tracker):
        """Blocked rows are permanently stuck without intervention -- treat
        the same as cancelled for accounting purposes."""
        item = GalleryQueueItem(path="/g")
        item.status = "completed"
        item.total_size = 1_000_000
        file_host_rows = [
            {
                "status": "blocked",
                "total_bytes": 0,
                "uploaded_bytes": 0,
                "file_size": 80_000_000,
                "deduped": False,
            },
        ]
        total, uploaded = tracker._compute_item_work_bytes(item, file_host_rows)
        assert total == 1_000_000
        assert uploaded == 1_000_000


class TestComputeItemDisplay:
    def test_image_upload_in_progress_keeps_uploading_status(self, tracker):
        item = GalleryQueueItem(path="/g")
        item.status = "uploading"
        item.total_size = 10_000_000
        item.total_images = 10
        item.uploaded_images = 5
        percent, effective = tracker.compute_item_display(item)
        assert effective == "uploading"
        assert percent == 50

    def test_image_host_done_no_file_hosts_shows_completed(self, tracker):
        item = GalleryQueueItem(path="/g")
        item.status = "completed"
        item.total_size = 1_000_000
        percent, effective = tracker.compute_item_display(item)
        assert effective == "completed"
        assert percent == 100

    def test_image_host_done_with_pending_file_host_downgrades_to_uploading(
        self, tracker
    ):
        """The core fix: don't read as Completed while file hosts are still in flight."""
        tracker._main_window.queue_manager.store.get_file_host_uploads.return_value = [
            {
                "status": "pending",
                "total_bytes": 0,
                "uploaded_bytes": 0,
                "file_size": 100_000_000,
                "deduped": False,
            }
        ]
        item = GalleryQueueItem(path="/g")
        item.status = "completed"
        item.total_size = 1_000_000
        percent, effective = tracker.compute_item_display(item)
        assert effective == "uploading"
        # 1 MB uploaded / 101 MB total ~= 0.99%, floors to 1%
        assert percent == 1

    def test_image_host_done_file_host_halfway_mid_percent(self, tracker):
        tracker._main_window.queue_manager.store.get_file_host_uploads.return_value = [
            {
                "status": "uploading",
                "total_bytes": 100_000_000,
                "uploaded_bytes": 50_000_000,
                "file_size": 100_000_000,
                "deduped": False,
            }
        ]
        item = GalleryQueueItem(path="/g")
        item.status = "completed"
        item.total_size = 1_000_000
        percent, effective = tracker.compute_item_display(item)
        assert effective == "uploading"
        # 51 MB / 101 MB ~= 50.5% -> 50
        assert 49 <= percent <= 51

    def test_all_file_hosts_done_shows_completed_100(self, tracker):
        tracker._main_window.queue_manager.store.get_file_host_uploads.return_value = [
            {
                "status": "completed",
                "total_bytes": 50_000_000,
                "uploaded_bytes": 50_000_000,
                "file_size": 50_000_000,
                "deduped": False,
            },
            {
                "status": "pending",
                "total_bytes": 0,
                "uploaded_bytes": 0,
                "file_size": 20_000_000,
                "deduped": True,  # deduped counts as done
            },
        ]
        item = GalleryQueueItem(path="/g")
        item.status = "completed"
        item.total_size = 1_000_000
        percent, effective = tracker.compute_item_display(item)
        assert effective == "completed"
        assert percent == 100

    def test_completed_with_inflight_never_reaches_100(self, tracker):
        """Guard rail: while file host is still uploading, percent stays < 100
        so the bar doesn't look stuck-at-full with a spinner."""
        tracker._main_window.queue_manager.store.get_file_host_uploads.return_value = [
            {
                "status": "uploading",
                "total_bytes": 100,
                "uploaded_bytes": 100,  # reports 100% but status is still 'uploading'
                "file_size": 100,
                "deduped": False,
            }
        ]
        item = GalleryQueueItem(path="/g")
        item.status = "completed"
        item.total_size = 100
        percent, effective = tracker.compute_item_display(item)
        assert effective == "uploading"
        assert percent == 99

    def test_pending_item_stays_pending(self, tracker):
        item = GalleryQueueItem(path="/g")
        item.status = "pending"
        item.total_size = 1_000_000
        percent, effective = tracker.compute_item_display(item)
        assert effective == "pending"
        assert percent == 0

    def test_cancelled_file_host_does_not_block_completed(self, tracker):
        """A cancelled file host row should let the gallery read as
        Completed at 100% rather than getting stuck at 'uploading'."""
        tracker._main_window.queue_manager.store.get_file_host_uploads.return_value = [
            {
                "status": "completed",
                "total_bytes": 50_000_000,
                "uploaded_bytes": 50_000_000,
                "file_size": 50_000_000,
                "deduped": False,
            },
            {
                "status": "cancelled",
                "total_bytes": 30_000_000,
                "uploaded_bytes": 10_000_000,
                "file_size": 30_000_000,
                "deduped": False,
            },
        ]
        item = GalleryQueueItem(path="/g")
        item.status = "completed"
        item.total_size = 1_000_000
        percent, effective = tracker.compute_item_display(item)
        assert effective == "completed"
        assert percent == 100

    def test_blocked_file_host_does_not_block_completed(self, tracker):
        """A blocked file host row should let the gallery read as Completed
        once the rest of the work is done -- otherwise galleries with one
        blocked host stay 'uploading' indefinitely."""
        tracker._main_window.queue_manager.store.get_file_host_uploads.return_value = [
            {
                "status": "completed",
                "total_bytes": 50_000_000,
                "uploaded_bytes": 50_000_000,
                "file_size": 50_000_000,
                "deduped": False,
            },
            {
                "status": "blocked",
                "total_bytes": 0,
                "uploaded_bytes": 0,
                "file_size": 30_000_000,
                "deduped": False,
            },
        ]
        item = GalleryQueueItem(path="/g")
        item.status = "completed"
        item.total_size = 1_000_000
        percent, effective = tracker.compute_item_display(item)
        assert effective == "completed"
        assert percent == 100

    def test_failed_file_host_shows_hosts_failed(self, tracker):
        """A 'failed' row is final (workers retry before writing it), so the
        gallery is done but not clean: never a checkmark, never a forever spinner."""
        tracker._main_window.queue_manager.store.get_file_host_uploads.return_value = [
            {
                "host_name": "filedot",
                "status": "failed",
                "total_bytes": 100_000_000,
                "uploaded_bytes": 20_000_000,
                "file_size": 100_000_000,
                "deduped": False,
            },
        ]
        item = GalleryQueueItem(path="/g")
        item.status = "completed"
        item.total_size = 1_000_000
        percent, effective = tracker.compute_item_display(item)
        assert effective == "hosts_failed"

    def test_failed_family_host_waits_for_hash_retry(self, tracker, monkeypatch):
        """A failed FileBoom head row is retried from TezFiles' copy, so not final yet."""
        monkeypatch.setattr(
            "src.core.file_host_settlement.is_family_dedup_enabled", lambda: True)
        tracker._main_window.queue_manager.store.get_file_host_uploads.return_value = [
            {"host_name": "tezfiles", "status": "completed", "part_number": 0},
            {"host_name": "fileboom", "status": "failed", "part_number": 0},
        ]
        item = GalleryQueueItem(path="/g")
        item.status = "completed"
        _, effective = tracker.compute_item_display(item)
        assert effective == "uploading"


class TestDisplayStatus:
    """display_status() is what every part of the row shows."""

    def _tracker_with(self, rows_by_path):
        mw = _make_main_window()
        store = mw.queue_manager.store
        # The real query keys its result by os.path.normpath(path).
        store.get_file_host_uploads_for_paths = MagicMock(
            side_effect=lambda paths: {os.path.normpath(p): rows_by_path.get(p, [])
                                       for p in paths})
        store.get_file_host_uploads = MagicMock(
            side_effect=lambda p: rows_by_path.get(p, []))
        items = {}
        for path in rows_by_path:
            item = GalleryQueueItem(path=path)
            item.status = "completed"
            items[path] = item
        mw.queue_manager.items = items
        return ProgressTracker(mw), items, store

    def test_completed_with_pending_host_shows_uploading(self):
        tracker, items, _ = self._tracker_with({
            "/a": [{"host_name": "fileboom", "status": "pending"}],
            "/b": [{"host_name": "fileboom", "status": "completed"}],
        })
        assert tracker.display_status(items["/a"]) == "uploading"
        assert tracker.display_status(items["/b"]) == "completed"

    def test_first_lookup_primes_all_rows_in_one_query(self):
        tracker, items, store = self._tracker_with({"/a": [], "/b": [], "/c": []})
        for item in items.values():
            tracker.display_status(item)
        store.get_file_host_uploads_for_paths.assert_called_once()
        store.get_file_host_uploads.assert_not_called()

    def test_refresh_updates_the_shown_status(self):
        rows = {"/a": [{"host_name": "fileboom", "status": "uploading"}]}
        tracker, items, _ = self._tracker_with(rows)
        assert tracker.display_status(items["/a"]) == "uploading"
        rows["/a"][0]["status"] = "completed"
        tracker.compute_item_display(items["/a"])
        assert tracker.display_status(items["/a"]) == "completed"

    def test_non_completed_status_passes_through(self):
        tracker, items, store = self._tracker_with({"/a": []})
        items["/a"].status = "ready"
        assert tracker.display_status(items["/a"]) == "ready"
        store.get_file_host_uploads_for_paths.assert_not_called()
