"""
Test suite for M3 Upload Pipeline - Response Contract Validation.

Verifies that:
1. normalize_response() produces the standard shape consumed by engine/workers
2. IMX client has get_default_headers() and supports_gallery_rename()
3. Turbo client normalizes raw API responses into the standard contract
4. Turbo client returns normalized errors (not raw exception-only paths)
"""

import os
import pytest
import tempfile
from unittest.mock import Mock, patch, MagicMock

from src.network.image_host_client import ImageHostClient
from src.core.image_host_config import ImageHostConfig


# ---------------------------------------------------------------------------
# normalize_response() – the shared helper every host uses
# ---------------------------------------------------------------------------

class TestNormalizeResponseHelper:
    """normalize_response must produce the exact dict shape the engine expects."""

    def test_success_has_all_required_keys(self):
        result = ImageHostClient.normalize_response(
            status='success',
            image_url='https://example.com/img.jpg',
            thumb_url='https://example.com/t.jpg',
            gallery_id='g1',
            original_filename='test.jpg',
        )
        assert result['status'] == 'success'
        assert result['error'] is None
        assert result['data']['image_url'] == 'https://example.com/img.jpg'
        assert result['data']['thumb_url'] == 'https://example.com/t.jpg'
        assert result['data']['gallery_id'] == 'g1'
        assert result['data']['original_filename'] == 'test.jpg'

    def test_error_has_all_required_keys(self):
        result = ImageHostClient.normalize_response(
            status='error',
            error='Upload timeout',
        )
        assert result['status'] == 'error'
        assert result['error'] == 'Upload timeout'
        assert 'data' in result
        # data fields default to empty strings / None
        assert result['data']['image_url'] == ''
        assert result['data']['gallery_id'] is None

    def test_defaults_when_only_status_and_url(self):
        result = ImageHostClient.normalize_response(
            status='success',
            image_url='https://x.com/i.jpg',
        )
        assert result['data']['thumb_url'] == ''
        assert result['data']['gallery_id'] is None
        assert result['data']['original_filename'] == ''
        assert result['error'] is None

    def test_gallery_id_none_preserved(self):
        result = ImageHostClient.normalize_response(
            status='success', image_url='u', gallery_id=None,
        )
        assert result['data']['gallery_id'] is None

    def test_is_callable_as_static_method(self):
        """Engine calls it without an instance."""
        result = ImageHostClient.normalize_response(status='success', image_url='u')
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# IMX client – verify ABC methods exist and behave
# ---------------------------------------------------------------------------

class TestIMXResponseContract:
    """IMX uploader must expose the M3 ABC surface."""

    def test_get_default_headers_returns_dict(self):
        from src.network.client import GUIImxToUploader
        with patch.object(GUIImxToUploader, '__init__', return_value=None):
            uploader = GUIImxToUploader()
            uploader.headers = {'User-Agent': 'test', 'Accept': '*/*'}
            headers = uploader.get_default_headers()
            assert isinstance(headers, dict)

    def test_supports_gallery_rename_true(self):
        from src.network.client import GUIImxToUploader
        with patch.object(GUIImxToUploader, '__init__', return_value=None):
            uploader = GUIImxToUploader()
            assert uploader.supports_gallery_rename() is True


# ---------------------------------------------------------------------------
# Turbo client – verify upload_image normalizes responses
# ---------------------------------------------------------------------------

