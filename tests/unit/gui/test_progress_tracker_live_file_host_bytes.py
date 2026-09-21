"""Unit tests for live file host bytes in the byte-weighted progress percent.

file_host_uploads.uploaded_bytes is only written when a transfer lands, so an
in-flight row contributed its full size to the denominator and nothing to the
numerator -- the percent sat still and then jumped in one lump. ProgressTracker
keeps an in-memory overlay fed by the worker's 4 Hz progress signal; these
tests cover how that overlay feeds _compute_item_work_bytes.
"""

import os

import pytest
from unittest.mock import MagicMock

from src.gui.progress_tracker import ProgressTracker
from src.storage.queue_manager import GalleryQueueItem


@pytest.fixture
def tracker():
    mw = MagicMock()
    mw.queue_manager = MagicMock()
    mw.queue_manager.store = MagicMock()
    mw.queue_manager.store.get_file_host_uploads = MagicMock(return_value=[])
    return ProgressTracker(mw)


def _item(path="/g", total_size=1_000_000, status="completed"):
    item = GalleryQueueItem(path=path)
    item.status = status
    item.total_size = total_size
    return item


def _uploading_row(host="rapidgator", total=100_000_000, uploaded=0):
    return {
        "host_name": host,
        "status": "uploading",
        "total_bytes": total,
        "uploaded_bytes": uploaded,
        "file_size": total,
        "deduped": False,
    }


class TestLiveFileHostBytes:
    def test_in_flight_bytes_count_toward_uploaded(self, tracker):
        item = _item()
        rows = [_uploading_row()]

        tracker.set_file_host_live_bytes("/g", "rapidgator", 40_000_000)

        total, uploaded = tracker._compute_item_work_bytes(item, rows)
        assert total == 101_000_000
        assert uploaded == 41_000_000  # 1 MB image host + 40 MB in flight

    def test_percent_climbs_with_in_flight_bytes(self, tracker):
        item = _item(total_size=0)
        rows = [_uploading_row(total=100_000_000)]

        first, _ = tracker.compute_item_display(item, rows)
        tracker.set_file_host_live_bytes("/g", "rapidgator", 50_000_000)
        second, _ = tracker.compute_item_display(item, rows)

        assert first == 0
        assert second > first

    def test_live_bytes_never_exceed_the_row_total(self, tracker):
        """A stale overlay must not push the gallery past 100%."""
        item = _item()
        rows = [_uploading_row(total=100_000_000)]

        tracker.set_file_host_live_bytes("/g", "rapidgator", 500_000_000)

        total, uploaded = tracker._compute_item_work_bytes(item, rows)
        assert uploaded == total

    def test_persisted_bytes_win_when_larger(self, tracker):
        """A row that already recorded more than the overlay keeps its value."""
        item = _item()
        rows = [_uploading_row(uploaded=60_000_000)]

        tracker.set_file_host_live_bytes("/g", "rapidgator", 10_000_000)

        _, uploaded = tracker._compute_item_work_bytes(item, rows)
        assert uploaded == 61_000_000

    def test_live_bytes_are_per_host(self, tracker):
        item = _item()
        rows = [
            _uploading_row(host="rapidgator", total=100_000_000),
            _uploading_row(host="katfile", total=100_000_000),
        ]

        tracker.set_file_host_live_bytes("/g", "rapidgator", 40_000_000)

        _, uploaded = tracker._compute_item_work_bytes(item, rows)
        assert uploaded == 41_000_000  # katfile contributes nothing

    def test_clearing_live_bytes_drops_the_overlay(self, tracker):
        item = _item()
        rows = [_uploading_row()]
        tracker.set_file_host_live_bytes("/g", "rapidgator", 40_000_000)

        tracker.clear_file_host_live_bytes("/g", "rapidgator")

        _, uploaded = tracker._compute_item_work_bytes(item, rows)
        assert uploaded == 1_000_000

    def test_completed_row_ignores_a_stale_overlay(self, tracker):
        """Once the row is completed it counts in full, overlay or not."""
        item = _item()
        rows = [{
            "host_name": "rapidgator",
            "status": "completed",
            "total_bytes": 100_000_000,
            "uploaded_bytes": 100_000_000,
            "file_size": 100_000_000,
            "deduped": False,
        }]
        tracker.set_file_host_live_bytes("/g", "rapidgator", 40_000_000)

        total, uploaded = tracker._compute_item_work_bytes(item, rows)
        assert total == uploaded == 101_000_000

    def test_part_boundary_does_not_credit_the_new_part_with_the_old_one(self, tracker):
        """Regression: a 1.5 GB gallery split into 3x500 MB parts.

        Part 1 lands (row 'completed'); part 2's row is created 'uploading'.
        The overlay still held part 1's final 500 MB, and effective_total falls
        back to the WHOLE gallery size -- so the cap did not trim it and part 2
        was credited 500 MB it had not sent, making the percent jump then drop.
        The worker now emits a zero-progress tick as each part starts.
        """
        item = _item(total_size=1_500_000_000, status="completed")
        item.total_size = 0  # isolate the file host contribution
        rows = [
            {
                "host_name": "rapidgator", "status": "completed",
                "total_bytes": 500_000_000, "uploaded_bytes": 500_000_000,
                "file_size": 500_000_000, "deduped": False,
            },
            {
                "host_name": "rapidgator", "status": "uploading",
                "total_bytes": 500_000_000, "uploaded_bytes": 0,
                "file_size": 500_000_000, "deduped": False,
            },
        ]
        tracker.set_file_host_live_bytes("/g", "rapidgator", 500_000_000)
        stale_percent, _ = tracker.compute_item_display(item, rows)

        # The zero tick the worker now emits at the start of each part.
        tracker.set_file_host_live_bytes("/g", "rapidgator", 0)
        settled_percent, _ = tracker.compute_item_display(item, rows)

        # The bar used to read 99% (clamped from 100 because work remained)
        # and then fall back to 50% a fraction of a second later.
        assert stale_percent == 99
        assert settled_percent == 50  # part 1 done, part 2 not started
        assert settled_percent < stale_percent

    def test_clear_with_unresolved_path_does_not_miss_the_real_entry(self, tracker):
        """_seed_db_id_path returns '' when a signal carried no path and the
        db_id cache misses. os.path.normpath('') is '.', so a clear keyed on
        the empty path must not quietly pop a phantom entry and leave the real
        one crediting the gallery forever.
        """
        item = _item()
        rows = [_uploading_row()]
        tracker.set_file_host_live_bytes("/g", "rapidgator", 40_000_000)

        tracker.clear_file_host_live_bytes("", "rapidgator")

        # The real entry is untouched by a clear that named no gallery...
        _, uploaded = tracker._compute_item_work_bytes(item, rows)
        assert uploaded == 41_000_000
        # ...and no phantom '.' entry was created either way.
        assert ('.', 'rapidgator') not in tracker._file_host_live_bytes

    def test_set_with_empty_path_records_nothing(self, tracker):
        tracker.set_file_host_live_bytes("", "rapidgator", 40_000_000)
        assert tracker._file_host_live_bytes == {}

    def test_path_separators_do_not_break_the_lookup(self, tracker):
        """Worker signals carry the DB's normalized path; queue items may not."""
        item = _item(path="C:/media/gallery one")
        rows = [_uploading_row()]

        tracker.set_file_host_live_bytes(
            os.path.normpath("C:/media/gallery one"), "rapidgator", 40_000_000
        )

        _, uploaded = tracker._compute_item_work_bytes(item, rows)
        assert uploaded == 41_000_000
