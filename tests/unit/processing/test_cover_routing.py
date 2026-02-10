# tests/unit/processing/test_cover_routing.py
"""Tests for cover upload routing based on gallery host."""
import pytest
from unittest.mock import patch, MagicMock, Mock

from src.storage.queue_manager import GalleryQueueItem


class TestCoverRouting:
    """Cover upload routes correctly based on gallery vs cover host."""

    @patch('src.processing.upload_workers.RenameWorker')
    def test_imx_gallery_imx_cover_uses_gallery_id(self, mock_rw_class):
        """IMX gallery + IMX cover: cover goes into that gallery."""
        from src.processing.upload_workers import UploadWorker

        worker = UploadWorker(Mock())
        worker.rename_worker = MagicMock()
        worker.rename_worker.login_successful = True
        worker.rename_worker.upload_cover.return_value = {"status": "success", "bbcode": "x"}

        item = GalleryQueueItem(
            path="/tmp/test",
            image_host_id="imx",
            cover_source_path="/tmp/test/cover.jpg",
            cover_host_id="imx",
        )

        with patch('src.processing.upload_workers.get_image_host_setting', return_value=2):
            worker._upload_cover(item, gallery_id="gal123")

        call_kwargs = worker.rename_worker.upload_cover.call_args[1]
        assert call_kwargs.get('gallery_id') == "gal123"

    @patch('src.processing.upload_workers.RenameWorker')
    def test_non_imx_gallery_imx_cover_uses_cover_gallery_setting(self, mock_rw_class):
        """Non-IMX gallery + IMX cover: uses cover_gallery setting."""
        from src.processing.upload_workers import UploadWorker

        worker = UploadWorker(Mock())
        worker.rename_worker = MagicMock()
        worker.rename_worker.login_successful = True
        worker.rename_worker.upload_cover.return_value = {"status": "success", "bbcode": "x"}

        item = GalleryQueueItem(
            path="/tmp/test",
            image_host_id="turbo",
            cover_source_path="/tmp/test/cover.jpg",
            cover_host_id="imx",
        )

        def mock_setting(host_id, key, value_type=None):
            if key == 'cover_gallery':
                return "my_cover_gallery"
            if key == 'cover_thumbnail_format':
                return 2
            return ""

        with patch('src.processing.upload_workers.get_image_host_setting', side_effect=mock_setting):
            worker._upload_cover(item, gallery_id="turbo_gal_id")

        call_kwargs = worker.rename_worker.upload_cover.call_args[1]
        # Should NOT pass the turbo gallery_id to IMX cover
        assert call_kwargs.get('gallery_id') == "my_cover_gallery"

    @patch('src.processing.upload_workers.RenameWorker')
    def test_non_imx_gallery_imx_cover_empty_cover_gallery(self, mock_rw_class):
        """Non-IMX gallery + IMX cover + no cover_gallery setting: empty gallery_id."""
        from src.processing.upload_workers import UploadWorker

        worker = UploadWorker(Mock())
        worker.rename_worker = MagicMock()
        worker.rename_worker.login_successful = True
        worker.rename_worker.upload_cover.return_value = {"status": "success", "bbcode": "x"}

        item = GalleryQueueItem(
            path="/tmp/test",
            image_host_id="turbo",
            cover_source_path="/tmp/test/cover.jpg",
            cover_host_id="imx",
        )

        def mock_setting(host_id, key, value_type=None):
            if key == 'cover_gallery':
                return ""
            if key == 'cover_thumbnail_format':
                return 2
            return ""

        with patch('src.processing.upload_workers.get_image_host_setting', side_effect=mock_setting):
            worker._upload_cover(item, gallery_id="turbo_gal_id")

        call_kwargs = worker.rename_worker.upload_cover.call_args[1]
        assert call_kwargs.get('gallery_id') == ""

    @patch('src.processing.upload_workers.RenameWorker')
    def test_same_host_uses_gallery_id(self, mock_rw_class):
        """Same host for gallery and cover: cover goes into that gallery."""
        from src.processing.upload_workers import UploadWorker

        worker = UploadWorker(Mock())
        worker.rename_worker = MagicMock()
        worker.rename_worker.login_successful = True
        worker.rename_worker.upload_cover.return_value = {"status": "success", "bbcode": "x"}

        item = GalleryQueueItem(
            path="/tmp/test",
            image_host_id="turbo",
            cover_source_path="/tmp/test/cover.jpg",
            cover_host_id="turbo",
        )

        with patch('src.processing.upload_workers.get_image_host_setting', return_value=2):
            worker._upload_cover(item, gallery_id="turbo_gal")

        call_kwargs = worker.rename_worker.upload_cover.call_args[1]
        assert call_kwargs.get('gallery_id') == "turbo_gal"

    @patch('src.processing.upload_workers.RenameWorker')
    def test_cover_host_id_defaults_to_image_host_id(self, mock_rw_class):
        """When cover_host_id is None, falls back to image_host_id for routing."""
        from src.processing.upload_workers import UploadWorker

        worker = UploadWorker(Mock())
        worker.rename_worker = MagicMock()
        worker.rename_worker.login_successful = True
        worker.rename_worker.upload_cover.return_value = {"status": "success", "bbcode": "x"}

        item = GalleryQueueItem(
            path="/tmp/test",
            image_host_id="imx",
            cover_source_path="/tmp/test/cover.jpg",
            cover_host_id=None,  # Not set, should default to image_host_id
        )

        with patch('src.processing.upload_workers.get_image_host_setting', return_value=2):
            worker._upload_cover(item, gallery_id="gal456")

        # cover_host_id defaults to image_host_id ("imx"), same host -> uses gallery_id
        call_kwargs = worker.rename_worker.upload_cover.call_args[1]
        assert call_kwargs.get('gallery_id') == "gal456"
