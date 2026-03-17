"""Tests for LinkScannerDashboard — the redesigned splitter-based dashboard."""

import os
import pytest
from unittest.mock import MagicMock

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
