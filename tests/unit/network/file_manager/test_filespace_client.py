"""Unit tests for FilespaceFileManagerClient (web-scraping subclass)."""

from __future__ import annotations

import pathlib
from typing import Dict, List, Tuple

import pytest

from src.network.file_manager.filespace_client import FilespaceFileManagerClient


class FakeFileHostClient:
    """Fake FileHostClient used by every filespace test — no network."""

    def __init__(self, responses: Dict[str, bytes]):
        self.responses = responses
        self.calls: List[Tuple[str, str, Dict]] = []

    def request(
        self,
        method,
        url,
        *,
        headers=None,
        body=None,
        follow_redirects=True,
        count_bandwidth=True,
        timeout=60,
    ):
        self.calls.append(
            (method, url, {"headers": headers, "body": body, "timeout": timeout})
        )
        for prefix, resp in self.responses.items():
            if url.startswith(prefix):
                return 200, {}, resp
        return 404, {}, b""


FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures"


def _load_my_files() -> bytes:
    path = FIXTURE_DIR / "filespace_my_files.htm"
    if not path.exists():
        pytest.skip(f"Fixture not found: {path}")
    return path.read_bytes()


def _load_file_edit() -> bytes:
    path = FIXTURE_DIR / "filespace_file_edit.htm"
    if not path.exists():
        pytest.skip(f"Fixture not found: {path}")
    return path.read_bytes()


# ---------------------------------------------------------------------------
# list_files / _scrape_page
# ---------------------------------------------------------------------------

def test_filespace_parses_fixture_root_page():
    """list_files('/') parses the fixture into 1 folder + 11 files."""
    html = _load_my_files()
    fake = FakeFileHostClient({"https://filespace.com/": html})
    client = FilespaceFileManagerClient(fake)

    result = client.list_files("/")
    folders = [f for f in result.files if f.is_folder]
    files = [f for f in result.files if not f.is_folder]

    assert len(folders) == 1, f"Expected 1 folder, got {len(folders)}"
    assert folders[0].id == "33018"
    assert folders[0].name == "subfolder test"

    assert len(files) == 11, f"Expected 11 files, got {len(files)}"
    codes = {f.id for f in files}
    assert "3zm41fbivvgp" in codes
    assert "i7off4ja4vio" in codes

    first = next(f for f in files if f.id == "3zm41fbivvgp")
    assert first.name == "Test114b.zip"
    assert first.size > 0

    # numeric id cache populated
    assert client._file_code_to_numeric["3zm41fbivvgp"] == "7265936"
    assert client._file_code_to_numeric["i7off4ja4vio"] == "7265934"
    assert client._known_folder_ids == {"33018"}


def test_filespace_list_root_builds_correct_url():
    """list_files('/') issues GET to /?op=my_files&fld_id=0&page=1."""
    fake = FakeFileHostClient({"https://filespace.com/": b"<html></html>"})
    client = FilespaceFileManagerClient(fake)

    client.list_files("/")

    assert len(fake.calls) == 1
    method, url, _ = fake.calls[0]
    assert method == "GET"
    assert url == "https://filespace.com/?op=my_files&fld_id=0&page=1"


def test_filespace_list_subfolder_builds_correct_url():
    """list_files('33018') issues GET with fld_id=33018."""
    fake = FakeFileHostClient({"https://filespace.com/": b"<html></html>"})
    client = FilespaceFileManagerClient(fake)

    client.list_files("33018")

    method, url, _ = fake.calls[0]
    assert url == "https://filespace.com/?op=my_files&fld_id=33018&page=1"
