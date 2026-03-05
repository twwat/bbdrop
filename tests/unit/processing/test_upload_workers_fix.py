# Verify that hook execution works when threads run naturally (not mocked)

import time
from unittest.mock import Mock, patch


def test_upload_gallery_with_hooks_FIXED():
    """
    Test upload with hook execution using natural thread execution.

    KEY FIX: Don't mock threading.Thread - let background threads run naturally
    for hook execution to complete.
    """
    with patch('src.processing.upload_workers.RenameWorker'), \
         patch('src.processing.upload_workers.execute_gallery_hooks') as mock_hooks, \
         patch('src.processing.upload_workers.get_image_host_setting', return_value=3), \
         patch('src.processing.upload_workers.is_image_host_enabled', return_value=True), \
         patch('src.processing.upload_workers.get_enabled_hosts', return_value={'imx': True}):

        # Hook returns ext field values
        mock_hooks.return_value = {'ext1': 'hook_value'}

        from src.processing.upload_workers import UploadWorker

        mock_queue_manager = Mock()
        worker = UploadWorker(mock_queue_manager)

        worker._current_host_id = "imx"
        worker.uploader = Mock()

        upload_results = {
            'successful_count': 50,
            'failed_count': 0,
            'gallery_id': 'gal123',
            'gallery_url': 'http://example.com/gal123',
        }

        mock_item = Mock()
        mock_item.path = "/path/to/gallery"
        mock_item.name = "Test Gallery"
        mock_item.tab_name = "Main"
        mock_item.total_images = 50
        mock_item.template_name = "default"
        mock_item.scan_complete = True
        mock_item.status = "uploading"
        mock_item.image_host_id = "imx"
        mock_item.start_time = 0.0
        mock_item.uploaded_bytes = 0
        mock_item.cover_source_path = None
        mock_item.cover_result = None
        mock_item.observed_peak_kbps = 0.0

        with patch.object(worker, '_run_upload_engine', return_value=upload_results), \
             patch.object(worker, '_process_upload_results'):
            worker.upload_gallery(mock_item)

        # Give background thread time to complete hook execution
        time.sleep(0.15)

        # Hook should have been executed at least for the 'started' event
        assert mock_hooks.call_count >= 1, \
            f"Expected hook to be called, but call_count={mock_hooks.call_count}"
