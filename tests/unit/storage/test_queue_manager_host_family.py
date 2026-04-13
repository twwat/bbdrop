"""Tests for family-aware batch enqueueing of file host uploads."""
import tempfile
from pathlib import Path

import pytest

from src.storage.database import QueueStore
from src.storage.queue_manager import queue_file_host_uploads_for_gallery


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as d:
        yield QueueStore(str(Path(d) / "test.db"))


def _upload_by_host(store, gallery_path, host):
    rows = store.get_file_host_uploads(gallery_path)
    return next((r for r in rows if r["host_name"] == host), None)


class TestFamilyBatchEnqueue:
    def test_single_family_host_created_as_plain_pending(self, store):
        queue_file_host_uploads_for_gallery(
            store,
            gallery_path="/tmp/g1",
            host_ids=["keep2share"],
            family_dedup_enabled=True,
        )
        row = _upload_by_host(store, "/tmp/g1", "keep2share")
        assert row["status"] == "pending"
        assert row["blocked_by_upload_id"] is None

    def test_full_family_creates_one_primary_two_blocked(self, store):
        queue_file_host_uploads_for_gallery(
            store,
            gallery_path="/tmp/g2",
            host_ids=["keep2share", "fileboom", "tezfiles"],
            family_dedup_enabled=True,
        )
        k2s = _upload_by_host(store, "/tmp/g2", "keep2share")
        fb = _upload_by_host(store, "/tmp/g2", "fileboom")
        tf = _upload_by_host(store, "/tmp/g2", "tezfiles")
        assert k2s["status"] == "pending"
        assert k2s["blocked_by_upload_id"] is None
        assert fb["status"] == "blocked"
        assert fb["blocked_by_upload_id"] == k2s["id"]
        assert tf["status"] == "blocked"
        assert tf["blocked_by_upload_id"] == k2s["id"]

    def test_family_without_highest_priority_picks_next(self, store):
        queue_file_host_uploads_for_gallery(
            store,
            gallery_path="/tmp/g3",
            host_ids=["fileboom", "tezfiles"],
            family_dedup_enabled=True,
        )
        fb = _upload_by_host(store, "/tmp/g3", "fileboom")
        tf = _upload_by_host(store, "/tmp/g3", "tezfiles")
        assert fb["status"] == "pending"
        assert fb["blocked_by_upload_id"] is None
        assert tf["status"] == "blocked"
        assert tf["blocked_by_upload_id"] == fb["id"]

    def test_mixed_family_and_non_family(self, store):
        queue_file_host_uploads_for_gallery(
            store,
            gallery_path="/tmp/g4",
            host_ids=["keep2share", "fileboom", "rapidgator"],
            family_dedup_enabled=True,
        )
        k2s = _upload_by_host(store, "/tmp/g4", "keep2share")
        fb = _upload_by_host(store, "/tmp/g4", "fileboom")
        rg = _upload_by_host(store, "/tmp/g4", "rapidgator")
        assert k2s["status"] == "pending"
        assert fb["status"] == "blocked"
        assert fb["blocked_by_upload_id"] == k2s["id"]
        assert rg["status"] == "pending"
        assert rg["blocked_by_upload_id"] is None

    def test_feature_disabled_all_pending(self, store):
        queue_file_host_uploads_for_gallery(
            store,
            gallery_path="/tmp/g5",
            host_ids=["keep2share", "fileboom", "tezfiles"],
            family_dedup_enabled=False,
        )
        for host in ("keep2share", "fileboom", "tezfiles"):
            row = _upload_by_host(store, "/tmp/g5", host)
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
