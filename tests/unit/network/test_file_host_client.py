"""
Comprehensive pytest test suite for FileHostClient.

Tests file uploads, authentication, retry logic, token refresh,
and session management with full pycurl mocking.
"""

import pytest
import json
import tempfile
import time
import hashlib
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
from io import BytesIO

import pycurl

from src.network.file_host_client import FileHostClient
from src.core.file_host_config import HostConfig
from src.core.engine import AtomicCounter


class TestFileHostClientInitialization:
    """Test suite for FileHostClient initialization."""

    @pytest.fixture
    def mock_host_config(self):
        """Create a mock HostConfig."""
        config = Mock(spec=HostConfig)
        config.name = "TestHost"
        config.requires_auth = False
        config.auth_type = None
        config.upload_endpoint = "https://testhost.com/upload"
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
        config.upload_init_url = None
        return config

    @pytest.fixture
    def bandwidth_counter(self):
        """Create a bandwidth counter."""
        return AtomicCounter()

    def test_initialization_no_auth(self, mock_host_config, bandwidth_counter):
        """Test client initialization without authentication."""
        client = FileHostClient(
            host_config=mock_host_config,
            bandwidth_counter=bandwidth_counter
        )

        assert client.config == mock_host_config
        assert client.bandwidth_counter == bandwidth_counter
        assert client.credentials is None
        assert client.auth_token is None
        assert client.cookie_jar == {}

    def test_initialization_with_api_key(self, mock_host_config, bandwidth_counter):
        """Test client initialization with API key authentication."""
        mock_host_config.requires_auth = True
        mock_host_config.auth_type = "api_key"

        client = FileHostClient(
            host_config=mock_host_config,
            bandwidth_counter=bandwidth_counter,
            credentials="test_api_key_123"
        )

        assert client.auth_token == "test_api_key_123"

    @patch('src.network.file_host_client.pycurl.Curl')
    def test_initialization_with_token_login_cached(
        self, mock_curl_class, mock_host_config, bandwidth_counter
    ):
        """Test client initialization with cached token."""
        mock_host_config.requires_auth = True
        mock_host_config.auth_type = "token_login"
        mock_host_config.login_url = "https://testhost.com/login"
        mock_host_config.login_fields = {}
        mock_host_config.token_path = ["token"]

        # Mock token cache
        with patch('src.network.token_cache.get_token_cache') as mock_get_cache:
            mock_cache = Mock()
            mock_cache.get_token.return_value = "cached_token_xyz"
            mock_get_cache.return_value = mock_cache

            client = FileHostClient(
                host_config=mock_host_config,
                bandwidth_counter=bandwidth_counter,
                credentials="user:pass",
                host_id="testhost"
            )

            assert client.auth_token == "cached_token_xyz"
            mock_cache.get_token.assert_called_once_with("testhost")

    @patch('src.network.file_host_client.pycurl.Curl')
    @patch('certifi.where', return_value='/etc/ssl/certs/ca-certificates.crt')
    def test_initialization_with_token_login_no_cache(
        self, mock_certifi, mock_curl_class, mock_host_config, bandwidth_counter
    ):
        """Test client initialization with token login (no cache)."""
        mock_host_config.requires_auth = True
        mock_host_config.auth_type = "token_login"
        mock_host_config.login_url = "https://testhost.com/api/login"
        mock_host_config.login_fields = {"user": "{username}", "pass": "{password}"}
        mock_host_config.token_path = ["data", "token"]
        mock_host_config.token_ttl = 3600

        # Mock curl
        mock_curl = MagicMock()
        mock_curl_class.return_value = mock_curl

        # Mock response
        login_response = {"status": 200, "data": {"token": "new_token_abc"}}
        mock_curl.getinfo.return_value = 200

        def mock_perform():
            # Simulate writing response to buffer
            response_buffer = None
            for call_item in mock_curl.setopt.call_args_list:
                if call_item[0][0] == pycurl.WRITEDATA:
                    response_buffer = call_item[0][1]
            if response_buffer:
                response_buffer.write(json.dumps(login_response).encode())

        mock_curl.perform.side_effect = mock_perform

        # Mock token cache
        with patch('src.network.token_cache.get_token_cache') as mock_get_cache:
            mock_cache = Mock()
            mock_cache.get_token.return_value = None  # No cached token
            mock_get_cache.return_value = mock_cache

            client = FileHostClient(
                host_config=mock_host_config,
                bandwidth_counter=bandwidth_counter,
                credentials="testuser:testpass",
                host_id="testhost"
            )

            assert client.auth_token == "new_token_abc"
            mock_cache.store_token.assert_called_once_with("testhost", "new_token_abc", 3600)

    @patch('src.network.file_host_client.pycurl.Curl')
    def test_initialization_with_session_reuse(
        self, mock_curl_class, mock_host_config, bandwidth_counter
    ):
        """Test client initialization with existing session cookies."""
        mock_host_config.requires_auth = True
        mock_host_config.auth_type = "session"

        existing_cookies = {"PHPSESSID": "abc123", "user_id": "456"}
        existing_token = "sess_token_xyz"
        session_timestamp = time.time() - 100

        client = FileHostClient(
            host_config=mock_host_config,
            bandwidth_counter=bandwidth_counter,
            credentials="user:pass",
            session_cookies=existing_cookies,
            session_token=existing_token,
            session_timestamp=session_timestamp
        )

        assert client.cookie_jar == existing_cookies
        assert client.auth_token == existing_token
        assert client._session_token_timestamp == session_timestamp


