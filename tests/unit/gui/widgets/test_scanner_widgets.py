#!/usr/bin/env python3
"""
Tests for scanner UI widgets used by the LinkScannerDashboard.

Covers:
- HostSummaryCard: compact per-host status card with health bar
- ScanControlsWidget: age/host filter dropdowns and scan buttons
- ScanProgressWidget: overall + per-host progress bars with stop
- HostResultsTabWidget: per-host sortable result tables
"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from unittest.mock import MagicMock
from PyQt6.QtTest import QSignalSpy


# ============================================================================
# HostSummaryCard Tests (Task 9)
# ============================================================================

class TestHostSummaryCard:

    @pytest.fixture
    def card(self, qtbot):
        from src.gui.widgets.scanner_widgets import HostSummaryCard
        card = HostSummaryCard(host_id='imx', host_label='IMX')
        qtbot.addWidget(card)
        return card

    def test_initial_state(self, card):
        assert card._host_id == 'imx'
        assert card._label.text() == 'IMX'
        assert card._count_label.text() == '0'
        assert card._pct_label.text() == '--'

    def test_update_stats_all_online(self, qtbot):
        from src.gui.widgets.scanner_widgets import HostSummaryCard
        card = HostSummaryCard(host_id='turbo', host_label='Turbo')
        qtbot.addWidget(card)
        card.update_stats(total_galleries=50, online_items=200, total_items=200)
        assert card._count_label.text() == '50'
        assert card._pct_label.text() == '100%'

    def test_update_stats_partial(self, qtbot):
        from src.gui.widgets.scanner_widgets import HostSummaryCard
        card = HostSummaryCard(host_id='imx', host_label='IMX')
        qtbot.addWidget(card)
        card.update_stats(total_galleries=100, online_items=190, total_items=200)
        assert card._pct_label.text() == '95%'

    def test_update_stats_zero_total(self, qtbot):
        from src.gui.widgets.scanner_widgets import HostSummaryCard
        card = HostSummaryCard(host_id='imx', host_label='IMX')
        qtbot.addWidget(card)
        card.update_stats(total_galleries=0, online_items=0, total_items=0)
        assert card._pct_label.text() == '--'

    def test_click_emits_signal(self, card, qtbot):
        spy = QSignalSpy(card.host_clicked)
        card.mousePressEvent(MagicMock())
        assert len(spy) == 1
        assert spy[0][0] == 'imx'

    def test_color_coding_healthy(self, qtbot):
        from src.gui.widgets.scanner_widgets import HostSummaryCard
        card = HostSummaryCard(host_id='imx', host_label='IMX')
        qtbot.addWidget(card)
        card.update_stats(total_galleries=10, online_items=95, total_items=100)
        assert card._bar.value() == 95

    def test_color_coding_problems(self, qtbot):
        from src.gui.widgets.scanner_widgets import HostSummaryCard
        card = HostSummaryCard(host_id='k2s', host_label='K2S')
        qtbot.addWidget(card)
        card.update_stats(total_galleries=10, online_items=30, total_items=100)
        assert card._bar.value() == 30

    def test_color_coding_unchecked(self, qtbot):
        from src.gui.widgets.scanner_widgets import HostSummaryCard
        card = HostSummaryCard(host_id='rg', host_label='RG')
        qtbot.addWidget(card)
        card.update_stats(total_galleries=5, online_items=0, total_items=0)
        assert card._bar.value() == 0


# ============================================================================
# ScanControlsWidget Tests (Task 10)
# ============================================================================

class TestScanControlsWidget:

    @pytest.fixture
    def controls(self, qtbot):
        from src.gui.widgets.scanner_widgets import ScanControlsWidget
        widget = ScanControlsWidget()
        qtbot.addWidget(widget)
        return widget

    def test_initial_state(self, controls):
        assert controls._age_combo.count() == 5
        assert controls._age_combo.currentText() == '30+ days'
        assert controls._host_combo.count() == 1
        assert controls._start_btn.isEnabled()
        assert controls._unchecked_btn.isEnabled()
        assert controls._problems_btn.isEnabled()

    def test_set_hosts(self, qtbot):
        from src.gui.widgets.scanner_widgets import ScanControlsWidget
        widget = ScanControlsWidget()
        qtbot.addWidget(widget)
        widget.set_hosts(['imx', 'turbo', 'rapidgator'])
        assert widget._host_combo.count() == 4
        assert widget._host_combo.itemText(0) == 'All hosts'
        assert widget._host_combo.itemText(1) == 'imx'

    def test_start_scan_emits_age_type(self, controls, qtbot):
        spy = QSignalSpy(controls.scan_requested)
        controls._start_btn.click()
        assert len(spy) == 1
        age_days, host_filter, scan_type = spy[0]
        assert age_days == 30
        assert host_filter == ''
        assert scan_type == 'age'

    def test_unchecked_emits_unchecked_type(self, controls, qtbot):
        spy = QSignalSpy(controls.scan_requested)
        controls._age_combo.setCurrentIndex(0)
        controls._unchecked_btn.click()
        assert len(spy) == 1
        age_days, host_filter, scan_type = spy[0]
        assert age_days == 0
        assert scan_type == 'unchecked'

    def test_problems_emits_problems_type(self, controls, qtbot):
        spy = QSignalSpy(controls.scan_requested)
        controls._problems_btn.click()
        assert len(spy) == 1
        age_days, host_filter, scan_type = spy[0]
        assert age_days == 0
        assert scan_type == 'problems'

    def test_host_filter_passed_through(self, controls, qtbot):
        controls.set_hosts(['imx', 'turbo'])
        controls._host_combo.setCurrentIndex(1)
        spy = QSignalSpy(controls.scan_requested)
        controls._start_btn.click()
        assert len(spy) == 1
        _, host_filter, _ = spy[0]
        assert host_filter == 'imx'

    def test_age_dropdown_values(self, controls):
        expected_days = [7, 14, 30, 60, 90]
        for i, days in enumerate(expected_days):
            assert controls._age_combo.itemData(i) == days

    def test_set_enabled(self, controls):
        controls.set_enabled(False)
        assert not controls._start_btn.isEnabled()
        assert not controls._unchecked_btn.isEnabled()
        assert not controls._problems_btn.isEnabled()
        assert not controls._age_combo.isEnabled()
        assert not controls._host_combo.isEnabled()


# ============================================================================
# ScanProgressWidget Tests (Task 11)
# ============================================================================

class TestScanProgressWidget:

    @pytest.fixture
    def progress(self, qtbot):
        from src.gui.widgets.scanner_widgets import ScanProgressWidget
        widget = ScanProgressWidget()
        qtbot.addWidget(widget)
        return widget

    def test_initial_state(self, progress):
        assert progress._status_label.text() == 'Scanning...'
        assert progress._stop_btn.isEnabled()
        assert progress._overall_bar.value() == 0

    def test_set_overall_progress(self, progress):
        progress.set_overall(156, 342)
        assert progress._overall_bar.value() == 156
        assert progress._overall_bar.maximum() == 342
        assert '156/342' in progress._overall_count.text()
        assert '46%' in progress._overall_count.text()

    def test_update_host_progress_creates_bar(self, progress):
        progress.update_progress('imx', 10, 50)
        assert 'imx' in progress._host_bars
        bar, label = progress._host_bars['imx']
        assert bar.value() == 10
        assert bar.maximum() == 50

    def test_update_host_progress_updates_existing(self, progress):
        progress.update_progress('turbo', 5, 100)
        progress.update_progress('turbo', 45, 100)
        assert len(progress._host_bars) == 1
        bar, label = progress._host_bars['turbo']
        assert bar.value() == 45

    def test_multiple_hosts_layout(self, progress):
        progress.update_progress('imx', 10, 50)
        progress.update_progress('turbo', 20, 60)
        progress.update_progress('k2s', 3, 98)
        assert len(progress._host_bars) == 3

    def test_stop_emits_signal(self, progress, qtbot):
        spy = QSignalSpy(progress.stop_requested)
        progress._stop_btn.click()
        assert len(spy) == 1

    def test_reset_clears_everything(self, progress):
        progress.set_overall(100, 200)
        progress.update_progress('imx', 50, 100)
        progress.update_progress('turbo', 30, 60)
        progress.reset()
        assert progress._overall_bar.value() == 0
        assert progress._overall_count.text() == ''
        assert len(progress._host_bars) == 0

    def test_set_overall_zero_total(self, progress):
        progress.set_overall(0, 0)
        assert progress._overall_bar.value() == 0

    def test_stop_button_disabled_after_click(self, progress, qtbot):
        progress._stop_btn.click()
        assert not progress._stop_btn.isEnabled()


# ============================================================================
# HostResultsTabWidget Tests (Task 12)
# ============================================================================

class TestHostResultsTabWidget:

    @pytest.fixture
    def tabs(self, qtbot):
        from src.gui.widgets.scanner_widgets import HostResultsTabWidget
        widget = HostResultsTabWidget()
        qtbot.addWidget(widget)
        return widget

    def test_initial_state_empty(self, tabs):
        assert tabs.count() == 0

    def test_update_result_creates_tab(self, tabs):
        tabs.update_result('imx', 'Gallery A', 10, 10, '2026-03-10 14:00')
        assert tabs.count() == 1
        assert tabs.tabText(0).upper() == 'IMX'

    def test_update_result_adds_row(self, tabs):
        tabs.update_result('imx', 'Gallery A', 10, 10, '2026-03-10 14:00')
        tabs.update_result('imx', 'Gallery B', 7, 10, '2026-03-10 14:00')
        assert tabs.count() == 1
        table = tabs.widget(0)
        assert table.rowCount() == 2

    def test_update_result_updates_existing_row(self, tabs):
        tabs.update_result('imx', 'Gallery A', 10, 10, '2026-03-10 14:00')
        tabs.update_result('imx', 'Gallery A', 8, 10, '2026-03-11 15:00')
        table = tabs.widget(0)
        assert table.rowCount() == 1
        status_item = table.item(0, 1)
        assert '8/10' in status_item.text()

    def test_multiple_hosts_separate_tabs(self, tabs):
        tabs.update_result('imx', 'Gallery A', 10, 10, '2026-03-10 14:00')
        tabs.update_result('turbo', 'Gallery B', 5, 5, '2026-03-10 14:00')
        tabs.update_result('rapidgator', 'Gallery C', 3, 3, '2026-03-10 14:00')
        assert tabs.count() == 3

    def test_status_format_all_online(self, tabs):
        tabs.update_result('imx', 'Gallery A', 10, 10, '2026-03-10 14:00')
        table = tabs.widget(0)
        assert table.item(0, 1).text() == '10/10'

    def test_status_format_partial(self, tabs):
        tabs.update_result('imx', 'Gallery A', 7, 10, '2026-03-10 14:00')
        table = tabs.widget(0)
        assert table.item(0, 1).text() == '7/10'

    def test_status_format_offline(self, tabs):
        tabs.update_result('imx', 'Gallery A', 0, 10, '2026-03-10 14:00')
        table = tabs.widget(0)
        assert table.item(0, 1).text() == '0/10'

    def test_sorting_enabled(self, tabs):
        tabs.update_result('imx', 'Gallery A', 10, 10, '2026-03-10 14:00')
        table = tabs.widget(0)
        assert table.isSortingEnabled()

    def test_activate_host_tab(self, tabs):
        tabs.update_result('imx', 'Gallery A', 10, 10, '2026-03-10 14:00')
        tabs.update_result('turbo', 'Gallery B', 5, 5, '2026-03-10 14:00')
        tabs.activate_host('turbo')
        assert tabs.currentIndex() == 1

    def test_clear_all(self, tabs):
        tabs.update_result('imx', 'Gallery A', 10, 10, '2026-03-10')
        tabs.update_result('turbo', 'Gallery B', 5, 5, '2026-03-10')
        tabs.clear_all()
        assert tabs.count() == 0

    def test_load_initial_data(self, tabs):
        results = [
            {'host_id': 'imx', 'gallery_name': 'Gal A', 'online': 10, 'total': 10, 'checked_ts': '2026-03-10'},
            {'host_id': 'imx', 'gallery_name': 'Gal B', 'online': 7, 'total': 10, 'checked_ts': '2026-03-10'},
            {'host_id': 'turbo', 'gallery_name': 'Gal C', 'online': 5, 'total': 5, 'checked_ts': '2026-03-10'},
        ]
        tabs.load_results(results)
        assert tabs.count() == 2
        imx_table = tabs.widget(0)
        assert imx_table.rowCount() == 2
