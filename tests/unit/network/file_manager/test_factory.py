"""Unit tests for create_file_manager_client factory."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.network.file_manager.factory import create_file_manager_client
from src.network.file_manager.filedot_client import FiledotFileManagerClient


# ---------------------------------------------------------------------------
# Minimal stub — only needs to be structurally compatible with FileHostClient
# ---------------------------------------------------------------------------

class _StubFileHostClient:
    """Minimal duck-type stub; no network calls made in factory tests."""

    def request(self, method, url, *, headers=None, body=None,
                follow_redirects=True, count_bandwidth=True, timeout=60):
        return 200, {}, b""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_factory_rejects_filedot_without_client():
    """factory raises ValueError when filedot is requested without file_host_client."""
    with pytest.raises(ValueError) as exc_info:
        create_file_manager_client("filedot")
    assert "Enable Filedot" in str(exc_info.value)


def test_factory_accepts_filedot_with_client():
    """factory returns a FiledotFileManagerClient wired to the injected client."""
    fake = _StubFileHostClient()
    client = create_file_manager_client("filedot", file_host_client=fake)
    assert isinstance(client, FiledotFileManagerClient)
    assert client._http is fake


def test_factory_api_hosts_unchanged():
    """API-key hosts (keep2share, katfile) still work without file_host_client."""
    with patch(
        "src.network.file_manager.factory._load_auth_token",
        return_value="fake_token",
    ):
        k2s_client = create_file_manager_client("keep2share")
        assert k2s_client is not None

        katfile_client = create_file_manager_client("katfile")
        assert katfile_client is not None
