"""End-to-end integration tests for K2S family dedup feature.

Harnesses QueueStore + queue_file_host_uploads_for_gallery +
HostFamilyCoordinator + FileHostWorker._try_family_mirror together.
We do not run real QThreads; we simulate upload outcomes by directly
calling store methods and the coordinator.
"""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.storage.database import QueueStore
from src.storage.queue_manager import queue_file_host_uploads_for_gallery
from src.processing.host_family_coordinator import HostFamilyCoordinator
from src.processing.file_host_workers import FileHostWorker


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as d:
        yield QueueStore(str(Path(d) / "test.db"))


@pytest.fixture
def coord(store):
    return HostFamilyCoordinator(queue_store=store)


@pytest.fixture(autouse=True)
def patch_worker_deps():
    """Patch out external dependencies so FileHostWorker can be instantiated."""
    with patch('src.processing.file_host_workers.get_config_manager') as mock_cfg, \
         patch('src.processing.file_host_workers.get_coordinator'), \
         patch('src.processing.file_host_workers.get_archive_manager'), \
         patch('src.processing.file_host_workers.QSettings'), \
         patch('src.processing.host_family_coordinator.is_family_dedup_enabled', return_value=True):
        mock_config = Mock()
        mock_config.name = "Keep2Share"
        mock_cfg.return_value.get_host.return_value = mock_config
        yield


def _mk_worker(store, host_id):
    return FileHostWorker(host_id=host_id, queue_store=store)


def _mock_success_client(urls_by_hash):
    c = MagicMock()

    def _try(md5, name):
        return {"status": "success", "url": urls_by_hash.get(md5, "https://x/x"), "file_id": "fid"}

    c.try_create_by_hash.side_effect = _try
    return c


class TestWithinRunSinglePart:
    def test_one_upload_two_dedups(self, store, coord):
        path = "/tmp/int1"
        ids = queue_file_host_uploads_for_gallery(
            store, gallery_path=path,
            host_ids=["keep2share", "fileboom", "tezfiles"],
            family_dedup_enabled=True,
        )
        # Primary should be keep2share (pending); fileboom/tezfiles should be blocked
        rows = store.get_file_host_uploads(path)
        k2s_row = next(r for r in rows if r["host_name"] == "keep2share")
        assert k2s_row["status"] == "pending"
        fb_row = next(r for r in rows if r["host_name"] == "fileboom")
        assert fb_row["status"] == "blocked"
        tf_row = next(r for r in rows if r["host_name"] == "tezfiles")
        assert tf_row["status"] == "blocked"

        # Primary completes
        store.update_file_host_upload(
            ids["keep2share"], status="completed", md5_hash="m0", file_name="g.zip"
        )
        gallery_fk = k2s_row["gallery_fk"]
        coord.on_host_gallery_settled(gallery_fk, "keep2share", True)

        # Secondaries now pending — workers pick them up and run family-mirror
        fb_worker = _mk_worker(store, "fileboom")
        tf_worker = _mk_worker(store, "tezfiles")
        client = _mock_success_client({"m0": "https://fb/1"})

        fb_row = next(iter(store.get_pending_file_host_uploads(host_name="fileboom")))
        assert fb_worker._try_family_mirror(fb_row, client, family="k2s") is True
        tf_row = next(iter(store.get_pending_file_host_uploads(host_name="tezfiles")))
        assert tf_worker._try_family_mirror(tf_row, client, family="k2s") is True

        # All three completed
        for host in ("keep2share", "fileboom", "tezfiles"):
            r = next(r for r in store.get_file_host_uploads(path) if r["host_name"] == host)
            assert r["status"] == "completed"


class TestCrossSessionRetrofit:
    def test_enable_fileboom_after_k2s_run(self, store, coord):
        path = "/tmp/int_xs"
        # Day 1: K2S upload completed (seeded)
        ids = queue_file_host_uploads_for_gallery(
            store, path, ["keep2share"], family_dedup_enabled=True
        )
        store.update_file_host_upload(
            ids["keep2share"], status="completed", md5_hash="m0", file_name="g.zip"
        )

        # Day 2: enable FileBoom, queue again
        queue_file_host_uploads_for_gallery(
            store, path, ["fileboom"], family_dedup_enabled=True
        )
        # FileBoom is alone in its batch -> plain pending.
        # Cross-session dedup happens at worker pickup time.
        fb_row = next(iter(store.get_pending_file_host_uploads(host_name="fileboom")))
        worker = _mk_worker(store, "fileboom")
        client = _mock_success_client({"m0": "https://fb/1"})

        assert worker._try_family_mirror(fb_row, client, family="k2s") is True
        client.try_create_by_hash.assert_called_once_with("m0", "g.zip")

        fb_final = next(
            r for r in store.get_file_host_uploads(path) if r["host_name"] == "fileboom"
        )
        assert fb_final["status"] == "completed"
        assert fb_final["deduped"] == 1


class TestPartialPrimaryFailure:
    def test_promotion_on_failure_triggers_retry_with_dedup_only(self, store, coord):
        path = "/tmp/int_pf"
        ids = queue_file_host_uploads_for_gallery(
            store, path, ["keep2share", "fileboom", "tezfiles"], family_dedup_enabled=True
        )
        # K2S fails
        store.update_file_host_upload(ids["keep2share"], status="failed")
        gallery_fk = store.get_file_host_uploads(path)[0]["gallery_fk"]
        coord.on_host_gallery_settled(gallery_fk, "keep2share", False)

        fb_row = next(
            r for r in store.get_file_host_uploads(path) if r["host_name"] == "fileboom"
        )
        assert fb_row["status"] == "pending"
        assert fb_row["blocked_by_upload_id"] is None

        # FileBoom completes
        store.update_file_host_upload(
            fb_row["id"], status="completed", md5_hash="m0", file_name="g.zip"
        )
        coord.on_host_gallery_settled(gallery_fk, "fileboom", True)

        # TezFiles unblocked
        tf_row = next(
            r for r in store.get_file_host_uploads(path) if r["host_name"] == "tezfiles"
        )
        assert tf_row["status"] == "pending"

        # Original K2S retried with dedup_only=1
        k2s_row = next(
            r for r in store.get_file_host_uploads(path) if r["host_name"] == "keep2share"
        )
        assert k2s_row["status"] == "pending"
        assert k2s_row["dedup_only"] == 1
