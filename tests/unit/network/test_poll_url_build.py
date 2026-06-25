"""
Test for poll URL builder with None upload_id guard.

Tests the _build_poll_url helper method to ensure it safely handles None
or empty upload_id values without raising TypeError.
"""

import pytest
from unittest.mock import Mock
from types import SimpleNamespace

from src.network.file_host_client import FileHostClient
from src.core.engine import AtomicCounter


class TestPollUrlBuilder:
    """Test suite for FileHostClient._build_poll_url helper."""

    @pytest.fixture
    def bandwidth_counter(self):
        """Create a bandwidth counter."""
        return AtomicCounter()

    @pytest.fixture
    def mock_host_config(self):
        """Create a minimal mock HostConfig for poll URL testing."""
        config = Mock()
        config.upload_poll_url = "https://host.com/poll?id={upload_id}&token={token}"
        return config

    def _create_client_minimal(self, mock_config, bandwidth_counter):
        """Create a FileHostClient instance with minimal setup for testing."""
        client = object.__new__(FileHostClient)
        client.config = mock_config
        client.bandwidth_counter = bandwidth_counter
        client.auth_token = None
        return client

    def test_build_poll_url_with_valid_upload_id(self, mock_host_config, bandwidth_counter):
        """Test _build_poll_url with a valid (non-None) upload_id."""
        client = self._create_client_minimal(mock_host_config, bandwidth_counter)
        client.auth_token = "TOK123"

        result = client._build_poll_url("abc-def-123")
        assert result == "https://host.com/poll?id=abc-def-123&token=TOK123"

    def test_build_poll_url_with_none_upload_id(self, mock_host_config, bandwidth_counter):
        """Test _build_poll_url with None upload_id does not raise TypeError."""
        client = self._create_client_minimal(mock_host_config, bandwidth_counter)
        client.auth_token = "TOK456"

        # Should NOT raise TypeError: replace() argument 2 must be str, not None
        result = client._build_poll_url(None)
        assert result == "https://host.com/poll?id=&token=TOK456"

    def test_build_poll_url_with_none_auth_token(self, mock_host_config, bandwidth_counter):
        """Test _build_poll_url with None auth_token replaces {token} with empty string."""
        client = self._create_client_minimal(mock_host_config, bandwidth_counter)
        client.auth_token = None

        result = client._build_poll_url("xyz789")
        assert result == "https://host.com/poll?id=xyz789&token="

    def test_build_poll_url_with_both_none(self, mock_host_config, bandwidth_counter):
        """Test _build_poll_url with both upload_id and auth_token as None."""
        client = self._create_client_minimal(mock_host_config, bandwidth_counter)
        client.auth_token = None

        result = client._build_poll_url(None)
        assert result == "https://host.com/poll?id=&token="

    def test_build_poll_url_with_empty_string_upload_id(self, mock_host_config, bandwidth_counter):
        """Test _build_poll_url with empty string upload_id."""
        client = self._create_client_minimal(mock_host_config, bandwidth_counter)
        client.auth_token = "TOK999"

        result = client._build_poll_url("")
        assert result == "https://host.com/poll?id=&token=TOK999"
