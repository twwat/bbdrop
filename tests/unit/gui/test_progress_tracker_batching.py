"""Regression tests for ProgressTracker file-host row batching.

`_compute_work_bytes` runs on the GUI thread and is rescheduled every 150ms
for the duration of a file host upload. It used to call
`get_file_host_uploads(path)` once per queue item, and every one of those
opens a fresh SQLite connection (four PRAGMAs + a JOIN) -- roughly 0.5ms.
At ~1700 galleries that is ~0.8s of blocking work per pass against a 150ms
schedule, which pins the GUI thread for the whole upload.

These tests pin the fix: one query per pass, regardless of item count.
"""

import pytest
from unittest.mock import MagicMock

from src.gui.progress_tracker import ProgressTracker
from src.storage.queue_manager import GalleryQueueItem


def _row(status="completed", total=1_000, uploaded=1_000, file_size=1_000, deduped=0):
    return {
        "status": status,
        "total_bytes": total,
        "uploaded_bytes": uploaded,
        "file_size": file_size,
        "deduped": deduped,
    }


def _make_main_window(rows_by_path=None):
    mw = MagicMock()
    mw.queue_manager = MagicMock()
    store = MagicMock()
    rows_by_path = rows_by_path or {}
    store.get_file_host_uploads = MagicMock(
        side_effect=lambda p: list(rows_by_path.get(p, []))
    )
    store.get_all_file_host_uploads_batch = MagicMock(
        return_value={k: list(v) for k, v in rows_by_path.items()}
    )
    # The scoped variant is what _compute_work_bytes uses: one query covering
    # exactly the paths on screen, rather than every gallery in the database.
    store.get_file_host_uploads_for_paths = MagicMock(
        side_effect=lambda paths: {
            k: list(v) for k, v in rows_by_path.items() if k in set(paths)
        }
    )
    mw.queue_manager.store = store
    return mw


def _items(n, total_size=1_000_000, status="completed"):
    out = []
    for i in range(n):
        item = GalleryQueueItem(path=f"/g{i}")
        item.status = status
        item.total_size = total_size
        out.append(item)
    return out


class TestComputeWorkBytesBatching:
    @pytest.mark.unit
    def test_single_query_for_many_items(self):
        """One bulk lookup per pass, not one query per item."""
        mw = _make_main_window()
        tracker = ProgressTracker(mw)
        store = mw.queue_manager.store

        tracker._compute_work_bytes(_items(50))

        assert store.get_file_host_uploads.call_count == 0, (
            "per-item query still happening: "
            f"{store.get_file_host_uploads.call_count} calls"
        )
        assert store.get_file_host_uploads_for_paths.call_count == 1

    @pytest.mark.unit
    def test_totals_match_per_item_computation(self):
        """Batching must not change the numbers it produces."""
        rows = {"/g0": [_row(total=5_000, uploaded=5_000, file_size=5_000)]}
        mw = _make_main_window(rows)
        tracker = ProgressTracker(mw)

        items = _items(1, total_size=1_000)
        total, uploaded = tracker._compute_work_bytes(items)

        # image host 1_000 (completed) + file host row 5_000 completed
        assert total == 6_000
        assert uploaded == 6_000

    @pytest.mark.unit
    def test_item_without_file_host_rows_counts_image_bytes_only(self):
        """A gallery missing from the bulk map contributes only image bytes."""
        mw = _make_main_window({"/other": [_row()]})
        tracker = ProgressTracker(mw)

        total, uploaded = tracker._compute_work_bytes(_items(1, total_size=7_000))
        assert total == uploaded == 7_000

    @pytest.mark.unit
    def test_falls_back_cleanly_when_bulk_lookup_unavailable(self):
        """An older/mocked store without the bulk method must not crash."""
        mw = _make_main_window()
        del mw.queue_manager.store.get_file_host_uploads_for_paths
        tracker = ProgressTracker(mw)

        total, uploaded = tracker._compute_work_bytes(_items(3, total_size=1_000))
        assert total == uploaded == 3_000

    @pytest.mark.unit
    def test_bulk_lookup_failure_does_not_break_progress(self):
        """A DB error during the bulk read degrades to image-only bytes."""
        mw = _make_main_window()
        mw.queue_manager.store.get_file_host_uploads_for_paths.side_effect = RuntimeError("db gone")
        tracker = ProgressTracker(mw)

        total, uploaded = tracker._compute_work_bytes(_items(2, total_size=1_000))
        assert total == uploaded == 2_000
