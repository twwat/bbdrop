"""
Tests for TurboImageHostClient.create_gallery() and _parse_create_gallery_response().

Verifies gallery creation request handling and HTML response parsing
for extracting the new gallery ID from the #album dropdown.
"""

import pytest
from unittest.mock import patch, MagicMock, call

from src.network.turbo_image_host_client import TurboImageHostClient


@pytest.fixture
def turbo_client():
    """Build a TurboImageHostClient with __init__ bypassed."""
    with patch.object(TurboImageHostClient, '__init__', return_value=None):
        client = TurboImageHostClient()
        client.base_url = "https://www.turboimagehost.com"
        client.cookie_jar = {"PHPSESSID": "abc123", "skey": "xyz", "user_id": "42"}
        client.upload_connect_timeout = None
        client._thread_local = MagicMock()
        return client


# --- _parse_create_gallery_response tests ---


class TestParseCreateGalleryResponse:
    """Test the HTML parsing logic in isolation."""

    def test_parses_selected_option(self, turbo_client):
        """Should extract gallery ID from the selected option."""
        html = """
        <html><body>
        <select id="album">
            <option value="0">No gallery</option>
            <option value="384030">Old Gallery</option>
            <option value="384037" selected>My New Gallery</option>
        </select>
        </body></html>
        """
        result = turbo_client._parse_create_gallery_response(html)
        assert result == "384037"

    def test_parses_selected_with_extra_attributes(self, turbo_client):
        """Should handle selected attribute with other attributes present."""
        html = '<option value="99001" selected="selected" class="active">Test</option>'
        result = turbo_client._parse_create_gallery_response(html)
        assert result == "99001"

    def test_fallback_to_last_option(self, turbo_client):
        """When no selected attribute, should return the last numeric option."""
        html = """
        <select id="album">
            <option value="0">No gallery</option>
            <option value="100">First</option>
            <option value="200">Second</option>
            <option value="300">Newest</option>
        </select>
        """
        result = turbo_client._parse_create_gallery_response(html)
        assert result == "300"

    def test_no_options_raises(self, turbo_client):
        """Should raise RuntimeError when no numeric options found."""
        html = "<html><body><p>No album dropdown here</p></body></html>"
        with pytest.raises(RuntimeError, match="Could not find gallery ID"):
            turbo_client._parse_create_gallery_response(html)

    def test_only_zero_value_option(self, turbo_client):
        """Option value='0' is not matched by \\d+ starting from 0... actually it is.
        Regex \\d+ matches '0'. This is fine -- the server wouldn't select value='0'."""
        # Actually \d+ does match "0", so this should return "0"
        html = '<option value="0">No gallery</option>'
        # \d+ matches one or more digits, "0" qualifies
        result = turbo_client._parse_create_gallery_response(html)
        assert result == "0"

    def test_selected_option_case_insensitive(self, turbo_client):
        """Regex should be case-insensitive for HTML attribute matching."""
        html = '<OPTION VALUE="55555" SELECTED>Gallery</OPTION>'
        result = turbo_client._parse_create_gallery_response(html)
        assert result == "55555"

    def test_multiple_selected_returns_first(self, turbo_client):
        """If multiple options have selected (malformed HTML), return the first."""
        html = """
        <option value="111" selected>First</option>
        <option value="222" selected>Second</option>
        """
        result = turbo_client._parse_create_gallery_response(html)
        assert result == "111"


# --- create_gallery tests ---


