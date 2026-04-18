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

        with patch('pycurl.Curl', return_value=mock_curl):
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

        with patch('pycurl.Curl', return_value=mock_curl):
            result = client.try_create_by_hash("aabbccdd", "archive.rar")

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
