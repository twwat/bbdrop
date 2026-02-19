# tests/unit/processing/test_cover_routing.py
"""Tests for cover upload routing based on gallery host."""
from unittest.mock import patch, MagicMock, Mock

from src.storage.queue_manager import GalleryQueueItem


def _mock_qsettings(overrides=None):
    """Create a QSettings mock that returns sensible defaults with overrides."""
    values = {
        'cover/host_id': '',
    }
    if overrides:
        values.update(overrides)

    mock_settings = MagicMock()
    mock_settings.value.side_effect = lambda key, default=None, **kw: values.get(key, default)
    return mock_settings


def _mock_host_setting(overrides=None):
    """Return a side_effect function for get_image_host_setting with overrides.

    Default returns:
        cover_gallery -> ''
        cover_thumbnail_format -> 2
        cover_thumbnail_size -> 600
    """
    defaults = {
        'cover_gallery': '',
        'cover_thumbnail_format': 2,
        'cover_thumbnail_size': 600,
    }
    if overrides:
        defaults.update(overrides)

    def side_effect(host_id, key, value_type='str'):
        return defaults.get(key)

    return side_effect


class TestCoverRouting:
    """Cover upload routes correctly based on gallery vs cover host."""

    @patch('src.processing.upload_workers.RenameWorker')
    def test_imx_gallery_imx_cover_uses_gallery_id(self, mock_rw_class):
        """IMX gallery + IMX cover + no explicit cover_gallery: cover goes into that gallery."""
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

        with patch('src.processing.upload_workers.QSettings', return_value=_mock_qsettings()), \
             patch('src.processing.upload_workers.get_image_host_setting',
                   side_effect=_mock_host_setting()):
            worker._upload_cover(item, gallery_id="gal123")

        call_kwargs = worker.rename_worker.upload_cover.call_args[1]
        assert call_kwargs.get('gallery_id') == "gal123"

    @patch('src.processing.upload_workers.RenameWorker')
    def test_non_imx_gallery_imx_cover_with_explicit_cover_gallery(self, mock_rw_class):
        """Non-IMX gallery + IMX cover + explicit cover_gallery: uses cover_gallery setting."""
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

        with patch('src.processing.upload_workers.QSettings', return_value=_mock_qsettings()), \
             patch('src.processing.upload_workers.get_image_host_setting',
                   side_effect=_mock_host_setting({'cover_gallery': 'my_cover_gallery'})):
            worker._upload_cover(item, gallery_id="turbo_gal_id")

        call_kwargs = worker.rename_worker.upload_cover.call_args[1]
        # Explicit cover_gallery takes priority over same-host fallback
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

        with patch('src.processing.upload_workers.QSettings', return_value=_mock_qsettings()), \
             patch('src.processing.upload_workers.get_image_host_setting',
                   side_effect=_mock_host_setting({'cover_gallery': ''})):
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
        # upload_image returns a normalized response (status + data dict)
        mock_client.upload_image.return_value = {
            "status": "success",
            "data": {"image_url": "img", "thumb_url": "thumb", "bbcode": "[img]x[/img]"},
        }

        with patch('src.processing.upload_workers.QSettings', return_value=_mock_qsettings()), \
             patch('src.processing.upload_workers.get_image_host_setting',
                   side_effect=_mock_host_setting()), \
             patch('src.processing.upload_workers.create_image_host_client', return_value=mock_client):
            result = worker._upload_cover(item, gallery_id="turbo_gal")

        # rename_worker should NOT be called for non-IMX cover host
        worker.rename_worker.upload_cover.assert_not_called()
        # Same host, no explicit cover_gallery -> passes gallery_id
        mock_client.upload_image.assert_called_once_with(
            "/tmp/test/cover.jpg",
            gallery_id="turbo_gal",
            thumbnail_size=600,
        )
        assert result is not None
        assert result["status"] == "success"
        assert result["bbcode"] == "[img]x[/img]"

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
        with patch('src.processing.upload_workers.QSettings', return_value=_mock_qsettings({'cover/host_id': ''})), \
             patch('src.processing.upload_workers.get_image_host_setting',
                   side_effect=_mock_host_setting()):
            worker._upload_cover(item, gallery_id="gal456")

        # cover_host_id defaults to image_host_id ("imx"), same host -> uses gallery_id
        call_kwargs = worker.rename_worker.upload_cover.call_args[1]
        assert call_kwargs.get('gallery_id') == "gal456"

    @patch('src.processing.upload_workers.RenameWorker')
    def test_explicit_cover_gallery_overrides_same_host_fallback(self, mock_rw_class):
        """When cover_gallery is set, it takes priority even for same-host uploads."""
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

        with patch('src.processing.upload_workers.QSettings', return_value=_mock_qsettings()), \
             patch('src.processing.upload_workers.get_image_host_setting',
                   side_effect=_mock_host_setting({'cover_gallery': 'dedicated_covers'})):
            worker._upload_cover(item, gallery_id="gal789")

        call_kwargs = worker.rename_worker.upload_cover.call_args[1]
        # Explicit cover_gallery should override same-host gallery_id fallback
        assert call_kwargs.get('gallery_id') == "dedicated_covers"

    @patch('src.processing.upload_workers.RenameWorker')
    def test_cover_thumbnail_format_from_ini(self, mock_rw_class):
        """IMX cover reads cover_thumbnail_format from per-host INI setting."""
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

        with patch('src.processing.upload_workers.QSettings', return_value=_mock_qsettings()), \
             patch('src.processing.upload_workers.get_image_host_setting',
                   side_effect=_mock_host_setting({'cover_thumbnail_format': 5})):
            worker._upload_cover(item, gallery_id="gal_fmt")

        call_kwargs = worker.rename_worker.upload_cover.call_args[1]
        assert call_kwargs.get('thumbnail_format') == 5

    @patch('src.processing.upload_workers.RenameWorker')
    def test_non_imx_cover_passes_thumbnail_size(self, mock_rw_class):
        """Non-IMX cover passes cover_thumbnail_size to upload_image()."""
        from src.processing.upload_workers import UploadWorker

        worker = UploadWorker(Mock())

        item = GalleryQueueItem(
            path="/tmp/test",
            image_host_id="turbo",
            cover_source_path="/tmp/test/cover.jpg",
            cover_host_id="turbo",
        )

        mock_client = MagicMock()
        mock_client.upload_image.return_value = {
            "status": "success",
            "data": {"image_url": "img", "thumb_url": "thumb", "bbcode": "[img]x[/img]"},
        }

        with patch('src.processing.upload_workers.QSettings', return_value=_mock_qsettings()), \
             patch('src.processing.upload_workers.get_image_host_setting',
                   side_effect=_mock_host_setting({'cover_thumbnail_size': 400})), \
             patch('src.processing.upload_workers.create_image_host_client', return_value=mock_client):
            worker._upload_cover(item, gallery_id="turbo_gal")

        mock_client.upload_image.assert_called_once_with(
            "/tmp/test/cover.jpg",
            gallery_id="turbo_gal",
            thumbnail_size=400,
        )

    @patch('src.processing.upload_workers.RenameWorker')
    def test_non_imx_different_host_no_cover_gallery_passes_none(self, mock_rw_class):
        """Different host, no explicit cover_gallery: gallery_id=None to upload_image()."""
        from src.processing.upload_workers import UploadWorker

        worker = UploadWorker(Mock())

        item = GalleryQueueItem(
            path="/tmp/test",
            image_host_id="turbo",
            cover_source_path="/tmp/test/cover.jpg",
            cover_host_id="other_host",
        )

        mock_client = MagicMock()
        mock_client.upload_image.return_value = {
            "status": "success",
            "data": {"image_url": "img", "thumb_url": "thumb", "bbcode": "bb"},
        }

        with patch('src.processing.upload_workers.QSettings', return_value=_mock_qsettings()), \
             patch('src.processing.upload_workers.get_image_host_setting',
                   side_effect=_mock_host_setting({'cover_gallery': ''})), \
             patch('src.processing.upload_workers.create_image_host_client', return_value=mock_client):
            worker._upload_cover(item, gallery_id="turbo_gal")

        # Different host, no explicit cover_gallery -> gallery_id=None
        mock_client.upload_image.assert_called_once_with(
            "/tmp/test/cover.jpg",
            gallery_id=None,
            thumbnail_size=600,
        )