class TestCreateGallery:
    """Test the full create_gallery method with mocked pycurl."""

    def _make_mock_curl(self, response_html, response_code=200):
        """Create a mock curl handle that writes response HTML into the buffer."""
        import pycurl

        mock_curl = MagicMock()
        mock_curl.getinfo.return_value = response_code

        # Track setopt calls to capture the WRITEDATA buffer
        setopt_calls = {}

        def track_setopt(option, value):
            setopt_calls[option] = value

        mock_curl.setopt.side_effect = track_setopt

        def perform_side_effect():
            buf = setopt_calls.get(pycurl.WRITEDATA)
            if buf is not None:
                buf.write(response_html.encode('utf-8'))

        mock_curl.perform.side_effect = perform_side_effect

        return mock_curl

    def test_create_gallery_success(self, turbo_client):
        """Full integration: creates gallery and returns parsed ID."""
        html = '<option value="384037" selected>Test Gallery</option>'
        mock_curl = self._make_mock_curl(html)
        turbo_client._get_thread_curl = MagicMock(return_value=mock_curl)
        turbo_client._set_cookies = MagicMock()

        result = turbo_client.create_gallery("Test Gallery")

        assert result == "384037"
        mock_curl.perform.assert_called_once()
        mock_curl.close.assert_called_once()

    def test_create_gallery_empty_name_raises(self, turbo_client):
        """Empty string should raise ValueError before any network call."""
        with pytest.raises(ValueError, match="Gallery name cannot be empty"):
            turbo_client.create_gallery("")

    def test_create_gallery_whitespace_name_raises(self, turbo_client):
        """Whitespace-only name should raise ValueError."""
        with pytest.raises(ValueError, match="Gallery name cannot be empty"):
            turbo_client.create_gallery("   ")

    def test_create_gallery_none_name_raises(self, turbo_client):
        """None should raise ValueError."""
        with pytest.raises(ValueError, match="Gallery name cannot be empty"):
            turbo_client.create_gallery(None)

    def test_create_gallery_sanitizes_name(self, turbo_client):
        """Should call sanitize_gallery_name on the input."""
        html = '<option value="12345" selected>sanitized</option>'
        mock_curl = self._make_mock_curl(html)
        turbo_client._get_thread_curl = MagicMock(return_value=mock_curl)
        turbo_client._set_cookies = MagicMock()

        with patch.object(turbo_client, 'sanitize_gallery_name', return_value='cleaned') as mock_sanitize:
            turbo_client.create_gallery("dirty!@#name")
            mock_sanitize.assert_called_once_with("dirty!@#name")

    def test_create_gallery_posts_sanitized_name(self, turbo_client):
        """Should use the sanitized name in the POST body."""
        import pycurl

        html = '<option value="12345" selected>My Gallery</option>'
        mock_curl = self._make_mock_curl(html)
        turbo_client._get_thread_curl = MagicMock(return_value=mock_curl)
        turbo_client._set_cookies = MagicMock()

        turbo_client.create_gallery("My Gallery!!")

        # Find the POSTFIELDS setopt call
        postfields_calls = [
            c for c in mock_curl.setopt.call_args_list
            if c[0][0] == pycurl.POSTFIELDS
        ]
        assert len(postfields_calls) == 1
        post_data = postfields_calls[0][0][1]
        assert "addalbum=My Gallery" in post_data
        assert "newalbum=Create+a+new+gallery" in post_data

    def test_create_gallery_http_error_raises(self, turbo_client):
        """Non-200 response should raise RuntimeError."""
        mock_curl = self._make_mock_curl("", response_code=500)
        turbo_client._get_thread_curl = MagicMock(return_value=mock_curl)
        turbo_client._set_cookies = MagicMock()

        with pytest.raises(RuntimeError, match="Gallery creation failed with status 500"):
            turbo_client.create_gallery("Test")

    def test_create_gallery_no_options_raises(self, turbo_client):
        """Response with no gallery options should raise RuntimeError."""
        html = "<html><body><p>Something went wrong</p></body></html>"
        mock_curl = self._make_mock_curl(html)
        turbo_client._get_thread_curl = MagicMock(return_value=mock_curl)
        turbo_client._set_cookies = MagicMock()

        with pytest.raises(RuntimeError, match="Could not find gallery ID"):
            turbo_client.create_gallery("Test")

    def test_create_gallery_calls_close_on_success(self, turbo_client):
        """curl.close() must be called even on success."""
        html = '<option value="999" selected>G</option>'
        mock_curl = self._make_mock_curl(html)
        turbo_client._get_thread_curl = MagicMock(return_value=mock_curl)
        turbo_client._set_cookies = MagicMock()

        turbo_client.create_gallery("G")
        mock_curl.close.assert_called_once()

    def test_create_gallery_calls_close_on_error(self, turbo_client):
        """curl.close() must be called even when an error is raised."""
        mock_curl = self._make_mock_curl("", response_code=403)
        turbo_client._get_thread_curl = MagicMock(return_value=mock_curl)
        turbo_client._set_cookies = MagicMock()

        with pytest.raises(RuntimeError):
            turbo_client.create_gallery("Test")
        mock_curl.close.assert_called_once()

    def test_create_gallery_sets_cookies(self, turbo_client):
        """Should call _set_cookies to send auth cookies."""
        html = '<option value="100" selected>G</option>'
        mock_curl = self._make_mock_curl(html)
        turbo_client._get_thread_curl = MagicMock(return_value=mock_curl)
        turbo_client._set_cookies = MagicMock()

        turbo_client.create_gallery("G")
        turbo_client._set_cookies.assert_called_once_with(mock_curl)

    def test_create_gallery_fallback_parsing(self, turbo_client):
        """When no selected option, should fall back to last numeric option."""
        html = """
        <select id="album">
            <option value="100">First</option>
            <option value="200">Second</option>
            <option value="300">Third</option>
        </select>
        """
        mock_curl = self._make_mock_curl(html)
        turbo_client._get_thread_curl = MagicMock(return_value=mock_curl)
        turbo_client._set_cookies = MagicMock()

        result = turbo_client.create_gallery("Test")
        assert result == "300"
