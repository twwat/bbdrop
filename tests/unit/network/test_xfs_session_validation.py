"""Session validation for XFS-family file hosts (filedot, filespace).

Covers the fix for the 2026-09-08 bug where a 5-day-old FileDot session caused
1.1 GB to be uploaded anonymously four times.
See docs/superpowers/specs/2026-09-08-xfs-session-validation.md
"""

import json

import pytest
import pycurl
from unittest.mock import Mock, MagicMock, patch

from src.core.engine import AtomicCounter
from src.core.file_host_config import HostConfig
from src.network.file_host_client import (
    FileHostClient,
    SessionExpiredError,
    UploadRejectedError,
)


FILEDOT_SESS_RE = r'name="sess_id"\s+value="([^"]+)"'


def make_curl_mock(status=200, effective_url="https://filedot.to/upload", body=""):
    """Build a MagicMock standing in for a pycurl.Curl handle.

    Replays whatever the code registered via WRITEDATA when perform() is
    called, and answers getinfo() for RESPONSE_CODE / EFFECTIVE_URL.
    """
    curl = MagicMock()

    def _getinfo(option):
        if option == pycurl.RESPONSE_CODE:
            return status
        if option == pycurl.EFFECTIVE_URL:
            return effective_url
        return None

    def _perform():
        for call_item in curl.setopt.call_args_list:
            if call_item[0][0] == pycurl.WRITEDATA:
                call_item[0][1].write(body.encode())

    curl.getinfo.side_effect = _getinfo
    curl.perform.side_effect = _perform
    return curl


@pytest.fixture
def bandwidth_counter():
    return AtomicCounter()


@pytest.fixture
def filedot_config():
    """Regex-scrape session host (FileDot).

    Deliberately diverges from assets/hosts/filedot.json in one respect: the
    real host uses `{server}/upload.cgi` plus a `get_server` probe, which adds
    a network round-trip before session acquisition. Most tests here null
    get_server and use a concrete endpoint so handle counts stay readable;
    `test_real_filedot_shape_probes_server_then_session` covers the real shape.
    """
    config = Mock(spec=HostConfig)
    config.name = "Filedot"
    config.requires_auth = True
    config.auth_type = "session"
    config.session_cookie_name = None
    config.session_id_regex = FILEDOT_SESS_RE
    config.upload_page_url = "https://filedot.to/upload"
    config.upload_endpoint = "https://fs29.example.test/cgi-bin/upload.cgi"
    config.session_token_ttl = 3600
    # Set explicitly: stale_token_patterns is a default_factory field so it is
    # absent from dir(HostConfig) and Mock(spec=...) would raise on it;
    # check_body_on_success IS in dir, so an unset Mock returns a truthy child
    # Mock — the opposite of its real False default.
    config.stale_token_patterns = []
    config.check_body_on_success = False
    config.user_info_url = None
    return config


@pytest.fixture
def filespace_config():
    """Cookie-as-sess_id session host (FileSpace)."""
    config = Mock(spec=HostConfig)
    config.name = "Filespace"
    config.requires_auth = True
    config.auth_type = "session"
    config.session_cookie_name = "xfss"
    config.session_id_regex = None
    config.upload_page_url = None
    config.upload_endpoint = "https://phoebe.example.test/cgi-bin/upload.cgi"
    config.session_token_ttl = 3600
    # Set explicitly: stale_token_patterns is a default_factory field so it is
    # absent from dir(HostConfig) and Mock(spec=...) would raise on it;
    # check_body_on_success IS in dir, so an unset Mock returns a truthy child
    # Mock — the opposite of its real False default.
    config.stale_token_patterns = []
    config.check_body_on_success = False
    config.user_info_url = None
    return config


def build_client(config, bandwidth_counter):
    """Construct a client without triggering login (credentials omitted)."""
    return FileHostClient(host_config=config, bandwidth_counter=bandwidth_counter)


