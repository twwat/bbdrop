"""Tests for K2S-family createFileByHash deduplication in FileHostClient."""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock

import pycurl

from src.network.file_host_client import FileHostClient
from src.core.file_host_config import HostConfig
from src.core.engine import AtomicCounter


@pytest.fixture
def k2s_config():
    """Create a HostConfig mock configured for K2S-style hash dedup."""
    config = Mock(spec=HostConfig)
    config.name = "Keep2Share"
    config.requires_auth = False  # Skip login in __init__
    config.auth_type = None
    config.upload_endpoint = "https://keep2share.cc/upload"
    config.upload_init_url = "https://api.keep2share.cc/v2/getUploadFormData"
    config.dedupe_endpoint = "createFileByHash"
    config.method = "POST"
    config.file_field = "file"
    config.extra_fields = {}
    config.response_type = "json"
    config.link_path = ["url"]
    config.link_prefix = ""
    config.link_suffix = ""
    config.link_regex = None
    config.storage_total_path = None
    config.storage_used_path = None
    config.storage_left_path = None
    config.premium_status_path = None
    config.file_id_path = ["file_id"]
    config.get_server = None
    config.upload_poll_url = None
    config.token_ttl = 3600
    return config


@pytest.fixture
def no_dedupe_config():
    """Create a HostConfig mock with no dedupe endpoint."""
    config = Mock(spec=HostConfig)
    config.name = "NoDedupe"
    config.requires_auth = False
    config.auth_type = None
    config.upload_endpoint = "https://example.com/upload"
    config.upload_init_url = None
    config.dedupe_endpoint = None
    config.method = "POST"
    config.file_field = "file"
    config.extra_fields = {}
    config.response_type = "json"
    config.link_path = ["url"]
    config.link_prefix = ""
    config.link_suffix = ""
    config.link_regex = None
    config.storage_total_path = None
    config.storage_used_path = None
    config.storage_left_path = None
    config.premium_status_path = None
    config.file_id_path = ["file_id"]
    config.get_server = None
    config.upload_poll_url = None
    config.token_ttl = 3600
    return config


@pytest.fixture
def bandwidth_counter():
    return AtomicCounter()


def _make_client(config, bandwidth_counter, auth_token=None):
    """Create a FileHostClient and set auth_token directly."""
    client = FileHostClient(
        host_config=config,
        bandwidth_counter=bandwidth_counter
    )
    client.auth_token = auth_token
    return client


class TestHashDedupTokenField:
    """Verify createFileByHash sends access_token (not auth_token) in the JSON body."""

    def test_request_body_uses_access_token(self, k2s_config, bandwidth_counter):
        """The JSON body must use 'access_token', matching other K2S endpoints."""
        client = _make_client(k2s_config, bandwidth_counter, auth_token="test-token-abc")

        captured_body = {}

        def fake_setopt(opt, val):
            if opt == pycurl.POSTFIELDS:
                captured_body.update(json.loads(val))
            if opt == pycurl.WRITEDATA:
                val.write(json.dumps({
                    "status": "success",
                    "id": "file123",
                    "link": "https://k2s.cc/file/file123/test.zip"
                }).encode('utf-8'))

        mock_curl = MagicMock()
        mock_curl.setopt.side_effect = fake_setopt
        mock_curl.getinfo.return_value = 200

        with patch('pycurl.Curl', return_value=mock_curl), \
                patch.object(client, '_wait_for_hash_copy', return_value=True):
            result = client.try_create_by_hash("d41d8cd98f00b204e9800998ecf8427e", "test.zip")

        # Key assertion: the field must be "access_token", NOT "auth_token"
        assert "access_token" in captured_body, (
            f"Expected 'access_token' in request body, got keys: {list(captured_body.keys())}"
        )
        assert "auth_token" not in captured_body, (
            "Request body must NOT contain 'auth_token' — K2S API rejects it"
        )
        assert captured_body["access_token"] == "test-token-abc"
        assert captured_body["hash"] == "d41d8cd98f00b204e9800998ecf8427e"
        assert captured_body["name"] == "test.zip"

    def test_access_token_empty_when_no_auth(self, k2s_config, bandwidth_counter):
        """access_token should be empty string when client has no auth token."""
        client = _make_client(k2s_config, bandwidth_counter, auth_token=None)

        captured_body = {}

        def fake_setopt(opt, val):
            if opt == pycurl.POSTFIELDS:
                captured_body.update(json.loads(val))
            if opt == pycurl.WRITEDATA:
                val.write(json.dumps({
                    "status": "error",
                    "errorCode": 10,
                    "message": "Unauthorized"
                }).encode())

        mock_curl = MagicMock()
        mock_curl.setopt.side_effect = fake_setopt
        mock_curl.getinfo.return_value = 403

        with patch('pycurl.Curl', return_value=mock_curl):
            result = client.try_create_by_hash("abc123", "file.bin")

        assert result is None
        assert captured_body["access_token"] == ""


