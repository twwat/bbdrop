"""Tests for RapidgatorFileManagerClient parsers."""
import pytest

from src.network.file_manager.rapidgator_client import (
    RapidgatorFileManagerClient,
    _RGAuthError,
)


def test_parse_file_copies_raw_dict_into_metadata():
    raw = {
        "file_id": "abc123",
        "mode": 0,
        "mode_label": "Public",
        "folder_id": "5106611",
        "name": "test.zip",
        "hash": "deadbeef",
        "size": 147,
        "created": 1775273358,
        "url": "https://rapidgator.net/file/abc123/test.zip.html",
        "nb_downloads": 42,
    }
    fi = RapidgatorFileManagerClient._parse_file(raw)
    assert fi.metadata == raw
    assert fi.metadata["nb_downloads"] == 42
    assert fi.metadata["url"] == "https://rapidgator.net/file/abc123/test.zip.html"
    assert fi.metadata["mode_label"] == "Public"


def test_parse_folder_copies_raw_dict_into_metadata():
    raw = {
        "folder_id": "7686821",
        "mode": 0,
        "mode_label": "Public",
        "parent_folder_id": "5106611",
        "name": "test",
        "url": "https://rapidgator.net/folder/7686821/test.html",
        "nb_folders": 3,
        "nb_files": 10,
        "size_files": 4951733274,
        "created": 1775704734,
    }
    fi = RapidgatorFileManagerClient._parse_folder(raw)
    assert fi.metadata == raw
    assert fi.metadata["nb_files"] == 10
    assert fi.metadata["nb_folders"] == 3
    assert fi.metadata["size_files"] == 4951733274


def test_parse_file_metadata_is_independent_copy():
    """Mutating metadata must not mutate the source dict."""
    raw = {"file_id": "x", "name": "y", "nb_downloads": 1}
    fi = RapidgatorFileManagerClient._parse_file(raw)
    fi.metadata["nb_downloads"] = 999
    assert raw["nb_downloads"] == 1


class _FakeCall:
    """Scripts _api_call_once responses across multiple invocations."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def __call__(self, endpoint, params=None):
        self.calls.append((endpoint, dict(params or {})))
        outcome = self._responses.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_api_call_retries_once_after_refresh():
    client = RapidgatorFileManagerClient(
        token="stale", refresh_token=lambda: "fresh",
    )
    fake = _FakeCall([_RGAuthError("401"), {"status": 200, "response": {}}])
    client._api_call_once = fake

    result = client._api_call("folder/content", {"folder_id": "/"})

    assert result == {"status": 200, "response": {}}
    assert client.token == "fresh"
    assert len(fake.calls) == 2


def test_api_call_gives_up_when_refresh_returns_same_token():
    client = RapidgatorFileManagerClient(
        token="stale", refresh_token=lambda: "stale",
    )
    fake = _FakeCall([_RGAuthError("401")])
    client._api_call_once = fake

    with pytest.raises(RuntimeError):
        client._api_call("folder/content")
    assert len(fake.calls) == 1


def test_api_call_gives_up_when_retry_also_fails():
    client = RapidgatorFileManagerClient(
        token="stale", refresh_token=lambda: "fresh",
    )
    fake = _FakeCall([_RGAuthError("401"), _RGAuthError("401 again")])
    client._api_call_once = fake

    with pytest.raises(RuntimeError):
        client._api_call("folder/content")
    assert len(fake.calls) == 2


def test_api_call_raises_runtime_error_when_no_refresh_configured():
    client = RapidgatorFileManagerClient(token="stale")
    fake = _FakeCall([_RGAuthError("401")])
    client._api_call_once = fake

    with pytest.raises(RuntimeError):
        client._api_call("folder/content")
    assert len(fake.calls) == 1


def test_rg_auth_error_is_not_runtime_error():
    """The in-module wrong-item-type fallbacks use `except RuntimeError:`
    as a sentinel — _RGAuthError must NOT subclass RuntimeError or a dead
    session would trigger doomed folder-variant retries."""
    assert not issubclass(_RGAuthError, RuntimeError)


def test_api_call_does_not_retry_on_non_auth_errors():
    refresh_calls = []

    def _refresh():
        refresh_calls.append(1)
        return "fresh"

    client = RapidgatorFileManagerClient(token="stale", refresh_token=_refresh)
    fake = _FakeCall([RuntimeError("RG API folder/content returned HTTP 500")])
    client._api_call_once = fake

    with pytest.raises(RuntimeError):
        client._api_call("folder/content")
    assert len(fake.calls) == 1
    assert refresh_calls == []


class _FakeCurl:
    """Minimal pycurl.Curl stand-in that writes a canned body."""

    def __init__(self, response_body: str, response_code: int = 200):
        self._body = response_body
        self._code = response_code
        self._write_buffer = None

    def setopt(self, option, value):
        import pycurl
        if option == pycurl.WRITEDATA:
            self._write_buffer = value

    def perform(self):
        if self._write_buffer is not None:
            self._write_buffer.write(self._body.encode("utf-8"))

    def getinfo(self, option):
        import pycurl
        if option == pycurl.RESPONSE_CODE:
            return self._code
        return 0

    def close(self):
        pass


def _install_fake_curl(monkeypatch, body: str, code: int = 200):
    import src.network.file_manager.rapidgator_client as mod

    def _factory():
        return _FakeCurl(body, code)

    monkeypatch.setattr(mod.pycurl, "Curl", _factory)


def test_api_call_once_raises_auth_error_on_inner_401(monkeypatch):
    body = (
        '{"status": 401, '
        '"response": {"error": "Session doesn\'t exist. Login to get new token."}}'
    )
    _install_fake_curl(monkeypatch, body)

    client = RapidgatorFileManagerClient(token="stale")
    with pytest.raises(_RGAuthError):
        client._api_call_once("folder/content")


def test_api_call_once_detects_auth_phrase_with_non_401_status(monkeypatch):
    """Some older RG endpoints return a different numeric status but
    still embed an auth-error phrase in the message — catch those too."""
    body = (
        '{"status": 500, '
        '"response": {"error": "Invalid token supplied"}}'
    )
    _install_fake_curl(monkeypatch, body)

    client = RapidgatorFileManagerClient(token="stale")
    with pytest.raises(_RGAuthError):
        client._api_call_once("folder/content")


def test_api_call_once_non_auth_500_stays_runtime_error(monkeypatch):
    body = (
        '{"status": 500, '
        '"response": {"error": "Internal server error"}}'
    )
    _install_fake_curl(monkeypatch, body)

    client = RapidgatorFileManagerClient(token="stale")
    with pytest.raises(RuntimeError) as exc_info:
        client._api_call_once("folder/content")
    assert not isinstance(exc_info.value, _RGAuthError)


def test_api_call_once_raises_auth_error_on_outer_401(monkeypatch):
    _install_fake_curl(monkeypatch, "", code=401)

    client = RapidgatorFileManagerClient(token="stale")
    with pytest.raises(_RGAuthError):
        client._api_call_once("folder/content")
