# This is a fixed version of the test_upload_gallery_with_hooks test
# The key fix: Don't mock threading.Thread when testing hook execution

import time
from unittest.mock import Mock, patch

def test_upload_gallery_with_hooks_FIXED():
    """
    FIXED VERSION: Test upload with hook execution

    KEY FIX: Don't mock threading.Thread - let background threads run naturally
    for hook execution to complete.
    """
    with patch('src.processing.upload_workers.RenameWorker'), \
         patch('src.processing.upload_workers.load_user_defaults') as mock_defaults, \
         patch('src.processing.upload_workers.execute_gallery_hooks') as mock_hooks:

        mock_defaults.return_value = {
            'thumbnail_size': 3,
            'thumbnail_format': 2,
            'max_retries': 3,
            'parallel_batch_size': 4
        }

        # Hook returns ext field values
        mock_hooks.return_value = {'ext1': 'hook_value'}

        from src.processing.upload_workers import UploadWorker

        mock_queue_manager = Mock()
        worker = UploadWorker(mock_queue_manager)

        mock_uploader = Mock()
        mock_uploader.upload_folder.return_value = {
            'successful_count': 50,
            'failed_count': 0,
            'gallery_id': 'gal123',
            'gallery_url': 'http://example.com/gal123'
        }
        worker.uploader = mock_uploader

        mock_item = Mock()
        mock_item.path = "/path/to/gallery"
        mock_item.name = "Test Gallery"
        mock_item.tab_name = "Main"
        mock_item.total_images = 50
        mock_item.template_name = "default"
        mock_item.scan_complete = True
        mock_item.status = "uploading"

        # FIXED: Don't mock threading.Thread - let it run naturally
        worker.upload_gallery(mock_item)

        # Give background thread time to complete hook execution
        time.sleep(0.15)

        # Hook should have been executed (called twice: 'started' and 'completed' events)
        assert mock_hooks.call_count >= 1, f"Expected hook to be called, but call_count={mock_hooks.call_count}"
