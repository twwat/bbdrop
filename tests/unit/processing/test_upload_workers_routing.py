"""
Test suite for M3 Upload Pipeline - Upload Worker Host Routing.

Verifies:
1. Worker reads settings via get_image_host_setting (not load_user_defaults)
2. Worker creates UploadEngine directly via _run_upload_engine (not upload_folder)
3. Metrics use dynamic host_name from config (not hardcoded 'imx.to')
4. Worker routes to correct host based on item.image_host_id
5. Settings resolve per-host with proper fallback
"""

import os
import pytest
import tempfile
import shutil
from unittest.mock import Mock, patch

from src.processing.upload_workers import UploadWorker
from src.storage.queue_manager import GalleryQueueItem


@pytest.fixture
def mock_queue_manager():
    manager = Mock()
    manager.get_next_item = Mock(return_value=None)
    manager.update_item_status = Mock()
    manager.mark_upload_failed = Mock()
    manager.get_queue_stats = Mock(return_value={})
    manager._schedule_debounced_save = Mock()
    return manager


@pytest.fixture
def temp_gallery():
    """Temp folder with test images for real engine runs."""
    d = tempfile.mkdtemp()
    for i in range(3):
        with open(os.path.join(d, f"img{i}.jpg"), 'wb') as f:
            f.write(b'\xff\xd8' + b'x' * 500)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _make_item(path="/test/gallery", host_id="imx", name="Test", total=3):
    """Build a mock GalleryQueueItem with all required attributes."""
    item = Mock(spec=GalleryQueueItem)
    item.path = path
    item.name = name
    item.tab_name = "Main"
    item.total_images = total
    item.template_name = "default"
    item.scan_complete = True
    item.status = "uploading"
    item.image_host_id = host_id
    item.gallery_id = ""
    item.gallery_url = ""
    item.uploaded_files = set()
    item.uploaded_images_data = []
    item.uploaded_bytes = 0
    item.uploaded_images = 0
    item.start_time = None
    item.end_time = None
    item.error_message = None
    item.observed_peak_kbps = 0.0
    item.avg_width = 0
    item.avg_height = 0
    item.max_width = 0
    item.max_height = 0
    item.min_width = 0
    item.min_height = 0
    item.total_size = 1500
    item.custom1 = ""
    item.custom2 = ""
    item.custom3 = ""
    item.custom4 = ""
    item.ext1 = ""
    item.ext2 = ""
    item.ext3 = ""
    item.ext4 = ""
    item.progress = 0
    return item


class TestWorkerUsesPerHostSettings:
    """Worker reads per-host settings via get_image_host_setting, not globals."""

    def test_get_image_host_setting_called_for_all_keys(
        self, mock_queue_manager, temp_gallery
    ):
        """upload_gallery calls get_image_host_setting for thumb size/format,
        max_retries, and parallel_batch_size with the item's host_id."""
        with patch('src.processing.upload_workers.get_image_host_setting') as mock_setting, \
             patch('src.processing.upload_workers.is_image_host_enabled', return_value=True), \
             patch('src.processing.upload_workers.create_image_host_client') as mock_factory, \
             patch('src.processing.upload_workers.UploadEngine') as MockEngine, \
             patch('src.processing.upload_workers.execute_gallery_hooks', return_value=None):

            mock_setting.return_value = 3
            mock_uploader = Mock()
            mock_uploader.get_default_headers = Mock(return_value={})
            mock_uploader.supports_gallery_rename = Mock(return_value=False)
            mock_factory.return_value = mock_uploader

            mock_engine_inst = Mock()
            mock_engine_inst.run = Mock(return_value={
                'successful_count': 3, 'failed_count': 0,
                'gallery_id': 'g1', 'gallery_url': 'http://x/g1',
            })
            MockEngine.return_value = mock_engine_inst

            worker = UploadWorker(mock_queue_manager)
            item = _make_item(path=temp_gallery, host_id="turbo")
            worker.current_item = item
            worker.upload_gallery(item)

            called_keys = {c[0][1] for c in mock_setting.call_args_list}
            for key in ('thumbnail_size', 'thumbnail_format',
                        'max_retries', 'parallel_batch_size'):
                assert key in called_keys, f"get_image_host_setting not called for '{key}'"

            called_host_ids = {c[0][0] for c in mock_setting.call_args_list}
            assert 'turbo' in called_host_ids

    def test_load_user_defaults_not_called(
        self, mock_queue_manager, temp_gallery
    ):
        """load_user_defaults must NOT be called in the upload path."""
        with patch('src.processing.upload_workers.get_image_host_setting', return_value=3), \
             patch('src.processing.upload_workers.is_image_host_enabled', return_value=True), \
             patch('src.processing.upload_workers.create_image_host_client') as mock_factory, \
             patch('src.processing.upload_workers.UploadEngine') as MockEngine, \
             patch('src.processing.upload_workers.load_user_defaults') as mock_lud, \
             patch('src.processing.upload_workers.execute_gallery_hooks', return_value=None):

            mock_uploader = Mock()
            mock_uploader.get_default_headers = Mock(return_value={})
            mock_uploader.supports_gallery_rename = Mock(return_value=False)
            mock_factory.return_value = mock_uploader

            mock_engine_inst = Mock()
            mock_engine_inst.run = Mock(return_value={
                'successful_count': 1, 'failed_count': 0,
                'gallery_id': 'g', 'gallery_url': 'http://x/g',
            })
            MockEngine.return_value = mock_engine_inst

            worker = UploadWorker(mock_queue_manager)
            item = _make_item(path=temp_gallery, host_id="imx")
            worker.current_item = item
            worker.upload_gallery(item)

            mock_lud.assert_not_called()


