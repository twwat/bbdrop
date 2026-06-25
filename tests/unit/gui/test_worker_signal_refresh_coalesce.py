from unittest.mock import MagicMock
from src.gui.worker_signal_handler import WorkerSignalHandler


def _handler():
    mw = MagicMock()
    mw._get_current_tab_items.return_value = []
    mw.queue_manager.store.get_file_host_uploads_for_paths.return_value = {}
    h = WorkerSignalHandler(mw)
    return h, mw


def test_leading_edge_refreshes_immediately():
    h, mw = _handler()
    h._request_refresh()  # first call after idle -> immediate
    assert mw.progress_tracker.update_progress_display.call_count == 1
    assert h._refresh_cooldown_active is True


def test_calls_during_cooldown_coalesce_to_one_trailing_pass():
    h, mw = _handler()
    h._request_refresh()                         # leading edge (pass #1)
    h._request_refresh()                         # in cooldown -> deferred
    h._request_refresh()                         # in cooldown -> deferred
    assert mw.progress_tracker.update_progress_display.call_count == 1
    assert h._refresh_trailing_pending is True

    h._end_refresh_cooldown()                    # trailing flush (pass #2)
    assert mw.progress_tracker.update_progress_display.call_count == 2

    h._end_refresh_cooldown()                    # nothing pending -> idle
    assert mw.progress_tracker.update_progress_display.call_count == 2
    assert h._refresh_cooldown_active is False


def test_one_scoped_query_per_pass():
    h, mw = _handler()
    store = mw.queue_manager.store
    h._request_refresh()
    assert store.get_file_host_uploads_for_paths.call_count == 1
    store.get_file_host_uploads.assert_not_called()
