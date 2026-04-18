"""Unit tests for file_manager_cache_store."""
import os
import pytest
from src.network.file_manager.client import FileInfo, FileListResult
from src.gui import file_manager_cache_store as store


@pytest.fixture
def tmp_cache_db(tmp_path, monkeypatch):
    """Point the store at a temp DB for isolation."""
    path = tmp_path / "file_manager_cache.db"
    monkeypatch.setattr(store, "_db_path", lambda: str(path))
    yield str(path)


def test_load_all_returns_empty_dict_for_unknown_host(tmp_cache_db):
    assert store.load_all("never_seen_host") == {}


def test_load_all_creates_db_file_on_first_access(tmp_cache_db):
    assert not os.path.exists(tmp_cache_db)
    store.load_all("rapidgator")
    assert os.path.exists(tmp_cache_db)


from datetime import datetime, timezone
from src.network.file_manager.client import FileInfo, FileListResult


def _sample_result() -> FileListResult:
    return FileListResult(
        files=[
            FileInfo(
                id="abc",
                name="photo.jpg",
                is_folder=False,
                size=1024,
                created=datetime(2025, 1, 15, 12, 30, 0, tzinfo=timezone.utc),
                access="public",
                is_available=True,
                md5="deadbeef",
                download_count=5,
                content_type="image/jpeg",
                parent_id="/",
                metadata={"nb_downloads": 5, "url": "https://example/abc"},
            ),
            FileInfo(
                id="folder1",
                name="pics",
                is_folder=True,
                created=None,
                parent_id="/",
                metadata={"nb_files": 10, "size_files": 999999},
            ),
        ],
        total=2,
        page=1,
        per_page=100,
    )


def test_save_then_load_all_roundtrips_result(tmp_cache_db):
    result = _sample_result()
    store.save("rapidgator", "/", result, 1_700_000_000.0)

    loaded = store.load_all("rapidgator")
    assert "/" in loaded
    got, fetched_at = loaded["/"]
    assert fetched_at == 1_700_000_000.0
    assert got.total == 2
    assert got.page == 1
    assert got.per_page == 100
    assert len(got.files) == 2

    file0 = got.files[0]
    assert file0.id == "abc"
    assert file0.name == "photo.jpg"
    assert file0.size == 1024
    assert file0.md5 == "deadbeef"
    assert file0.content_type == "image/jpeg"
    assert file0.created == datetime(2025, 1, 15, 12, 30, 0, tzinfo=timezone.utc)
    assert file0.metadata == {"nb_downloads": 5, "url": "https://example/abc"}

    folder0 = got.files[1]
    assert folder0.is_folder is True
    assert folder0.metadata == {"nb_files": 10, "size_files": 999999}


def test_save_upserts_on_conflict(tmp_cache_db):
    r1 = _sample_result()
    store.save("rapidgator", "/", r1, 1000.0)

    r2 = FileListResult(files=[], total=0, page=1, per_page=100)
    store.save("rapidgator", "/", r2, 2000.0)

    loaded = store.load_all("rapidgator")
    got, fetched_at = loaded["/"]
    assert fetched_at == 2000.0
    assert got.total == 0


def test_save_multiple_hosts_isolated(tmp_cache_db):
    r = _sample_result()
    store.save("rapidgator", "/", r, 1.0)
    store.save("keep2share", "/", r, 2.0)

    assert "/" in store.load_all("rapidgator")
    assert "/" in store.load_all("keep2share")
    assert store.load_all("filedot") == {}


def test_load_all_discards_corrupt_row(tmp_cache_db):
    r = _sample_result()
    store.save("rapidgator", "/", r, 1.0)

    # Inject corrupt JSON directly.
    import sqlite3
    conn = sqlite3.connect(tmp_cache_db)
    conn.execute(
        "INSERT INTO cache (host_name, folder_id, data_json, fetched_at) VALUES (?, ?, ?, ?)",
        ("rapidgator", "/bad", "{not json", 2.0),
    )
    conn.commit()
    conn.close()

    loaded = store.load_all("rapidgator")
    assert "/" in loaded
    assert "/bad" not in loaded  # corrupt row skipped

    # And the next load confirms it was deleted, not re-discovered.
    loaded2 = store.load_all("rapidgator")
    assert "/bad" not in loaded2
