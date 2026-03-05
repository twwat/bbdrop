"""
Test suite for M3 Upload Pipeline - Response Contract Validation.

Verifies that:
1. normalize_response() produces the standard shape consumed by engine/workers
2. IMX client has get_default_headers() and supports_gallery_rename()
3. Turbo client normalizes raw API responses into the standard contract
4. Turbo client returns normalized errors (not raw exception-only paths)
"""

import pycurl
import pytest
from unittest.mock import Mock, patch

from src.network.image_host_client import ImageHostClient


def _make_curl_mock(response_text, status_code=200):
    """Return a mock pycurl.Curl that writes response_text into WRITEDATA on perform()."""
    captured = {}

    def fake_setopt(opt, val):
        if opt == pycurl.WRITEDATA:
            captured['buf'] = val
        elif opt == pycurl.HTTPPOST:
            captured['form_fields'] = val

    def fake_perform():
        if 'buf' in captured:
            data = response_text.encode() if isinstance(response_text, str) else response_text
            captured['buf'].write(data)

    curl = Mock()
    curl.setopt.side_effect = fake_setopt
    curl.perform.side_effect = fake_perform
    curl.getinfo.side_effect = lambda opt: status_code if opt == pycurl.RESPONSE_CODE else None
    curl._captured = captured
    return curl


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
    """Turbo upload_image raises on failure or returns {status, data, error} shape on success."""

    @pytest.fixture
    def turbo_client(self):
        """Build a TurboImageHostClient with just enough state to call upload_image."""
        import threading
        from src.network.turbo_image_host_client import TurboImageHostClient
        with patch.object(TurboImageHostClient, '__init__', return_value=None):
            client = TurboImageHostClient()
            client.upload_connect_timeout = 30
            client.upload_read_timeout = 120
            client.upload_url = 'https://s8d8.turboimagehost.com/upload_html5.tu'
            client.base_url = 'https://www.turboimagehost.com'
            client._upload_count = 0
            client._upload_count_lock = threading.Lock()
            client._batch_upload_id = None
            client.cookie_jar = {'session': 'fake'}  # truthy → _ensure_session returns early
            client._thread_local = threading.local()
            client._session_lock = threading.Lock()
            client.proxy = None
            return client

    def test_upload_normalizes_success(self, turbo_client, tmp_path):
        """A 200 + success JSON returns the standard contract."""
        img = tmp_path / "photo.jpg"
        img.write_bytes(b'\xff\xd8' + b'x' * 500)

        curl = _make_curl_mock('{"success": true, "newUrl": "https://turbo.com/r?id=abc"}')
        with patch('src.network.turbo_image_host_client.get_image_host_setting', return_value=None), \
             patch.object(turbo_client, '_get_thread_curl', return_value=curl):
            result = turbo_client.upload_image(str(img), create_gallery=True, gallery_name="Test")

        assert result['status'] == 'success'
        assert 'data' in result
        assert result['data']['original_filename'] == 'photo.jpg'
        assert result['data']['gallery_id'] is not None  # _batch_upload_id set on create_gallery
        assert result['error'] is None
        assert 'upload_time' in result
        assert 'file_size' in result

    def test_upload_raises_on_failure_json(self, turbo_client, tmp_path):
        """A 200 + {"success": false} JSON raises an exception."""
        img = tmp_path / "bad.jpg"
        img.write_bytes(b'\xff\xd8' + b'x' * 100)

        curl = _make_curl_mock('{"success": false}')
        with patch('src.network.turbo_image_host_client.get_image_host_setting', return_value=None), \
             patch.object(turbo_client, '_get_thread_curl', return_value=curl):
            with pytest.raises(Exception, match="Upload rejected"):
                turbo_client.upload_image(str(img))

    def test_upload_raises_on_http_error(self, turbo_client, tmp_path):
        """Non-200 status code raises, not a silent failure."""
        img = tmp_path / "fail.jpg"
        img.write_bytes(b'\xff\xd8' + b'x' * 100)

        curl = _make_curl_mock('Internal Server Error', status_code=500)
        with patch('src.network.turbo_image_host_client.get_image_host_setting', return_value=None), \
             patch.object(turbo_client, '_get_thread_curl', return_value=curl):
            with pytest.raises(Exception, match="500"):
                turbo_client.upload_image(str(img))

    def test_get_default_headers_returns_dict(self, turbo_client):
        """get_default_headers() returns a dict with User-Agent and Referer."""
        headers = turbo_client.get_default_headers()
        assert isinstance(headers, dict)
        assert 'User-Agent' in headers
        assert 'Referer' in headers

    def test_supports_gallery_rename_false(self, turbo_client):
        """Turbo does NOT support gallery rename (ABC default)."""
        assert turbo_client.supports_gallery_rename() is False

    def test_file_not_found_raises(self, turbo_client):
        with patch('src.network.turbo_image_host_client.get_image_host_setting', return_value=None):
            with pytest.raises(FileNotFoundError):
                turbo_client.upload_image('/nonexistent/path/img.jpg')

    def test_gallery_name_in_form_fields(self, turbo_client, tmp_path):
        """gallery_name is passed in HTTPPOST form fields when create_gallery=True."""
        img = tmp_path / "x.jpg"
        img.write_bytes(b'\xff\xd8' + b'x' * 100)

        curl = _make_curl_mock('{"success": true, "newUrl": "https://turbo.com/r"}')
        with patch('src.network.turbo_image_host_client.get_image_host_setting', return_value=None), \
             patch.object(turbo_client, '_get_thread_curl', return_value=curl):
            turbo_client.upload_image(
                str(img), create_gallery=True,
                gallery_name="My Gallery",
            )

        form_fields = curl._captured.get('form_fields', [])
        gallery_n = next((v for k, v in form_fields if k == 'galleryN'), None)
        assert gallery_n == "My Gallery"


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
