"""Tests for FileHostWorker._try_family_mirror()."""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.storage.database import QueueStore
from src.processing.file_host_workers import FileHostWorker


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as d:
        yield QueueStore(str(Path(d) / "test.db"))


@pytest.fixture(autouse=True)
def patch_worker_deps():
    """Patch out external dependencies so FileHostWorker can be instantiated."""
    with patch('src.processing.file_host_workers.get_config_manager') as mock_cfg, \
         patch('src.processing.file_host_workers.get_coordinator'), \
         patch('src.processing.file_host_workers.get_archive_manager'), \
         patch('src.processing.file_host_workers.QSettings'):
        mock_config = Mock()
        mock_config.name = "FileBoom"
        mock_cfg.return_value.get_host.return_value = mock_config
        yield


@pytest.fixture
def worker(store):
    w = FileHostWorker(host_id="fileboom", queue_store=store)
    return w


@pytest.fixture
def client():
    c = MagicMock()
    c.try_create_by_hash = MagicMock(return_value={"status": "success", "url": "https://example/1"})
    return c


def _seed_primary_parts(store, gallery_path, host, part_defs):
    """Seed completed primary rows. part_defs = [(part_num, md5, file_name), ...]"""
    ids = []
    for part_num, md5, file_name in part_defs:
        uid = store.add_file_host_upload(
            gallery_path=gallery_path,
            host_name=host,
            status="completed",
            part_number=part_num,
        )
        store.update_file_host_upload(uid, md5_hash=md5, file_name=file_name)
        ids.append(uid)
    return ids


class TestTryFamilyMirror:
    def test_single_part_success(self, worker, store, client):
        path = "/tmp/mg1"
        _seed_primary_parts(store, path, "keep2share", [(0, "m0", "gallery.zip")])
        secondary_id = store.add_file_host_upload(path, "fileboom", status="pending", part_number=0)
        row = store.get_pending_file_host_uploads(host_name="fileboom")[0]

        ok = worker._try_family_mirror(row, client, family="k2s")
        assert ok is True
        client.try_create_by_hash.assert_called_once_with("m0", "gallery.zip")

        final = store.get_file_host_uploads(path)
        fb_row = next(r for r in final if r["host_name"] == "fileboom")
        assert fb_row["status"] == "completed"
        assert fb_row["deduped"] == 1

    def test_split_archive_creates_mirror_part_rows(self, worker, store, client):
        path = "/tmp/mg2"
        _seed_primary_parts(
            store, path, "keep2share",
            [(0, "m0", "g.part0.zip"), (1, "m1", "g.part1.zip"), (2, "m2", "g.part2.zip")],
        )
        store.add_file_host_upload(path, "fileboom", status="pending", part_number=0)
        row = store.get_pending_file_host_uploads(host_name="fileboom")[0]

        ok = worker._try_family_mirror(row, client, family="k2s")
        assert ok is True
        # Three dedup calls — one per primary part
        assert client.try_create_by_hash.call_count == 3

        fb_rows = [r for r in store.get_file_host_uploads(path) if r["host_name"] == "fileboom"]
        # Three fileboom rows (part 0, 1, 2)
        assert len(fb_rows) == 3
        for r in fb_rows:
            assert r["status"] == "completed"
            assert r["deduped"] == 1
        # Parts 1 and 2 should carry dedup_only=1; part 0 (original head row) may be either
        part1 = next(r for r in fb_rows if r["part_number"] == 1)
        part2 = next(r for r in fb_rows if r["part_number"] == 2)
        assert part1["dedup_only"] == 1
        assert part2["dedup_only"] == 1

    def test_dedup_miss_on_any_part_aborts(self, worker, store):
        path = "/tmp/mg3"
        _seed_primary_parts(
            store, path, "keep2share",
            [(0, "m0", "g.part0.zip"), (1, "m1", "g.part1.zip")],
        )
        store.add_file_host_upload(path, "fileboom", status="pending", part_number=0)
        row = store.get_pending_file_host_uploads(host_name="fileboom")[0]

        client = MagicMock()
        # First part matches, second does not
        client.try_create_by_hash.side_effect = [
            {"status": "success", "url": "https://example/0"},
            None,
        ]

        ok = worker._try_family_mirror(row, client, family="k2s")
        assert ok is False

    def test_empty_primary_set_returns_false(self, worker, store, client):
        path = "/tmp/mg4"
        store.add_file_host_upload(path, "fileboom", status="pending", part_number=0)
        row = store.get_pending_file_host_uploads(host_name="fileboom")[0]

        ok = worker._try_family_mirror(row, client, family="k2s")
        assert ok is False
        client.try_create_by_hash.assert_not_called()

    def test_non_family_host_returns_false(self, worker, store, client):
        # Worker for a non-family host shouldn't mirror anything
        non_family_worker = FileHostWorker(host_id="rapidgator", queue_store=store)
        path = "/tmp/mg5"
        store.add_file_host_upload(path, "rapidgator", status="pending", part_number=0)
        row = store.get_pending_file_host_uploads(host_name="rapidgator")[0]

        ok = non_family_worker._try_family_mirror(row, client, family=None)
        assert ok is False

    def test_partial_mirror_failure_leaves_head_row_pending(self, worker, store):
        """When dedup succeeds for part 0 but fails for part 1, the head row
        must remain `pending` so the caller can fall through to full upload."""
        path = "/tmp/mg_partial"
        _seed_primary_parts(
            store, path, "keep2share",
            [(0, "m0", "g.part0.zip"), (1, "m1", "g.part1.zip")],
        )
        store.add_file_host_upload(path, "fileboom", status="pending", part_number=0)
        row = store.get_pending_file_host_uploads(host_name="fileboom")[0]

        client = MagicMock()
        client.try_create_by_hash.side_effect = [
            {"status": "success", "url": "https://x/0"},
            None,  # part 1 misses
        ]

        ok = worker._try_family_mirror(row, client, family="k2s")
        assert ok is False

        # Head row must still be pending — nothing committed yet.
        fb_rows = [r for r in store.get_file_host_uploads(path) if r["host_name"] == "fileboom"]
        assert len(fb_rows) == 1, "No secondary rows should have been created"
        assert fb_rows[0]["status"] == "pending"
        assert not fb_rows[0]["deduped"]

    def test_mirror_excludes_own_host_from_sibling_parts(self, worker, store, client):
        """If the worker's own host has a prior completed row, it should NOT
        be treated as a sibling part for mirroring purposes."""
        path = "/tmp/mg_self"
        # Fileboom has a prior completed row (e.g., from a previous run)
        _seed_primary_parts(store, path, "fileboom", [(0, "m_fb", "g.zip")])
        # A new pending fileboom row is being processed now
        store.add_file_host_upload(path, "fileboom", status="pending", part_number=0)
        row = store.get_pending_file_host_uploads(host_name="fileboom")[0]

        ok = worker._try_family_mirror(row, client, family="k2s")
        # No sibling parts (only self), so mirror returns False
        assert ok is False
        client.try_create_by_hash.assert_not_called()

    def test_mirror_aborts_when_sibling_md5_missing(self, worker, store, client):
        """If the coordinator's poller gave up, sibling parts will have NULL
        md5. The mirror must abort without calling try_create_by_hash so the
        worker falls through to a full upload."""
        path = "/tmp/mg_no_md5"
        # Seed a completed K2S row but with NO md5 (poller never populated it)
        uid = store.add_file_host_upload(
            path, "keep2share", status="completed", part_number=0
        )
        store.update_file_host_upload(uid, file_name="g.zip")  # md5_hash stays NULL
        store.add_file_host_upload(path, "fileboom", status="pending", part_number=0)
        row = store.get_pending_file_host_uploads(host_name="fileboom")[0]

        ok = worker._try_family_mirror(row, client, family="k2s")
        assert ok is False
        client.try_create_by_hash.assert_not_called()