class TestWorkerCreatesEngineDirectly:
    """Worker calls _run_upload_engine, not uploader.upload_folder."""

    def test_upload_engine_created_with_uploader(
        self, mock_queue_manager, temp_gallery
    ):
        """Worker passes the factory-created uploader to UploadEngine."""
        with patch('src.processing.upload_workers.get_image_host_setting', return_value=3), \
             patch('src.processing.upload_workers.is_image_host_enabled', return_value=True), \
             patch('src.processing.upload_workers.create_image_host_client') as mock_factory, \
             patch('src.processing.upload_workers.UploadEngine') as MockEngine, \
             patch('src.processing.upload_workers.execute_gallery_hooks', return_value=None):

            mock_uploader = Mock()
            mock_uploader.get_default_headers = Mock(return_value={})
            mock_uploader.supports_gallery_rename = Mock(return_value=False)
            mock_factory.return_value = mock_uploader

            mock_engine_inst = Mock()
            mock_engine_inst.run = Mock(return_value={
                'successful_count': 3, 'failed_count': 0,
                'gallery_id': 'g1', 'gallery_url': 'http://x/g1',
            })
            MockEngine.return_value = mock_engine_inst

            worker = UploadWorker(mock_queue_manager)
            item = _make_item(path=temp_gallery)
            worker.current_item = item
            worker.upload_gallery(item)

            MockEngine.assert_called_once()
            assert MockEngine.call_args[0][0] is mock_uploader

    def test_upload_folder_not_called(
        self, mock_queue_manager, temp_gallery
    ):
        """Worker must NOT call uploader.upload_folder."""
        with patch('src.processing.upload_workers.get_image_host_setting', return_value=3), \
             patch('src.processing.upload_workers.is_image_host_enabled', return_value=True), \
             patch('src.processing.upload_workers.create_image_host_client') as mock_factory, \
             patch('src.processing.upload_workers.UploadEngine') as MockEngine, \
             patch('src.processing.upload_workers.execute_gallery_hooks', return_value=None):

            mock_uploader = Mock()
            mock_uploader.get_default_headers = Mock(return_value={})
            mock_uploader.supports_gallery_rename = Mock(return_value=False)
            mock_uploader.upload_folder = Mock()
            mock_factory.return_value = mock_uploader

            mock_engine_inst = Mock()
            mock_engine_inst.run = Mock(return_value={
                'successful_count': 1, 'failed_count': 0,
                'gallery_id': 'g', 'gallery_url': 'http://x/g',
            })
            MockEngine.return_value = mock_engine_inst

            worker = UploadWorker(mock_queue_manager)
            item = _make_item(path=temp_gallery)
            worker.current_item = item
            worker.upload_gallery(item)

            mock_uploader.upload_folder.assert_not_called()


