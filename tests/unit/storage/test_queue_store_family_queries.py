"""Tests for QueueStore family-aware query helpers."""
import sqlite3
import tempfile
from pathlib import Path

import pytest

from src.storage.database import QueueStore


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as d:
        yield QueueStore(str(Path(d) / "test.db"))


def _set_md5_and_complete(store, upload_id, md5, file_name):
    store.update_file_host_upload(
        upload_id,
        status="completed",
        md5_hash=md5,
        file_name=file_name,
    )


class TestGetFamilyCompletedParts:
    def test_returns_completed_sibling_parts_ordered(self, store):
        path = "/tmp/g"
        a0 = store.add_file_host_upload(path, "keep2share", status="completed", part_number=0)
        a1 = store.add_file_host_upload(path, "keep2share", status="completed", part_number=1)
        a2 = store.add_file_host_upload(path, "keep2share", status="completed", part_number=2)
        _set_md5_and_complete(store, a0, "m0", "part0.zip")
        _set_md5_and_complete(store, a1, "m1", "part1.zip")
        _set_md5_and_complete(store, a2, "m2", "part2.zip")

        gallery_fk = store.get_file_host_uploads(path)[0]["gallery_fk"]
        parts = store.get_family_completed_parts(gallery_fk, "k2s")

        assert [p["part_number"] for p in parts] == [0, 1, 2]
        assert [p["md5_hash"] for p in parts] == ["m0", "m1", "m2"]
        assert [p["file_name"] for p in parts] == ["part0.zip", "part1.zip", "part2.zip"]

    def test_ignores_non_completed_rows(self, store):
        path = "/tmp/g2"
        a0 = store.add_file_host_upload(path, "keep2share", status="completed", part_number=0)
        store.add_file_host_upload(path, "keep2share", status="failed", part_number=1)
        store.add_file_host_upload(path, "keep2share", status="pending", part_number=2)
        _set_md5_and_complete(store, a0, "m0", "part0.zip")

        gallery_fk = store.get_file_host_uploads(path)[0]["gallery_fk"]
        parts = store.get_family_completed_parts(gallery_fk, "k2s")
        assert len(parts) == 1
        assert parts[0]["part_number"] == 0

    def test_only_within_family(self, store):
        path = "/tmp/g3"
        a0 = store.add_file_host_upload(path, "keep2share", status="completed", part_number=0)
        r0 = store.add_file_host_upload(path, "rapidgator", status="completed", part_number=0)
        _set_md5_and_complete(store, a0, "m0", "part0.zip")
        _set_md5_and_complete(store, r0, "xx", "part0.zip")

        gallery_fk = store.get_file_host_uploads(path)[0]["gallery_fk"]
        parts = store.get_family_completed_parts(gallery_fk, "k2s")
        assert len(parts) == 1
        assert parts[0]["host_name"] == "keep2share"

    def test_returns_row_without_md5_for_refetch(self, store):
        """Rows without md5 are included so siblings can re-fetch from the API."""
        path = "/tmp/g4"
        a0 = store.add_file_host_upload(path, "keep2share", status="completed", part_number=0)
        # Deliberately do NOT set md5_hash — sibling should still see this row

        gallery_fk = store.get_file_host_uploads(path)[0]["gallery_fk"]
        parts = store.get_family_completed_parts(gallery_fk, "k2s")
        assert len(parts) == 1
        assert parts[0]["md5_hash"] is None

    def test_prefers_row_with_md5_over_without(self, store):
        """When both rows exist for same part, prefer the one with md5."""
        path = "/tmp/g4b"
        a0 = store.add_file_host_upload(path, "keep2share", status="completed", part_number=0)
        b0 = store.add_file_host_upload(path, "fileboom", status="completed", part_number=0)
        # Only fileboom has md5
        _set_md5_and_complete(store, b0, "fb_md5", "part0.zip")

        gallery_fk = store.get_file_host_uploads(path)[0]["gallery_fk"]
        parts = store.get_family_completed_parts(gallery_fk, "k2s")
        assert len(parts) == 1
        assert parts[0]["host_name"] == "fileboom"
        assert parts[0]["md5_hash"] == "fb_md5"

    def test_unknown_family_returns_empty(self, store):
        path = "/tmp/g5"
        a0 = store.add_file_host_upload(path, "keep2share", status="completed", part_number=0)
        _set_md5_and_complete(store, a0, "m0", "part0.zip")
        gallery_fk = store.get_file_host_uploads(path)[0]["gallery_fk"]
        assert store.get_family_completed_parts(gallery_fk, "nonexistent") == []

    def test_prefers_highest_priority_host_when_multiple_succeeded(self, store):
        path = "/tmp/g6"
        # Both K2S and FileBoom have completed uploads
        a0 = store.add_file_host_upload(path, "keep2share", status="completed", part_number=0)
        b0 = store.add_file_host_upload(path, "fileboom", status="completed", part_number=0)
        _set_md5_and_complete(store, a0, "m0_k2s", "part0.zip")
        _set_md5_and_complete(store, b0, "m0_fb", "part0.zip")

        gallery_fk = store.get_file_host_uploads(path)[0]["gallery_fk"]
        parts = store.get_family_completed_parts(gallery_fk, "k2s")
        # Should return just one row per part_number, preferring the higher-priority host
        assert len(parts) == 1
        assert parts[0]["host_name"] == "keep2share"
        assert parts[0]["md5_hash"] == "m0_k2s"


