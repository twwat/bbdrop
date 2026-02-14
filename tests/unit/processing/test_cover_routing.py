# tests/unit/processing/test_cover_routing.py
"""Tests for cover upload routing based on gallery host."""
import pytest
from unittest.mock import patch, MagicMock, Mock

from src.storage.queue_manager import GalleryQueueItem


def _mock_qsettings(overrides=None):
    """Create a QSettings mock that returns sensible defaults with overrides."""
    values = {
        'cover/host_id': '',
        'cover/thumbnail_format': 2,
        'cover/gallery': '',
    }
    if overrides:
        values.update(overrides)

    mock_settings = MagicMock()
    mock_settings.value.side_effect = lambda key, default=None, **kw: values.get(key, default)
    return mock_settings


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

        with patch('src.processing.upload_workers.QSettings', return_value=_mock_qsettings()):
            worker._upload_cover(item, gallery_id="gal123")

        call_kwargs = worker.rename_worker.upload_cover.call_args[1]
        assert call_kwargs.get('gallery_id') == "gal123"

    @patch('src.processing.upload_workers.RenameWorker')
    def test_non_imx_gallery_imx_cover_uses_cover_gallery_setting(self, mock_rw_class):
        """Non-IMX gallery + IMX cover: uses cover/gallery QSetting."""
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

        mock_settings = _mock_qsettings({'cover/gallery': 'my_cover_gallery'})
        with patch('src.processing.upload_workers.QSettings', return_value=mock_settings):
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

        mock_settings = _mock_qsettings({'cover/gallery': ''})
        with patch('src.processing.upload_workers.QSettings', return_value=mock_settings):
            worker._upload_cover(item, gallery_id="turbo_gal_id")

        call_kwargs = worker.rename_worker.upload_cover.call_args[1]
        assert call_kwargs.get('gallery_id') == ""

    @patch('src.processing.upload_workers.RenameWorker')
    def test_same_host_turbo_routes_to_image_host_client(self, mock_rw_class):
        """Same non-IMX host: cover routes through image_host_factory, not rename_worker."""
        from src.processing.upload_workers import UploadWorker

        worker = UploadWorker(Mock())
        worker.rename_worker = MagicMock()
        worker.rename_worker.login_successful = True

        item = GalleryQueueItem(
            path="/tmp/test",
            image_host_id="turbo",
            cover_source_path="/tmp/test/cover.jpg",
            cover_host_id="turbo",
        )

        mock_client = MagicMock()
        mock_client.upload_image.return_value = {"raw": "data"}
        mock_client.normalize_response.return_value = {"status": "success", "bbcode": "x"}

        mock_settings = _mock_qsettings()
        with patch('src.processing.upload_workers.QSettings', return_value=mock_settings), \
             patch('src.processing.upload_workers.create_image_host_client', return_value=mock_client):
            result = worker._upload_cover(item, gallery_id="turbo_gal")

        # rename_worker should NOT be called for non-IMX cover host
        worker.rename_worker.upload_cover.assert_not_called()
        mock_client.upload_image.assert_called_once_with("/tmp/test/cover.jpg")
        assert result is not None
        assert result["status"] == "success"

    @patch('src.processing.upload_workers.RenameWorker')
    def test_cover_host_id_defaults_to_image_host_id(self, mock_rw_class):
        """When cover_host_id is None, falls back through QSettings then image_host_id."""
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

        # QSettings cover/host_id returns '' so fallback chain: None -> '' -> 'imx'
        mock_settings = _mock_qsettings({'cover/host_id': ''})
        with patch('src.processing.upload_workers.QSettings', return_value=mock_settings):
            worker._upload_cover(item, gallery_id="gal456")

        # cover_host_id defaults to image_host_id ("imx"), same host -> uses gallery_id
        call_kwargs = worker.rename_worker.upload_cover.call_args[1]
        assert call_kwargs.get('gallery_id') == "gal456"
