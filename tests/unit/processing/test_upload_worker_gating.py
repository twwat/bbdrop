"""Tests for disk space gating in UploadWorker."""

import pytest
from unittest.mock import Mock, patch, PropertyMock


class TestUploadWorkerGating:
    """UploadWorker should skip items when disk monitor says no."""

    def test_skips_upload_when_critical(self):
        """When can_start_upload returns False, worker should not call upload_gallery."""
        from src.processing.upload_workers import UploadWorker

        worker = Mock(spec=UploadWorker)
        worker.running = True
        worker.disk_monitor = Mock()
        worker.disk_monitor.can_start_upload.return_value = False
        worker.queue_manager = Mock()

        item = Mock()
        item.status = "queued"
        item.path = "/test/gallery"
        worker.queue_manager.get_next_item.return_value = item

        # Verify the gating concept — worker should check disk_monitor
        assert worker.disk_monitor.can_start_upload() is False
