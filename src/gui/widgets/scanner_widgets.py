"""
Scanner UI widgets for the LinkScannerDashboard.

Provides compact visual components for displaying scan status, controlling
scan parameters, showing progress, and presenting per-host results.

Widgets:
    HostSummaryCard: Per-host status card with health progress bar
    ScanControlsWidget: Age/host filter dropdowns and scan trigger buttons
    ScanProgressWidget: Overall + per-host progress bars with stop control
    HostResultsTabWidget: Per-host sortable result tables
"""

from typing import Optional, Dict, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar,
    QFrame, QSizePolicy, QComboBox, QPushButton, QGridLayout,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QColor

from src.gui.theme_manager import get_online_status_colors


# ============================================================================
# Task 9: HostSummaryCard
# ============================================================================

class HostSummaryCard(QFrame):
    """Compact card showing per-host scan health summary.

    Displays a host label, gallery count, a color-coded health progress bar,
    and a percentage label. Clicking the card emits host_clicked with the
    host_id string.

    Color coding by health percentage:
        >= 80%: green (online)
        >= 50%: amber (partial)
        < 50%:  red (offline)
        0 total: gray
    """

    host_clicked = pyqtSignal(str)

    def __init__(self, host_id: str, host_label: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._host_id = host_id

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFixedWidth(90)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # Host label (bold)
        self._label = QLabel(host_label)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = self._label.font()
        font.setBold(True)
        self._label.setFont(font)
        layout.addWidget(self._label)

        # Gallery count
        self._count_label = QLabel('0')
        self._count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._count_label)

        # Health progress bar (8px tall, no text)
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(8)
        layout.addWidget(self._bar)

        # Percentage label
        self._pct_label = QLabel('--')
        self._pct_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._pct_label)

    def update_stats(self, total_galleries: int, online_items: int, total_items: int) -> None:
        """Update the card with fresh scan statistics.

        Args:
            total_galleries: Number of galleries for this host.
            online_items: Number of items confirmed online.
            total_items: Total number of items checked.
        """
        self._count_label.setText(str(total_galleries))

        if total_items == 0:
            self._pct_label.setText('--')
            self._bar.setValue(0)
            self._apply_color('gray')
            return

        pct = int(online_items * 100 / total_items)
        self._pct_label.setText(f'{pct}%')
        self._bar.setValue(pct)

        if pct >= 80:
            self._apply_color('online')
        elif pct >= 50:
            self._apply_color('partial')
        else:
            self._apply_color('offline')

    def _apply_color(self, status_key: str) -> None:
        """Apply a status color to the progress bar chunk.

        Args:
            status_key: One of 'online', 'partial', 'offline', 'gray'.
        """
        colors = get_online_status_colors()
        color = colors.get(status_key, colors['gray'])
        self._bar.setStyleSheet(
            f'QProgressBar::chunk {{ background-color: {color.name()}; }}'
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Emit host_clicked signal when the card is clicked."""
        self.host_clicked.emit(self._host_id)