class TestFileHostClientUploadStandard:
    """Test suite for standard file uploads."""

    @pytest.fixture
    def mock_host_config(self):
        """Create mock config for standard upload."""
        config = Mock(spec=HostConfig)
        config.name = "StandardHost"
        config.requires_auth = False
        config.upload_endpoint = "https://upload.test/api/upload"
        config.method = "POST"
        config.file_field = "filedata"
        config.extra_fields = {"folder": "root"}
        config.response_type = "json"
        config.link_path = ["data", "url"]
        config.link_prefix = "https://download.test/"
        config.link_suffix = ""
        config.link_regex = None
        config.storage_total_path = None
        config.storage_used_path = None
        config.storage_left_path = None
        config.premium_status_path = None
        config.file_id_path = ["data", "id"]
        config.get_server = None
        config.upload_init_url = None
        config.auth_type = None
        return config

    @pytest.fixture
    def test_file(self, tmp_path):
        """Create a test file."""
        file_path = tmp_path / "test_file.zip"
        file_path.write_bytes(b"test data content")
        return file_path

    @pytest.fixture
    def bandwidth_counter(self):
        """Create bandwidth counter."""
        return AtomicCounter()

    @patch('src.network.file_host_client.pycurl.Curl')
    def test_upload_file_success(
        self, mock_curl_class, mock_host_config, test_file, bandwidth_counter
    ):
        """Test successful file upload."""
        # Setup mock curl
        mock_curl = MagicMock()
        mock_curl_class.return_value = mock_curl

        upload_response = {
            "status": "success",
            "data": {
                "url": "abc123",
                "id": "file_456"
            }
        }

        mock_curl.getinfo.return_value = 200

        def mock_perform():
            for call_item in mock_curl.setopt.call_args_list:
                if call_item[0][0] == pycurl.WRITEDATA:
                    response_buffer = call_item[0][1]
                    response_buffer.write(json.dumps(upload_response).encode())

        mock_curl.perform.side_effect = mock_perform

        # Execute upload
        client = FileHostClient(
            host_config=mock_host_config,
            bandwidth_counter=bandwidth_counter
        )

        result = client.upload_file(test_file)

        # Verify result
        assert result['status'] == 'success'
        assert result['url'] == 'https://download.test/abc123'
        assert result['file_id'] == 'file_456'

        # Verify curl was configured correctly
        mock_curl.setopt.assert_any_call(pycurl.URL, 'https://upload.test/api/upload')
        mock_curl.setopt.assert_any_call(pycurl.TIMEOUT, 300)
        mock_curl.perform.assert_called_once()

    @patch('src.network.file_host_client.pycurl.Curl')
    def test_upload_file_with_progress_callback(
        self, mock_curl_class, mock_host_config, test_file, bandwidth_counter
    ):
        """Test upload with progress callback."""
        mock_curl = MagicMock()
        mock_curl_class.return_value = mock_curl
        mock_curl.getinfo.return_value = 200

        upload_response = {"status": "success", "data": {"url": "test123", "id": "id456"}}

        def mock_perform():
            # Simulate progress callbacks
            for call_item in mock_curl.setopt.call_args_list:
                if call_item[0][0] == pycurl.XFERINFOFUNCTION:
                    progress_func = call_item[0][1]
                    # Simulate upload progress
                    progress_func(0, 0, 1000, 500)
                    progress_func(0, 0, 1000, 1000)
                if call_item[0][0] == pycurl.WRITEDATA:
                    call_item[0][1].write(json.dumps(upload_response).encode())

        mock_curl.perform.side_effect = mock_perform

        # Track progress calls
        progress_calls = []

        def on_progress(uploaded, total):
            progress_calls.append((uploaded, total))

        client = FileHostClient(
            host_config=mock_host_config,
            bandwidth_counter=bandwidth_counter
        )

        result = client.upload_file(test_file, on_progress=on_progress)

        # Verify progress was tracked
        assert len(progress_calls) > 0
        assert result['status'] == 'success'

    @patch('src.network.file_host_client.pycurl.Curl')
    def test_upload_file_cancellation(
        self, mock_curl_class, mock_host_config, test_file, bandwidth_counter
    ):
        """Test upload cancellation via should_stop callback."""
        mock_curl = MagicMock()
        mock_curl_class.return_value = mock_curl

        def mock_perform():
            # Simulate progress callback that triggers cancellation
            for call_item in mock_curl.setopt.call_args_list:
                if call_item[0][0] == pycurl.XFERINFOFUNCTION:
                    progress_func = call_item[0][1]
                    # Progress function should return 1 to abort
                    result = progress_func(0, 0, 1000, 500)
                    if result == 1:
                        raise pycurl.error(42, "Callback aborted")

        mock_curl.perform.side_effect = mock_perform

        # Setup cancellation
        should_stop_called = False

        def should_stop():
            nonlocal should_stop_called
            should_stop_called = True
            return True

        client = FileHostClient(
            host_config=mock_host_config,
            bandwidth_counter=bandwidth_counter
        )

        # Execute with cancellation
        with pytest.raises(pycurl.error):
            client.upload_file(test_file, should_stop=should_stop)

        assert should_stop_called

    @patch('src.network.file_host_client.pycurl.Curl')
    def test_upload_file_http_error(
        self, mock_curl_class, mock_host_config, test_file, bandwidth_counter
    ):
        """Test upload failure with HTTP error."""
        mock_curl = MagicMock()
        mock_curl_class.return_value = mock_curl
        mock_curl.getinfo.return_value = 500  # Server error

        def mock_perform():
            for call_item in mock_curl.setopt.call_args_list:
                if call_item[0][0] == pycurl.WRITEDATA:
                    call_item[0][1].write(b"Internal Server Error")

        mock_curl.perform.side_effect = mock_perform

        client = FileHostClient(
            host_config=mock_host_config,
            bandwidth_counter=bandwidth_counter
        )

        with pytest.raises(Exception) as exc_info:
            client.upload_file(test_file)

        assert "500" in str(exc_info.value)

    @patch('src.network.file_host_client.pycurl.Curl')
    def test_upload_file_network_timeout(
        self, mock_curl_class, mock_host_config, test_file, bandwidth_counter
    ):
        """Test upload failure due to network timeout."""
        mock_curl = MagicMock()
        mock_curl_class.return_value = mock_curl
        mock_curl.perform.side_effect = pycurl.error(28, "Operation timed out")

        client = FileHostClient(
            host_config=mock_host_config,
            bandwidth_counter=bandwidth_counter
        )

        with pytest.raises(pycurl.error) as exc_info:
            client.upload_file(test_file)

        assert exc_info.value.args[0] == 28


