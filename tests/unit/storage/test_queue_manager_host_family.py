"""Tests for family-aware batch enqueueing of file host uploads."""
import os
import tempfile
from pathlib import Path

import pytest

from src.storage.database import QueueStore
from src.storage.queue_manager import queue_file_host_uploads_for_gallery


def _np(path: str) -> str:
    """Normalize a POSIX test literal to this platform's path form so it
    matches what QueueStore.add_file_host_upload actually stores."""
    return os.path.normpath(path)


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as d:
        yield QueueStore(str(Path(d) / "test.db"))


def _upload_by_host(store, gallery_path, host):
    rows = store.get_file_host_uploads(gallery_path)
    return next((r for r in rows if r["host_name"] == host), None)


class TestFamilyBatchEnqueue:
    def test_single_family_host_created_as_plain_pending(self, store):
        path = _np("/tmp/g1")
        queue_file_host_uploads_for_gallery(
            store,
            gallery_path=path,
            host_ids=["keep2share"],
            family_dedup_enabled=True,
        )
        row = _upload_by_host(store, path, "keep2share")
        assert row["status"] == "pending"
        assert row["blocked_by_upload_id"] is None

    def test_full_family_creates_one_primary_two_blocked(self, store):
        path = _np("/tmp/g2")
        queue_file_host_uploads_for_gallery(
            store,
            gallery_path=path,
            host_ids=["keep2share", "fileboom", "tezfiles"],
            family_dedup_enabled=True,
        )
        k2s = _upload_by_host(store, path, "keep2share")
        fb = _upload_by_host(store, path, "fileboom")
        tf = _upload_by_host(store, path, "tezfiles")
        assert k2s["status"] == "pending"
        assert k2s["blocked_by_upload_id"] is None
        assert fb["status"] == "blocked"
        assert fb["blocked_by_upload_id"] == k2s["id"]
        assert tf["status"] == "blocked"
        assert tf["blocked_by_upload_id"] == k2s["id"]

    def test_family_without_highest_priority_picks_next(self, store):
        path = _np("/tmp/g3")
        queue_file_host_uploads_for_gallery(
            store,
            gallery_path=path,
            host_ids=["fileboom", "tezfiles"],
            family_dedup_enabled=True,
        )
        fb = _upload_by_host(store, path, "fileboom")
        tf = _upload_by_host(store, path, "tezfiles")
        assert fb["status"] == "pending"
        assert fb["blocked_by_upload_id"] is None
        assert tf["status"] == "blocked"
        assert tf["blocked_by_upload_id"] == fb["id"]

    def test_mixed_family_and_non_family(self, store):
        path = _np("/tmp/g4")
        queue_file_host_uploads_for_gallery(
            store,
            gallery_path=path,
            host_ids=["keep2share", "fileboom", "rapidgator"],
            family_dedup_enabled=True,
        )
        k2s = _upload_by_host(store, path, "keep2share")
        fb = _upload_by_host(store, path, "fileboom")
        rg = _upload_by_host(store, path, "rapidgator")
        assert k2s["status"] == "pending"
        assert fb["status"] == "blocked"
        assert fb["blocked_by_upload_id"] == k2s["id"]
        assert rg["status"] == "pending"
        assert rg["blocked_by_upload_id"] is None

    def test_feature_disabled_all_pending(self, store):
        path = _np("/tmp/g5")
        queue_file_host_uploads_for_gallery(
            store,
            gallery_path=path,
            host_ids=["keep2share", "fileboom", "tezfiles"],
            family_dedup_enabled=False,
        )
        for host in ("keep2share", "fileboom", "tezfiles"):
            row = _upload_by_host(store, path, host)
            assert row["status"] == "pending"
            assert row["blocked_by_upload_id"] is None

    def test_returns_upload_id_map(self, store):
        result = queue_file_host_uploads_for_gallery(
            store,
            gallery_path="/tmp/g6",
            host_ids=["keep2share", "fileboom"],
            family_dedup_enabled=True,
        )
        assert "keep2share" in result
        assert "fileboom" in result
        assert result["keep2share"] > 0
        assert result["fileboom"] > 0

    def test_primary_insertion_failure_falls_back_to_plain_pending(self, store, monkeypatch):
        """When primary add_file_host_upload returns None, all members get plain pending
        rather than orphaned blocked rows with None blocked_by_upload_id."""
        original = store.add_file_host_upload
        call_count = {"n": 0}

        def fail_first_call(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return None  # Simulate primary insertion failure
            return original(*args, **kwargs)

        monkeypatch.setattr(store, "add_file_host_upload", fail_first_call)

        path = _np("/tmp/gx")
        queue_file_host_uploads_for_gallery(
            store,
            gallery_path=path,
            host_ids=["keep2share", "fileboom", "tezfiles"],
            family_dedup_enabled=True,
        )

        rows = store.get_file_host_uploads(path)
        # Primary insertion failed; keep2share should not be in the results.
        # Fallback: fileboom + tezfiles created as plain pending.
        non_primary_rows = [r for r in rows if r["host_name"] in ("fileboom", "tezfiles")]
        assert len(non_primary_rows) == 2
        for r in non_primary_rows:
            assert r["status"] == "pending"
            assert r["blocked_by_upload_id"] is None
