"""IMG-5: uploaded-image rows must round-trip so a resume can skip them."""

import queue
import threading
from unittest.mock import patch

import pytest

from src.storage.database import QueueStore
from src.storage.queue_manager import QueueManager, GalleryQueueItem, _normalize_path
from src.core.constants import QUEUE_STATE_UPLOADING


@pytest.fixture
def store(tmp_path):
    s = QueueStore(db_path=str(tmp_path / "t.db"))
    yield s
    s._executor.shutdown(wait=True)


A = ("a.jpg", {'image_url': 'https://h/i/a', 'thumb_url': 'https://h/t/a.jpg',
               'size_bytes': 10, 'width': 1, 'height': 2})
B = ("b.jpg", {'image_url': 'https://h/i/b', 'thumb_url': '',
               'size_bytes': 20, 'width': 3, 'height': 4})


def _gallery(path, files):
    return {
        'path': path, 'name': 'g', 'status': 'incomplete', 'gallery_id': 'G1',
        'uploaded_images': len(files), 'total_images': 3, 'tab_name': 'Main',
        'uploaded_files': [fname for fname, _ in files],
        'uploaded_images_data': list(files),
    }


def test_get_uploaded_images_round_trips_bulk_upsert(store):
    store.bulk_upsert([_gallery("/g/one", [A, B])])

    rows = store.get_uploaded_images("/g/one")

    assert [fname for fname, _ in rows] == ["a.jpg", "b.jpg"]
    assert rows[0][1] == A[1]
    assert rows[1][1]['thumb_url'] == ''


def test_get_uploaded_images_is_per_gallery(store):
    store.bulk_upsert([_gallery("/g/one", [A]), _gallery("/g/two", [B])])

    assert [fname for fname, _ in store.get_uploaded_images("/g/two")] == ["b.jpg"]


def test_get_uploaded_images_unknown_gallery(store):
    assert store.get_uploaded_images("/g/missing") == []


def test_clear_uploaded_images_only_touches_that_gallery(store):
    store.bulk_upsert([_gallery("/g/one", [A, B]), _gallery("/g/two", [B])])

    store.clear_uploaded_images("/g/one").result(timeout=5)

    assert store.get_uploaded_images("/g/one") == []
    assert len(store.get_uploaded_images("/g/two")) == 1


def test_clear_runs_after_queued_async_save(store):
    gate = threading.Event()
    store._executor.submit(gate.wait, 5)                     # hold the single worker
    store.bulk_upsert_async([_gallery("/g/one", [A, B])])    # stale save, queued

    future = store.clear_uploaded_images("/g/one")
    gate.set()
    future.result(timeout=5)

    assert store.get_uploaded_images("/g/one") == []


@pytest.fixture
def queue_manager(store):
    """Real QueueManager wired to the real (tmp_path) QueueStore above."""
    with patch('src.storage.queue_manager.QueueStore', return_value=store):
        with patch('src.storage.queue_manager.QSettings'):
            manager = QueueManager()
            yield manager
            # Same shutdown sequence as the queue_manager fixture in
            # test_queue_manager.py: stop and join the scan worker before
            # the tmp_path store gets torn down, or Windows leaves the
            # sqlite file handle open.
            manager._scan_worker_running = False
            try:
                manager._scan_queue.put(None, timeout=0.1)
            except (queue.Full, AttributeError):
                pass
            if manager._scan_worker and manager._scan_worker.is_alive():
                manager._scan_worker.join(timeout=3.0)


def test_worker_thread_incomplete_save_persists_uploaded_images(store, queue_manager, qtbot):
    """A worker-thread status save must actually land the uploaded-images
    rows a later resume reads back via get_uploaded_images (IMG-5: proves
    the persistence half, not just the in-memory restore guard)."""
    path = _normalize_path("/g/e2e")
    item = GalleryQueueItem(
        path=path, name="g", status=QUEUE_STATE_UPLOADING,
        gallery_id="G1", uploaded_images=2, total_images=3,
    )
    item.uploaded_files = {"a.jpg", "b.jpg"}
    item.uploaded_images_data = [A, B]
    queue_manager.items[path] = item

    t = threading.Thread(target=queue_manager.update_item_status, args=(path, "incomplete"))
    t.start()
    t.join(timeout=5)

    qtbot.waitUntil(lambda: bool(store.get_uploaded_images(path)), timeout=5000)

    rows = store.get_uploaded_images(path)
    assert [fname for fname, _ in rows] == ["a.jpg", "b.jpg"]
    assert rows[0][1] == A[1]