@pytest.mark.unit
class TestAcquireSessionIdCookieBranch:

    def test_present_cookie_returned(self, filespace_config, bandwidth_counter):
        client = build_client(filespace_config, bandwidth_counter)
        client.cookie_jar = {"xfss": "live-session-value"}

        result = client._acquire_session_id("https://phoebe.example.test/x")

        assert result == "live-session-value"

    def test_missing_cookie_raises(self, filespace_config, bandwidth_counter):
        client = build_client(filespace_config, bandwidth_counter)
        client.cookie_jar = {"other": "value"}

        with pytest.raises(SessionExpiredError, match="xfss"):
            client._acquire_session_id("https://phoebe.example.test/x")

    def test_empty_cookie_raises(self, filespace_config, bandwidth_counter):
        client = build_client(filespace_config, bandwidth_counter)
        client.cookie_jar = {"xfss": "   "}

        with pytest.raises(SessionExpiredError):
            client._acquire_session_id("https://phoebe.example.test/x")


@pytest.mark.unit
class TestAcquireSessionIdRegexBranch:

    @patch('src.network.file_host_client.pycurl.Curl')
    def test_valid_page_returns_sess_id(self, mock_curl_class, filedot_config, bandwidth_counter):
        mock_curl_class.return_value = make_curl_mock(
            status=200,
            effective_url="https://filedot.to/upload",
            body='<input type="hidden" name="sess_id" value="abc123def">',
        )
        client = build_client(filedot_config, bandwidth_counter)
        client.cookie_jar = {"xfss": "live"}

        result = client._acquire_session_id("https://fs29.example.test/cgi-bin/upload.cgi")

        assert result == "abc123def"
        assert client._session_token_timestamp is not None

    @patch('src.network.file_host_client.pycurl.Curl')
    def test_redirect_to_login_raises(self, mock_curl_class, filedot_config, bandwidth_counter):
        """The exact FileDot failure: 302 -> ?op=login, followed by FOLLOWLOCATION."""
        mock_curl_class.return_value = make_curl_mock(
            status=200,
            effective_url="https://filedot.to/?op=login",
            body="<html><body>Login</body></html>",
        )
        client = build_client(filedot_config, bandwidth_counter)
        client.cookie_jar = {"xfss": "five-days-old"}

        with pytest.raises(SessionExpiredError, match="login"):
            client._acquire_session_id("https://fs29.example.test/cgi-bin/upload.cgi")

    @patch('src.network.file_host_client.pycurl.Curl')
    def test_non_200_raises(self, mock_curl_class, filedot_config, bandwidth_counter):
        mock_curl_class.return_value = make_curl_mock(
            status=503, effective_url="https://filedot.to/upload", body="")
        client = build_client(filedot_config, bandwidth_counter)

        with pytest.raises(SessionExpiredError, match="503"):
            client._acquire_session_id("https://fs29.example.test/cgi-bin/upload.cgi")

    @patch('src.network.file_host_client.pycurl.Curl')
    def test_no_regex_match_raises(self, mock_curl_class, filedot_config, bandwidth_counter):
        """A 200 page with no sess_id field is still a dead session."""
        mock_curl_class.return_value = make_curl_mock(
            status=200,
            effective_url="https://filedot.to/upload",
            body="<html><body>nothing useful here</body></html>",
        )
        client = build_client(filedot_config, bandwidth_counter)

        with pytest.raises(SessionExpiredError, match="sess_id"):
            client._acquire_session_id("https://fs29.example.test/cgi-bin/upload.cgi")


    def test_unexpanded_template_fallback_is_a_config_error(
        self, filedot_config, bandwidth_counter
    ):
        """_refresh_auth_token passes config.upload_endpoint raw, which for
        filedot is "{server}/upload.cgi". With no upload_page_url configured
        the fallback would derive "{server}/upload" and fetch garbage."""
        filedot_config.upload_page_url = None
        client = build_client(filedot_config, bandwidth_counter)

        with pytest.raises(ValueError, match="upload_page_url") as exc:
            client._acquire_session_id("{server}/upload.cgi")

        # A config error, not a session error — must not trigger a re-login
        # retry via _with_token_retry.
        assert not isinstance(exc.value, SessionExpiredError)


@pytest.mark.unit
class TestAcquireSessionIdNonSessionHosts:

    def test_api_key_host_returns_none(self, bandwidth_counter):
        config = Mock(spec=HostConfig)
        config.name = "Katfile"
        config.requires_auth = True
        config.auth_type = "api_key"
        client = FileHostClient(host_config=config, bandwidth_counter=bandwidth_counter)

        assert client._acquire_session_id("https://katfile.test/upload") is None
