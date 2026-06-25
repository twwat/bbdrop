#!/usr/bin/env python3
"""
Test for data race bug fix in UploadWorker started-hook thread.

The bug: run_started_hook() executes in a daemon thread and writes item.ext1-4
via setattr(). Meanwhile, the UploadWorker thread later calls
_save_artifacts_for_result() which reads ext1-4 to build custom_fields.
If the hook thread hasn't finished by the time artifacts are saved, the
artifacts get stale/empty ext fields.

The fix: keep a handle on the started-hook thread and join() it (with timeout)
before reading ext1-4 in _save_artifacts_for_result().
"""

import threading
import time
import unittest
from unittest.mock import Mock, patch, MagicMock, call

from src.processing.upload_workers import UploadWorker
from src.storage.queue_manager import GalleryQueueItem


class TestUploadWorkerHookRace(unittest.TestCase):
    """Test data race between started-hook and artifact save."""

    def setUp(self):
        """Create a mock queue manager for testing."""
        self.mock_queue_manager = Mock()
        self.mock_queue_manager._schedule_debounced_save = Mock()

    def test_started_hook_thread_is_joined_before_artifact_read(self):
        """
        Test that _save_artifacts_for_result joins the started-hook thread
        before reading ext1-4, ensuring hook writes are visible.

        This is a DETERMINISTIC test: we control the hook thread's delay
        and verify that custom_fields capture the post-hook value of ext1.
        """
        # Create a real UploadWorker instance (constructor is lightweight)
        worker = UploadWorker(self.mock_queue_manager)

        # Create a test item
        item = GalleryQueueItem(
            path="/test/gallery",
            name="test_gallery",
            total_images=1,
            image_host_id="imx",
            tab_name="default"
        )
        # Initialize ext fields (hook will update ext1)
        item.ext1 = "BEFORE_HOOK"
        item.ext2 = "ext2_val"
        item.ext3 = "ext3_val"
        item.ext4 = "ext4_val"
        item.custom1 = "custom1_val"
        item.custom2 = "custom2_val"
        item.custom3 = "custom3_val"
        item.custom4 = "custom4_val"
        item.template_name = "default"
        item.cover_result = []

        # Create a thread that sleeps briefly then updates ext1
        # This simulates the real started-hook delay
        def update_ext1():
            time.sleep(0.1)  # 100ms delay to simulate hook work
            item.ext1 = "HOOKVAL"

        hook_thread = threading.Thread(target=update_ext1, daemon=True)
        # Simulate the hook thread assignment from upload_gallery
        worker._started_hook_thread = hook_thread
        hook_thread.start()

        # Mock save_gallery_artifacts to capture the custom_fields argument
        with patch('src.processing.upload_workers.save_gallery_artifacts') as mock_save:
            mock_save.return_value = {}

            # Call _save_artifacts_for_result without any delay
            # The fix ensures join() happens before reading ext1
            results = {"successful_count": 1, "gallery_id": "123"}
            worker._save_artifacts_for_result(item, results)

            # Verify save_gallery_artifacts was called
            self.assertEqual(mock_save.call_count, 1)

            # Extract the custom_fields from the call
            call_kwargs = mock_save.call_args[1]
            custom_fields = call_kwargs.get('custom_fields', {})

            # DETERMINISTIC CHECK: custom_fields['ext1'] must be "HOOKVAL"
            # Without the join(), this would be "BEFORE_HOOK" (race condition).
            # With the join(), the hook thread has definitely finished,
            # so ext1 is guaranteed to be "HOOKVAL".
            self.assertEqual(
                custom_fields['ext1'],
                "HOOKVAL",
                "ext1 should be set by hook thread before artifact save"
            )

    def test_started_hook_thread_join_is_invoked(self):
        """
        Test that _save_artifacts_for_result calls join() on the hook thread
        if it exists and is alive.
        """
        worker = UploadWorker(self.mock_queue_manager)

        item = GalleryQueueItem(
            path="/test/gallery",
            name="test_gallery",
            total_images=1,
            image_host_id="imx",
            tab_name="default"
        )
        item.ext1 = "ext1"
        item.ext2 = "ext2"
        item.ext3 = "ext3"
        item.ext4 = "ext4"
        item.custom1 = "c1"
        item.custom2 = "c2"
        item.custom3 = "c3"
        item.custom4 = "c4"
        item.template_name = "default"
        item.cover_result = []

        # Create a mock thread that tracks join() calls
        mock_thread = Mock()
        mock_thread.is_alive.return_value = True
        mock_thread.join = Mock()

        worker._started_hook_thread = mock_thread

        with patch('src.processing.upload_workers.save_gallery_artifacts') as mock_save:
            mock_save.return_value = {}

            results = {"successful_count": 1, "gallery_id": "123"}
            worker._save_artifacts_for_result(item, results)

            # Verify join() was called with timeout
            mock_thread.join.assert_called_once()
            # Verify timeout was passed (default is 30)
            call_args = mock_thread.join.call_args
            self.assertIsNotNone(call_args[1].get('timeout'), "join() must have a timeout")

    def test_started_hook_thread_not_called_if_none(self):
        """Test that join() is skipped if _started_hook_thread is None."""
        worker = UploadWorker(self.mock_queue_manager)
        worker._started_hook_thread = None

        item = GalleryQueueItem(
            path="/test/gallery",
            name="test_gallery",
            total_images=1,
            image_host_id="imx",
            tab_name="default"
        )
        item.ext1 = "ext1"
        item.ext2 = "ext2"
        item.ext3 = "ext3"
        item.ext4 = "ext4"
        item.custom1 = "c1"
        item.custom2 = "c2"
        item.custom3 = "c3"
        item.custom4 = "c4"
        item.template_name = "default"
        item.cover_result = []

        with patch('src.processing.upload_workers.save_gallery_artifacts') as mock_save:
            mock_save.return_value = {}

            # Should not raise an error
            results = {"successful_count": 1, "gallery_id": "123"}
            worker._save_artifacts_for_result(item, results)

            mock_save.assert_called_once()

    def test_started_hook_thread_not_called_if_not_alive(self):
        """Test that join() is skipped if thread is not alive."""
        worker = UploadWorker(self.mock_queue_manager)

        item = GalleryQueueItem(
            path="/test/gallery",
            name="test_gallery",
            total_images=1,
            image_host_id="imx",
            tab_name="default"
        )
        item.ext1 = "ext1"
        item.ext2 = "ext2"
        item.ext3 = "ext3"
        item.ext4 = "ext4"
        item.custom1 = "c1"
        item.custom2 = "c2"
        item.custom3 = "c3"
        item.custom4 = "c4"
        item.template_name = "default"
        item.cover_result = []

        mock_thread = Mock()
        mock_thread.is_alive.return_value = False
        mock_thread.join = Mock()

        worker._started_hook_thread = mock_thread

        with patch('src.processing.upload_workers.save_gallery_artifacts') as mock_save:
            mock_save.return_value = {}

            results = {"successful_count": 1, "gallery_id": "123"}
            worker._save_artifacts_for_result(item, results)

            # join() should not be called if thread is not alive
            mock_thread.join.assert_not_called()

    def test_hook_thread_timeout_prevents_deadlock(self):
        """
        Test that join() with a timeout prevents a hung hook from deadlocking
        the worker thread.
        """
        worker = UploadWorker(self.mock_queue_manager)

        item = GalleryQueueItem(
            path="/test/gallery",
            name="test_gallery",
            total_images=1,
            image_host_id="imx",
            tab_name="default"
        )
        item.ext1 = "initial"
        item.ext2 = "ext2"
        item.ext3 = "ext3"
        item.ext4 = "ext4"
        item.custom1 = "c1"
        item.custom2 = "c2"
        item.custom3 = "c3"
        item.custom4 = "c4"
        item.template_name = "default"
        item.cover_result = []

        # Create a mock thread that never finishes
        mock_thread = Mock()
        mock_thread.is_alive.return_value = True
        mock_thread.join = Mock()  # Returns immediately (mocked)

        worker._started_hook_thread = mock_thread

        start_time = time.time()
        with patch('src.processing.upload_workers.save_gallery_artifacts') as mock_save:
            mock_save.return_value = {}

            results = {"successful_count": 1, "gallery_id": "123"}
            worker._save_artifacts_for_result(item, results)

        end_time = time.time()
        elapsed = end_time - start_time

        # Should complete quickly (not wait 30s for a real hung thread)
        # Since join is mocked, this just verifies the call path doesn't error
        mock_thread.join.assert_called_once()
        self.assertLess(elapsed, 2.0, "Should not hang on join with timeout")


if __name__ == '__main__':
    unittest.main()
