"""Tests for XFSWebFileChecker — walk + inventory check + storage calc."""
import threading
from unittest.mock import MagicMock

import pytest

from src.network.file_manager.client import FileInfo
from src.network.xfs_web_file_checker import XFSWebFileChecker


def _file(code, size=100, available=True):
    return FileInfo(
        id=code, name=code, is_folder=False, size=size,
        is_available=available, metadata={"file_code": code},
    )


def _folder(fid, name="f", file_count=0):
    return FileInfo(
        id=fid, name=name, is_folder=True,
        metadata={"fld_id": fid, "file_count": file_count},
    )


class FakeFileManager:
    """Stub that returns canned (folders, files) per (folder_id, page)."""

    PER_PAGE_MAX = 5000

    def __init__(self, pages):
        # pages: dict[(folder_id, page)] -> (folders, files)
        self._pages = pages
        self.calls = []

    def _scrape_page(self, folder_id, page, per_page=None):
        self.calls.append((folder_id, page, per_page))
        return self._pages.get((folder_id, page), ([], []))


class TestWalkAccount:
    def test_flat_root_with_files(self):
        fm = FakeFileManager({
            ("0", 1): ([], [_file("a"), _file("b"), _file("c")]),
        })
        checker = XFSWebFileChecker(fm)
        inventory = checker.walk_account()
        assert set(inventory.keys()) == {"a", "b", "c"}

    def test_nested_folders_recurse(self):
        fm = FakeFileManager({
            ("0", 1):    ([_folder("10", file_count=2)], [_file("a")]),
            ("10", 1):   ([], [_file("b"), _file("c")]),
        })
        checker = XFSWebFileChecker(fm)
        inventory = checker.walk_account()
        assert set(inventory.keys()) == {"a", "b", "c"}

    def test_empty_folder_skipped(self):
        fm = FakeFileManager({
            ("0", 1): ([_folder("10", file_count=0)], [_file("a")]),
            # If we did enter folder 10, this would add "x" — but we shouldn't.
            ("10", 1): ([], [_file("x")]),
        })
        checker = XFSWebFileChecker(fm)
        inventory = checker.walk_account()
        assert set(inventory.keys()) == {"a"}
        # Folder 10 must NOT have been scraped
        assert ("10", 1, fm.PER_PAGE_MAX) not in fm.calls

    def test_pagination_when_full_page(self):
        full_page = [_file(f"a{i}") for i in range(5000)]
        fm = FakeFileManager({
            ("0", 1): ([], full_page),
            ("0", 2): ([], [_file("z1"), _file("z2")]),
        })
        checker = XFSWebFileChecker(fm)
        inventory = checker.walk_account()
        assert "z1" in inventory and "z2" in inventory
        assert len(inventory) == 5002

    def test_cancel_event_stops_walk(self):
        cancel = threading.Event()
        cancel.set()
        fm = FakeFileManager({
            ("0", 1): ([_folder("10", file_count=2)], [_file("a")]),
            ("10", 1): ([], [_file("b")]),
        })
        checker = XFSWebFileChecker(fm)
        inventory = checker.walk_account(cancel_event=cancel)
        assert inventory == {}


class TestCheckGalleryFromInventory:
    def test_all_online(self):
        inv = {"a": _file("a"), "b": _file("b")}
        checker = XFSWebFileChecker(FakeFileManager({}))
        result = checker.check_gallery_from_inventory(
            {"a": "https://x/a", "b": "https://x/b"}, inv
        )
        assert result["status"] == "online"
        assert result["online"] == 2 and result["total"] == 2

    def test_all_offline_missing(self):
        inv = {}
        checker = XFSWebFileChecker(FakeFileManager({}))
        result = checker.check_gallery_from_inventory(
            {"a": "https://x/a"}, inv
        )
        assert result["status"] == "offline"
        assert result["offline_urls"] == ["https://x/a"]

    def test_all_offline_marked_unavailable(self):
        inv = {"a": _file("a", available=False)}
        checker = XFSWebFileChecker(FakeFileManager({}))
        result = checker.check_gallery_from_inventory(
            {"a": "https://x/a"}, inv
        )
        assert result["status"] == "offline"
        assert result["offline_urls"] == ["https://x/a"]

    def test_partial(self):
        inv = {"a": _file("a"), "b": _file("b", available=False)}
        checker = XFSWebFileChecker(FakeFileManager({}))
        result = checker.check_gallery_from_inventory(
            {"a": "https://x/a", "b": "https://x/b"}, inv
        )
        assert result["status"] == "partial"
        assert result["online"] == 1
        assert result["offline_urls"] == ["https://x/b"]

    def test_empty_input_unknown(self):
        checker = XFSWebFileChecker(FakeFileManager({}))
        result = checker.check_gallery_from_inventory({}, {})
        assert result["status"] == "unknown"


class TestCalcStorageUsed:
    def test_sums_only_available(self):
        inv = {
            "a": _file("a", size=100, available=True),
            "b": _file("b", size=200, available=True),
            "c": _file("c", size=999, available=False),
        }
        checker = XFSWebFileChecker(FakeFileManager({}))
        assert checker.calc_storage_used(inv) == 300


def test_filedot_class_exposes_per_page_max():
    from src.network.file_manager.filedot_client import FiledotFileManagerClient
    assert FiledotFileManagerClient.PER_PAGE_MAX == 5000


def test_filespace_class_exposes_per_page_max():
    from src.network.file_manager.filespace_client import FilespaceFileManagerClient
    assert FilespaceFileManagerClient.PER_PAGE_MAX == 500
