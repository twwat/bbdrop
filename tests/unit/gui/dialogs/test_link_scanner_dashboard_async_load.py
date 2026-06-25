"""Tests for LinkScannerDashboard async gallery table loading (off the GUI thread)."""

import os
import pytest
from unittest.mock import MagicMock, patch, call

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class TestAsyncGalleryTableLoad:
    """Test that _reload_gallery_table loads gallery data off the GUI thread."""

    @pytest.fixture
    def mock_store(self):
        store = MagicMock()
        store.get_hosts_with_uploads.return_value = {
            ('image', 'imx'): {'gallery_count': 10, 'image_count': 100},
            ('image', 'turbo'): {'gallery_count': 5, 'image_count': 50},
        }
        store.get_galleries_for_dashboard.return_value = [
            {'host_id': 'imx', 'name': 'gallery1'},
            {'host_id': 'turbo', 'name': 'gallery2'},
            {'host_id': 'imx', 'name': 'gallery3'},
        ]
        store.get_scan_stats_by_host.return_value = {}
        return store

    @pytest.fixture
    def mock_queue_manager(self, mock_store):
        qm = MagicMock()
        qm.store = mock_store
        return qm

    @pytest.fixture
    def dashboard(self, qtbot, mock_queue_manager):
        from src.gui.dialogs.link_scanner_dashboard import LinkScannerDashboard
        dlg = LinkScannerDashboard(parent=None, queue_manager=mock_queue_manager)
        qtbot.addWidget(dlg)
        return dlg

    def test_reload_gallery_table_schedules_work_not_sync_query(self, dashboard, mock_queue_manager):
        """_reload_gallery_table should schedule work via QThreadPool, not call get_galleries_for_dashboard synchronously."""
        mock_queue_manager.store.get_galleries_for_dashboard.reset_mock()

        with patch('PyQt6.QtCore.QThreadPool.globalInstance') as mock_pool:
            mock_pool_instance = MagicMock()
            mock_pool.return_value = mock_pool_instance

            # Call _reload_gallery_table
            dashboard._reload_gallery_table('imx')

            # The store method should NOT be called synchronously in this thread
            mock_queue_manager.store.get_galleries_for_dashboard.assert_not_called()

            # QThreadPool.start should have been called
            mock_pool_instance.start.assert_called_once()

    def test_reload_gallery_table_clears_table_immediately(self, dashboard):
        """_reload_gallery_table should clear the gallery table immediately."""
        mock_gallery_table = MagicMock()
        dashboard._gallery_table = mock_gallery_table
        mock_gallery_table.clear_rows = MagicMock()

        with patch('PyQt6.QtCore.QThreadPool.globalInstance'):
            dashboard._reload_gallery_table('imx')

        # clear_rows should have been called immediately
        mock_gallery_table.clear_rows.assert_called_once()

    def test_on_gallery_data_loaded_ignores_stale_generation(self, dashboard):
        """_on_gallery_data_loaded should ignore results from older generations."""
        dashboard._gallery_load_gen = 5
        mock_gallery_table = MagicMock()
        dashboard._gallery_table = mock_gallery_table

        # Call with gen=3 (stale)
        dashboard._on_gallery_data_loaded(gen=3, host_id='imx', rows=[
            {'host_id': 'imx', 'name': 'gallery1'},
        ])

        # load_results should NOT be called
        mock_gallery_table.load_results.assert_not_called()

    def test_on_gallery_data_loaded_accepts_current_generation(self, dashboard):
        """_on_gallery_data_loaded should accept results from the current generation."""
        dashboard._gallery_load_gen = 5
        mock_gallery_table = MagicMock()
        dashboard._gallery_table = mock_gallery_table

        rows = [
            {'host_id': 'imx', 'name': 'gallery1'},
            {'host_id': 'imx', 'name': 'gallery2'},
        ]

        # Call with gen=5 (current)
        dashboard._on_gallery_data_loaded(gen=5, host_id='imx', rows=rows)

        # load_results should be called with the rows
        mock_gallery_table.load_results.assert_called_once_with(rows)

    def test_on_gallery_data_loaded_filters_by_host_id(self, dashboard):
        """_on_gallery_data_loaded should filter rows by host_id before passing to load_results."""
        dashboard._gallery_load_gen = 1
        mock_gallery_table = MagicMock()
        dashboard._gallery_table = mock_gallery_table

        rows = [
            {'host_id': 'imx', 'name': 'gallery1'},
            {'host_id': 'turbo', 'name': 'gallery2'},
            {'host_id': 'imx', 'name': 'gallery3'},
        ]

        # Call with gen=1 (current), host_id='imx'
        dashboard._on_gallery_data_loaded(gen=1, host_id='imx', rows=rows)

        # load_results should be called with only imx rows
        expected_filtered = [
            {'host_id': 'imx', 'name': 'gallery1'},
            {'host_id': 'imx', 'name': 'gallery3'},
        ]
        mock_gallery_table.load_results.assert_called_once_with(expected_filtered)

    def test_reload_gallery_table_emits_loaded_signal_async(self, qtbot, dashboard, mock_queue_manager):
        """When _reload_gallery_table is called, it should eventually emit loaded signal with filtered results."""
        mock_gallery_table = MagicMock()
        dashboard._gallery_table = mock_gallery_table

        # Wait for the loaded signal
        with qtbot.waitSignal(dashboard._gallery_load_signals.loaded, timeout=2000):
            dashboard._reload_gallery_table('imx')

        # After the signal fires, load_results should have been called with filtered rows
        # (The slot _on_gallery_data_loaded is connected via Qt.QueuedConnection,
        #  so it runs on the GUI thread after the signal is emitted.)
        mock_gallery_table.load_results.assert_called()

    def test_reload_gallery_table_handles_get_galleries_exception(self, qtbot, dashboard, mock_queue_manager):
        """If get_galleries_for_dashboard raises an exception, async task should log it and emit empty rows."""
        mock_queue_manager.store.get_galleries_for_dashboard.side_effect = RuntimeError("DB error")
        mock_gallery_table = MagicMock()
        dashboard._gallery_table = mock_gallery_table

        with patch('src.gui.dialogs.link_scanner_dashboard.log') as mock_log:
            with qtbot.waitSignal(dashboard._gallery_load_signals.loaded, timeout=2000):
                dashboard._reload_gallery_table('imx')

            # The async task should have called log with error level
            error_calls = [c for c in mock_log.call_args_list if c[1].get('level') == 'error']
            assert len(error_calls) > 0, "Expected error log when get_galleries_for_dashboard fails"

            # load_results should be called with empty list (filtered from empty rows)
            mock_gallery_table.load_results.assert_called()
            call_args = mock_gallery_table.load_results.call_args[0][0]
            assert call_args == [], f"Expected empty list after exception, got {call_args}"

    def test_reload_gallery_table_increments_generation(self, dashboard):
        """_reload_gallery_table should increment the generation counter on each call."""
        gen_before = dashboard._gallery_load_gen

        with patch('PyQt6.QtCore.QThreadPool.globalInstance'):
            dashboard._reload_gallery_table('imx')

        assert dashboard._gallery_load_gen == gen_before + 1

    def test_multiple_reloads_only_latest_results_applied(self, qtbot, dashboard, mock_queue_manager):
        """If multiple _reload_gallery_table calls are made before results come back,
        only the latest generation's result should be applied."""
        mock_gallery_table = MagicMock()
        dashboard._gallery_table = mock_gallery_table

        # Manually set generation to 1 to simulate first reload
        dashboard._gallery_load_gen = 1
        gen1 = 1
        gen2 = 2

        # Apply gen2 result (newer) first
        dashboard._gallery_load_gen = gen2  # Simulate second reload incrementing generation
        dashboard._on_gallery_data_loaded(gen=gen2, host_id='imx', rows=[{'host_id': 'imx', 'name': 'new'}])
        assert mock_gallery_table.load_results.call_count == 1

        # Then apply gen1 result (older) — should be ignored
        dashboard._on_gallery_data_loaded(gen=gen1, host_id='imx', rows=[{'host_id': 'imx', 'name': 'old'}])

        # load_results should still only have been called once (not twice)
        assert mock_gallery_table.load_results.call_count == 1
        # And it should still be the new result
        call_args = mock_gallery_table.load_results.call_args[0][0]
        assert call_args[0]['name'] == 'new'
