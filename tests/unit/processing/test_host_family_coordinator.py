"""Tests for HostFamilyCoordinator — drives the coordinator via host_gallery_settled emits."""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.storage.database import QueueStore
from src.processing.host_family_coordinator import HostFamilyCoordinator


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as d:
        yield QueueStore(str(Path(d) / "test.db"))


@pytest.fixture
def coord(store):
    return HostFamilyCoordinator(queue_store=store)


@pytest.fixture(autouse=True)
def _force_family_dedup_enabled(monkeypatch):
    """Guard against the coordinator reading the real user INI.

    HostFamilyCoordinator.on_host_gallery_settled calls is_family_dedup_enabled()
    which reads ~/.bbdrop/bbdrop.ini. Without this patch, a developer with
    k2s_family_dedup_enabled=false in their INI would see all coordinator tests
    vacuous-pass.
    """
    monkeypatch.setattr(
        "src.processing.host_family_coordinator.is_family_dedup_enabled",
        lambda: True,
    )


def _add_family_rows(store, gallery_path, enabled_hosts):
    from src.storage.queue_manager import queue_file_host_uploads_for_gallery
    return queue_file_host_uploads_for_gallery(
        store, gallery_path=gallery_path, host_ids=enabled_hosts, family_dedup_enabled=True
    )


def _row_status(store, gallery_path, host):
    rows = store.get_file_host_uploads(gallery_path)
    r = next((r for r in rows if r["host_name"] == host), None)
    return r["status"] if r else None


def _row(store, gallery_path, host):
    return next(
        (r for r in store.get_file_host_uploads(gallery_path) if r["host_name"] == host),
        None,
    )


class TestCoordinatorUnblockOnSuccess:
    def test_primary_success_unblocks_secondaries(self, store, coord):
        path = "/tmp/c1"
        ids = _add_family_rows(store, path, ["keep2share", "fileboom", "tezfiles"])
        # Mark primary completed
        store.update_file_host_upload(ids["keep2share"], status="completed", md5_hash="m0")
        gallery_fk = _row(store, path, "keep2share")["gallery_fk"]

        coord.on_host_gallery_settled(gallery_fk, "keep2share", True)

        assert _row_status(store, path, "fileboom") == "pending"
        assert _row_status(store, path, "tezfiles") == "pending"

    def test_success_with_no_family_is_noop(self, store, coord):
        path = "/tmp/c1b"
        store.add_file_host_upload(path, "rapidgator", status="pending")
        gallery_fk = _row(store, path, "rapidgator")["gallery_fk"]
        coord.on_host_gallery_settled(gallery_fk, "rapidgator", True)
        # No errors, nothing changes
        assert _row_status(store, path, "rapidgator") == "pending"


class TestCoordinatorPromoteOnFailure:
    def test_primary_failure_promotes_next_in_chain(self, store, coord):
        path = "/tmp/c2"
        ids = _add_family_rows(store, path, ["keep2share", "fileboom", "tezfiles"])
        store.update_file_host_upload(ids["keep2share"], status="failed")
        gallery_fk = _row(store, path, "keep2share")["gallery_fk"]

        coord.on_host_gallery_settled(gallery_fk, "keep2share", False)

        # fileboom promoted
        fb = _row(store, path, "fileboom")
        assert fb["status"] == "pending"
        assert fb["blocked_by_upload_id"] is None
        # tezfiles reassigned to the new primary
        tf = _row(store, path, "tezfiles")
        assert tf["status"] == "blocked"
        assert tf["blocked_by_upload_id"] == fb["id"]

    def test_promoted_primary_success_retries_original_primary(self, store, coord):
        path = "/tmp/c3"
        ids = _add_family_rows(store, path, ["keep2share", "fileboom", "tezfiles"])
        gallery_fk = _row(store, path, "keep2share")["gallery_fk"]

        # Primary fails, promote
        store.update_file_host_upload(ids["keep2share"], status="failed")
        coord.on_host_gallery_settled(gallery_fk, "keep2share", False)

        # Promoted primary succeeds
        fb_id = _row(store, path, "fileboom")["id"]
        store.update_file_host_upload(fb_id, status="completed", md5_hash="m0")
        coord.on_host_gallery_settled(gallery_fk, "fileboom", True)

        # Original primary should be flipped to dedup_only retry
        k2s_row = _row(store, path, "keep2share")
        assert k2s_row["status"] == "pending"
        assert k2s_row["dedup_only"] == 1
        assert k2s_row["blocked_by_upload_id"] is None
        # Remaining blocked (tezfiles) should be unblocked
        tf_row = _row(store, path, "tezfiles")
        assert tf_row["status"] == "pending"

    def test_all_primaries_fail_leaves_all_failed(self, store, coord):
        path = "/tmp/c4"
        ids = _add_family_rows(store, path, ["keep2share", "fileboom", "tezfiles"])
        gallery_fk = _row(store, path, "keep2share")["gallery_fk"]

        # K2S fails → promote fileboom
        store.update_file_host_upload(ids["keep2share"], status="failed")
        coord.on_host_gallery_settled(gallery_fk, "keep2share", False)

        # FileBoom fails → promote tezfiles
        store.update_file_host_upload(_row(store, path, "fileboom")["id"], status="failed")
        coord.on_host_gallery_settled(gallery_fk, "fileboom", False)

        # TezFiles fails
        store.update_file_host_upload(_row(store, path, "tezfiles")["id"], status="failed")
        coord.on_host_gallery_settled(gallery_fk, "tezfiles", False)

        for host in ("keep2share", "fileboom", "tezfiles"):
            assert _row_status(store, path, host) == "failed"


class TestCoordinatorNoOpCases:
    def test_single_family_member_enabled_is_noop(self, store, coord):
        path = "/tmp/c5"
        _add_family_rows(store, path, ["keep2share"])
        gallery_fk = _row(store, path, "keep2share")["gallery_fk"]
        coord.on_host_gallery_settled(gallery_fk, "keep2share", True)
        assert _row_status(store, path, "keep2share") in ("pending", "completed")
