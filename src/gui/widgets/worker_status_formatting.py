"""Pure formatters for the worker status table.

Kept separate from worker_status_widget.py so unit tests can exercise the
formatting logic without importing the heavy Qt widget module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtGui import QColor

if TYPE_CHECKING:
    from src.gui.widgets.worker_status_widget import WorkerStatus


def format_status_speed_cell(
    worker: "WorkerStatus",
) -> tuple[str, "QColor | None", str, bool]:
    """Format the combined status/speed cell for one worker.

    Returns:
        (text, color, tooltip, italic) — color is None when the caller
        should fall back to the default text colour. italic=True means the
        caller should set an italic font (used for disabled workers).
    """
    status = worker.status or "idle"
    speed_bps = worker.speed_bps or 0.0

    base_status = status
    detail = ""
    if ":" in status:
        base_status, _, detail = status.partition(":")

    text = base_status.capitalize()
    tooltip = f"Status: {text}"
    color: QColor | None = None
    italic = False

    if base_status == "uploading":
        color = QColor("darkgreen")
        if speed_bps > 0:
            speed_text = _format_speed_value(speed_bps)
            text = f"Uploading · {speed_text}"
            tooltip = f"Status: Uploading\nCurrent Speed: {speed_text}"
    elif base_status == "retry_pending":
        color = QColor("#DAA520")
        if detail:
            text = f"Retrying in {detail}s"
            tooltip = f"Retry pending - will retry in {detail} seconds"
        else:
            text = "Retrying..."
            tooltip = "Retry pending"
    elif base_status in ("failed", "error"):
        color = QColor("#FF6B6B")
        text = "Failed"
        if detail:
            tooltip = f"Failed: {detail}"
        elif worker.error_message:
            tooltip = f"Failed: {worker.error_message}"
        else:
            tooltip = "Upload failed"
    elif base_status == "network_error":
        color = QColor("#DAA520")
        text = "Network Error"
        if detail:
            tooltip = f"Network Error: {detail}"
        else:
            tooltip = "Network error occurred"
    elif base_status == "paused":
        color = QColor("#B8860B")
    elif base_status == "disabled":
        italic = True

    return text, color, tooltip, italic


# Intentionally independent of WorkerStatusWidget._format_speed so this
# module stays pure and importable without the Qt widget module.
def _format_speed_value(speed_bps: float) -> str:
    """Format a bytes/sec value as 'N.NN M/s' (zero/None → '— M/s')."""
    if speed_bps is None or speed_bps <= 0:
        return "— M/s"
    return f"{speed_bps / (1024.0 * 1024.0):.2f} M/s"