class TestFileHostClientUploadMultistep:
    """Test suite for multi-step uploads (init -> upload -> poll)."""

    @pytest.fixture
    def mock_host_config(self):
        """Create mock config for multi-step upload."""
        config = Mock(spec=HostConfig)
        config.name = "MultiStepHost"
        config.requires_auth = True
        config.auth_type = "api_key"
        config.upload_endpoint = "https://upload.test/files"
        config.upload_init_url = "https://api.test/upload/init?filename={filename}&size={size}&token={token}"
        config.upload_url_path = ["upload_url"]
        config.upload_id_path = ["upload_id"]
        config.file_field_path = None
        config.form_data_path = None
        config.upload_poll_url = "https://api.test/upload/status/{upload_id}?token={token}"
        config.upload_poll_delay = 0.1
        config.upload_poll_retries = 3
        config.link_path = ["file_url"]
        config.file_id_path = ["file_id"]
        config.require_file_hash = False
        config.init_method = "GET"
        config.init_body_json = False
        return config

    @pytest.fixture
    def test_file(self, tmp_path):
        """Create test file."""
        file_path = tmp_path / "test_upload.zip"
        file_path.write_bytes(b"multi-step test data")
        return file_path

    @pytest.fixture
    def bandwidth_counter(self):
        """Create bandwidth counter."""
        return AtomicCounter()

    @patch('src.network.file_host_client.pycurl.Curl')
    def test_multistep_upload_success(
        self, mock_curl_class, mock_host_config, test_file, bandwidth_counter
    ):
        """Test successful multi-step upload."""
        # Setup responses for each step
        init_response = {
            "upload_url": "https://upload.test/session/abc123",
            "upload_id": "upload_456"
        }

        upload_response = {"status": "processing"}

        poll_response = {
            "file_url": "https://download.test/file/abc123",
            "file_id": "file_789"
        }

        responses = [init_response, upload_response, poll_response]
        response_idx = [0]

        def create_mock_curl():
            mock_curl = MagicMock()

            # Pre-configure getinfo to return 200
            mock_curl.getinfo.return_value = 200

            def mock_perform():
                idx = response_idx[0]
                response_idx[0] += 1

                # Write response data
                for call_item in mock_curl.setopt.call_args_list:
                    if call_item[0][0] == pycurl.WRITEDATA:
                        buffer = call_item[0][1]
                        buffer.write(json.dumps(responses[min(idx, len(responses) - 1)]).encode())

            mock_curl.perform.side_effect = mock_perform
            return mock_curl

        mock_curl_class.side_effect = create_mock_curl

        # Execute upload
        client = FileHostClient(
            host_config=mock_host_config,
            bandwidth_counter=bandwidth_counter,
            credentials="api_key_xyz"
        )

        result = client.upload_file(test_file)

        # Verify result
        assert result['status'] == 'success'
        assert result['url'] == 'https://download.test/file/abc123'
        assert result['file_id'] == 'file_789'
        assert result['upload_id'] == 'upload_456'

    @patch('src.network.file_host_client.pycurl.Curl')
    def test_multistep_upload_init_failure(
        self, mock_curl_class, mock_host_config, test_file, bandwidth_counter
    ):
        """Test multi-step upload failing at init stage."""
        mock_curl = MagicMock()
        mock_curl_class.return_value = mock_curl
        mock_curl.getinfo.return_value = 403  # Forbidden

        error_response = {"status": 403, "response": {"details": "Invalid API key"}}

        def mock_perform():
            for call_item in mock_curl.setopt.call_args_list:
                if call_item[0][0] == pycurl.WRITEDATA:
                    call_item[0][1].write(json.dumps(error_response).encode())

        mock_curl.perform.side_effect = mock_perform

        client = FileHostClient(
            host_config=mock_host_config,
            bandwidth_counter=bandwidth_counter,
            credentials="invalid_key"
        )

        with pytest.raises(Exception) as exc_info:
            client.upload_file(test_file)

        assert "403" in str(exc_info.value)
        assert "Invalid API key" in str(exc_info.value)

    @patch('src.network.file_host_client.pycurl.Curl')
    @patch('time.sleep')
    def test_multistep_upload_poll_timeout(
        self, mock_sleep, mock_curl_class, mock_host_config, test_file, bandwidth_counter
    ):
        """Test multi-step upload timing out during polling."""
        # Init and upload succeed, but polling never returns final URL
        init_response = {"upload_url": "https://upload.test/abc", "upload_id": "123"}
        upload_response = {"status": "ok"}
        poll_response = {"status": "processing"}  # Never completes

        responses = [init_response, upload_response] + [poll_response] * 10
        response_idx = [0]

        def create_mock_curl():
            mock_curl = MagicMock()

            def mock_perform():
                idx = response_idx[0]
                response_idx[0] += 1
                mock_curl.getinfo.return_value = 200

                for call_item in mock_curl.setopt.call_args_list:
                    if call_item[0][0] == pycurl.WRITEDATA:
                        call_item[0][1].write(json.dumps(responses[min(idx, len(responses) - 1)]).encode())

            mock_curl.perform.side_effect = mock_perform
            return mock_curl

        mock_curl_class.side_effect = create_mock_curl

        client = FileHostClient(
            host_config=mock_host_config,
            bandwidth_counter=bandwidth_counter,
            credentials="api_key"
        )

        with pytest.raises(Exception) as exc_info:
            client.upload_file(test_file)

        assert "timeout" in str(exc_info.value).lower()


