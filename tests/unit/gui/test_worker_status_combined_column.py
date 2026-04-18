"""Unit tests for the combined status/speed cell formatter."""

import pytest
from PyQt6.QtGui import QColor

from src.gui.widgets.worker_status_formatting import (
    WorkerStatus,
    format_status_speed_cell,
)


def _w(**overrides):
    base = dict(
        worker_id="w1",
        worker_type="imagehost",
        hostname="imx",
        display_name="IMX",
    )
    base.update(overrides)
    return WorkerStatus(**base)


class TestFormatStatusSpeedCell:
    def test_uploading_with_speed_appends_speed(self):
        text, color, tooltip, italic = format_status_speed_cell(
            _w(status="uploading", speed_bps=1.23 * 1024 * 1024)
        )
        assert text == "Uploading · 1.23 M/s"
        assert color == QColor("darkgreen")
        assert italic is False
        assert "Uploading" in tooltip
        assert "1.23 M/s" in tooltip

    def test_uploading_zero_speed_omits_suffix(self):
        text, _, _, _ = format_status_speed_cell(
            _w(status="uploading", speed_bps=0.0)
        )
        assert text == "Uploading"

    def test_idle_shows_capitalized_status(self):
        text, color, tooltip, italic = format_status_speed_cell(
            _w(status="idle", speed_bps=0.0)
        )
        assert text == "Idle"
        assert color is None
        assert italic is False

    def test_retry_pending_with_detail_shows_countdown(self):
        text, color, _, _ = format_status_speed_cell(
            _w(status="retry_pending:45", speed_bps=0.0)
        )
        assert text == "Retrying in 45s"
        assert color == QColor("#DAA520")

    def test_retry_pending_without_detail(self):
        text, _, _, _ = format_status_speed_cell(
            _w(status="retry_pending", speed_bps=0.0)
        )
        assert text == "Retrying..."

    def test_failed_with_error_message_in_tooltip(self):
        text, color, tooltip, _ = format_status_speed_cell(
            _w(status="failed", speed_bps=0.0, error_message="timeout")
        )
        assert text == "Failed"
        assert color == QColor("#FF6B6B")
        assert "timeout" in tooltip

    def test_failed_compound_status_uses_detail(self):
        _, _, tooltip, _ = format_status_speed_cell(
            _w(status="failed:HTTP 500", speed_bps=0.0)
        )
        assert "HTTP 500" in tooltip

    def test_network_error_styling(self):
        text, color, _, _ = format_status_speed_cell(
            _w(status="network_error", speed_bps=0.0)
        )
        assert text == "Network Error"
        assert color == QColor("#DAA520")

    def test_paused_styling(self):
        text, color, _, _ = format_status_speed_cell(
            _w(status="paused", speed_bps=0.0)
        )
        assert text == "Paused"
        assert color == QColor("#B8860B")

    def test_disabled_is_italic_placeholder(self):
        text, color, _, italic = format_status_speed_cell(
            _w(status="disabled", speed_bps=0.0)
        )
        assert text == "Disabled"
        assert color is None  # caller resolves placeholder colour
        assert italic is True

    def test_speed_suffix_only_added_when_uploading(self):
        # A non-zero speed reading on a non-uploading worker should not appear.
        text, _, _, _ = format_status_speed_cell(
            _w(status="paused", speed_bps=999_999.0)
        )
        assert "M/s" not in text

    def test_empty_status_falls_back_to_idle(self):
        text, color, _, italic = format_status_speed_cell(
            _w(status="", speed_bps=0.0)
        )
        assert text == "Idle"
        assert color is None
        assert italic is False

    def test_multi_colon_status_keeps_remainder_as_detail(self):
        # "failed:HTTP 500: connection reset" → base="failed", detail="HTTP 500: connection reset"
        _, _, tooltip, _ = format_status_speed_cell(
            _w(status="failed:HTTP 500: connection reset", speed_bps=0.0)
        )
        assert tooltip == "Failed: HTTP 500: connection reset"
