"""Unit tests for FiledotFileManagerClient (web-scraping client)."""

from __future__ import annotations

import pathlib
from typing import Dict, List, Tuple

import pytest

from src.network.file_manager.filedot_client import FiledotFileManagerClient

# ---------------------------------------------------------------------------
# Fake HTTP client — no network, records all calls
# ---------------------------------------------------------------------------

class FakeFileHostClient:
    def __init__(self, responses: Dict[str, bytes]):
        # responses: url-prefix -> body bytes
        self.responses = responses
        self.calls: List[Tuple[str, str, Dict]] = []  # (method, url, kwargs)

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
        self.calls.append((method, url, {"headers": headers, "body": body, "timeout": timeout}))
        for prefix, resp in self.responses.items():
            if url.startswith(prefix):
                return 200, {}, resp
        return 404, {}, b""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_sample_html() -> bytes:
    """Return the bytes of the saved Filedot file-listing page, or skip."""
    path = pathlib.Path(__file__).parents[4] / "logs" / "filedot.to-files.htm"
    if not path.exists():
        pytest.skip(f"Sample HTML not found at {path}")
    return path.read_bytes()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_filedot_parses_user_sample_html():
    """FiledotFileManagerClient correctly parses the real saved HTML page."""
    html_bytes = _load_sample_html()
    fake = FakeFileHostClient({"https://filedot.to/files/": html_bytes})
    client = FiledotFileManagerClient(fake)

    result = client.list_files("/")

    folders = [f for f in result.files if f.is_folder]
    files = [f for f in result.files if not f.is_folder]

    assert len(folders) == 17, f"Expected 17 folders, got {len(folders)}"
    assert len(files) == 500, f"Expected 500 files, got {len(files)}"
    assert client._action_token == "a8ea1b794ae9b74e79471c0a98e8d2fa", (
        f"Token mismatch: {client._action_token!r}"
    )

    # list_files returns folders first then files
    first_file = files[0]
    assert first_file.name, "First file should have a non-empty name"
    assert first_file.id, "First file should have a non-empty id (file code)"
    assert first_file.size > 0, "First file should have a positive size"
    assert not first_file.is_folder


def test_filedot_navigate_into_subfolder_builds_correct_url():
    """list_files('14264') should request the URL with fld_id=14264&page=1."""
    fake = FakeFileHostClient({"https://filedot.to/files/": b"<html></html>"})
    client = FiledotFileManagerClient(fake)

    client.list_files("14264")

    assert len(fake.calls) == 1
    method, url, _ = fake.calls[0]
    assert method == "GET"
    assert url == "https://filedot.to/files/?fld_id=14264&page=1"


def test_filedot_delete_uses_cached_token():
    """delete() should use the token scraped by the preceding list_files call."""
    html_bytes = _load_sample_html()
    fake = FakeFileHostClient({
        "https://filedot.to/files/?fld_id=0": html_bytes,
        "https://filedot.to/files?del_code=": b"<html>ok</html>",
    })
    client = FiledotFileManagerClient(fake)

    # Prime the token cache
    client.list_files("/")
    assert client._action_token == "a8ea1b794ae9b74e79471c0a98e8d2fa"

    result = client.delete(["clsl0fz7pfhl"])

    assert "clsl0fz7pfhl" in result.succeeded
    assert not result.failed

    # Find the delete call in the recorded calls
    delete_calls = [
        (m, u) for m, u, _ in fake.calls
        if "del_code" in u
    ]
    assert len(delete_calls) == 1, "Expected exactly one delete request"
    _method, delete_url = delete_calls[0]
    assert "del_code=clsl0fz7pfhl" in delete_url
    assert "token=a8ea1b794ae9b74e79471c0a98e8d2fa" in delete_url