class TestFileHostClientAuthentication:
    """Test suite for authentication mechanisms."""

    @pytest.fixture
    def bandwidth_counter(self):
        """Create bandwidth counter."""
        return AtomicCounter()

    @patch('src.network.file_host_client.pycurl.Curl')
    @patch('certifi.where', return_value='/etc/ssl/certs/ca-certificates.crt')
    def test_token_login_success(
        self, mock_certifi, mock_curl_class, bandwidth_counter
    ):
        """Test successful token-based login."""
        config = Mock(spec=HostConfig)
        config.name = "TokenHost"
        config.requires_auth = True
        config.auth_type = "token_login"
        config.login_url = "https://api.test/auth/login"
        config.login_fields = {"username": "{username}", "password": "{password}"}
        config.token_path = ["auth", "access_token"]
        config.storage_total_path = None
        config.storage_used_path = None
        config.storage_left_path = None
        config.premium_status_path = None
        config.token_ttl = 7200

        mock_curl = MagicMock()
        mock_curl_class.return_value = mock_curl
        mock_curl.getinfo.return_value = 200

        login_response = {
            "status": 200,
            "auth": {"access_token": "token_abc123xyz"}
        }

        def mock_perform():
            for call_item in mock_curl.setopt.call_args_list:
                if call_item[0][0] == pycurl.WRITEDATA:
                    call_item[0][1].write(json.dumps(login_response).encode())

        mock_curl.perform.side_effect = mock_perform

        with patch('src.network.token_cache.get_token_cache') as mock_get_cache:
            mock_cache = Mock()
            mock_cache.get_token.return_value = None
            mock_get_cache.return_value = mock_cache

            client = FileHostClient(
                host_config=config,
                bandwidth_counter=bandwidth_counter,
                credentials="testuser:testpass",
                host_id="tokenhost"
            )

            assert client.auth_token == "token_abc123xyz"
            mock_cache.store_token.assert_called_once_with("tokenhost", "token_abc123xyz", 7200)

    @patch('src.network.file_host_client.pycurl.Curl')
    @patch('certifi.where', return_value='/etc/ssl/certs/ca-certificates.crt')
    def test_token_login_failure(
        self, mock_certifi, mock_curl_class, bandwidth_counter
    ):
        """Test token login failure."""
        config = Mock(spec=HostConfig)
        config.name = "TokenHost"
        config.requires_auth = True
        config.auth_type = "token_login"
        config.login_url = "https://api.test/auth/login"
        config.login_fields = {"user": "{username}", "pass": "{password}"}
        config.token_path = ["token"]
        config.storage_total_path = None
        config.storage_used_path = None
        config.storage_left_path = None
        config.premium_status_path = None

        mock_curl = MagicMock()
        mock_curl_class.return_value = mock_curl
        mock_curl.getinfo.return_value = 401

        def mock_perform():
            for call_item in mock_curl.setopt.call_args_list:
                if call_item[0][0] == pycurl.WRITEDATA:
                    call_item[0][1].write(b'{"error": "Invalid credentials"}')

        mock_curl.perform.side_effect = mock_perform

        with patch('src.network.token_cache.get_token_cache') as mock_get_cache:
            mock_cache = Mock()
            mock_cache.get_token.return_value = None
            mock_get_cache.return_value = mock_cache

            with pytest.raises(ValueError) as exc_info:
                FileHostClient(
                    host_config=config,
                    bandwidth_counter=bandwidth_counter,
                    credentials="bad_user:bad_pass",
                    host_id="tokenhost"
                )

            assert "401" in str(exc_info.value)

    @patch('src.network.file_host_client.pycurl.Curl')
    def test_session_based_login_success(self, mock_curl_class, bandwidth_counter):
        """Test successful session-based login."""
        config = Mock(spec=HostConfig)
        config.name = "SessionHost"
        config.requires_auth = True
        config.auth_type = "session"
        config.login_url = "https://sessionhost.test/login"
        config.login_fields = {"username": "{username}", "password": "{password}"}
        config.captcha_regex = None

        # Mock curl instances for GET and POST
        curl_instances = []

        curl_instances = []
        
        def create_mock_curl():
            mock_curl = MagicMock()
            curl_instances.append(mock_curl)
            return mock_curl

        mock_curl_class.side_effect = create_mock_curl

        # GET response (login page with hidden fields)
        get_response = b'<input type="hidden" name="csrf_token" value="abc123" />'
        get_headers = b'HTTP/1.1 200 OK\r\nSet-Cookie: PHPSESSID=session123; path=/\r\n\r\n'

        # POST response (login success)
        post_headers = b'HTTP/1.1 302 Found\r\nSet-Cookie: user_token=token456; path=/\r\n\r\n'

        def mock_get_perform():
            curl = curl_instances[0]
            for call_item in curl.setopt.call_args_list:
                if call_item[0][0] == pycurl.WRITEDATA:
                    call_item[0][1].write(get_response)
                elif call_item[0][0] == pycurl.HEADERFUNCTION:
                    call_item[0][1](get_headers)

        def mock_post_perform():
            curl = curl_instances[1]
            curl.getinfo.return_value = 302
            for call_item in curl.setopt.call_args_list:
                if call_item[0][0] == pycurl.WRITEDATA:
                    call_item[0][1].write(b'Redirect')
                elif call_item[0][0] == pycurl.HEADERFUNCTION:
                    call_item[0][1](post_headers)

        curl_instances[0].perform.side_effect = mock_get_perform
        curl_instances[1].perform.side_effect = mock_post_perform

        client = FileHostClient(
            host_config=config,
            bandwidth_counter=bandwidth_counter,
            credentials="user:pass"
        )

        # Verify cookies were set
        assert "PHPSESSID" in client.cookie_jar
        assert "user_token" in client.cookie_jar


