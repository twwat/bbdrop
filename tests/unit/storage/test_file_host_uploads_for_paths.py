import os
import pytest
from src.storage.database import QueueStore


@pytest.fixture
def store(tmp_path):
    return QueueStore(db_path=str(tmp_path / "t.db"))


def test_for_paths_groups_and_matches_single_query(store, tmp_path):
    g1 = str(tmp_path / "g1"); os.makedirs(g1)
    g2 = str(tmp_path / "g2"); os.makedirs(g2)
    store.add_file_host_upload(g1, "rapidgator", status="completed")
    store.add_file_host_upload(g1, "keep2share", status="uploading")
    store.add_file_host_upload(g2, "fileboom", status="pending")

    result = store.get_file_host_uploads_for_paths([g1, g2])

    # One entry per requested path, grouped correctly
    assert set(result.keys()) == {os.path.normpath(g1), os.path.normpath(g2)}
    assert {r["host_name"] for r in result[os.path.normpath(g1)]} == {"rapidgator", "keep2share"}
    assert len(result[os.path.normpath(g2)]) == 1

    # Identical row dicts to the per-path method (drop-in replacement)
    assert result[os.path.normpath(g1)] == store.get_file_host_uploads(g1)
    # Full field set present
    row = result[os.path.normpath(g1)][0]
    for key in ("status", "deduped", "file_size", "total_bytes",
                "uploaded_bytes", "blocked_by_upload_id", "dedup_only"):
        assert key in row


def test_for_paths_empty_input_returns_empty(store):
    assert store.get_file_host_uploads_for_paths([]) == {}


def test_for_paths_unknown_path_maps_to_empty_list(store, tmp_path):
    missing = str(tmp_path / "nope")
    result = store.get_file_host_uploads_for_paths([missing])
    assert result == {os.path.normpath(missing): []}
