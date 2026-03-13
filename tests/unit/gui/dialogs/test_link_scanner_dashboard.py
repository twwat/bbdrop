"""Tests for LinkScannerDashboard — the assembled dashboard dialog."""

import os
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt


class TestLinkScannerDashboard:
    """Tests for the assembled dashboard dialog."""

    @pytest.fixture
    def mock_store(self):
        store = MagicMock()
        store.get_scan_stats_by_host.return_value = {
            ('image', 'imx'): {
                'total_galleries': 100,
                'online_galleries': 80,
                'partial_galleries': 15,
                'offline_galleries': 5,
                'total_online': 900,
                'total_items': 1000,
            },
            ('image', 'turbo'): {
                'total_galleries': 50,
                'online_galleries': 48,
                'partial_galleries': 2,
                'offline_galleries': 0,
                'total_online': 490,
                'total_items': 500,
            },
        }
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

    def test_summary_cards_created(self, dashboard):
        assert len(dashboard._summary_cards) == 2
        assert 'imx' in dashboard._summary_cards
        assert 'turbo' in dashboard._summary_cards

    def test_controls_visible_initially(self, dashboard):
        assert dashboard._control_stack.currentWidget() == dashboard._controls

    def test_scan_requested_starts_coordinator(self, dashboard, qtbot):
        dashboard._coordinator = MagicMock()
        dashboard._on_scan_requested(30, '', 'age')
        dashboard._coordinator.start_scan.assert_called_once()

    def test_scan_switches_to_progress_view(self, dashboard):
        dashboard._coordinator = MagicMock()
        dashboard._on_scan_requested(30, '', 'age')
        assert dashboard._control_stack.currentWidget() == dashboard._progress

    def test_stop_cancels_coordinator(self, dashboard):
        dashboard._coordinator = MagicMock()
        dashboard._on_stop_requested()
        dashboard._coordinator.cancel.assert_called_once()

    def test_scan_complete_switches_back_to_controls(self, dashboard):
        dashboard._coordinator = MagicMock()
        dashboard._on_scan_requested(30, '', 'age')
        assert dashboard._control_stack.currentWidget() == dashboard._progress
        dashboard._on_scan_complete({'total_hosts': 2, 'total_galleries': 10, 'elapsed': 5.0})
        assert dashboard._control_stack.currentWidget() == dashboard._controls

    def test_card_click_activates_results_tab(self, dashboard):
        dashboard._results_tabs.update_result('imx', 'Gallery A', 10, 10, '2026-03-10')
        dashboard._results_tabs.update_result('turbo', 'Gallery B', 5, 5, '2026-03-10')
        dashboard._on_host_card_clicked('turbo')
        assert dashboard._results_tabs.currentIndex() == 1

    def test_no_store_shows_empty(self, qtbot):
        from src.gui.dialogs.link_scanner_dashboard import LinkScannerDashboard
        dlg = LinkScannerDashboard(parent=None, queue_manager=None)
        qtbot.addWidget(dlg)
        assert len(dlg._summary_cards) == 0

    def test_progress_callback_updates_widgets(self, dashboard):
        dashboard._on_scan_progress('image', 'imx', 25, 100)
        assert 'imx' in dashboard._progress._host_bars
