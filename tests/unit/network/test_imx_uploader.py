"""Unit tests for ImxToUploader.upload_image against the current IMX.to API.

The client is built without __init__ and fed a fake pycurl handle, so nothing
touches the network.
"""
import json
import threading
from unittest.mock import patch

import pycurl
import pytest

from src.core.image_host_config import ImageHostConfigManager
from src.network.imx_uploader import ImxToUploader

pytestmark = pytest.mark.unit


class FakeCurl:
    """Records setopt calls; perform() writes the canned body into WRITEDATA."""

    def __init__(self, body: bytes, code: int = 200):
        self.opts = {}
        self.body = body
        self.code = code

    def reset(self):
        pass

    def setopt(self, opt, val):
        self.opts[opt] = val

    def perform(self):
        self.opts[pycurl.WRITEDATA].write(self.body)

    def getinfo(self, _):
        return self.code


@pytest.fixture
def client():
    with patch.object(ImxToUploader, '__init__', return_value=None):
        c = ImxToUploader()
    c.headers = {"X-API-Key": "k"}
    c.upload_url = "https://api.imx.to/v1/upload.php"
    c.proxy = None
    c.upload_connect_timeout = 30
    c.upload_read_timeout = 120
    c._upload_count = 0
    c._upload_count_lock = threading.Lock()
    c._curl_local = threading.local()
    return c


@pytest.fixture
def image(tmp_path):
    p = tmp_path / "photo.jpg"
    p.write_bytes(b"\xff\xd8\xff\xe0fakejpeg")
    return str(p)


NEW_SUCCESS = {
    "status": "success",
    "message": "Image uploaded successfully",
    "data": {
        "image_url": "https://imx.to/i/abc123",
        "image_id": "abc123",
        "thumbnail_url": "https://imx.to/t/2026/11/01/abc123.jpg",
        "bbcode": "[URL=https://imx.to/i/abc123][IMG]https://imx.to/t/2026/11/01/abc123.jpg[/IMG][/URL]",
        "html": "<a href=\"https://imx.to/i/abc123\"></a>",
        "gallery_id": "x1y2",
        "gallery_name": "Holiday 2025",
    },
}


def body_of(obj) -> bytes:
    return json.dumps(obj).encode()


def run_upload(client, image, body=None, code=200, **kwargs):
    """Run upload_image with a FakeCurl; returns (result, fake)."""
    fake = FakeCurl(body if body is not None else body_of(NEW_SUCCESS), code)
    with patch.object(client, '_get_thread_curl', return_value=fake):
        result = client.upload_image(image, **kwargs)
    return result, fake


def form_fields(fake: FakeCurl) -> dict:
    """{field: value} for the plain (non-file) fields of the HTTPPOST form."""
    return {k: v for k, v in fake.opts[pycurl.HTTPPOST] if isinstance(v, str)}


def test_create_with_name_sends_create_gallery_1_and_gallery_name(client, image):
    _, fake = run_upload(client, image, create_gallery=True, gallery_name="Holiday 2025")
    fields = form_fields(fake)
    assert fields['create_gallery'] == '1'
    assert fields['gallery_name'] == 'Holiday 2025'


def test_gallery_name_not_sent_without_create_gallery(client, image):
    _, fake = run_upload(client, image, gallery_id='x1y2', gallery_name="Holiday 2025")
    fields = form_fields(fake)
    assert 'gallery_name' not in fields
    assert 'create_gallery' not in fields
    assert fields['gallery_id'] == 'x1y2'


def test_create_without_name_sends_no_gallery_name(client, image):
    _, fake = run_upload(client, image, create_gallery=True)
    fields = form_fields(fake)
    assert fields['create_gallery'] == '1'
    assert 'gallery_name' not in fields


def test_thumbnail_size_5_is_sent(client, image):
    _, fake = run_upload(client, image, thumbnail_size=5)
    assert form_fields(fake)['thumbnail_size'] == '5'


def test_new_response_shape_maps_thumbnail_url_image_id_gallery_name(client, image):
    r, _ = run_upload(client, image, create_gallery=True, gallery_name="Holiday 2025")
    assert r['status'] == 'success'
    assert r['error'] is None
    assert r['data']['image_url'] == 'https://imx.to/i/abc123'
    assert r['data']['thumb_url'] == 'https://imx.to/t/2026/11/01/abc123.jpg'
    assert r['data']['image_id'] == 'abc123'
    assert r['data']['gallery_id'] == 'x1y2'
    assert r['data']['gallery_name'] == 'Holiday 2025'
    assert r['data']['bbcode'].startswith('[URL=')