class TestHashDedupResponses:
    """Test try_create_by_hash response handling."""

    def test_returns_none_when_no_dedupe_endpoint(self, no_dedupe_config, bandwidth_counter):
        """Should return None immediately if config has no dedupe_endpoint."""
        client = _make_client(no_dedupe_config, bandwidth_counter)
        result = client.try_create_by_hash("abc123", "file.zip")
        assert result is None

    def test_returns_none_when_no_upload_init_url(self, k2s_config, bandwidth_counter):
        """Should return None if upload_init_url is not set."""
        k2s_config.upload_init_url = None
        client = _make_client(k2s_config, bandwidth_counter)
        result = client.try_create_by_hash("abc123", "file.zip")
        assert result is None

    def test_success_returns_dedup_result(self, k2s_config, bandwidth_counter):
        """Successful hash match returns result with deduplication=True."""
        client = _make_client(k2s_config, bandwidth_counter, auth_token="tok")

        def fake_setopt(opt, val):
            if opt == pycurl.WRITEDATA:
                val.write(json.dumps({
                    "status": "success",
                    "id": "file999",
                    "link": "https://k2s.cc/file/file999/archive.rar"
                }).encode())

        mock_curl = MagicMock()
        mock_curl.setopt.side_effect = fake_setopt
        mock_curl.getinfo.return_value = 200

        with patch('pycurl.Curl', return_value=mock_curl), \
                patch.object(client, '_wait_for_hash_copy', return_value=True) as wait:
            result = client.try_create_by_hash("aabbccdd", "archive.rar")

        # Only reported once getFilesInfo confirms the new file exists.
        wait.assert_called_once_with("https://api.keep2share.cc/v2", "file999")

        assert result is not None
        assert result["status"] == "success"
        assert result["deduplication"] is True
        assert result["file_id"] == "file999"
        assert result["url"] == "https://k2s.cc/file/file999/archive.rar"

    def test_error_code_20_returns_none(self, k2s_config, bandwidth_counter):
        """Error code 20 (hash not found) should return None for normal upload."""
        client = _make_client(k2s_config, bandwidth_counter, auth_token="tok")

        def fake_setopt(opt, val):
            if opt == pycurl.WRITEDATA:
                val.write(json.dumps({
                    "status": "error",
                    "errorCode": 20,
                    "message": "File not found"
                }).encode())

        mock_curl = MagicMock()
        mock_curl.setopt.side_effect = fake_setopt
        mock_curl.getinfo.return_value = 200

        with patch('pycurl.Curl', return_value=mock_curl):
            result = client.try_create_by_hash("aabbccdd", "file.zip")

        assert result is None

    def test_error_code_10_returns_none_for_fallback(self, k2s_config, bandwidth_counter):
        """Error code 10 (auth error) should return None so caller falls back to regular upload."""
        client = _make_client(k2s_config, bandwidth_counter, auth_token="bad-tok")
        log_messages = []
        client._log_callback = lambda msg, level: log_messages.append((msg, level))

        def fake_setopt(opt, val):
            if opt == pycurl.WRITEDATA:
                val.write(json.dumps({
                    "status": "error",
                    "errorCode": 10,
                    "message": "You are not authorized for this action"
                }).encode())

        mock_curl = MagicMock()
        mock_curl.setopt.side_effect = fake_setopt
        mock_curl.getinfo.return_value = 403

        with patch('pycurl.Curl', return_value=mock_curl):
            result = client.try_create_by_hash("aabbccdd", "file.zip")

        assert result is None
        # Should log a warning about the auth error
        assert any("auth error" in msg and level == "warning"
                    for msg, level in log_messages)

    def test_error_code_64_raises_quota_error(self, k2s_config, bandwidth_counter):
        """Error code 64 should raise a quota exceeded exception."""
        client = _make_client(k2s_config, bandwidth_counter, auth_token="tok")

        def fake_setopt(opt, val):
            if opt == pycurl.WRITEDATA:
                val.write(json.dumps({
                    "status": "error",
                    "errorCode": 64,
                    "message": "Disk quota exceeded"
                }).encode())

        mock_curl = MagicMock()
        mock_curl.setopt.side_effect = fake_setopt
        mock_curl.getinfo.return_value = 200

        with patch('pycurl.Curl', return_value=mock_curl):
            with pytest.raises(Exception, match="Disk quota exceeded"):
                client.try_create_by_hash("aabbccdd", "file.zip")

    def test_network_error_returns_none(self, k2s_config, bandwidth_counter):
        """pycurl network errors should return None (caller uploads normally)."""
        client = _make_client(k2s_config, bandwidth_counter, auth_token="tok")

        mock_curl = MagicMock()
        mock_curl.perform.side_effect = pycurl.error(28, "Connection timed out")

        with patch('pycurl.Curl', return_value=mock_curl):
            result = client.try_create_by_hash("aabbccdd", "file.zip")

        assert result is None

    def test_invalid_json_returns_none(self, k2s_config, bandwidth_counter):
        """Invalid JSON response should return None."""
        client = _make_client(k2s_config, bandwidth_counter, auth_token="tok")

        def fake_setopt(opt, val):
            if opt == pycurl.WRITEDATA:
                val.write(b"not json at all")

        mock_curl = MagicMock()
        mock_curl.setopt.side_effect = fake_setopt
        mock_curl.getinfo.return_value = 200

        with patch('pycurl.Curl', return_value=mock_curl):
            result = client.try_create_by_hash("aabbccdd", "file.zip")

        assert result is None

    def test_builds_correct_dedupe_url(self, k2s_config, bandwidth_counter):
        """Dedupe URL should be built from upload_init_url base + dedupe_endpoint."""
        client = _make_client(k2s_config, bandwidth_counter, auth_token="tok")

        captured_url = []

        def fake_setopt(opt, val):
            if opt == pycurl.URL:
                captured_url.append(val)
            if opt == pycurl.WRITEDATA:
                val.write(json.dumps({"status": "error", "errorCode": 20}).encode())

        mock_curl = MagicMock()
        mock_curl.setopt.side_effect = fake_setopt
        mock_curl.getinfo.return_value = 200

        with patch('pycurl.Curl', return_value=mock_curl):
            client.try_create_by_hash("aabbccdd", "file.zip")

        assert len(captured_url) == 1
        assert captured_url[0] == "https://api.keep2share.cc/v2/createFileByHash"


