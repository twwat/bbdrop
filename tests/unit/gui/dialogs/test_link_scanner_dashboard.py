"""Tests for LinkScannerDashboard — the redesigned splitter-based dashboard."""

import os
import pytest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class TestLinkScannerDashboard:

    @pytest.fixture
    def mock_store(self):
        store = MagicMock()
        store.get_hosts_with_uploads.return_value = {
            ('image', 'imx'): {'gallery_count': 10, 'image_count': 100},
            ('image', 'turbo'): {'gallery_count': 5, 'image_count': 50},
        }
        store.get_galleries_for_dashboard.return_value = []
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

    def test_creates_without_error(self, dashboard):
        assert dashboard is not None

    def test_is_non_modal(self, dashboard):
        assert not dashboard.isModal()

    def test_has_host_table(self, dashboard):
        from src.gui.widgets.scanner_widgets import HostTableWidget
        assert isinstance(dashboard._host_table, HostTableWidget)

    def test_has_gallery_table(self, dashboard):
        from src.gui.widgets.scanner_widgets import GalleryResultsTable
        assert isinstance(dashboard._gallery_table, GalleryResultsTable)

    def test_host_table_populated(self, dashboard):
        assert dashboard._host_table.rowCount() == 2

    def test_has_controls(self, dashboard):
        from src.gui.widgets.scanner_widgets import ScanControlsWidget
        assert isinstance(dashboard._controls, ScanControlsWidget)

    def test_progress_bar_hidden_initially(self, dashboard):
        assert not dashboard._overall_bar.isVisible()

    def test_has_header_text(self, dashboard):
        assert dashboard._header_label.text() != ''

    def test_no_host_selected_initially(self, dashboard):
        assert dashboard._host_table.get_selected_host_id() is None
        assert dashboard._controls.get_host_filter() == ''
        assert dashboard._gallery_table.rowCount() == 0

    def test_host_click_syncs_dropdown(self, dashboard):
        dashboard._host_table.selectRow(1)
        assert dashboard._controls.get_host_filter() == 'turbo'

    def test_scan_requested_starts_coordinator(self, dashboard):
        dashboard._coordinator = MagicMock()
        dashboard._controls.scan_requested.emit(30, '', 'age', 'last_scan')
        dashboard._coordinator.start_scan.assert_called_once()

    def test_stop_cancels_coordinator(self, dashboard):
        dashboard._coordinator = MagicMock()
        dashboard._on_stop_requested()
        dashboard._coordinator.cancel.assert_called_once()

    def test_wider_than_old_dialog(self, dashboard):
        assert dashboard.minimumWidth() >= 750

    def test_close_event_cancels_scan_and_waits(self, qtbot, dashboard, mock_queue_manager):
        """BUG A: closeEvent should cancel any running scan before the dialog is destroyed."""
        from PyQt6.QtGui import QCloseEvent

        # Mock the coordinator with a running scan
        dashboard._coordinator = MagicMock()
        dashboard._coordinator.is_scanning = True
        dashboard._coordinator.wait.return_value = True

        # Trigger closeEvent
        dashboard.closeEvent(QCloseEvent())

        # Assert cancel and wait were called
        dashboard._coordinator.cancel.assert_called_once()
        dashboard._coordinator.wait.assert_called_once()
        # Check that wait was called with a timeout
        call_args = dashboard._coordinator.wait.call_args
        assert call_args[1]['timeout'] == 5.0 or call_args[0][0] == 5.0

    def test_close_event_no_coordinator(self, qtbot, dashboard):
        """closeEvent should not crash if coordinator is None."""
        from PyQt6.QtGui import QCloseEvent
        dashboard._coordinator = None

        # Should not raise
        dashboard.closeEvent(QCloseEvent())

        # Verify no cancel/wait were attempted since there's no coordinator
        # (This is a simple sanity check that closeEvent completes successfully)
        assert dashboard._coordinator is None

    def test_load_initial_data_logs_scan_stats_error(self, qtbot, mock_queue_manager):
        """FIX 1: _load_initial_data should log error when get_scan_stats_by_host() fails."""
        from src.gui.dialogs.link_scanner_dashboard import LinkScannerDashboard

        # Make get_scan_stats_by_host raise an exception
        mock_queue_manager.store.get_scan_stats_by_host.side_effect = RuntimeError("DB connection failed")

        with patch('src.gui.dialogs.link_scanner_dashboard.log') as mock_log:
            # Construct the dashboard — this calls _load_initial_data
            dlg = LinkScannerDashboard(parent=None, queue_manager=mock_queue_manager)
            qtbot.addWidget(dlg)

            # Assert that log was called with error level for the scan stats failure
            # Look for the error log call about scan stats
            error_calls = [call for call in mock_log.call_args_list
                          if call[1].get('level') == 'error']
            assert len(error_calls) > 0, "No error log call found for scan stats failure"

            # Check that one of the error logs mentions scan stats
            found_scan_stats_error = any(
                'scan' in str(call[0][0]).lower() or 'stats' in str(call[0][0]).lower()
                for call in error_calls
            )
            assert found_scan_stats_error, f"Expected scan/stats error log, but got: {error_calls}"

    def test_close_event_scanner_not_running(self, qtbot, dashboard):
        """closeEvent should not call wait if scanner is not running."""
        from PyQt6.QtGui import QCloseEvent

        dashboard._coordinator = MagicMock()
        dashboard._coordinator.is_scanning = False

        dashboard.closeEvent(QCloseEvent())

        # cancel and wait should NOT be called
        dashboard._coordinator.cancel.assert_not_called()
        dashboard._coordinator.wait.assert_not_called()

    def test_reload_gallery_table_logs_error_on_db_failure(self, dashboard, mock_queue_manager):
        """BUG B: _reload_gallery_table should log errors instead of silently swallowing them."""
        mock_queue_manager.store.get_galleries_for_dashboard.side_effect = RuntimeError("DB connection failed")

        with patch('src.gui.dialogs.link_scanner_dashboard.log') as mock_log:
            dashboard._reload_gallery_table('imx')

            # Assert log was called with error level
            mock_log.assert_called()
            call_args = mock_log.call_args
            # Should log with level="error"
            assert call_args[1]['level'] == 'error'
            assert 'Failed to reload gallery table' in call_args[0][0]
