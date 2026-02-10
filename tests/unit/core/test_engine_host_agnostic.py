"""
Test suite for M3 Upload Pipeline - Host-Agnostic UploadEngine.

Verifies that UploadEngine works with ANY ImageHostClient, not just IMX:
1. A mock client can drive a full upload cycle
2. get_default_headers() are propagated to thread-local sessions
3. clear_api_cookies is guarded by hasattr (no crash on hosts without it)
4. supports_gallery_rename() gates rename behavior
5. Resume (already_uploaded) skips files correctly
6. Callbacks fire for any client type
"""

import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch
from typing import Dict, Any, Optional

import pytest

from src.core.engine import UploadEngine, AtomicCounter
from src.network.image_host_client import ImageHostClient
from src.core.image_host_config import ImageHostConfig


# ---------------------------------------------------------------------------
# Concrete mock client used by all tests
# ---------------------------------------------------------------------------

class MockImageHostClient(ImageHostClient):
    """Fully-functional mock that returns standard responses."""

    def __init__(self, name="MockHost", supports_rename=False,
                 has_clear_cookies=True):
        config = ImageHostConfig(name=name, host_id="mock")
        super().__init__(config)
        self._web_url = "https://mockhost.example.com"
        self._supports_rename = supports_rename
        self._headers = {"X-Mock": "true", "User-Agent": "MockAgent"}
        self._has_clear_cookies = has_clear_cookies
        self.upload_calls = []
        self.clear_cookies_called = False

    @property
    def web_url(self) -> str:
        return self._web_url

    def get_default_headers(self) -> dict:
        return dict(self._headers)

    def supports_gallery_rename(self) -> bool:
        return self._supports_rename

    def upload_image(self, image_path, create_gallery=False,
                     gallery_id=None, thumbnail_size=3, thumbnail_format=2,
                     thread_session=None, progress_callback=None,
                     content_type="all", gallery_name=None) -> dict:
        self.upload_calls.append(image_path)
        fname = os.path.basename(image_path)
        return self.normalize_response(
            status='success',
            image_url=f'{self._web_url}/img/{fname}',
            thumb_url=f'{self._web_url}/t/{fname}',
            gallery_id=gallery_id or 'mock_gal_1',
            original_filename=fname,
        )


class NoCookieClient(MockImageHostClient):
    """Client that genuinely has no clear_api_cookies method."""

    def __init__(self):
        super().__init__(name="NoCookie", has_clear_cookies=False)

    # Intentionally omit clear_api_cookies — engine must not crash


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def img_folder(tmp_path):
    """Create a temp dir with 3 small test images."""
    for i in range(3):
        (tmp_path / f"img{i}.jpg").write_bytes(b'\xff\xd8' + b'x' * 512)
    return str(tmp_path)


@pytest.fixture
def single_img_folder(tmp_path):
    """Folder with one image."""
    (tmp_path / "solo.jpg").write_bytes(b'\xff\xd8' + b'x' * 256)
    return str(tmp_path)


# ---------------------------------------------------------------------------
# Core engine tests
# ---------------------------------------------------------------------------

class TestEngineWithMockClient:
    """Engine works identically with any ImageHostClient subclass."""

    def test_full_upload_cycle(self, img_folder):
        """3 images → successful_count=3, gallery_id populated."""
        client = MockImageHostClient()
        engine = UploadEngine(client)
        result = engine.run(
            folder_path=img_folder, gallery_name="Test",
            thumbnail_size=3, thumbnail_format=2,
            max_retries=1, parallel_batch_size=2,
            template_name="default",
        )
        assert result['successful_count'] == 3
        assert result['failed_count'] == 0
        assert result['gallery_id'] == 'mock_gal_1'
        assert len(client.upload_calls) == 3

    def test_headers_propagated_to_thread_sessions(self, img_folder):
        """get_default_headers() values end up on per-thread sessions."""
        client = MockImageHostClient()
        client._headers = {'Authorization': 'Bearer tok', 'X-Test': '1'}

        captured_sessions = []
        real_upload = client.upload_image

        def spy_upload(image_path, thread_session=None, **kw):
            if thread_session is not None:
                captured_sessions.append(dict(thread_session.headers))
            return real_upload(image_path, thread_session=thread_session, **kw)

        client.upload_image = spy_upload
        engine = UploadEngine(client)
        engine.run(
            folder_path=img_folder, gallery_name="Test",
            thumbnail_size=3, thumbnail_format=2,
            max_retries=1, parallel_batch_size=1,
            template_name="default",
        )
        # Thread sessions should have our custom headers
        assert len(captured_sessions) >= 1
        for sess_headers in captured_sessions:
            assert 'Authorization' in sess_headers
            assert sess_headers['Authorization'] == 'Bearer tok'

    def test_no_crash_without_clear_api_cookies(self, img_folder):
        """Hosts without clear_api_cookies don't crash the engine."""
        client = NoCookieClient()
        assert not hasattr(client, 'clear_api_cookies')
        engine = UploadEngine(client)
        result = engine.run(
            folder_path=img_folder, gallery_name="Test",
            thumbnail_size=3, thumbnail_format=2,
            max_retries=1, parallel_batch_size=2,
            template_name="default",
        )
        assert result['successful_count'] == 3

    def test_clear_api_cookies_called_when_present(self, img_folder):
        """Hosts WITH clear_api_cookies have it called before first upload."""
        client = MockImageHostClient()
        client.clear_api_cookies = Mock()
        engine = UploadEngine(client)
        engine.run(
            folder_path=img_folder, gallery_name="Test",
            thumbnail_size=3, thumbnail_format=2,
            max_retries=1, parallel_batch_size=2,
            template_name="default",
        )
        client.clear_api_cookies.assert_called_once()