class TestHashDedupAccessField:
    """K2S-family dedup must pin ``access`` so dedup hits don't inherit the
    account's server-side default (commonly ``premium``)."""

    def test_access_public_by_default(self, k2s_config, bandwidth_counter, monkeypatch):
        """With no Advanced override, the body must declare access=public."""
        monkeypatch.setattr(
            "src.network.file_host_client._k2s_default_upload_access",
            lambda: "public",
        )
        client = _make_client(k2s_config, bandwidth_counter, auth_token="tok")

        captured_body = {}

        def fake_setopt(opt, val):
            if opt == pycurl.POSTFIELDS:
                captured_body.update(json.loads(val))
            if opt == pycurl.WRITEDATA:
                val.write(json.dumps({"status": "error", "errorCode": 20}).encode())

        mock_curl = MagicMock()
        mock_curl.setopt.side_effect = fake_setopt
        mock_curl.getinfo.return_value = 200

        with patch('pycurl.Curl', return_value=mock_curl):
            client.try_create_by_hash("aabbccdd", "file.zip")

        assert captured_body.get("access") == "public"

    def test_access_respects_advanced_override(self, k2s_config, bandwidth_counter, monkeypatch):
        """When the Advanced setting is flipped, the body carries that value."""
        monkeypatch.setattr(
            "src.network.file_host_client._k2s_default_upload_access",
            lambda: "private",
        )
        client = _make_client(k2s_config, bandwidth_counter, auth_token="tok")

        captured_body = {}

        def fake_setopt(opt, val):
            if opt == pycurl.POSTFIELDS:
                captured_body.update(json.loads(val))
            if opt == pycurl.WRITEDATA:
                val.write(json.dumps({"status": "error", "errorCode": 20}).encode())

        mock_curl = MagicMock()
        mock_curl.setopt.side_effect = fake_setopt
        mock_curl.getinfo.return_value = 200

        with patch('pycurl.Curl', return_value=mock_curl):
            client.try_create_by_hash("aabbccdd", "file.zip")

        assert captured_body.get("access") == "private"


