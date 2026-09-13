"""A final ordered save must not be overwritten by an older queued async save."""

import threading
import time

import pytest

from src.storage.database import QueueStore, _ConnectionContext


@pytest.fixture
def store(tmp_path):
    s = QueueStore(db_path=str(tmp_path / "t.db"))
    yield s
    s._executor.shutdown(wait=True)


def _gallery(status):
    return {'path': '/g/order', 'name': 'g', 'status': status, 'tab_name': 'Main'}


def _status(store):
    with _ConnectionContext(store.db_path) as conn:
        return conn.execute(
            "SELECT status FROM galleries WHERE path = ?", ('/g/order',)).fetchone()[0]


def test_bulk_upsert_ordered_runs_after_queued_async_saves(store):
    gate = threading.Event()
    store._executor.submit(gate.wait, 5)          # hold the single worker
    store.bulk_upsert_async([_gallery('ready')])  # older snapshot, queued behind it

    saver = threading.Thread(
        target=lambda: store.bulk_upsert_ordered([_gallery('incomplete')]))
    saver.start()
    time.sleep(0.2)
    assert saver.is_alive()  # must still be queued behind the held worker
    gate.set()
    saver.join(10)

    assert not saver.is_alive()
    assert _status(store) == 'incomplete'


def test_bulk_upsert_ordered_after_executor_shutdown(store):
    store._executor.shutdown(wait=True)

    store.bulk_upsert_ordered([_gallery('incomplete')])

    assert _status(store) == 'incomplete'