class TestFileHostClientTokenRefresh:
    """Test suite for automatic token refresh and retry logic."""

    @pytest.fixture
    def bandwidth_counter(self):
        """Create bandwidth counter."""
        return AtomicCounter()

    @pytest.fixture
    def test_file(self, tmp_path):
        """Create test file."""
        file_path = tmp_path / "test.zip"
        file_path.write_bytes(b"test data")
        return file_path

    @patch('src.network.file_host_client.pycurl.Curl')
    @patch('certifi.where', return_value='/etc/ssl/certs/ca-certificates.crt')
    def test_token_refresh_on_stale_error(
        self, mock_certifi, mock_curl_class, bandwidth_counter, test_file
    ):
        """Test automatic token refresh when stale token detected."""
        config = Mock(spec=HostConfig)
        config.name = "RefreshHost"
        config.requires_auth = True
        config.auth_type = "token_login"
        config.login_url = "https://api.test/login"
        config.login_fields = {"user": "{username}", "pass": "{password}"}
        config.token_path = ["token"]
        config.token_ttl = 3600
        config.upload_endpoint = "https://upload.test/api/upload"
        config.upload_init_url = "https://api.test/init?token={token}"
        config.upload_url_path = ["upload_url"]
        config.upload_id_path = ["upload_id"]
        config.file_field_path = None
        config.form_data_path = None
        config.upload_poll_url = None
        config.link_path = ["url"]
        config.file_id_path = ["file_id"]
        config.stale_token_patterns = ["token expired", "unauthorized"]
        config.require_file_hash = False
        config.init_method = "GET"
        config.init_body_json = False
        config.storage_total_path = None
        config.storage_used_path = None
        config.storage_left_path = None
        config.premium_status_path = None

        # First init attempt fails with stale token
        stale_response = {"error": "token expired"}
        # Refresh login succeeds
        refresh_response = {"status": 200, "token": "new_token_refreshed"}
        # Second init attempt succeeds
        init_success = {"upload_url": "https://upload.test/session", "upload_id": "123"}
        # Upload succeeds
        upload_success = {"url": "https://download.test/file", "file_id": "456"}

        responses = [stale_response, refresh_response, init_success, upload_success]
        response_idx = [0]

        def create_mock_curl():
            mock_curl = MagicMock()

            def mock_perform():
                idx = response_idx[0]
                response_idx[0] += 1

                if idx == 0:  # Stale token error
                    mock_curl.getinfo.return_value = 401
                else:  # Success responses
                    mock_curl.getinfo.return_value = 200

                for call_item in mock_curl.setopt.call_args_list:
                    if call_item[0][0] == pycurl.WRITEDATA:
                        call_item[0][1].write(json.dumps(responses[min(idx, len(responses) - 1)]).encode())

            mock_curl.perform.side_effect = mock_perform
            return mock_curl

        mock_curl_class.side_effect = create_mock_curl

        with patch('src.network.token_cache.get_token_cache') as mock_get_cache:
            mock_cache = Mock()
            mock_cache.get_token.return_value = "old_stale_token"
            mock_get_cache.return_value = mock_cache

            client = FileHostClient(
                host_config=config,
                bandwidth_counter=bandwidth_counter,
                credentials="user:pass",
                host_id="refreshhost"
            )

            # This should trigger refresh and retry
            result = client.upload_file(test_file)

            # Verify token was refreshed
            assert client.auth_token == "new_token_refreshed"

    def test_proactive_token_refresh_on_ttl_expiry(self, bandwidth_counter):
        """Test proactive token refresh based on TTL."""
        config = Mock(spec=HostConfig)
        config.name = "TTLHost"
        config.auth_type = "session"
        config.session_token_ttl = 1  # 1 second TTL
        config.session_id_regex = r'sess_id:\s*([a-z0-9]+)'
        config.upload_page_url = "https://ttlhost.test/upload"

        client = FileHostClient(
            host_config=config,
            bandwidth_counter=bandwidth_counter
        )

        # Set session token with timestamp
        client.auth_token = "old_session_token"
        client._session_token_timestamp = time.time() - 2  # 2 seconds ago (expired)

        # Check staleness
        assert client._is_token_stale() is True


