"""Unit tests for metric-column rendering in the worker status table.

Two behaviours live here:

1. Metric cells survive a full table rebuild for hosts whose display name
   differs from their canonical host_id (IMX.to/imx, TurboImageHost/turbo).
   The metrics cache is keyed by host_id; the rebuild used to read it by
   display name, so those rows blanked to em-dash on every rebuild.

2. In-flight file host bytes are added to the "uploaded" columns while a
   transfer is running, so they climb in step with queue (bytes) instead of
   jumping at completion.
"""

import pytest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSettings

from src.gui.widgets.worker_status_widget import (
    AVAILABLE_COLUMNS,
    WorkerStatusWidget,
    format_bytes,
)


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def mock_settings(monkeypatch):
    mock_qs = MagicMock(spec=QSettings)

    def mock_value(key, default=None, **kwargs):
        return default

    mock_qs.value.side_effect = mock_value
    monkeypatch.setattr(
        "src.gui.widgets.worker_status_widget.QSettings",
        lambda *args, **kwargs: mock_qs,
    )
    return mock_qs


@pytest.fixture
def widget(qapp, mock_settings):
    return WorkerStatusWidget()


def _show_only(widget, *col_ids):
    """Restrict the table to the given columns so cell indexes are stable."""
    widget._active_columns = [AVAILABLE_COLUMNS[c] for c in col_ids]
    widget._rebuild_table_columns()


def _cell_text(widget, worker_id, col_id):
    row = widget._worker_row_map[worker_id]
    col = widget._get_column_index(col_id)
    item = widget.status_table.item(row, col)
    return item.text() if item is not None else None


class TestMetricCacheKeyedByHostId:
    """A rebuild must find cached metrics via host_id, not display name."""

    def test_imx_session_bytes_survive_full_rebuild(self, widget):
        _show_only(widget, 'hostname', 'bytes_session')
        widget.update_worker_status(
            worker_id="upload_worker_imx",
            worker_type="imagehost",
            hostname="IMX.to",          # display name, as registered at startup
            speed_bps=0.0,
            status="idle",
            host_id="imx",              # canonical id, how metrics are keyed
        )
        widget._on_host_metrics_updated("imx", {'session': {'bytes_uploaded': 5_000_000}})

        widget._refresh_display()

        assert _cell_text(widget, "upload_worker_imx", 'bytes_session') == \
            format_bytes(5_000_000)

    def test_turbo_session_bytes_survive_full_rebuild(self, widget):
        _show_only(widget, 'hostname', 'bytes_session')
        widget.update_worker_status(
            worker_id="upload_worker_turbo",
            worker_type="imagehost",
            hostname="TurboImageHost",
            speed_bps=0.0,
            status="idle",
            host_id="turbo",
        )
        widget._on_host_metrics_updated("turbo", {'session': {'bytes_uploaded': 3_000_000}})

        widget._refresh_display()

        assert _cell_text(widget, "upload_worker_turbo", 'bytes_session') == \
            format_bytes(3_000_000)


