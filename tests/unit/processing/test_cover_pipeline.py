# tests/unit/processing/test_cover_pipeline.py
"""Tests for cover photo upload wired into the upload pipeline."""
from unittest.mock import patch, MagicMock, Mock

from src.storage.queue_manager import GalleryQueueItem


class TestCoverPipeline:
    """Cover upload triggers after gallery upload completes."""

    @patch('src.processing.upload_workers.RenameWorker')
    def test_cover_uploaded_when_source_path_set(self, mock_rw_class):
        """When item has cover_source_path, _upload_cover is called."""
        from src.processing.upload_workers import UploadWorker

        worker = UploadWorker(Mock())
        worker.rename_worker = MagicMock()
        worker.rename_worker.login_successful = True
        worker.rename_worker.upload_cover.return_value = {
            "status": "success",
            "bbcode": "[url=img][img]thumb[/img][/url]",
            "image_url": "img",
            "thumb_url": "thumb",
        }

        item = GalleryQueueItem(
            path="/tmp/test",
            name="test",
            cover_source_path="/tmp/test/cover.jpg",
            cover_host_id="imx",
        )

        result = worker._upload_cover(item, gallery_id="gal123")

        assert result is not None
        assert result["status"] == "success"
        worker.rename_worker.upload_cover.assert_called_once()

    @patch('src.processing.upload_workers.RenameWorker')
    def test_no_cover_when_source_path_none(self, mock_rw_class):
        """When item has no cover_source_path, _upload_cover returns None."""
        from src.processing.upload_workers import UploadWorker

        worker = UploadWorker(Mock())

        item = GalleryQueueItem(path="/tmp/test", name="test")
        result = worker._upload_cover(item, gallery_id="gal123")
        assert result is None

    @patch('src.processing.upload_workers.RenameWorker')
    def test_cover_failure_does_not_propagate(self, mock_rw_class):
        """Cover upload failure returns None but doesn't raise."""
        from src.processing.upload_workers import UploadWorker

        worker = UploadWorker(Mock())
        worker.rename_worker = MagicMock()
        worker.rename_worker.login_successful = True
        worker.rename_worker.upload_cover.return_value = None

        item = GalleryQueueItem(
            path="/tmp/test",
            name="test",
            cover_source_path="/tmp/test/cover.jpg",
            cover_host_id="imx",
        )

        result = worker._upload_cover(item, gallery_id="gal123")
        assert result is None

    @patch('src.processing.upload_workers.RenameWorker')
    def test_cover_skipped_when_no_rename_worker(self, mock_rw_class):
        """Cover upload skipped when rename_worker not available."""
        from src.processing.upload_workers import UploadWorker

        worker = UploadWorker(Mock())
        worker.rename_worker = None

        item = GalleryQueueItem(
            path="/tmp/test",
            name="test",
            cover_source_path="/tmp/test/cover.jpg",
            cover_host_id="imx",
        )

        result = worker._upload_cover(item, gallery_id="gal123")
        assert result is None

    @patch('src.processing.upload_workers.RenameWorker')
    def test_cover_skipped_when_not_logged_in(self, mock_rw_class):
        """Cover upload skipped when rename_worker exists but not authenticated."""
        from src.processing.upload_workers import UploadWorker

        worker = UploadWorker(Mock())
        worker.rename_worker = MagicMock()
        worker.rename_worker.login_successful = False

        item = GalleryQueueItem(
            path="/tmp/test",
            name="test",
            cover_source_path="/tmp/test/cover.jpg",
            cover_host_id="imx",
        )

        result = worker._upload_cover(item, gallery_id="gal123")
        assert result is None

    @patch('src.processing.upload_workers.RenameWorker')
    def test_cover_exception_returns_none(self, mock_rw_class):
        """Cover upload exception is caught and returns None."""
        from src.processing.upload_workers import UploadWorker

        worker = UploadWorker(Mock())
        worker.rename_worker = MagicMock()
        worker.rename_worker.login_successful = True
        worker.rename_worker.upload_cover.side_effect = RuntimeError("network error")

        item = GalleryQueueItem(
            path="/tmp/test",
            name="test",
            cover_source_path="/tmp/test/cover.jpg",
            cover_host_id="imx",
        )

        result = worker._upload_cover(item, gallery_id="gal123")
        assert result is None

    @patch('src.processing.upload_workers.RenameWorker')
    def test_cover_result_stored_on_item(self, mock_rw_class):
        """Successful cover upload stores result on the item."""
        from src.processing.upload_workers import UploadWorker

        worker = UploadWorker(Mock())
        worker.rename_worker = MagicMock()
        worker.rename_worker.login_successful = True
        cover_data = {
            "status": "success",
            "bbcode": "[url=img][img]thumb[/img][/url]",
            "image_url": "img",
            "thumb_url": "thumb",
        }
        worker.rename_worker.upload_cover.return_value = cover_data

        item = GalleryQueueItem(
            path="/tmp/test",
            name="test",
            cover_source_path="/tmp/test/cover.jpg",
            cover_host_id="imx",
        )

        worker._upload_cover(item, gallery_id="gal123")
        assert item.cover_result == cover_data

    @patch('src.processing.upload_workers.RenameWorker')
    def test_cover_uses_item_host_id_fallback(self, mock_rw_class):
        """When cover_host_id is None, falls back to image_host_id."""
        from src.processing.upload_workers import UploadWorker

        worker = UploadWorker(Mock())
        worker.rename_worker = MagicMock()
        worker.rename_worker.login_successful = True
        worker.rename_worker.upload_cover.return_value = {
            "status": "success",
            "bbcode": "[url=img][img]thumb[/img][/url]",
            "image_url": "img",
            "thumb_url": "thumb",
        }

        item = GalleryQueueItem(
            path="/tmp/test",
            name="test",
            cover_source_path="/tmp/test/cover.jpg",
            cover_host_id=None,
            image_host_id="imx",
        )

        result = worker._upload_cover(item, gallery_id="gal123")
        assert result is not None
