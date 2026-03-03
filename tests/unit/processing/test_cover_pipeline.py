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
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["status"] == "success"
        assert result[0]["source_path"] == "/tmp/test/cover.jpg"
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
        """Cover upload failure returns list with failed entry but doesn't raise."""
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
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]['status'] == 'failed'
        assert result[0]['source_path'] == '/tmp/test/cover.jpg'

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
    def test_cover_exception_returns_list_with_error(self, mock_rw_class):
        """Cover upload exception is caught per-path and returns list with error entry."""
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
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]['status'] == 'failed'
        assert 'network error' in result[0]['error']
        assert result[0]['source_path'] == '/tmp/test/cover.jpg'

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
        assert isinstance(item.cover_result, list)
        assert len(item.cover_result) == 1
        # Result dict should contain original fields plus source_path
        assert item.cover_result[0]['status'] == cover_data['status']
        assert item.cover_result[0]['bbcode'] == cover_data['bbcode']
        assert item.cover_result[0]['source_path'] == '/tmp/test/cover.jpg'

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
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]['status'] == 'success'


class TestCoverProgressDecoupled:
    """Cover operations must NOT inflate gallery progress or final results."""

    @patch('src.processing.upload_workers.UploadEngine')
    @patch('src.processing.upload_workers.RenameWorker')
    def test_progress_callback_excludes_cover_ops(self, mock_rw_class, mock_engine_class):
        """Progress callback should report gallery-only counts, not inflate with cover ops."""
        from src.processing.upload_workers import UploadWorker

        worker = UploadWorker(Mock())
        worker.rename_worker = MagicMock()
        worker.current_item = None
        worker.global_byte_counter = MagicMock()
        worker.current_gallery_counter = MagicMock()
        worker.progress_updated = MagicMock()
        worker._bw_last_bytes = 0
        worker._bw_last_time = 0

        # Item has 2 cover source paths, but gallery has 38 images
        item = GalleryQueueItem(
            path="/tmp/gallery38",
            name="gallery38",
            cover_source_path="/tmp/gallery38/cover1.jpg;/tmp/gallery38/cover2.jpg",
            cover_host_id="imx",
            image_host_id="imx",
        )
        item.template_name = None

        # When engine.run() is called, invoke on_progress with gallery-only counts
        def fake_run(**kwargs):
            on_progress = kwargs['on_progress']
            on_progress(38, 38, 100, "last.jpg")
            return {'successful_count': 38, 'total_images': 38, 'gallery_id': 'g1'}

        mock_engine_instance = mock_engine_class.return_value
        mock_engine_instance.run.side_effect = fake_run

        result = worker._run_upload_engine(
            item, thumbnail_size=350, thumbnail_format=2,
            max_retries=3, parallel_batch_size=5,
        )

        # The progress_updated signal should have received gallery-only total (38),
        # NOT 40 (which would be 38 gallery + 2 covers)
        worker.progress_updated.emit.assert_called_once_with(
            "/tmp/gallery38", 38, 38, 100, "last.jpg"
        )

    @patch('src.processing.upload_workers.RenameWorker')
    def test_final_results_exclude_cover_ops_from_total(self, mock_rw_class):
        """Final total_images should reflect gallery-only count, not inflated with cover ops."""
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
        worker.queue_manager = MagicMock()
        worker.gallery_completed = MagicMock()
        worker.gallery_failed = MagicMock()
        worker._soft_stop_requested_for = None
        worker._emit_queue_stats = MagicMock()

        # Item has 2 cover paths but gallery has 38 images
        item = GalleryQueueItem(
            path="/tmp/gallery38",
            name="gallery38",
            cover_source_path="/tmp/gallery38/cover1.jpg;/tmp/gallery38/cover2.jpg",
            cover_host_id="imx",
            image_host_id="imx",
        )
        item.start_time = 1000.0
        item.uploaded_bytes = 0

        results = {
            'successful_count': 38,
            'total_images': 38,
            'failed_count': 0,
            'gallery_id': 'g1',
            'gallery_url': 'https://imx.to/g/g1',
        }

        with patch('src.utils.metrics_store.get_metrics_store', return_value=None), \
             patch.object(worker, '_upload_cover', return_value={
                 'status': 'success', 'bbcode': 'bb', 'image_url': 'img', 'thumb_url': 'thumb',
             }), \
             patch.object(worker, '_save_artifacts_for_result', return_value={}), \
             patch('src.processing.upload_workers.execute_gallery_hooks', return_value={}):
            worker._process_upload_results(item, results)

        # total_images should stay 38 (gallery only), NOT 40 (38 + 2 covers)
        assert results['total_images'] == 38
        assert results['successful_count'] == 38
        # Gallery should be marked completed (38/38 success)
        worker.queue_manager.update_item_status.assert_called_with("/tmp/gallery38", "completed")