class TestInflightBytesInUploadedColumns:
    """In-flight file host bytes show in the uploaded columns while running."""

    def _add_rapidgator(self, widget):
        widget.update_worker_status(
            worker_id="filehost_rapidgator",
            worker_type="filehost",
            hostname="rapidgator",
            speed_bps=0.0,
            status="uploading",
            host_id="rapidgator",
        )

    def test_inflight_bytes_add_to_session_column(self, widget):
        _show_only(widget, 'hostname', 'bytes_session')
        self._add_rapidgator(widget)
        widget._on_host_metrics_updated(
            "rapidgator", {'session': {'bytes_uploaded': 1_000_000}}
        )

        widget.set_inflight_bytes("rapidgator", 500_000)

        assert _cell_text(widget, "filehost_rapidgator", 'bytes_session') == \
            format_bytes(1_500_000)

    def test_inflight_bytes_add_to_today_and_all_time_columns(self, widget):
        _show_only(widget, 'hostname', 'bytes_today', 'bytes_alltime')
        self._add_rapidgator(widget)
        widget._on_host_metrics_updated("rapidgator", {
            'today': {'bytes_uploaded': 2_000_000},
            'all_time': {'bytes_uploaded': 9_000_000},
        })

        widget.set_inflight_bytes("rapidgator", 500_000)

        assert _cell_text(widget, "filehost_rapidgator", 'bytes_today') == \
            format_bytes(2_500_000)
        assert _cell_text(widget, "filehost_rapidgator", 'bytes_alltime') == \
            format_bytes(9_500_000)

    def test_inflight_bytes_survive_full_rebuild(self, widget):
        _show_only(widget, 'hostname', 'bytes_session')
        self._add_rapidgator(widget)
        widget._on_host_metrics_updated(
            "rapidgator", {'session': {'bytes_uploaded': 1_000_000}}
        )
        widget.set_inflight_bytes("rapidgator", 500_000)

        widget._refresh_display()

        assert _cell_text(widget, "filehost_rapidgator", 'bytes_session') == \
            format_bytes(1_500_000)

    def test_inflight_bytes_do_not_touch_non_byte_metrics(self, widget):
        _show_only(widget, 'hostname', 'files_session', 'peak_speed_session')
        self._add_rapidgator(widget)
        widget._on_host_metrics_updated("rapidgator", {
            'session': {'files_uploaded': 3, 'peak_speed': 1_048_576},
        })
        before_files = _cell_text(widget, "filehost_rapidgator", 'files_session')
        before_peak = _cell_text(widget, "filehost_rapidgator", 'peak_speed_session')

        widget.set_inflight_bytes("rapidgator", 500_000)

        assert _cell_text(widget, "filehost_rapidgator", 'files_session') == before_files
        assert _cell_text(widget, "filehost_rapidgator", 'peak_speed_session') == before_peak

    def test_clearing_inflight_bytes_drops_the_overlay(self, widget):
        _show_only(widget, 'hostname', 'bytes_session')
        self._add_rapidgator(widget)
        widget._on_host_metrics_updated(
            "rapidgator", {'session': {'bytes_uploaded': 1_000_000}}
        )
        widget.set_inflight_bytes("rapidgator", 500_000)

        widget.clear_inflight_bytes("rapidgator")

        assert _cell_text(widget, "filehost_rapidgator", 'bytes_session') == \
            format_bytes(1_000_000)

    def test_metrics_update_for_host_clears_its_overlay(self, widget):
        """record_transfer's own signal is the transfer landing — the overlay
        must drop then, or the finished file counts twice."""
        _show_only(widget, 'hostname', 'bytes_session')
        self._add_rapidgator(widget)
        widget.set_inflight_bytes("rapidgator", 500_000)

        # record_transfer lands: session now includes the 500_000 that moved.
        widget._on_host_metrics_updated(
            "rapidgator", {'session': {'bytes_uploaded': 500_000}}
        )

        assert _cell_text(widget, "filehost_rapidgator", 'bytes_session') == \
            format_bytes(500_000)

    def test_metrics_reach_a_worker_registered_without_a_host_id(self, widget, monkeypatch):
        """Metric routing must resolve a worker the same way everywhere. A
        worker carrying only a display name is still that host."""
        # The host registry is a lazily-filled module cache; if another test on
        # this xdist worker filled it under a patched project root, 'IMX.to'
        # isn't in it. Pin the entries this test depends on.
        from src.core import host_registry
        monkeypatch.setattr(host_registry, '_DISPLAY_NAMES', {'imx': 'IMX.to'})
        monkeypatch.setattr(host_registry, '_REVERSE_LOOKUP', {'imx': 'imx', 'imx.to': 'imx'})
        _show_only(widget, 'hostname', 'bytes_session')
        widget.update_worker_status(
            worker_id="upload_worker_imx",
            worker_type="imagehost",
            hostname="IMX.to",
            speed_bps=0.0,
            status="idle",
            host_id=None,
        )

        widget._on_host_metrics_updated("imx", {'session': {'bytes_uploaded': 7_000_000}})

        assert _cell_text(widget, "upload_worker_imx", 'bytes_session') == \
            format_bytes(7_000_000)

    def test_overlay_is_per_host(self, widget):
        _show_only(widget, 'hostname', 'bytes_session')
        self._add_rapidgator(widget)
        widget.update_worker_status(
            worker_id="filehost_katfile",
            worker_type="filehost",
            hostname="katfile",
            speed_bps=0.0,
            status="uploading",
            host_id="katfile",
        )
        widget._on_host_metrics_updated(
            "katfile", {'session': {'bytes_uploaded': 4_000_000}}
        )

        widget.set_inflight_bytes("rapidgator", 500_000)

        assert _cell_text(widget, "filehost_katfile", 'bytes_session') == \
            format_bytes(4_000_000)
