"""update_progress_display must survive being wired to a str-emitting signal.

main_window connects gallery_table.tab_changed -- pyqtSignal(str) -- directly
to ProgressTracker.update_progress_display. PyQt binds a signal's arguments to
any slot parameters that will accept them, so the tab NAME lands in
`file_host_map`, which _compute_work_bytes then calls .get() on:

    AttributeError: 'str' object has no attribute 'get'

That crashed on every tab change (crash.log, 2026-09-12 07:41 and 10:05).
The wiring is fixed to discard the argument, and the parameter is also
type-guarded so any other signal wired this way degrades instead of crashing.
"""

import pytest
from unittest.mock import MagicMock

from src.gui.progress_tracker import ProgressTracker
from src.storage.queue_manager import GalleryQueueItem


def _mw(rows_by_path=None):
    mw = MagicMock()
    mw.queue_manager = MagicMock()
    store = MagicMock()
    rows_by_path = rows_by_path or {}
    store.get_file_host_uploads_for_paths = MagicMock(
        side_effect=lambda paths: {k: list(v) for k, v in rows_by_path.items()}
    )
    store.get_file_host_uploads = MagicMock(side_effect=lambda p: [])
    mw.queue_manager.store = store
    return mw


def _items(n, total_size=1_000):
    out = []
    for i in range(n):
        it = GalleryQueueItem(path=f"/g{i}")
        it.status = "completed"
        it.total_size = total_size
        out.append(it)
    return out


@pytest.mark.unit
class TestComputeWorkBytesRejectsNonMapping:

    def test_str_file_host_map_does_not_crash(self):
        """A tab name arriving as file_host_map must not raise."""
        mw = _mw()
        tracker = ProgressTracker(mw)

        total, uploaded = tracker._compute_work_bytes(_items(2), "All Galleries")

        # Degrades to the normal scoped lookup rather than blowing up.
        assert total == uploaded == 2_000

    def test_valid_mapping_still_used(self):
        """The real dict path must keep working unchanged."""
        rows = {"/g0": [{"status": "completed", "total_bytes": 5_000,
                         "uploaded_bytes": 5_000, "file_size": 5_000, "deduped": 0}]}
        mw = _mw(rows)
        tracker = ProgressTracker(mw)

        total, uploaded = tracker._compute_work_bytes(_items(1), rows)

        assert total == 6_000
        assert uploaded == 6_000