def _curl_factory(responses_by_endpoint):
    """Build a pycurl.Curl replacement that answers per endpoint.

    `responses_by_endpoint` maps an endpoint suffix ("createFileByHash",
    "getFilesInfo", "deleteFiles") to a list of JSON bodies served in order;
    the last body repeats once the list runs out. Returns (factory, calls),
    where calls records (endpoint, request_body) for every perform().
    """
    calls = []
    served = {k: 0 for k in responses_by_endpoint}

    def make_curl():
        state = {}
        curl = MagicMock()

        def setopt(opt, val):
            if opt == pycurl.URL:
                state["url"] = val
            elif opt == pycurl.POSTFIELDS:
                state["body"] = val
            elif opt == pycurl.WRITEDATA:
                state["buf"] = val

        def perform():
            endpoint = state["url"].rsplit("/", 1)[-1]
            calls.append((endpoint, json.loads(state.get("body") or "{}")))
            bodies = responses_by_endpoint[endpoint]
            body = bodies[min(served[endpoint], len(bodies) - 1)]
            served[endpoint] += 1
            if isinstance(body, Exception):
                raise body
            state["buf"].write(json.dumps(body).encode())

        curl.setopt.side_effect = setopt
        curl.perform.side_effect = perform
        curl.getinfo.return_value = 202
        return curl

    return make_curl, calls


ACCEPTED = {"status": "success", "id": "user42", "link": "https://fboom.me/file/9b29053e83d75"}
STUB = {"files": [{"id": "9b29053e83d75", "name": "", "md5": "", "is_available": False}]}
REAL = {"files": [{"id": "9b29053e83d75", "name": "g.zip", "md5": "aabbccdd", "is_available": True}]}


@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr("src.network.file_host_client.time.sleep", lambda s: None)