class TestAddFileHostUploadFamilyParams:
    def test_add_with_blocked_by_and_dedup_only(self, store):
        primary_id = store.add_file_host_upload(
            gallery_path="/tmp/fx",
            host_name="keep2share",
            status="pending",
        )
        secondary_id = store.add_file_host_upload(
            gallery_path="/tmp/fx",
            host_name="fileboom",
            status="blocked",
            blocked_by_upload_id=primary_id,
        )
        retry_id = store.add_file_host_upload(
            gallery_path="/tmp/fx",
            host_name="tezfiles",
            status="pending",
            dedup_only=1,
        )
        assert all([primary_id, secondary_id, retry_id])


class TestGetPendingReturnsDedupOnly:
    def test_pending_row_includes_dedup_only_field(self, store):
        store.add_file_host_upload(
            gallery_path="/tmp/fy",
            host_name="fileboom",
            status="pending",
            dedup_only=1,
        )
        rows = store.get_pending_file_host_uploads(host_name="fileboom")
        assert len(rows) == 1
        assert rows[0]["dedup_only"] == 1
        assert rows[0]["blocked_by_upload_id"] is None

    def test_pending_row_defaults_dedup_only_to_zero(self, store):
        store.add_file_host_upload(
            gallery_path="/tmp/fz",
            host_name="fileboom",
            status="pending",
        )
        rows = store.get_pending_file_host_uploads(host_name="fileboom")
        assert len(rows) == 1
        assert rows[0]["dedup_only"] == 0


class TestGetFileHostPendingStats:
    """get_file_host_pending_stats must count blocked rows alongside pending/uploading."""

    def test_counts_pending_and_uploading(self, store):
        path = "/tmp/stats1"
        store.add_file_host_upload(path, "keep2share", status="pending")
        uid = store.add_file_host_upload(path, "keep2share", status="pending", part_number=1)
        store.update_file_host_upload(uid, status="uploading")
        result = store.get_file_host_pending_stats("keep2share")
        assert result["files"] == 2

    def test_blocked_rows_included_in_count(self, store):
        """A blocked secondary should count as queued work, not be invisible."""
        path = "/tmp/stats2"
        primary_id = store.add_file_host_upload(path, "keep2share", status="pending")
        store.add_file_host_upload(
            path, "fileboom", status="blocked", blocked_by_upload_id=primary_id
        )
        k2s = store.get_file_host_pending_stats("keep2share")
        fboom = store.get_file_host_pending_stats("fileboom")
        # Primary pending visible to its own host stats
        assert k2s["files"] == 1
        # Blocked secondary visible to fileboom's stats
        assert fboom["files"] == 1

    def test_completed_and_failed_rows_excluded(self, store):
        path = "/tmp/stats3"
        cid = store.add_file_host_upload(path, "keep2share", status="pending")
        fid = store.add_file_host_upload(path, "keep2share", status="pending", part_number=1)
        store.update_file_host_upload(cid, status="completed")
        store.update_file_host_upload(fid, status="failed")
        result = store.get_file_host_pending_stats("keep2share")
        assert result["files"] == 0
