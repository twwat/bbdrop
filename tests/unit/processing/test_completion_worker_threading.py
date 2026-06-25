#!/usr/bin/env python3
"""Unit tests for CompletionWorker threading safety.

Tests verify that CompletionWorker does not access Qt widgets or
unguarded queue_manager dicts from the worker thread.
"""

import unittest
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from datetime import datetime
from queue import Queue

from src.processing.artifact_handler import CompletionWorker


class TestCompletionWorkerThreading(unittest.TestCase):
    """Test thread safety of CompletionWorker."""

    def setUp(self):
        """Set up test fixtures."""
        self.worker = CompletionWorker()

    def tearDown(self):
        """Clean up after tests."""
        self.worker.stop()
        self.worker.wait(2000)

    def test_process_completion_reads_ui_settings_on_gui_thread(self):
        """Verify process_completion (GUI thread) reads combo values and queues them."""
        # Create a mock gui_parent with combo controls
        gui_parent = Mock()
        gui_parent.thumbnail_size_combo = Mock()
        gui_parent.thumbnail_size_combo.currentIndex = Mock(return_value=1)  # Returns index; we +1 it
        gui_parent.thumbnail_format_combo = Mock()
        gui_parent.thumbnail_format_combo.currentIndex = Mock(return_value=2)
        gui_parent.queue_manager = Mock()

        path = "/test/gallery"
        results = {'gallery_id': 'test_id', 'gallery_name': 'test'}

        # Enqueue the item; process_completion should read combos
        self.worker.process_completion(path, results, gui_parent)

        # Verify the queue now has a 4-tuple with ui_settings
        item = self.worker.completion_queue.get(timeout=1.0)
        self.assertIsNotNone(item)
        self.assertEqual(len(item), 4)

        queued_path, queued_results, queued_gui_parent, queued_ui_settings = item
        self.assertEqual(queued_path, path)
        self.assertEqual(queued_results, results)
        self.assertEqual(queued_gui_parent, gui_parent)

        # Verify ui_settings contains the read values
        self.assertIn('thumbnail_size', queued_ui_settings)
        self.assertIn('thumbnail_format', queued_ui_settings)
        self.assertEqual(queued_ui_settings['thumbnail_size'], 2)  # index 1 + 1
        self.assertEqual(queued_ui_settings['thumbnail_format'], 3)  # index 2 + 1

    def test_completion_worker_does_not_access_combo_widgets(self):
        """Verify _process_completion_background does NOT touch combo widgets."""
        # Create a gui_parent whose combo widgets will raise if accessed
        gui_parent = Mock()

        # Make combo access raise AttributeError if accessed during processing
        combo_error = RuntimeError("Widget access off thread!")

        def combo_side_effect(*args, **kwargs):
            raise combo_error

        gui_parent.thumbnail_size_combo = Mock(side_effect=combo_side_effect)
        gui_parent.thumbnail_format_combo = Mock(side_effect=combo_side_effect)

        # Set up queue_manager with a cached queue_item
        queue_item = Mock()
        queue_item.start_time = datetime.now().timestamp()
        queue_item.total_size = 1000
        queue_item.avg_width = 800
        queue_item.avg_height = 600
        queue_item.max_width = 1000
        queue_item.max_height = 900
        queue_item.min_width = 100
        queue_item.min_height = 100
        queue_item.template_name = 'default'
        queue_item.custom1 = ''
        queue_item.custom2 = ''
        queue_item.custom3 = ''
        queue_item.custom4 = ''
        queue_item.ext1 = ''
        queue_item.ext2 = ''
        queue_item.ext3 = ''
        queue_item.ext4 = ''

        gui_parent.queue_manager = Mock()
        gui_parent.queue_manager.get_item = Mock(return_value=queue_item)

        # Make items dict raise on access to catch any TOCTOU bugs
        items_dict = Mock()
        items_dict.__getitem__ = Mock(side_effect=RuntimeError("Dict access off thread!"))
        items_dict.__contains__ = Mock(side_effect=RuntimeError("Dict access off thread!"))
        gui_parent.queue_manager.items = items_dict

        path = "/test/gallery"
        results = {
            'gallery_id': 'test_id',
            'gallery_name': 'TestGallery',
            'images': [
                {'image_url': 'http://example.com/img.jpg', 'bbcode': '[img]test[/img]'}
            ],
            'failed_details': [],
            'total_size': 1000,
            'avg_width': 800,
            'avg_height': 600,
            'max_width': 1000,
            'max_height': 900,
            'min_width': 100,
            'min_height': 100,
        }

        # Provide ui_settings (pre-read on GUI thread)
        ui_settings = {
            'thumbnail_size': 2,
            'thumbnail_format': 3,
        }

        # Mock external functions to avoid file I/O
        with patch('src.storage.gallery_management.save_unnamed_gallery'):
            with patch('src.storage.gallery_management.get_unnamed_galleries', return_value={}):
                with patch('src.storage.gallery_management.check_gallery_renamed', return_value=True):
                    with patch('src.utils.templates.save_gallery_artifacts', return_value={'central': {}, 'uploaded': {}}) as mock_save:
                        with patch('src.utils.paths.load_user_defaults', return_value={}):
                            # This should NOT raise "Widget access off thread!"
                            # It should use ui_settings instead
                            self.worker._process_completion_background(path, results, gui_parent, ui_settings)

                            # Verify save_gallery_artifacts was called with the ui_settings values
                            mock_save.assert_called_once()
                            call_args = mock_save.call_args
                            results_arg = call_args[1]['results']

                            # Verify thumbnail values came from ui_settings, not from widget access
                            self.assertEqual(results_arg['thumbnail_size'], 2)
                            self.assertEqual(results_arg['thumbnail_format'], 3)

    def test_completion_worker_uses_cached_queue_item_for_start_time(self):
        """Verify start_time comes from cached get_item, not from items dict."""
        # Create a gui_parent
        gui_parent = Mock()

        # Make items dict raise on access to catch TOCTOU bugs
        items_dict = Mock()
        items_dict.__contains__ = Mock(side_effect=RuntimeError("Dict access on worker thread!"))
        items_dict.__getitem__ = Mock(side_effect=RuntimeError("Dict access on worker thread!"))
        gui_parent.queue_manager.items = items_dict

        # Set up cached queue_item with start_time
        start_time_ts = datetime(2026, 6, 24, 10, 30, 45).timestamp()
        queue_item = Mock()
        queue_item.start_time = start_time_ts
        queue_item.total_size = 1000
        queue_item.avg_width = 800
        queue_item.avg_height = 600
        queue_item.max_width = 1000
        queue_item.max_height = 900
        queue_item.min_width = 100
        queue_item.min_height = 100
        queue_item.template_name = 'default'
        queue_item.custom1 = ''
        queue_item.custom2 = ''
        queue_item.custom3 = ''
        queue_item.custom4 = ''
        queue_item.ext1 = ''
        queue_item.ext2 = ''
        queue_item.ext3 = ''
        queue_item.ext4 = ''

        gui_parent.queue_manager.get_item = Mock(return_value=queue_item)

        # Also shield combo access
        gui_parent.thumbnail_size_combo = Mock(side_effect=RuntimeError("Widget access off thread!"))
        gui_parent.thumbnail_format_combo = Mock(side_effect=RuntimeError("Widget access off thread!"))

        path = "/test/gallery"
        results = {
            'gallery_id': 'test_id',
            'gallery_name': 'TestGallery',
            'images': [
                {'image_url': 'http://example.com/img.jpg', 'bbcode': '[img]test[/img]'}
            ],
            'failed_details': [],
            'total_size': 1000,
            'avg_width': 800,
            'avg_height': 600,
            'max_width': 1000,
            'max_height': 900,
            'min_width': 100,
            'min_height': 100,
        }

        ui_settings = {'thumbnail_size': 2, 'thumbnail_format': 3}

        with patch('src.storage.gallery_management.save_unnamed_gallery'):
            with patch('src.storage.gallery_management.get_unnamed_galleries', return_value={}):
                with patch('src.storage.gallery_management.check_gallery_renamed', return_value=True):
                    with patch('src.utils.templates.save_gallery_artifacts', return_value={'central': {}, 'uploaded': {}}) as mock_save:
                        with patch('src.utils.paths.load_user_defaults', return_value={}):
                            # Should NOT access items dict and should NOT raise
                            self.worker._process_completion_background(path, results, gui_parent, ui_settings)

                            # Verify started_at was computed from queue_item.start_time
                            mock_save.assert_called_once()
                            call_args = mock_save.call_args
                            results_arg = call_args[1]['results']

                            # Should have started_at from the cached queue_item
                            self.assertIsNotNone(results_arg['started_at'])
                            self.assertEqual(results_arg['started_at'], '2026-06-24 10:30:45')

    def test_run_unpacks_four_tuple_from_queue(self):
        """Verify run() correctly unpacks 4-tuple and calls _process_completion_background with ui_settings."""
        # Prepare a 4-tuple item
        path = "/test/gallery"
        results = {'gallery_id': 'test_id', 'gallery_name': 'TestGallery'}
        gui_parent = Mock()
        ui_settings = {'thumbnail_size': 2, 'thumbnail_format': 3}

        # Put the item into the queue manually
        self.worker.completion_queue.put((path, results, gui_parent, ui_settings))
        self.worker.completion_queue.put(None)  # Stop signal

        # Mock the processing method
        with patch.object(self.worker, '_process_completion_background') as mock_process:
            self.worker.run()

            # Verify it was called with the 4-tuple unpacked
            mock_process.assert_called_once_with(path, results, gui_parent, ui_settings)

    def test_process_completion_handles_exception_safely(self):
        """Verify process_completion handles combo read exceptions gracefully."""
        gui_parent = Mock()
        gui_parent.thumbnail_size_combo = Mock(side_effect=Exception("Widget error"))
        gui_parent.thumbnail_format_combo = Mock(side_effect=Exception("Widget error"))
        gui_parent.queue_manager = Mock()

        path = "/test/gallery"
        results = {'gallery_id': 'test_id', 'gallery_name': 'test'}

        # This should not raise; instead ui_settings should have defaults
        self.worker.process_completion(path, results, gui_parent)

        item = self.worker.completion_queue.get(timeout=1.0)
        queued_path, queued_results, queued_gui_parent, queued_ui_settings = item

        # When exception occurs, ui_settings should be empty or have safe defaults
        self.assertIsInstance(queued_ui_settings, dict)


if __name__ == '__main__':
    unittest.main()