class TestWorkerUploadLoopFamilyBranch:
    """Test the wiring of _try_family_mirror into the worker's main upload flow.

    We call _process_single_pending_row directly with a mock client so we can
    control try_create_by_hash responses without running the full QThread loop.
    """

    def test_pre_upload_branch_short_circuits_on_mirror_success(
        self, worker, store, client, monkeypatch
    ):
        path = "/tmp/lp1"
        _seed_primary_parts(store, path, "keep2share", [(0, "m0", "g.zip")])
        store.add_file_host_upload(path, "fileboom", status="pending", part_number=0)
        row = store.get_pending_file_host_uploads(host_name="fileboom")[0]

        archive_mgr_called = []
        monkeypatch.setattr(
            worker, "_get_or_create_archive",
            lambda *a, **kw: archive_mgr_called.append(True),
            raising=False,
        )

        settled_events = []
        worker.host_gallery_settled.connect(
            lambda gid, host, success: settled_events.append((gid, host, success))
        )
        # Call the per-row helper directly with a mock client
        worker._process_single_pending_row(row, client)

        assert archive_mgr_called == []  # never asked for archive
        assert settled_events == [(row["gallery_fk"], "fileboom", True)]
        final = next(
            r for r in store.get_file_host_uploads(path) if r["host_name"] == "fileboom"
        )
        assert final["status"] == "completed"
        assert final["deduped"] == 1

    def test_dedup_only_row_fails_terminally_on_mirror_miss(
        self, worker, store, monkeypatch
    ):
        path = "/tmp/lp2"
        # No primary rows exist — mirror will miss
        store.add_file_host_upload(
            path, "fileboom", status="pending", part_number=0, dedup_only=1
        )
        row = store.get_pending_file_host_uploads(host_name="fileboom")[0]

        archive_mgr_called = []
        monkeypatch.setattr(
            worker, "_get_or_create_archive",
            lambda *a, **kw: archive_mgr_called.append(True),
            raising=False,
        )

        client = MagicMock()
        client.try_create_by_hash = MagicMock(return_value=None)  # miss

        settled_events = []
        worker.host_gallery_settled.connect(
            lambda gid, host, success: settled_events.append((gid, host, success))
        )
        worker._process_single_pending_row(row, client)

        assert archive_mgr_called == []
        assert settled_events == [(row["gallery_fk"], "fileboom", False)]
        final = next(
            r for r in store.get_file_host_uploads(path) if r["host_name"] == "fileboom"
        )
        assert final["status"] == "failed"

    def test_aggregate_signal_emitted_even_if_process_upload_raises(
        self, worker, store, monkeypatch
    ):
        """host_gallery_settled must fire from finally block, even on exception."""
        path = "/tmp/lp_exc"
        store.add_file_host_upload(path, "fileboom", status="pending", part_number=0)
        row = store.get_pending_file_host_uploads(host_name="fileboom")[0]

        # Non-family context: disable feature, so we skip the mirror branch
        # and go straight to the full-upload path (where we'll raise).
        import src.processing.file_host_workers as fhw
        monkeypatch.setattr(fhw, "is_family_dedup_enabled", lambda: False)

        def boom(*a, **kw):
            raise RuntimeError("simulated upload crash")
        monkeypatch.setattr(worker, "_process_upload", boom)

        settled = []
        worker.host_gallery_settled.connect(
            lambda gid, host, success: settled.append((gid, host, success))
        )
        with pytest.raises(RuntimeError):
            worker._process_single_pending_row(row, client=None, host_config=MagicMock())

        assert settled == [(row["gallery_fk"], "fileboom", False)]
