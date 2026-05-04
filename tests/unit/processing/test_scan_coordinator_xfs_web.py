"""End-to-end smoke test: ScanCoordinator routes filedot job through
XFSWebFileChecker and produces a result tuple + storage summary."""
import json
import threading
from unittest.mock import MagicMock

from src.network.file_manager.client import FileInfo
from src.processing.scan_coordinator import (
    ScanCoordinator, HostScanJob,
)


def _file(code, size=100, available=True):
    return FileInfo(
        id=code, name=code, is_folder=False, size=size,
        is_available=available, metadata={"file_code": code},
    )


class FakeFM:
    PER_PAGE_MAX = 5000

    def __init__(self, files):
        self._files = files
        self.calls = 0

    def _scrape_page(self, folder_id, page, per_page=None):
        self.calls += 1
        if folder_id == "0" and page == 1:
            return [], list(self._files.values())
        return [], []


def test_filedot_e2e_smoke(monkeypatch):
    coord = ScanCoordinator(store=MagicMock(), connection_limiter=MagicMock())

    # Pretend the auth step has already produced a logged-in client.
    coord._xfs_clients["filedot"] = object()

    fake_fm = FakeFM({
        "abc": _file("abc", size=500, available=True),
        "def": _file("def", size=200, available=False),
    })

    # Bypass the real file-manager construction in _run_xfs_web_job.
    monkeypatch.setattr(
        "src.network.file_manager.filedot_client.FiledotFileManagerClient",
        lambda **kw: fake_fm,
    )

    job = HostScanJob(
        host_type="file", host_id="filedot",
        galleries=[
            {"db_id": 1, "file_ids": {"abc": "https://filedot.to/abc"}},
            {"db_id": 2, "file_ids": {"def": "https://filedot.to/def"}},
            {"db_id": 3, "file_ids": {"abc": "https://filedot.to/abc",
                                       "def": "https://filedot.to/def"}},
        ],
    )
    results = coord._run_xfs_web_job(job)
    assert len(results) == 3
    by_db = {r[0]: r for r in results}
    # Result tuple: (db_id, host_type, host_id, status, online, total, now, detail)
    assert by_db[1][3] == "online"
    assert by_db[2][3] == "offline"
    assert by_db[3][3] == "partial"
    detail = json.loads(by_db[2][7])
    assert detail["offline_urls"] == ["https://filedot.to/def"]

    # Storage cache populated
    assert coord._xfs_storage_by_host["filedot"] == 500


def test_completion_summary_includes_xfs_storage_keys():
    captured = {}

    def on_complete(summary):
        captured.update(summary)

    coord = ScanCoordinator(
        store=MagicMock(), connection_limiter=MagicMock(),
        completion_callback=on_complete,
    )
    # Pre-populate state as if walks already completed
    coord._xfs_storage_by_host["filedot"] = 1234
    coord._xfs_storage_by_host["filespace"] = 5678

    # Need at least one job to trigger the full summary code path
    # Use an image gallery to avoid complex file host setup
    coord._run_scan(
        image_galleries=[
            {
                "db_id": 99,
                "host_id": "imx",
                "path": "/gallery",
                "thumb_urls": ["https://imx.to/a.jpg"],
            }
        ],
        file_uploads=[],
    )

    assert captured.get("filedot_storage_used") == 1234
    assert captured.get("filespace_storage_used") == 5678
