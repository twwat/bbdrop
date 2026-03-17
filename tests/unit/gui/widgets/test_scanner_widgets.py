#!/usr/bin/env python3
"""
Tests for scanner UI widgets used by the LinkScannerDashboard.

Covers:
- HostTableWidget: left-panel per-host table with health bars
- ScanControlsWidget: radio scan type + age/mode/host dropdowns
- GalleryResultsTable: right-panel gallery results table
"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtTest import QSignalSpy


# ============================================================================
# HostTableWidget Tests
# ============================================================================

class TestHostTableWidget:

    @pytest.fixture
    def host_table(self, qtbot):
        from src.gui.widgets.scanner_widgets import HostTableWidget
        w = HostTableWidget()
        qtbot.addWidget(w)
        return w

    def test_initial_state_empty(self, host_table):
        assert host_table.rowCount() == 0

    def test_set_hosts_populates_rows(self, host_table):
        host_table.set_hosts({
            'imx': {'label': 'IMX', 'gallery_count': 10, 'image_count': 100, 'online_items': 90, 'total_items': 100},
            'turbo': {'label': 'Turbo', 'gallery_count': 5, 'image_count': 50, 'online_items': 0, 'total_items': 0},
        })
        assert host_table.rowCount() == 2

    def test_count_column_shows_images(self, host_table):
        host_table.set_hosts({
            'imx': {'label': 'IMX', 'gallery_count': 10, 'image_count': 250, 'online_items': 90, 'total_items': 100},
        })
        assert host_table.item(0, 2).text() == '250'
        assert '10' in host_table.item(0, 2).toolTip()  # gallery count in tooltip

    def test_click_emits_host_selected(self, host_table, qtbot):
        host_table.set_hosts({
            'imx': {'label': 'IMX', 'gallery_count': 10, 'image_count': 100, 'online_items': 90, 'total_items': 100},
        })
        spy = QSignalSpy(host_table.host_selected)
        host_table.selectRow(0)
        assert len(spy) == 1
        assert spy[0][0] == 'imx'

    def test_select_host_by_id(self, host_table):
        host_table.set_hosts({
            'imx': {'label': 'IMX', 'gallery_count': 10, 'image_count': 100, 'online_items': 90, 'total_items': 100},
            'turbo': {'label': 'Turbo', 'gallery_count': 5, 'image_count': 50, 'online_items': 49, 'total_items': 50},
        })
        host_table.select_host('turbo')
        assert host_table.currentRow() == 1

    def test_update_scan_progress(self, host_table):
        host_table.set_hosts({
            'imx': {'label': 'IMX', 'gallery_count': 10, 'image_count': 100, 'online_items': 90, 'total_items': 100},
        })
        host_table.update_scan_progress('imx', 50, 100, online_count=40, total_items=80)
        # Health bar shows online/total ratio
        bar = host_table._get_bar(0)
        assert bar.value() == 40
        assert bar.maximum() == 80
        # Thin scan bar shows scan progress (use isHidden to check widget's own state)
        scan_bar = host_table._get_scan_bar(0)
        assert scan_bar is not None
        assert not scan_bar.isHidden()
        assert scan_bar.value() == 50
        assert scan_bar.maximum() == 100

    def test_revert_to_health_after_scan(self, host_table):
        host_table.set_hosts({
            'imx': {'label': 'IMX', 'gallery_count': 10, 'image_count': 100, 'online_items': 90, 'total_items': 100},
        })
        host_table.update_scan_progress('imx', 100, 100, online_count=90, total_items=100)
        # Scan bar should not be hidden during scan
        scan_bar = host_table._get_scan_bar(0)
        assert not scan_bar.isHidden()
        host_table.revert_to_health('imx', online_items=95, total_items=100)
        bar = host_table._get_bar(0)
        assert bar.value() == 95
        assert bar.maximum() == 100
        # Scan bar should be hidden after revert
        assert scan_bar.isHidden()

    def test_get_selected_host_id(self, host_table):
        host_table.set_hosts({
            'imx': {'label': 'IMX', 'gallery_count': 1, 'image_count': 10, 'online_items': 0, 'total_items': 0},
        })
        host_table.selectRow(0)
        assert host_table.get_selected_host_id() == 'imx'


# ============================================================================
# ScanControlsWidget Tests (Task 10)
# ============================================================================

class TestScanControlsWidget:

    @pytest.fixture
    def controls(self, qtbot):
        from src.gui.widgets.scanner_widgets import ScanControlsWidget
        w = ScanControlsWidget()
        qtbot.addWidget(w)
        return w

    def test_initial_scan_type_is_stale(self, controls):
        assert controls.get_scan_type() == 'age'

    def test_scan_type_radio_unchecked(self, controls):
        controls._unchecked_radio.setChecked(True)
        assert controls.get_scan_type() == 'unchecked'

    def test_scan_type_radio_problems(self, controls):
        controls._problems_radio.setChecked(True)
        assert controls.get_scan_type() == 'problems'

    def test_age_dropdown_has_all_option(self, controls):
        assert controls._age_combo.itemData(0) == 0  # "All" = 0 days

    def test_age_dropdown_default_is_30(self, controls):
        assert controls._age_combo.currentData() == 30

    def test_age_mode_dropdown_options(self, controls):
        modes = [controls._age_mode_combo.itemData(i) for i in range(controls._age_mode_combo.count())]
        assert 'last_scan' in modes
        assert 'upload' in modes

    def test_age_mode_disabled_when_all_selected(self, controls):
        controls._age_combo.setCurrentIndex(0)  # "All" = 0
        assert not controls._age_mode_combo.isEnabled()

    def test_age_mode_enabled_when_days_selected(self, controls):
        controls._age_combo.setCurrentIndex(0)  # "All"
        controls._age_combo.setCurrentIndex(3)  # "30+ days"
        assert controls._age_mode_combo.isEnabled()

    def test_host_dropdown_starts_with_all(self, controls):
        assert controls._host_combo.currentData() == ''

    def test_set_hosts_populates_dropdown(self, controls):
        controls.set_hosts(['imx', 'turbo'])
        assert controls._host_combo.count() == 3  # All + imx + turbo

    def test_start_scan_emits_signal(self, controls, qtbot):
        spy = QSignalSpy(controls.scan_requested)
        controls._start_btn.click()
        assert len(spy) == 1
        # (age_days, host_filter, scan_type, age_mode)
        assert spy[0][2] == 'age'  # scan_type

    def test_has_info_buttons(self, controls):
        from src.gui.widgets.info_button import InfoButton
        info_buttons = controls.findChildren(InfoButton)
        assert len(info_buttons) >= 4  # scan type, age, age mode, host

    def test_select_host(self, controls):
        controls.set_hosts(['imx', 'turbo'])
        controls.select_host('turbo')
        assert controls._host_combo.currentData() == 'turbo'


# ============================================================================
# GalleryResultsTable Tests
# ============================================================================

class TestGalleryResultsTable:

    @pytest.fixture
    def table(self, qtbot):
        from src.gui.widgets.scanner_widgets import GalleryResultsTable
        t = GalleryResultsTable()
        qtbot.addWidget(t)
        return t

    def test_initial_state_empty(self, table):
        assert table.rowCount() == 0

    def test_load_results_populates_rows(self, table):
        table.load_results([
            {'gallery_name': 'Gallery A', 'online': 10, 'total': 10, 'checked_ts': '2026-03-10', 'upload_ts': '2026-03-01'},
            {'gallery_name': 'Gallery B', 'online': None, 'total': None, 'checked_ts': '', 'upload_ts': '2026-03-02'},
        ])
        assert table.rowCount() == 2

    def test_clear_and_reload(self, table):
        table.load_results([
            {'gallery_name': 'Gallery A', 'online': 10, 'total': 10, 'checked_ts': '', 'upload_ts': ''},
        ])
        assert table.rowCount() == 1
        table.clear_rows()
        assert table.rowCount() == 0

    def test_unchecked_shows_gray(self, table):
        table.load_results([
            {'gallery_name': 'X', 'online': None, 'total': None, 'checked_ts': '', 'upload_ts': ''},
        ])
        assert table.item(0, 1).text() == 'Unchecked'

    def test_status_format(self, table):
        table.load_results([
            {'gallery_name': 'X', 'online': 8, 'total': 10, 'checked_ts': '', 'upload_ts': ''},
        ])
        assert table.item(0, 1).text() == '8/10'

    def test_sorting_enabled(self, table):
        assert table.isSortingEnabled()
