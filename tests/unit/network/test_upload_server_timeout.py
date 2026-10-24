"""The upload-server lookup honours the host's connect timeout setting.

A fixed 10s limit failed Filedot uploads permanently whenever its /server
endpoint took longer than that to answer (2026-10-24, galleries 2396-2398, 2410).
"""
from unittest.mock import Mock, patch

import pycurl
import pytest

from src.core.engine import AtomicCounter
from src.core.file_host_config import HostConfig
from src.network.file_host_client import FileHostClient

from tests.unit.network.test_xfs_session_validation import make_curl_mock

pytestmark = pytest.mark.unit


def _config():
    config = Mock(spec=HostConfig)
    config.name = "Filedot"
    config.requires_auth = False
    config.get_server = "https://filedot.to/server"
    config.upload_endpoint = "{server}/upload.cgi"
    config.server_response_path = ["url"]
    config.server_session_id_path = None
    config.inactivity_timeout = 300
    config.upload_timeout = None
    return config


def _timeouts_used(connect_timeout):
    settings = {"connect_timeout": connect_timeout}
    with patch("src.core.file_host_config.get_file_host_setting",
               side_effect=lambda host, key, kind="str": settings.get(key)):
        client = FileHostClient(_config(), AtomicCounter(), host_id="filedot")
    curl = make_curl_mock(body='{"url": "https://fs7.filedot.to/cgi-bin"}')
    with patch("src.network.file_host_client.pycurl.Curl", return_value=curl):
        server_url, _ = client._get_upload_server()
    assert server_url == "https://fs7.filedot.to/cgi-bin/upload.cgi"
    return [c.args[1] for c in curl.setopt.call_args_list if c.args[0] == pycurl.TIMEOUT]


def test_server_lookup_uses_connect_timeout_setting():
    assert _timeouts_used(45) == [45]


def test_server_lookup_defaults_to_30_seconds_when_unset():
    assert _timeouts_used(None) == [30]
