"""
Tests for TurboImageHostClient.upload_image() album field support.

Verifies that when gallery_id is provided and create_gallery is False,
the upload POST includes an 'album' field so images go into the existing gallery.
"""

import pytest
import pycurl
from unittest.mock import patch, MagicMock

from src.network.turbo_image_host_client import TurboImageHostClient


@pytest.fixture
def turbo_client():
    """Build a TurboImageHostClient with __init__ bypassed."""
    with patch.object(TurboImageHostClient, '__init__', return_value=None):
        client = TurboImageHostClient()
        client.base_url = "https://www.turboimagehost.com"
        client.upload_url = "https://s8d8.turboimagehost.com/upload_html5.tu"
        client.cookie_jar = {"PHPSESSID": "abc123"}
        client.upload_connect_timeout = None
        client.upload_read_timeout = None
        client._batch_upload_id = None
        client._upload_count = 0
        client._upload_count_lock = MagicMock()
        client._thread_local = MagicMock()
        client._session_lock = MagicMock()
        return client


def _make_mock_curl(response_json='{"success": true, "newUrl": "https://example.com/result"}',
                    response_code=200):
    """Create a mock curl handle that captures setopt calls and simulates a response."""
    mock_curl = MagicMock()
    setopt_calls = {}

    def track_setopt(option, value):
        setopt_calls[option] = value

    mock_curl.setopt.side_effect = track_setopt
    mock_curl.getinfo.return_value = response_code

    def perform_side_effect():
        buf = setopt_calls.get(pycurl.WRITEDATA)
        if buf is not None:
            buf.write(response_json.encode('utf-8'))

    mock_curl.perform.side_effect = perform_side_effect
    mock_curl._setopt_calls = setopt_calls

    return mock_curl


def _get_form_fields(mock_curl):
    """Extract the HTTPPOST form_fields list from a mock curl's setopt calls."""
    return mock_curl._setopt_calls.get(pycurl.HTTPPOST, [])


@pytest.fixture
def fake_image(tmp_path):
    """Create a temporary image file for upload tests."""
    img = tmp_path / "test_image.jpg"
    img.write_bytes(b'\xff\xd8\xff\xe0' + b'\x00' * 100)  # minimal JPEG header
    return str(img)


class TestUploadAlbumField:
    """Test that the album field is correctly included/excluded in upload form data."""

    def test_album_field_included_when_gallery_id_set(self, turbo_client, fake_image):
        """When gallery_id='384022' and create_gallery=False, form fields should include ('album', '384022')."""
        mock_curl = _make_mock_curl()
        turbo_client._get_thread_curl = MagicMock(return_value=mock_curl)
        turbo_client._ensure_session = MagicMock()
        turbo_client._set_cookies = MagicMock()

        with patch('src.network.turbo_image_host_client.get_image_host_setting', return_value='all'):
            turbo_client.upload_image(
                image_path=fake_image,
                create_gallery=False,
                gallery_id="384022",
            )

        form_fields = _get_form_fields(mock_curl)
        assert ('album', '384022') in form_fields

    def test_album_field_not_included_without_gallery_id(self, turbo_client, fake_image):
        """When gallery_id is None, no album field should be present."""
        mock_curl = _make_mock_curl()
        turbo_client._get_thread_curl = MagicMock(return_value=mock_curl)
        turbo_client._ensure_session = MagicMock()
        turbo_client._set_cookies = MagicMock()

        with patch('src.network.turbo_image_host_client.get_image_host_setting', return_value='all'):
            turbo_client.upload_image(
                image_path=fake_image,
                create_gallery=False,
                gallery_id=None,
            )

        form_fields = _get_form_fields(mock_curl)
        album_fields = [f for f in form_fields if isinstance(f, tuple) and len(f) == 2 and f[0] == 'album']
        assert album_fields == [], f"Expected no album field, got: {album_fields}"

    def test_album_field_not_included_when_create_gallery(self, turbo_client, fake_image):
        """When create_gallery=True (even with gallery_id), no album field -- new gallery creation takes precedence."""
        mock_curl = _make_mock_curl()
        turbo_client._get_thread_curl = MagicMock(return_value=mock_curl)
        turbo_client._ensure_session = MagicMock()
        turbo_client._set_cookies = MagicMock()

        with patch('src.network.turbo_image_host_client.get_image_host_setting', return_value='all'):
            turbo_client.upload_image(
                image_path=fake_image,
                create_gallery=True,
                gallery_id="384022",
                gallery_name="Test Gallery",
            )

        form_fields = _get_form_fields(mock_curl)
        album_fields = [f for f in form_fields if isinstance(f, tuple) and len(f) == 2 and f[0] == 'album']
        assert album_fields == [], f"Expected no album field when create_gallery=True, got: {album_fields}"