class TestEngineSupportGalleryRename:
    """supports_gallery_rename gates rename behavior."""

    def test_no_rename_queued_when_false(self, img_folder):
        client = MockImageHostClient(supports_rename=False)
        rename_worker = Mock()
        engine = UploadEngine(client, rename_worker=rename_worker)
        engine.run(
            folder_path=img_folder, gallery_name="Test",
            thumbnail_size=3, thumbnail_format=2,
            max_retries=1, parallel_batch_size=2,
            template_name="default",
        )
        rename_worker.queue_rename.assert_not_called()

    def test_rename_queued_when_true(self, img_folder):
        client = MockImageHostClient(supports_rename=True)
        rename_worker = Mock()
        engine = UploadEngine(client, rename_worker=rename_worker)
        engine.run(
            folder_path=img_folder, gallery_name="My Gallery",
            thumbnail_size=3, thumbnail_format=2,
            max_retries=1, parallel_batch_size=2,
            template_name="default",
        )
        rename_worker.queue_rename.assert_called_once()
        args = rename_worker.queue_rename.call_args[0]
        assert args[1] == "My Gallery"


class TestEngineResume:
    """Resume skips already-uploaded files and reports correct counts."""

    def test_resume_skips_uploaded(self, img_folder):
        client = MockImageHostClient()
        engine = UploadEngine(client)
        result = engine.run(
            folder_path=img_folder, gallery_name="Test",
            thumbnail_size=3, thumbnail_format=2,
            max_retries=1, parallel_batch_size=2,
            template_name="default",
            existing_gallery_id="existing_gal",
            already_uploaded={'img0.jpg'},
        )
        # Only img1.jpg and img2.jpg should be uploaded
        assert len(client.upload_calls) == 2
        # successful_count includes already-uploaded + newly uploaded
        assert result['successful_count'] == 3


class TestEngineCallbacks:
    """Progress and uploaded callbacks fire for any client."""

    def test_progress_callback_fires(self, img_folder):
        client = MockImageHostClient()
        progress_calls = []

        def on_progress(completed, total, percent, fname):
            progress_calls.append((completed, total))

        engine = UploadEngine(client)
        engine.run(
            folder_path=img_folder, gallery_name="Test",
            thumbnail_size=3, thumbnail_format=2,
            max_retries=1, parallel_batch_size=2,
            template_name="default",
            on_progress=on_progress,
        )
        assert len(progress_calls) >= 3  # at least once per image

    def test_image_uploaded_callback_fires(self, img_folder):
        client = MockImageHostClient()
        uploaded = []

        def on_uploaded(fname, data, size):
            uploaded.append(fname)

        engine = UploadEngine(client)
        engine.run(
            folder_path=img_folder, gallery_name="Test",
            thumbnail_size=3, thumbnail_format=2,
            max_retries=1, parallel_batch_size=2,
            template_name="default",
            on_image_uploaded=on_uploaded,
        )
        assert len(uploaded) == 3


class TestEngineResponseParsing:
    """Engine extracts gallery_id and handles errors from standard responses."""

    def test_gallery_id_from_first_upload(self, single_img_folder):
        client = MockImageHostClient()
        engine = UploadEngine(client)
        result = engine.run(
            folder_path=single_img_folder, gallery_name="Test",
            thumbnail_size=3, thumbnail_format=2,
            max_retries=1, parallel_batch_size=1,
            template_name="default",
        )
        assert result['gallery_id'] == 'mock_gal_1'

    def test_failed_first_upload_raises(self, single_img_folder):
        """If first image fails, engine raises (can't create gallery)."""
        client = MockImageHostClient()
        client.upload_image = lambda *a, **kw: ImageHostClient.normalize_response(
            status='error', error='server down',
        )
        engine = UploadEngine(client)
        with pytest.raises(Exception, match="Failed to create gallery"):
            engine.run(
                folder_path=single_img_folder, gallery_name="Test",
                thumbnail_size=3, thumbnail_format=2,
                max_retries=0, parallel_batch_size=1,
                template_name="default",
            )

    def test_gallery_url_uses_uploader_method(self, single_img_folder):
        """Engine uses uploader.get_gallery_url() for the URL, not hardcoded IMX."""
        client = MockImageHostClient()
        engine = UploadEngine(client)
        result = engine.run(
            folder_path=single_img_folder, gallery_name="Test",
            thumbnail_size=3, thumbnail_format=2,
            max_retries=1, parallel_batch_size=1,
            template_name="default",
        )
        # Should use the mock host's URL pattern, not imx.to
        assert 'imx.to' not in result.get('gallery_url', '')


class TestEngineMultipleClients:
    """Same engine code works across different client implementations."""

    def test_three_different_clients(self, img_folder):
        for name, rename in [("Host1", False), ("Host2", True), ("Host3", False)]:
            client = MockImageHostClient(name=name, supports_rename=rename)
            engine = UploadEngine(client)
            result = engine.run(
                folder_path=img_folder, gallery_name="Test",
                thumbnail_size=3, thumbnail_format=2,
                max_retries=1, parallel_batch_size=2,
                template_name="default",
            )
            assert result['successful_count'] == 3
            assert result['failed_count'] == 0
