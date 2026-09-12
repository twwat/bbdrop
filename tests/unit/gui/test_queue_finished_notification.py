"""Tests for the 'queue finished' notification gate.

`_on_upload_worker_finished` is wired to `gallery_completed` /
`gallery_failed` -- per-gallery signals, not a per-queue one. It fired
`queue_finished` every time no item was in ('queued', 'uploading'), which
meant:

  * it announced "done" while file host uploads were still in flight, and
  * it re-announced after each subsequent gallery.

The 1500ms notification debounce didn't help, since galleries finish tens of
seconds apart. These tests pin the fix: file host work counts as outstanding,
and the notification fires at most once per upload run.
"""

import pytest
from unittest.mock import MagicMock

from src.gui.worker_signal_handler import WorkerSignalHandler


def _item(path, status="completed"):
    it = MagicMock()
    it.path = path
    it.status = status
    return it


def _row(status="completed", deduped=0):
    return {"status": status, "deduped": deduped}


def _make_handler(items, rows_by_path=None):
    mw = MagicMock()
    mw.queue_manager.get_all_items.return_value = items
    mw.queue_manager.store.get_all_file_host_uploads_batch.return_value = (
        rows_by_path or {}
    )
    handler = WorkerSignalHandler.__new__(WorkerSignalHandler)
    handler._main_window = mw
    handler._queue_finished_notified = False
    return handler, mw


def _notified(mw):
    return [c.args[0] for c in mw.notification_manager.notify.call_args_list]


class TestQueueFinishedGate:
    @pytest.mark.unit
    def test_fires_when_everything_is_done(self):
        handler, mw = _make_handler(
            [_item("/g1"), _item("/g2")],
            {"/g1": [_row()], "/g2": [_row()]},
        )
        handler._maybe_notify_queue_finished()
        assert _notified(mw) == ["queue_finished"]

    @pytest.mark.unit
    def test_suppressed_while_image_upload_active(self):
        handler, mw = _make_handler([_item("/g1", "uploading"), _item("/g2")])
        handler._maybe_notify_queue_finished()
        assert _notified(mw) == []

    @pytest.mark.unit
    @pytest.mark.parametrize("status", ["pending", "uploading"])
    def test_suppressed_while_file_host_upload_active(self, status):
        """The reported bug: images done, filedot still uploading."""
        handler, mw = _make_handler(
            [_item("/g1"), _item("/g2")],
            {"/g1": [_row()], "/g2": [_row(status=status)]},
        )
        handler._maybe_notify_queue_finished()
        assert _notified(mw) == [], f"announced done with a {status} file host row"

    @pytest.mark.unit
    def test_fires_only_once_per_run(self):
        """Repeated per-gallery signals must not re-announce."""
        handler, mw = _make_handler([_item("/g1")], {"/g1": [_row()]})
        for _ in range(5):
            handler._maybe_notify_queue_finished()
        assert _notified(mw) == ["queue_finished"]

    @pytest.mark.unit
    def test_stale_rows_for_galleries_not_in_queue_are_ignored(self):
        """A pending row for some other gallery must not suppress forever.

        The batch query returns every gallery in the DB (~1700 here), many
        with old rows. Only galleries actually in the queue count.
        """
        handler, mw = _make_handler(
            [_item("/g1")],
            {"/g1": [_row()], "/some-old-gallery": [_row(status="pending")]},
        )
        handler._maybe_notify_queue_finished()
        assert _notified(mw) == ["queue_finished"]

    @pytest.mark.unit
    def test_deduped_row_counts_as_done(self):
        handler, mw = _make_handler(
            [_item("/g1")],
            {"/g1": [_row(status="pending", deduped=1)]},
        )
        handler._maybe_notify_queue_finished()
        assert _notified(mw) == ["queue_finished"]

    @pytest.mark.unit
    def test_failed_file_host_row_does_not_block_forever(self):
        """A permanently failed upload still lets the run be 'finished'."""
        handler, mw = _make_handler([_item("/g1")], {"/g1": [_row(status="failed")]})
        handler._maybe_notify_queue_finished()
        assert _notified(mw) == ["queue_finished"]

    @pytest.mark.unit
    def test_db_failure_does_not_suppress_notification(self):
        handler, mw = _make_handler([_item("/g1")])
        mw.queue_manager.store.get_all_file_host_uploads_batch.side_effect = RuntimeError("db")
        handler._maybe_notify_queue_finished()
        assert _notified(mw) == ["queue_finished"]

    @pytest.mark.unit
    def test_guard_resets_for_a_new_run(self):
        handler, mw = _make_handler([_item("/g1")], {"/g1": [_row()]})
        handler._maybe_notify_queue_finished()
        handler._queue_finished_notified = False  # what start_worker does
        handler._maybe_notify_queue_finished()
        assert _notified(mw) == ["queue_finished", "queue_finished"]