class TestHashCopyVerification:
    """createFileByHash's 202 'success' only means the request was accepted.

    The copy is built afterwards and on some hosts (Keep2Share always,
    FileBoom sometimes) it stays an empty stub forever. The client must not
    report a hash hit until getFilesInfo shows the file.
    """

    def test_stub_that_never_appears_is_not_reported_as_created(
            self, k2s_config, bandwidth_counter, no_sleep):
        k2s_config.delete_url = "https://api.keep2share.cc/v2/deleteFiles"
        k2s_config.delete_body_json = True
        client = _make_client(k2s_config, bandwidth_counter, auth_token="tok")
        logs = []
        client._log_callback = lambda msg, level: logs.append((msg, level))
        factory, calls = _curl_factory({
            "createFileByHash": [ACCEPTED],
            "getFilesInfo": [STUB],
            "deleteFiles": [{"status": "success", "deleted": 1}],
        })

        with patch("pycurl.Curl", side_effect=factory), \
                patch("src.network.file_host_client._k2s_hash_copy_wait_seconds",
                      return_value=30):
            result = client.try_create_by_hash("aabbccdd", "g.zip")

        assert result is None  # caller falls through to a real upload
        assert not any("file created without upload" in m for m, _ in logs)
        assert any("never appeared" in m and lvl == "warning" for m, lvl in logs)
        info_calls = [b for ep, b in calls if ep == "getFilesInfo"]
        assert len(info_calls) == 10
        assert info_calls[0]["ids"] == ["9b29053e83d75"]
        # The empty stub is cleaned up so it doesn't litter the account.
        delete_calls = [b for ep, b in calls if ep == "deleteFiles"]
        assert delete_calls and delete_calls[0]["ids"] == ["9b29053e83d75"]

    def test_copy_that_appears_is_reported(self, k2s_config, bandwidth_counter, no_sleep):
        client = _make_client(k2s_config, bandwidth_counter, auth_token="tok")
        logs = []
        client._log_callback = lambda msg, level: logs.append((msg, level))
        factory, calls = _curl_factory({
            "createFileByHash": [ACCEPTED],
            "getFilesInfo": [STUB, STUB, REAL],
        })

        with patch("pycurl.Curl", side_effect=factory):
            result = client.try_create_by_hash("aabbccdd", "g.zip")

        assert result["status"] == "success"
        assert result["url"] == "https://fboom.me/file/9b29053e83d75"
        assert [ep for ep, _ in calls].count("getFilesInfo") == 3
        assert any("file created without upload" in m for m, _ in logs)

    def test_poll_errors_are_retried(self, k2s_config, bandwidth_counter, no_sleep):
        client = _make_client(k2s_config, bandwidth_counter, auth_token="tok")
        factory, calls = _curl_factory({
            "createFileByHash": [ACCEPTED],
            "getFilesInfo": [pycurl.error(28, "timeout"), REAL],
        })

        with patch("pycurl.Curl", side_effect=factory):
            result = client.try_create_by_hash("aabbccdd", "g.zip")

        assert result is not None

    def test_delete_failure_still_falls_through(self, k2s_config, bandwidth_counter, no_sleep):
        client = _make_client(k2s_config, bandwidth_counter, auth_token="tok")
        factory, _ = _curl_factory({
            "createFileByHash": [ACCEPTED],
            "getFilesInfo": [STUB],
        })

        with patch("pycurl.Curl", side_effect=factory), \
                patch.object(client, "delete_file", side_effect=ValueError("no delete")):
            result = client.try_create_by_hash("aabbccdd", "g.zip")

        assert result is None


