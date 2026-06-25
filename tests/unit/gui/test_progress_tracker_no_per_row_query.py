from types import SimpleNamespace
from unittest.mock import MagicMock
from src.gui.progress_tracker import ProgressTracker


def _item(path, status="completed", total_size=1000, total_images=10,
          uploaded_images=10, media_type="image"):
    return SimpleNamespace(
        path=path, status=status, total_size=total_size,
        total_images=total_images, uploaded_images=uploaded_images,
        media_type=media_type, screenshot_sheet_path="", progress=0,
    )


def _tracker_with_store():
    mw = MagicMock()
    store = mw.queue_manager.store
    # If the byte-math ever falls back to per-path queries, this is how we'd catch it
    store.get_file_host_uploads.side_effect = AssertionError("per-row query issued!")
    return ProgressTracker(mw), store


def test_compute_work_bytes_with_map_issues_no_per_row_query():
    tracker, store = _tracker_with_store()
    items = [_item("/g1"), _item("/g2")]
    fh_map = {
        "/g1": [{"status": "completed", "total_bytes": 500, "uploaded_bytes": 500,
                 "deduped": False, "file_size": 500}],
        "/g2": [],
    }
    total, uploaded = tracker._compute_work_bytes(items, file_host_map=fh_map)
    # g1: 1000 image + 1000 filehost (effective_total=max(500,500,1000)); g2: 1000 image = 3000 total, fully uploaded
    assert total == 3000 and uploaded == 3000
    store.get_file_host_uploads.assert_not_called()


def test_compute_work_bytes_without_map_uses_scoped_batch_once():
    tracker, store = _tracker_with_store()
    store.get_file_host_uploads_for_paths.return_value = {"/g1": [], "/g2": []}
    items = [_item("/g1"), _item("/g2")]
    tracker._compute_work_bytes(items)
    # exactly one scoped batch call, never the per-path method
    store.get_file_host_uploads_for_paths.assert_called_once()
    store.get_file_host_uploads.assert_not_called()
