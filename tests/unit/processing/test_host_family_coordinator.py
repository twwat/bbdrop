"""Tests for HostFamilyCoordinator — drives the coordinator via host_gallery_settled emits."""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.storage.database import QueueStore
from src.processing import host_family_coordinator as hfc_module
from src.processing.host_family_coordinator import (
    HostFamilyCoordinator,
    _canonical_file_id_from_url,
)


class TestCanonicalFileIdFromUrl:
    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://k2s.cc/file/abc123/gallery.zip", "abc123"),
            ("https://fboom.me/file/xyz789/My.Photo.Pack.zip", "xyz789"),
            ("https://tezfiles.com/file/deadbeef/", "deadbeef"),
            ("https://tezfiles.com/file/deadbeef", "deadbeef"),
            ("https://k2s.cc/file/id1/sub/more/file.zip", "id1"),
            ("https://k2s.cc/file/abc?dl=1", "abc"),
            # Unparseable / malformed inputs: returns None, never raises
            ("", None),
            (None, None),
            ("https://k2s.cc/nofile/abc/g.zip", None),
            ("not a url at all", None),
        ],
    )
    def test_extracts_canonical_id(self, url, expected):
        assert _canonical_file_id_from_url(url) == expected


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


class TestCoordinatorMd5Poller:
    """Covers the NULL-md5 path where the coordinator spawns a background
    poller instead of unblocking siblings immediately. Tests run the poller
    synchronously by overriding `_schedule_md5_fetch` — no real threading
    or HTTP happens.
    """

    @pytest.fixture
    def sync_coord(self, store):
        """Coordinator that runs the md5 poller synchronously on this thread."""
        c = HostFamilyCoordinator(queue_store=store)

        def _run_sync(gallery_fk, family, primary_row_id, host_name, canonical_file_id):
            hfc_module._md5_fetch_worker(
                store, gallery_fk, family, primary_row_id, host_name, canonical_file_id
            )

        c._schedule_md5_fetch = _run_sync
        return c

    def test_null_md5_with_url_schedules_poller_and_unblocks_on_landing(
        self, store, sync_coord
    ):
        path = "/tmp/md5_poll1"
        ids = _add_family_rows(store, path, ["keep2share", "fileboom", "tezfiles"])
        # Primary completes with NULL md5 but a real download URL
        store.update_file_host_upload(
            ids["keep2share"],
            status="completed",
            download_url="https://k2s.cc/file/abc123/gallery.zip",
        )
        gallery_fk = _row(store, path, "keep2share")["gallery_fk"]

        # Poller lands md5 on first call
        with patch.object(
            hfc_module.FileHostClient, "fetch_md5_for_host", return_value="server-md5"
        ) as mock_fetch:
            sync_coord.on_host_gallery_settled(gallery_fk, "keep2share", True)

        mock_fetch.assert_called_once()
        # canonical id should be "abc123", not the user_file_id
        assert mock_fetch.call_args.args[1] == "abc123"

        # md5 written to primary row
        assert _row(store, path, "keep2share")["md5_hash"] == "server-md5"
        # Siblings unblocked
        assert _row_status(store, path, "fileboom") == "pending"
        assert _row_status(store, path, "tezfiles") == "pending"

    def test_poller_exhausted_unblocks_anyway(self, store, sync_coord):
        path = "/tmp/md5_poll2"
        ids = _add_family_rows(store, path, ["keep2share", "fileboom", "tezfiles"])
        store.update_file_host_upload(
            ids["keep2share"],
            status="completed",
            download_url="https://k2s.cc/file/zzz999/g.zip",
        )
        gallery_fk = _row(store, path, "keep2share")["gallery_fk"]

        with patch.object(
            hfc_module.FileHostClient, "fetch_md5_for_host", return_value=None
        ) as mock_fetch, \
             patch.object(hfc_module.time, "sleep"):  # skip the backoff waits
            sync_coord.on_host_gallery_settled(gallery_fk, "keep2share", True)

        assert mock_fetch.call_count == hfc_module.K2S_MD5_MAX_ATTEMPTS
        # md5 still NULL, but siblings unblocked so they can full-upload
        assert _row(store, path, "keep2share")["md5_hash"] is None
        assert _row_status(store, path, "fileboom") == "pending"
        assert _row_status(store, path, "tezfiles") == "pending"

    def test_null_md5_no_url_unblocks_immediately_without_poll(self, store, sync_coord):
        """Row has NULL md5 AND no download URL — the poller has nothing to
        query, so we unblock immediately instead of spawning it. Siblings
        will fall through to full upload."""
        path = "/tmp/md5_poll3"
        ids = _add_family_rows(store, path, ["keep2share", "fileboom"])
        store.update_file_host_upload(ids["keep2share"], status="completed")
        gallery_fk = _row(store, path, "keep2share")["gallery_fk"]

        with patch.object(
            hfc_module.FileHostClient, "fetch_md5_for_host"
        ) as mock_fetch:
            sync_coord.on_host_gallery_settled(gallery_fk, "keep2share", True)

        mock_fetch.assert_not_called()
        assert _row_status(store, path, "fileboom") == "pending"

    def test_dedup_only_retry_blocks_when_winner_has_null_md5(self, store):
        """Regression: after a primary fails and a promoted primary succeeds
        with NULL md5, `_run_family_retry_scan` must NOT flip the original
        primary's failed row to `pending` immediately. If it did, that
        dedup_only row would race the coordinator's md5 poller — running
        `_try_family_mirror` against a NULL-md5 sibling and failing
        terminally. Instead the retry row gets blocked on the winner, and
        the poller unblocks it naturally when md5 lands.
        """
        path = "/tmp/b1_retry"
        ids = _add_family_rows(store, path, ["keep2share", "fileboom", "tezfiles"])
        gallery_fk = _row(store, path, "keep2share")["gallery_fk"]

        # Coordinator that defers the poller: captures the schedule call
        # instead of running it. This lets `_run_family_retry_scan` run while
        # md5 is still NULL (the exact race the fix addresses), and lets the
        # test explicitly drive the poller afterwards.
        coord = HostFamilyCoordinator(queue_store=store)
        deferred_polls: list = []
        coord._schedule_md5_fetch = lambda **kw: deferred_polls.append(kw)

        # keep2share fails → fileboom promoted to primary
        store.update_file_host_upload(ids["keep2share"], status="failed")
        coord.on_host_gallery_settled(gallery_fk, "keep2share", False)
        assert _row_status(store, path, "fileboom") == "pending"

        # Promoted fileboom completes with NULL md5 but a usable download URL
        fb_id = _row(store, path, "fileboom")["id"]
        store.update_file_host_upload(
            fb_id,
            status="completed",
            download_url="https://fboom.me/file/xyz789/g.zip",
        )
        coord.on_host_gallery_settled(gallery_fk, "fileboom", True)

        # Poller got scheduled (but not run). Retry scan already executed —
        # it should have BLOCKED keep2share on the winner, not flipped to pending.
        assert len(deferred_polls) == 1
        k2s = _row(store, path, "keep2share")
        assert k2s["dedup_only"] == 1
        assert k2s["status"] == "blocked", (
            f"keep2share retry row should be blocked on winner, got {k2s['status']}"
        )
        assert k2s["blocked_by_upload_id"] == fb_id
        # tezfiles is still blocked too — nothing unblocks until the poller runs
        assert _row_status(store, path, "tezfiles") == "blocked"

        # Now actually run the poller. With md5 landing, both the dedup_only
        # retry row AND the tezfiles waiter should be unblocked.
        with patch.object(
            hfc_module.FileHostClient,
            "fetch_md5_for_host",
            return_value="post-rewrite-md5",
        ):
            hfc_module._md5_fetch_worker(store, **deferred_polls[0])

        assert _row(store, path, "fileboom")["md5_hash"] == "post-rewrite-md5"
        k2s_after = _row(store, path, "keep2share")
        assert k2s_after["status"] == "pending"
        assert k2s_after["dedup_only"] == 1
        assert _row_status(store, path, "tezfiles") == "pending"

    def test_no_waiters_is_noop(self, store, sync_coord):
        """Primary succeeds but nothing is blocked on it — skip the poller
        entirely, even if md5 is NULL."""
        path = "/tmp/md5_poll4"
        _add_family_rows(store, path, ["keep2share"])
        k2s_id = _row(store, path, "keep2share")["id"]
        store.update_file_host_upload(
            k2s_id,
            status="completed",
            download_url="https://k2s.cc/file/nope/g.zip",
        )
        gallery_fk = _row(store, path, "keep2share")["gallery_fk"]

        with patch.object(
            hfc_module.FileHostClient, "fetch_md5_for_host"
        ) as mock_fetch:
            sync_coord.on_host_gallery_settled(gallery_fk, "keep2share", True)

        mock_fetch.assert_not_called()