class TestHashCopyWaitSetting:
    """How long to wait for a hash copy is [Advanced]
    k2s_family/hash_copy_wait_seconds, not a hardcoded number."""

    def _read(self, tmp_path, ini_text=None):
        from src.network.file_host_client import _k2s_hash_copy_wait_seconds
        ini = tmp_path / "bbdrop.ini"
        if ini_text is not None:
            ini.write_text(ini_text, encoding="utf-8")
        with patch("src.utils.paths.get_config_path", return_value=str(ini)):
            return _k2s_hash_copy_wait_seconds()

    def test_default_when_unset(self, tmp_path):
        from src.network.file_host_client import HASH_COPY_WAIT_DEFAULT_SEC
        assert self._read(tmp_path) == HASH_COPY_WAIT_DEFAULT_SEC
        assert self._read(tmp_path, "[Advanced]\n") == HASH_COPY_WAIT_DEFAULT_SEC

    def test_reads_configured_value(self, tmp_path):
        assert self._read(
            tmp_path, "[Advanced]\nk2s_family/hash_copy_wait_seconds = 120\n") == 120

    def test_garbage_falls_back_to_default(self, tmp_path):
        from src.network.file_host_client import HASH_COPY_WAIT_DEFAULT_SEC
        assert self._read(
            tmp_path, "[Advanced]\nk2s_family/hash_copy_wait_seconds = soon\n"
        ) == HASH_COPY_WAIT_DEFAULT_SEC

    def test_out_of_range_is_clamped(self, tmp_path):
        from src.network.file_host_client import (
            HASH_COPY_WAIT_MAX_SEC, HASH_COPY_WAIT_MIN_SEC)
        assert self._read(
            tmp_path, "[Advanced]\nk2s_family/hash_copy_wait_seconds = 99999\n"
        ) == HASH_COPY_WAIT_MAX_SEC
        assert self._read(
            tmp_path, "[Advanced]\nk2s_family/hash_copy_wait_seconds = 0\n"
        ) == HASH_COPY_WAIT_MIN_SEC

    def test_poll_count_follows_setting(self, k2s_config, bandwidth_counter, no_sleep):
        client = _make_client(k2s_config, bandwidth_counter, auth_token="tok")
        factory, calls = _curl_factory({
            "createFileByHash": [ACCEPTED],
            "getFilesInfo": [STUB],
        })

        with patch("pycurl.Curl", side_effect=factory), \
                patch("src.network.file_host_client._k2s_hash_copy_wait_seconds",
                      return_value=9), \
                patch.object(client, "delete_file"):
            assert client.try_create_by_hash("aabbccdd", "g.zip") is None

        # 9s at one check every 3s
        assert [ep for ep, _ in calls].count("getFilesInfo") == 3

    def test_setting_is_in_advanced_tab(self):
        from src.gui.settings.advanced_tab import ADVANCED_SETTINGS
        from src.network.file_host_client import (
            HASH_COPY_WAIT_DEFAULT_SEC, HASH_COPY_WAIT_MAX_SEC, HASH_COPY_WAIT_MIN_SEC)
        row = next(s for s in ADVANCED_SETTINGS
                   if s["key"] == "k2s_family/hash_copy_wait_seconds")
        assert row["type"] == "int"
        assert (row["default"], row["min"], row["max"]) == (
            HASH_COPY_WAIT_DEFAULT_SEC, HASH_COPY_WAIT_MIN_SEC, HASH_COPY_WAIT_MAX_SEC)

    def test_stop_ends_the_wait(self, k2s_config, bandwidth_counter, no_sleep):
        client = _make_client(k2s_config, bandwidth_counter, auth_token="tok")
        client.should_stop_func = lambda: True
        logs = []
        client._log_callback = lambda msg, level: logs.append((msg, level))
        factory, calls = _curl_factory({
            "createFileByHash": [ACCEPTED],
            "getFilesInfo": [STUB],
        })

        with patch("pycurl.Curl", side_effect=factory), \
                patch("src.network.file_host_client._k2s_hash_copy_wait_seconds",
                      return_value=600), \
                patch.object(client, "delete_file") as mock_delete:
            assert client.try_create_by_hash("aabbccdd", "g.zip") is None

        assert [ep for ep, _ in calls].count("getFilesInfo") == 0
        assert not any("never appeared" in m for m, _ in logs)
        mock_delete.assert_called_once_with("9b29053e83d75")