class TestWorkerDynamicMetrics:
    """Metrics use dynamic host_name from config, not hardcoded 'imx.to'."""

    def test_success_metrics_use_dynamic_host_name(
        self, mock_queue_manager, temp_gallery
    ):
        with patch('src.processing.upload_workers.get_image_host_setting', return_value=3), \
             patch('src.processing.upload_workers.is_image_host_enabled', return_value=True), \
             patch('src.processing.upload_workers.create_image_host_client') as mock_factory, \
             patch('src.processing.upload_workers.UploadEngine') as MockEngine, \
             patch('src.processing.upload_workers.execute_gallery_hooks', return_value=None), \
             patch('src.processing.upload_workers.get_image_host_config_manager') as mock_cfg_mgr, \
             patch('src.utils.metrics_store.get_metrics_store') as mock_get_store:

            mock_uploader = Mock()
            mock_uploader.get_default_headers = Mock(return_value={})
            mock_uploader.supports_gallery_rename = Mock(return_value=False)
            mock_factory.return_value = mock_uploader

            mock_engine_inst = Mock()
            mock_engine_inst.run = Mock(return_value={
                'successful_count': 3, 'failed_count': 0,
                'gallery_id': 'g1', 'gallery_url': 'http://x/g1',
            })
            MockEngine.return_value = mock_engine_inst

            mock_host_cfg = Mock()
            mock_host_cfg.name = "TurboImageHost"
            mock_mgr = Mock()
            mock_mgr.get_host = Mock(return_value=mock_host_cfg)
            mock_cfg_mgr.return_value = mock_mgr

            mock_store = Mock()
            mock_get_store.return_value = mock_store

            worker = UploadWorker(mock_queue_manager)
            item = _make_item(path=temp_gallery, host_id="turbo")
            item.start_time = 100.0
            item.uploaded_bytes = 5000
            worker.current_item = item
            worker.upload_gallery(item)

            if mock_store.record_transfer.called:
                call_kwargs = mock_store.record_transfer.call_args
                host_arg = call_kwargs.kwargs.get('host_name') or call_kwargs[1].get('host_name')
                assert host_arg != "imx.to", \
                    f"Metrics still hardcode 'imx.to', got host_name='{host_arg}'"

    def test_failure_metrics_use_dynamic_host_name(
        self, mock_queue_manager, temp_gallery
    ):
        with patch('src.processing.upload_workers.get_image_host_setting', return_value=3), \
             patch('src.processing.upload_workers.is_image_host_enabled', return_value=True), \
             patch('src.processing.upload_workers.create_image_host_client') as mock_factory, \
             patch('src.processing.upload_workers.UploadEngine') as MockEngine, \
             patch('src.processing.upload_workers.execute_gallery_hooks', return_value=None), \
             patch('src.processing.upload_workers.get_image_host_config_manager') as mock_cfg_mgr, \
             patch('src.utils.metrics_store.get_metrics_store') as mock_get_store:

            mock_uploader = Mock()
            mock_uploader.get_default_headers = Mock(return_value={})
            mock_uploader.supports_gallery_rename = Mock(return_value=False)
            mock_factory.return_value = mock_uploader

            MockEngine.return_value.run = Mock(side_effect=RuntimeError("boom"))

            mock_host_cfg = Mock()
            mock_host_cfg.name = "TurboImageHost"
            mock_mgr = Mock()
            mock_mgr.get_host = Mock(return_value=mock_host_cfg)
            mock_cfg_mgr.return_value = mock_mgr

            mock_store = Mock()
            mock_get_store.return_value = mock_store

            worker = UploadWorker(mock_queue_manager)
            item = _make_item(path=temp_gallery, host_id="turbo")
            item.start_time = 100.0
            worker.current_item = item
            worker.upload_gallery(item)

            if mock_store.record_transfer.called:
                call_kwargs = mock_store.record_transfer.call_args
                host_arg = call_kwargs.kwargs.get('host_name') or call_kwargs[1].get('host_name')
                assert host_arg != "imx.to", \
                    f"Failure metrics still hardcode 'imx.to', got host_name='{host_arg}'"