def test_gallery_name_absent_when_api_returns_none(client, image):
    body = {"status": "success", "data": {
        "image_url": "https://imx.to/i/abc123", "image_id": "abc123",
        "thumbnail_url": "https://imx.to/t/abc123.jpg"}}
    r, _ = run_upload(client, image, body=body_of(body))
    assert 'gallery_name' not in r['data']
    assert r['data']['image_id'] == 'abc123'


def test_old_response_shape_thumb_url_still_read(client, image):
    body = {"status": "success", "data": {
        "image_url": "https://imx.to/i/abc123",
        "thumb_url": "https://imx.to/u/t/abc123.jpg",
        "gallery_id": "x1y2"}}
    r, _ = run_upload(client, image, body=body_of(body))
    assert r['data']['thumb_url'] == 'https://imx.to/u/t/abc123.jpg'


def test_original_filename_falls_back_to_basename(client, image):
    r, _ = run_upload(client, image)
    assert r['data']['original_filename'] == 'photo.jpg'


def test_error_status_puts_message_in_error(client, image):
    body = {"status": "error", "message": "Invalid or inactive API key"}
    r, _ = run_upload(client, image, body=body_of(body))
    assert r['status'] == 'error'
    assert r['error'] == 'Invalid or inactive API key'


def test_warning_is_logged(client, image):
    body = dict(NEW_SUCCESS, warning="gallery_name ignored without create_gallery")
    with patch("src.network.imx_uploader.log") as mock_log:
        run_upload(client, image, body=body_of(body))
    warnings = [c for c in mock_log.call_args_list if c.kwargs.get("level") == "warning"]
    assert len(warnings) == 1
    assert 'gallery_name ignored' in warnings[0].args[0]
    assert 'photo.jpg' in warnings[0].args[0]


def test_non_200_raises_with_json_message(client, image):
    body = b'{"status":"error","message":"User account is locked"}'
    with pytest.raises(Exception, match='User account is locked') as exc:
        run_upload(client, image, body=body, code=403)
    assert '403' in str(exc.value)
    assert '"status"' not in str(exc.value)


def test_non_200_non_json_falls_back_to_raw_body(client, image):
    with pytest.raises(Exception, match='502.*Bad Gateway'):
        run_upload(client, image, body=b'<html>Bad Gateway</html>', code=502)


class TestSanitizeGalleryName:
    def test_keeps_square_brackets(self, client):
        assert client.sanitize_gallery_name('Set [HD] (2026)') == 'Set [HD] (2026)'

    def test_drops_disallowed_and_collapses_spaces(self, client):
        assert client.sanitize_gallery_name('A  &  B:  C') == 'A B C'

    def test_accents_are_dropped(self, client):
        assert client.sanitize_gallery_name('Café (2026)') == 'Caf (2026)'

    def test_only_disallowed_becomes_untitled(self, client):
        assert client.sanitize_gallery_name('♥♥♥') == 'untitled'

    def test_empty_becomes_untitled(self, client):
        assert client.sanitize_gallery_name('') == 'untitled'

    def test_capped_at_100(self, client):
        assert len(client.sanitize_gallery_name('x' * 150)) == 100

    def test_cap_does_not_leave_trailing_space(self, client):
        result = client.sanitize_gallery_name('x' * 99 + ' ' + 'y' * 20)
        assert result == 'x' * 99

    def test_tab_becomes_a_space(self, client):
        assert client.sanitize_gallery_name('A\tB') == 'A B'

    def test_non_breaking_space_becomes_a_space(self, client):
        assert client.sanitize_gallery_name('A\u00a0B') == 'A B'


def test_imx_config_has_size_5_and_name_cap():
    # A fresh manager: the shared one may have been built by another test under patches
    manager = ImageHostConfigManager()
    manager.load_all()
    cfg = manager.get_host('imx')
    assert [s['id'] for s in cfg.thumbnail_sizes] == [1, 6, 2, 3, 4, 5]
    assert cfg.thumbnail_sizes[-1]['label'] == '600x600 (Cover)'
    assert cfg.gallery_name_max_length == 100