class TestMultiCoverUpload:
    """Tests for multi-cover upload behavior (Task 5)."""

    @patch('src.processing.upload_workers.RenameWorker')
    def test_upload_cover_imx_uploads_all_paths(self, mock_rw_class):
        """IMX should upload each cover individually, not just paths[0]."""
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
            cover_source_path="/tmp/test/cover1.jpg;/tmp/test/cover2.jpg;/tmp/test/cover3.jpg",
            cover_host_id="imx",
        )

        result = worker._upload_cover(item, gallery_id="gal123")

        # All 3 paths should have been uploaded
        assert worker.rename_worker.upload_cover.call_count == 3
        assert isinstance(result, list)
        assert len(result) == 3
        # Each result should have its own source_path
        assert result[0]['source_path'] == '/tmp/test/cover1.jpg'
        assert result[1]['source_path'] == '/tmp/test/cover2.jpg'
        assert result[2]['source_path'] == '/tmp/test/cover3.jpg'

    @patch('src.processing.upload_workers.RenameWorker')
    def test_upload_cover_returns_list_of_results(self, mock_rw_class):
        """_upload_cover should return a list of per-cover result dicts."""
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

        assert isinstance(result, list)
        assert len(result) == 1
        assert 'status' in result[0]
        assert 'source_path' in result[0]
        assert result[0]['status'] == 'success'

    @patch('src.processing.upload_workers.RenameWorker')
    def test_upload_cover_failed_returns_list_with_error(self, mock_rw_class):
        """When a cover upload fails, return list with {status: 'failed', error, source_path}."""
        from src.processing.upload_workers import UploadWorker

        worker = UploadWorker(Mock())
        worker.rename_worker = MagicMock()
        worker.rename_worker.login_successful = True
        worker.rename_worker.upload_cover.side_effect = RuntimeError("connection refused")

        item = GalleryQueueItem(
            path="/tmp/test",
            name="test",
            cover_source_path="/tmp/test/cover.jpg",
            cover_host_id="imx",
        )

        result = worker._upload_cover(item, gallery_id="gal123")

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]['status'] == 'failed'
        assert 'connection refused' in result[0]['error']
        assert result[0]['source_path'] == '/tmp/test/cover.jpg'

    @patch('src.processing.upload_workers.RenameWorker')
    def test_upload_cover_sets_cover_status_completed(self, mock_rw_class):
        """After all covers succeed, item.cover_status should be 'completed'."""
        from src.processing.upload_workers import UploadWorker

        worker = UploadWorker(Mock())
        worker.rename_worker = MagicMock()
        worker.rename_worker.login_successful = True
        worker.rename_worker.upload_cover.return_value = {
            "status": "success",
            "bbcode": "bb",
            "image_url": "img",
            "thumb_url": "thumb",
        }

        item = GalleryQueueItem(
            path="/tmp/test",
            name="test",
            cover_source_path="/tmp/test/cover1.jpg;/tmp/test/cover2.jpg",
            cover_host_id="imx",
        )

        worker._upload_cover(item, gallery_id="gal123")
        assert item.cover_status == "completed"

    @patch('src.processing.upload_workers.RenameWorker')
    def test_upload_cover_sets_cover_status_partial(self, mock_rw_class):
        """When some covers fail, item.cover_status should be 'partial'."""
        from src.processing.upload_workers import UploadWorker

        worker = UploadWorker(Mock())
        worker.rename_worker = MagicMock()
        worker.rename_worker.login_successful = True
        # First call succeeds, second fails
        worker.rename_worker.upload_cover.side_effect = [
            {"status": "success", "bbcode": "bb", "image_url": "img", "thumb_url": "thumb"},
            RuntimeError("timeout"),
        ]

        item = GalleryQueueItem(
            path="/tmp/test",
            name="test",
            cover_source_path="/tmp/test/cover1.jpg;/tmp/test/cover2.jpg",
            cover_host_id="imx",
        )

        result = worker._upload_cover(item, gallery_id="gal123")
        assert item.cover_status == "partial"
        assert len(result) == 2
        assert result[0]['status'] == 'success'
        assert result[1]['status'] == 'failed'

    @patch('src.processing.upload_workers.RenameWorker')
    def test_upload_cover_sets_cover_status_failed(self, mock_rw_class):
        """When all covers fail, item.cover_status should be 'failed'."""
        from src.processing.upload_workers import UploadWorker

        worker = UploadWorker(Mock())
        worker.rename_worker = MagicMock()
        worker.rename_worker.login_successful = True
        worker.rename_worker.upload_cover.return_value = None  # All uploads return None

        item = GalleryQueueItem(
            path="/tmp/test",
            name="test",
            cover_source_path="/tmp/test/cover1.jpg;/tmp/test/cover2.jpg",
            cover_host_id="imx",
        )

        result = worker._upload_cover(item, gallery_id="gal123")
        assert item.cover_status == "failed"
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(r['status'] == 'failed' for r in result)
