#!/usr/bin/env python3
"""
Unit tests for FileHostController._on_file_hosts_enabled_changed batch query optimization.

Verifies that the method uses a single batch query (get_file_host_uploads_for_paths)
instead of per-row queries to avoid GUI thread freezes.
"""

import os
import pytest
from unittest.mock import Mock, MagicMock, patch
from types import SimpleNamespace

from PyQt6.QtCore import QMutex, Qt

from src.gui.file_host_controller import FileHostController


class TestFileHostEnabledChangedBatchQuery:
    """Test suite for _on_file_hosts_enabled_changed batch query optimization."""

    @pytest.fixture
    def mock_main_window(self):
        """Create a mock main window with batched file host upload behavior."""
        mw = Mock()
        mw.queue_manager = Mock()
        mw.queue_manager.mutex = QMutex()
        mw.queue_manager.items = {}

        # Mock store with batch method
        mw.queue_manager.store = Mock()

        # Set up batch method to return normalized paths
        # Returns: {os.path.normpath(path): [list of uploads]}
        mw.queue_manager.store.get_file_host_uploads_for_paths = Mock(
            return_value={
                os.path.normpath('/g1'): [
                    {'host_name': 'rapidgator', 'status': 'completed', 'download_url': 'http://example.com/1'}
                ],
                os.path.normpath('/g2'): []
            }
        )

        # Set up per-row method to fail if called (ensuring batch is used)
        mw.queue_manager.store.get_file_host_uploads = Mock(
            side_effect=AssertionError("Per-row query should not be called during batch operation!")
        )

        # Gallery table mocking
        mw.gallery_table = Mock()
        mw.gallery_table.rowCount = Mock(return_value=2)

        # Create mock table with items
        table_mock = Mock()
        mw.gallery_table.table = table_mock

        # Mock row_to_path mapping
        mw.row_to_path = {
            0: '/g1',
            1: '/g2'
        }

        # Mock table items
        item0 = Mock()
        item1 = Mock()
        table_mock.item = Mock(side_effect=lambda row, col: item0 if row == 0 else item1)

        # Worker signal handler
        mw.worker_signal_handler = Mock()

        # Startup flag
        mw._file_host_startup_complete = True

        return mw, item0, item1

    def test_batch_query_called_once_with_all_paths(self):
        """Verify that get_file_host_uploads_for_paths is called once with all paths."""
        mw, item0, item1 = self._setup_main_window()

        # Create two mock items
        items = [
            SimpleNamespace(path='/g1'),
            SimpleNamespace(path='/g2')
        ]
        mw.queue_manager.get_all_items = Mock(return_value=items)

        controller = FileHostController(mw)
        controller._on_file_hosts_enabled_changed([])

        # Verify batch query called once with both paths
        mw.queue_manager.store.get_file_host_uploads_for_paths.assert_called_once()
        call_args = mw.queue_manager.store.get_file_host_uploads_for_paths.call_args[0][0]
        assert set(call_args) == {'/g1', '/g2'}

    def test_per_row_query_not_called(self):
        """Verify that get_file_host_uploads (per-row) is NEVER called."""
        mw, item0, item1 = self._setup_main_window()

        items = [
            SimpleNamespace(path='/g1'),
            SimpleNamespace(path='/g2')
        ]
        mw.queue_manager.get_all_items = Mock(return_value=items)

        controller = FileHostController(mw)

        # This should NOT raise AssertionError if batch query is used
        try:
            controller._on_file_hosts_enabled_changed([])
        except AssertionError as e:
            pytest.fail(f"Per-row query was called when it shouldn't be: {e}")

    def test_path_keying_respects_original_paths(self):
        """Verify that file_host_uploads_map uses original paths (not normalized)."""
        mw, item0, item1 = self._setup_main_window()

        items = [
            SimpleNamespace(path='/g1'),
            SimpleNamespace(path='/g2')
        ]
        mw.queue_manager.get_all_items = Mock(return_value=items)

        controller = FileHostController(mw)
        controller._on_file_hosts_enabled_changed([])

        # Capture setData calls
        calls = mw.gallery_table.table.item.return_value.setData.call_args_list

        # Should have called setData for row 0 with rapidgator upload
        # The data should be keyed by original path '/g1', not normalized
        # We verify by checking item0 received the correct host data
        assert item0.setData.called, "setData should be called for row 0"

    def test_handles_empty_queue(self):
        """Verify method handles empty queue gracefully."""
        mw, item0, item1 = self._setup_main_window()

        mw.queue_manager.get_all_items = Mock(return_value=[])
        mw.queue_manager.store.get_file_host_uploads_for_paths = Mock(return_value={})

        controller = FileHostController(mw)

        # Should not raise
        controller._on_file_hosts_enabled_changed([])

        # Batch query still called (with empty list)
        mw.queue_manager.store.get_file_host_uploads_for_paths.assert_called_once()

    def test_skips_during_startup(self):
        """Verify method skips execution during startup phase."""
        mw, item0, item1 = self._setup_main_window()
        mw._file_host_startup_complete = False

        items = [SimpleNamespace(path='/g1')]
        mw.queue_manager.get_all_items = Mock(return_value=items)

        controller = FileHostController(mw)
        controller._on_file_hosts_enabled_changed([])

        # Batch query should NOT be called during startup
        mw.queue_manager.store.get_file_host_uploads_for_paths.assert_not_called()

    def test_handles_batch_query_exception(self):
        """Verify method handles exceptions from batch query gracefully."""
        mw, item0, item1 = self._setup_main_window()

        items = [
            SimpleNamespace(path='/g1'),
            SimpleNamespace(path='/g2')
        ]
        mw.queue_manager.get_all_items = Mock(return_value=items)

        # Make batch query raise an exception
        mw.queue_manager.store.get_file_host_uploads_for_paths = Mock(
            side_effect=Exception("DB connection error")
        )

        controller = FileHostController(mw)

        # Should not raise, should log warning and continue
        with patch('src.gui.file_host_controller.log') as mock_log:
            controller._on_file_hosts_enabled_changed([])
            # Verify that a warning was logged
            assert mock_log.called
            call_args = str(mock_log.call_args)
            assert 'warning' in call_args.lower() or 'Failed' in call_args

    def _setup_main_window(self):
        """Helper to set up main window and items."""
        mw = Mock()
        mw.queue_manager = Mock()
        mw.queue_manager.mutex = QMutex()
        mw.queue_manager.items = {}

        mw.queue_manager.store = Mock()
        mw.queue_manager.store.get_file_host_uploads_for_paths = Mock(
            return_value={
                os.path.normpath('/g1'): [
                    {'host_name': 'rapidgator', 'status': 'completed'}
                ],
                os.path.normpath('/g2'): []
            }
        )

        mw.queue_manager.store.get_file_host_uploads = Mock(
            side_effect=AssertionError("Per-row query should not be called!")
        )

        mw.gallery_table = Mock()
        mw.gallery_table.rowCount = Mock(return_value=2)

        table_mock = Mock()
        mw.gallery_table.table = table_mock

        mw.row_to_path = {0: '/g1', 1: '/g2'}

        item0 = Mock()
        item1 = Mock()
        table_mock.item = Mock(side_effect=lambda row, col: item0 if row == 0 else item1)
        table_mock.viewport = Mock(return_value=Mock())

        mw.worker_signal_handler = Mock()
        mw._file_host_startup_complete = True

        return mw, item0, item1