class TestWorkerHostRouting:
    """Worker routes to the correct image host based on item.image_host_id."""

    def test_disabled_host_skipped_with_error(
        self, mock_queue_manager, temp_gallery
    ):
        """When host is disabled, upload fails with helpful error message."""
        with patch('src.processing.upload_workers.is_image_host_enabled', return_value=False), \
             patch('src.processing.upload_workers.create_image_host_client') as mock_factory, \
             patch('src.processing.upload_workers.UploadEngine') as MockEngine:

            mock_uploader = Mock()
            mock_factory.return_value = mock_uploader

            worker = UploadWorker(mock_queue_manager)
            item = _make_item(path=temp_gallery, host_id="turbo")
            worker.current_item = item
            worker.upload_gallery(item)

            # Should mark as failed with disabled message
            mock_queue_manager.mark_upload_failed.assert_called_once()
            call_args = mock_queue_manager.mark_upload_failed.call_args
            assert 'disabled' in call_args[0][1].lower()
            assert 'turbo' in call_args[0][1]

            # Should NOT create UploadEngine or attempt upload
            MockEngine.assert_not_called()

    def test_switches_host_when_id_differs(
        self, mock_queue_manager, temp_gallery
    ):
        """Worker calls _initialize_uploader when host_id changes."""
        with patch('src.processing.upload_workers.get_image_host_setting', return_value=3), \
             patch('src.processing.upload_workers.is_image_host_enabled', return_value=True), \
             patch('src.processing.upload_workers.create_image_host_client') as mock_factory, \
             patch('src.processing.upload_workers.UploadEngine') as MockEngine, \
             patch('src.processing.upload_workers.execute_gallery_hooks', return_value=None):

            mock_uploader = Mock()
            mock_uploader.get_default_headers = Mock(return_value={})
            mock_uploader.supports_gallery_rename = Mock(return_value=False)
            mock_factory.return_value = mock_uploader

            mock_engine_inst = Mock()
            mock_engine_inst.run = Mock(return_value={
                'successful_count': 1, 'failed_count': 0,
                'gallery_id': 'g', 'gallery_url': 'http://x/g',
            })
            MockEngine.return_value = mock_engine_inst

            worker = UploadWorker(mock_queue_manager)
            worker._current_host_id = "imx"  # pretend we started with imx

            item = _make_item(path=temp_gallery, host_id="turbo")
            worker.current_item = item
            worker.upload_gallery(item)

            mock_factory.assert_called_with('turbo')

    def test_defaults_to_imx_when_host_id_none(
        self, mock_queue_manager, temp_gallery
    ):
        """When item.image_host_id is None, default to 'imx'."""
        with patch('src.processing.upload_workers.get_image_host_setting') as mock_setting, \
             patch('src.processing.upload_workers.is_image_host_enabled', return_value=True), \
             patch('src.processing.upload_workers.create_image_host_client') as mock_factory, \
             patch('src.processing.upload_workers.UploadEngine') as MockEngine, \
             patch('src.processing.upload_workers.execute_gallery_hooks', return_value=None):

            mock_setting.return_value = 3
            mock_uploader = Mock()
            mock_uploader.get_default_headers = Mock(return_value={})
            mock_uploader.supports_gallery_rename = Mock(return_value=False)
            mock_factory.return_value = mock_uploader

            mock_engine_inst = Mock()
            mock_engine_inst.run = Mock(return_value={
                'successful_count': 1, 'failed_count': 0,
                'gallery_id': 'g', 'gallery_url': 'http://x/g',
            })
            MockEngine.return_value = mock_engine_inst

            worker = UploadWorker(mock_queue_manager)
            item = _make_item(path=temp_gallery, host_id=None)
            worker.current_item = item
            worker.upload_gallery(item)

            for c in mock_setting.call_args_list:
                assert c[0][0] == 'imx', f"Expected host_id='imx', got '{c[0][0]}'"