class TestTurboImageHostResponseContract:
    """Turbo upload_image must return the standard {status, data, error} shape."""

    @pytest.fixture
    def turbo_client(self):
        """Build a TurboImageHostClient with just enough state to call upload_image."""
        import threading
        from src.network.turbo_image_host_client import TurboImageHostClient
        with patch.object(TurboImageHostClient, '__init__', return_value=None):
            client = TurboImageHostClient()
            client.session = Mock()
            client.upload_connect_timeout = 30
            client.upload_read_timeout = 120
            client.upload_url = 'https://s8d8.turboimagehost.com/upload_html5.tu'
            client._upload_count = 0
            client._upload_count_lock = threading.Lock()
            return client

    def test_upload_normalizes_success(self, turbo_client, tmp_path):
        """A 200 + success JSON returns the standard contract."""
        img = tmp_path / "photo.jpg"
        img.write_bytes(b'\xff\xd8' + b'x' * 500)

        # Mock the HTTP POST to return valid JSON
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.text = '{"success": true, "url": "https://turbo.com/img/abc.jpg", "thumb_url": "https://turbo.com/t/abc.jpg", "album_id": "alb42"}'
        turbo_client.session.post.return_value = mock_resp

        result = turbo_client.upload_image(str(img), create_gallery=True, gallery_name="Test")

        # Standard contract shape
        assert result['status'] == 'success'
        assert 'data' in result
        assert result['data']['image_url'] == 'https://turbo.com/img/abc.jpg'
        assert result['data']['thumb_url'] == 'https://turbo.com/t/abc.jpg'
        assert result['data']['gallery_id'] == 'alb42'
        assert result['data']['original_filename'] == 'photo.jpg'
        assert result['error'] is None
        # Extra fields from Turbo
        assert 'upload_time' in result
        assert 'file_size' in result

    def test_upload_normalizes_error_response(self, turbo_client, tmp_path):
        """A 200 + failure JSON returns status='error' with error message."""
        img = tmp_path / "bad.jpg"
        img.write_bytes(b'\xff\xd8' + b'x' * 100)

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.text = '{"success": false}'
        turbo_client.session.post.return_value = mock_resp

        result = turbo_client.upload_image(str(img))

        assert result['status'] == 'error'
        assert result['error'] is not None
        assert 'no success indicator' in result['error'].lower()

    def test_upload_raises_on_http_error(self, turbo_client, tmp_path):
        """Non-200 status code raises, not a silent failure."""
        img = tmp_path / "fail.jpg"
        img.write_bytes(b'\xff\xd8' + b'x' * 100)

        mock_resp = Mock()
        mock_resp.status_code = 500
        mock_resp.text = 'Internal Server Error'
        turbo_client.session.post.return_value = mock_resp

        with pytest.raises(Exception, match="500"):
            turbo_client.upload_image(str(img))

    def test_get_default_headers_returns_session_headers(self, turbo_client):
        turbo_client.session.headers = {'User-Agent': 'Mozilla/5.0', 'X-Custom': 'val'}
        headers = turbo_client.get_default_headers()
        assert isinstance(headers, dict)
        assert headers['User-Agent'] == 'Mozilla/5.0'

    def test_supports_gallery_rename_false(self, turbo_client):
        """Turbo does NOT support gallery rename (ABC default)."""
        assert turbo_client.supports_gallery_rename() is False

    def test_file_not_found_raises(self, turbo_client):
        with pytest.raises(FileNotFoundError):
            turbo_client.upload_image('/nonexistent/path/img.jpg')

    def test_gallery_name_truncated_to_20(self, turbo_client, tmp_path):
        """Turbo truncates gallery names > 20 chars before sending."""
        img = tmp_path / "x.jpg"
        img.write_bytes(b'\xff\xd8' + b'x' * 100)

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.text = '{"success": true, "url": "https://turbo.com/i/1.jpg"}'
        turbo_client.session.post.return_value = mock_resp

        turbo_client.upload_image(
            str(img), create_gallery=True,
            gallery_name="A" * 30,
        )
        # Verify the form data sent to the server had truncated name
        call_kwargs = turbo_client.session.post.call_args
        form_data = call_kwargs.kwargs.get('data') or call_kwargs[1].get('data', {})
        assert len(form_data.get('galleryN', '')) <= 20


# ---------------------------------------------------------------------------
# Cross-host contract compliance
# ---------------------------------------------------------------------------

class TestResponseContractCompliance:
    """Verify contract invariants hold for any status."""

    @pytest.mark.parametrize("status", ['success', 'error'])
    def test_top_level_keys_present(self, status):
        result = ImageHostClient.normalize_response(
            status=status,
            error='err' if status == 'error' else None,
        )
        for key in ('status', 'data', 'error'):
            assert key in result

    def test_data_has_all_required_fields(self):
        result = ImageHostClient.normalize_response(status='success', image_url='u')
        for field in ('image_url', 'thumb_url', 'gallery_id', 'original_filename'):
            assert field in result['data']
