"""Cover results are written straight to the galleries row and cleared by a complete reset."""
import os
import tempfile

import pytest

from src.storage.database import QueueStore

pytestmark = pytest.mark.unit


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield QueueStore(db_path=path)
    try:
        os.unlink(path)
    except OSError:
        pass


def _row(store, path):
    items = {i['path']: i for i in store.load_all_items()}
    return items[path]


def _add(store, path):
    store.bulk_upsert([{
        'path': path, 'name': 'g', 'status': 'queued', 'template_name': 'default',
        'cover_source_path': '/g/cover.jpg', 'cover_host_id': 'imx', 'cover_status': 'pending',
    }])


def test_set_cover_result_updates_only_the_cover_columns(store):
    _add(store, '/g')
    results = [{'status': 'success', 'source_path': '/g/cover.jpg', 'bbcode': 'B'}]
    store.set_cover_result('/g', 'completed', results)

    row = _row(store, '/g')
    assert row['cover_status'] == 'completed'
    assert row['cover_result'] == results
    assert row['cover_source_path'] == '/g/cover.jpg' and row['status'] == 'queued'


def test_set_cover_result_none_clears_results(store):
    _add(store, '/g')
    store.set_cover_result('/g', 'completed', [{'status': 'success', 'source_path': '/g/cover.jpg'}])
    store.set_cover_result('/g', 'pending', None)
    row = _row(store, '/g')
    assert row['cover_result'] is None and row['cover_status'] == 'pending'


def test_set_cover_result_for_unknown_path_is_harmless(store):
    store.set_cover_result('/nope', 'completed', [])
    store.set_cover_result('', 'completed', [])