class TestFileHostClientEdgeCases:
    """Test suite for edge cases and error handling."""

    @pytest.fixture
    def bandwidth_counter(self):
        """Create bandwidth counter."""
        return AtomicCounter()

    def test_clean_filename_removes_internal_prefix(self, bandwidth_counter):
        """Test internal filename prefix removal."""
        config = Mock(spec=HostConfig)
        config.requires_auth = False

        client = FileHostClient(
            host_config=config,
            bandwidth_counter=bandwidth_counter
        )

        # Test with internal prefix
        assert client._get_clean_filename("imxup_1555_Gallery.zip") == "Gallery.zip"
        assert client._get_clean_filename("imxup_999_My_Photos.zip") == "My_Photos.zip"

        # Test without prefix
        assert client._get_clean_filename("normal_file.zip") == "normal_file.zip"

    def test_extract_from_json_nested_paths(self, bandwidth_counter):
        """Test JSON extraction with nested paths."""
        config = Mock(spec=HostConfig)
        config.requires_auth = False

        client = FileHostClient(
            host_config=config,
            bandwidth_counter=bandwidth_counter
        )

        data = {
            "status": "success",
            "data": {
                "user": {
                    "profile": {
                        "name": "Test User"
                    }
                }
            }
        }

        result = client._extract_from_json(data, ["data", "user", "profile", "name"])
        assert result == "Test User"

    def test_extract_from_json_with_array_indices(self, bandwidth_counter):
        """Test JSON extraction with array indices."""
        config = Mock(spec=HostConfig)
        config.requires_auth = False

        client = FileHostClient(
            host_config=config,
            bandwidth_counter=bandwidth_counter
        )

        data = {
            "files": [
                {"id": "file1", "url": "https://test.com/1"},
                {"id": "file2", "url": "https://test.com/2"}
            ]
        }

        result = client._extract_from_json(data, ["files", 1, "url"])
        assert result == "https://test.com/2"

    def test_calculate_file_hash(self, bandwidth_counter, tmp_path):
        """Test MD5 hash calculation."""
        config = Mock(spec=HostConfig)
        config.requires_auth = False

        client = FileHostClient(
            host_config=config,
            bandwidth_counter=bandwidth_counter
        )

        # Create test file
        test_file = tmp_path / "hash_test.dat"
        test_data = b"test data for hashing"
        test_file.write_bytes(test_data)

        # Calculate expected hash
        expected_hash = hashlib.md5(test_data).hexdigest()

        # Test hash calculation
        calculated_hash = client._calculate_file_hash(test_file)
        assert calculated_hash == expected_hash
