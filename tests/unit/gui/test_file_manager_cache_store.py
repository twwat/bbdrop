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
