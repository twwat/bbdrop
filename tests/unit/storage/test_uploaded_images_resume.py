"""IMG-5: uploaded-image rows must round-trip so a resume can skip them."""

import threading

import pytest

from src.storage.database import QueueStore


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
