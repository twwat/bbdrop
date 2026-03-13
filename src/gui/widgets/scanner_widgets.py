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


# ============================================================================
# Task 10: ScanControlsWidget
# ============================================================================

class ScanControlsWidget(QWidget):
    """Control panel for initiating link scans with filter options.

    Provides age and host filter dropdowns plus three scan trigger buttons:
    - Start Scan: scans galleries older than the selected age threshold
    - Unchecked Only: scans galleries that have never been checked
    - Problems: scans only galleries with known offline items

    The scan_requested signal carries (age_days, host_filter, scan_type).
    """

    scan_requested = pyqtSignal(int, str, str)

    _AGE_OPTIONS = [
        ('7+ days', 7),
        ('14+ days', 14),
        ('30+ days', 30),
        ('60+ days', 60),
        ('90+ days', 90),
    ]

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Age filter dropdown
        self._age_combo = QComboBox()
        for label, days in self._AGE_OPTIONS:
            self._age_combo.addItem(label, days)
        self._age_combo.setCurrentIndex(2)  # default: 30+ days
        layout.addWidget(self._age_combo)

        # Host filter dropdown
        self._host_combo = QComboBox()
        self._host_combo.addItem('All hosts', '')
        layout.addWidget(self._host_combo)

        # Start Scan button (age-based)
        self._start_btn = QPushButton('Start Scan')
        self._start_btn.clicked.connect(self._on_start)
        layout.addWidget(self._start_btn)

        # Unchecked Only button
        self._unchecked_btn = QPushButton('Unchecked Only')
        self._unchecked_btn.clicked.connect(self._on_unchecked)
        layout.addWidget(self._unchecked_btn)

        # Problems button
        self._problems_btn = QPushButton('Problems')
        self._problems_btn.clicked.connect(self._on_problems)
        layout.addWidget(self._problems_btn)

    def set_hosts(self, host_ids: list[str]) -> None:
        """Populate the host filter dropdown.

        Preserves the 'All hosts' entry at index 0 and appends each host_id.

        Args:
            host_ids: List of host identifier strings to add.
        """
        self._host_combo.clear()
        self._host_combo.addItem('All hosts', '')
        for hid in host_ids:
            self._host_combo.addItem(hid, hid)

    def set_enabled(self, enabled: bool) -> None:
        """Toggle all controls on or off.

        Args:
            enabled: True to enable, False to disable.
        """
        self._start_btn.setEnabled(enabled)
        self._unchecked_btn.setEnabled(enabled)
        self._problems_btn.setEnabled(enabled)
        self._age_combo.setEnabled(enabled)
        self._host_combo.setEnabled(enabled)

    def _get_host_filter(self) -> str:
        """Return the currently selected host filter value."""
        return self._host_combo.currentData() or ''

    def _on_start(self) -> None:
        """Emit scan_requested for an age-based scan."""
        age_days = self._age_combo.currentData()
        self.scan_requested.emit(age_days, self._get_host_filter(), 'age')

    def _on_unchecked(self) -> None:
        """Emit scan_requested for unchecked galleries (age=0)."""
        self.scan_requested.emit(0, self._get_host_filter(), 'unchecked')

    def _on_problems(self) -> None:
        """Emit scan_requested for problem galleries (age=0)."""
        self.scan_requested.emit(0, self._get_host_filter(), 'problems')


# ============================================================================
# Task 11: ScanProgressWidget
# ============================================================================

class ScanProgressWidget(QWidget):
    """Progress display for an active link scan.

    Shows an overall progress bar with count/percentage, a stop button,
    and dynamically created per-host progress bars arranged in a grid
    (two hosts per row).

    Emits stop_requested when the user clicks Stop.
    """

    stop_requested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # Top row: status label + stop button
        top_row = QHBoxLayout()
        self._status_label = QLabel('Scanning...')
        top_row.addWidget(self._status_label)
        top_row.addStretch()

        self._stop_btn = QPushButton('Stop')
        self._stop_btn.setFixedWidth(60)
        self._stop_btn.clicked.connect(self._on_stop)
        top_row.addWidget(self._stop_btn)
        outer.addLayout(top_row)

        # Overall progress bar
        self._overall_bar = QProgressBar()
        self._overall_bar.setValue(0)
        outer.addWidget(self._overall_bar)

        # Overall count label
        self._overall_count = QLabel('')
        self._overall_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._overall_count)

        # Per-host progress grid (2 hosts per row, each entry = label + bar + count)
        self._host_grid = QGridLayout()
        self._host_grid.setContentsMargins(0, 4, 0, 0)
        outer.addLayout(self._host_grid)

        self._host_bars: Dict[str, tuple] = {}

    def set_overall(self, current: int, total: int) -> None:
        """Update the overall progress bar and count label.

        Args:
            current: Number of items processed so far.
            total: Total number of items to process.
        """
        self._overall_bar.setMaximum(total)
        self._overall_bar.setValue(current)

        if total > 0:
            pct = round(current * 100 / total)
            self._overall_count.setText(f'{current}/{total}  ({pct}%)')
        else:
            self._overall_count.setText('')

    def update_progress(self, host_id: str, current: int, total: int) -> None:
        """Create or update a per-host progress bar.

        New hosts are added to a grid with two hosts per row. Each entry
        consists of a label (host_id uppercased), a 14px progress bar,
        and a count label showing "current/total".

        Args:
            host_id: Host identifier string.
            current: Items processed for this host.
            total: Total items for this host.
        """
        if host_id in self._host_bars:
            bar, count_label = self._host_bars[host_id]
            bar.setMaximum(total)
            bar.setValue(current)
            count_label.setText(f'{current}/{total}')
            return

        # Calculate grid position: 2 hosts per row, 3 columns each
        idx = len(self._host_bars)
        row = idx // 2
        col_offset = (idx % 2) * 3

        label = QLabel(host_id.upper())
        self._host_grid.addWidget(label, row, col_offset)

        bar = QProgressBar()
        bar.setFixedHeight(14)
        bar.setMaximum(total)
        bar.setValue(current)
        bar.setTextVisible(False)
        self._host_grid.addWidget(bar, row, col_offset + 1)

        count_label = QLabel(f'{current}/{total}')
        self._host_grid.addWidget(count_label, row, col_offset + 2)

        self._host_bars[host_id] = (bar, count_label)

    def reset(self) -> None:
        """Clear all host bars, reset overall progress, re-enable stop."""
        self._overall_bar.setValue(0)
        self._overall_bar.setMaximum(100)
        self._overall_count.setText('')
        self._status_label.setText('Scanning...')
        self._stop_btn.setEnabled(True)

        # Remove all per-host widgets from the grid
        while self._host_grid.count():
            item = self._host_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._host_bars.clear()

    def _on_stop(self) -> None:
        """Disable the stop button, update label, and emit stop_requested."""
        self._stop_btn.setEnabled(False)
        self._status_label.setText('Stopping...')
        self.stop_requested.emit()


# ============================================================================
# Task 12: HostResultsTabWidget
# ============================================================================

class _StatusSortItem(QTableWidgetItem):
    """Custom table item that sorts by offline count descending.

    Stores (offline_count, timestamp) in UserRole so that galleries with
    more problems sort first. Falls back to text comparison if no data set.
    """

    def __lt__(self, other: QTableWidgetItem) -> bool:
        my_data = self.data(Qt.ItemDataRole.UserRole)
        other_data = other.data(Qt.ItemDataRole.UserRole)
        if my_data is not None and other_data is not None:
            # Higher offline count = more problems = sort first (descending)
            my_offline, my_ts = my_data
            other_offline, other_ts = other_data
            if my_offline != other_offline:
                return my_offline > other_offline
            return my_ts < other_ts
        return super().__lt__(other)


class HostResultsTabWidget(QTabWidget):
    """Tabbed display of per-host scan results.

    Each host gets its own tab containing a sortable QTableWidget with
    columns: Name, Status (online/total), Last Checked. Status cells are
    color-coded using get_online_status_colors().

    Tabs are created lazily on first result for a given host_id.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._host_tabs: Dict[str, QTableWidget] = {}
        self._gallery_rows: Dict[str, Dict[str, int]] = {}

    def update_result(
        self,
        host_id: str,
        gallery_name: str,
        online: int,
        total: int,
        checked_ts: str,
    ) -> None:
        """Add or update a single gallery result row.

        Creates the host tab if it doesn't exist yet. If the gallery already
        has a row, updates it in place.

        Args:
            host_id: Host identifier string.
            gallery_name: Display name of the gallery.
            online: Number of items confirmed online.
            total: Total number of items in the gallery.
            checked_ts: Timestamp string of the last check.
        """
        table = self._ensure_tab(host_id)

        # Disable sorting while updating to prevent row index shifts
        table.setSortingEnabled(False)

        host_rows = self._gallery_rows.setdefault(host_id, {})

        if gallery_name in host_rows:
            row = host_rows[gallery_name]
        else:
            row = table.rowCount()
            table.insertRow(row)
            host_rows[gallery_name] = row

        # Column 0: Name
        name_item = QTableWidgetItem(gallery_name)
        table.setItem(row, 0, name_item)

        # Column 1: Status (online/total) with color coding
        status_text = f'{online}/{total}'
        status_item = _StatusSortItem(status_text)
        offline_count = total - online
        status_item.setData(Qt.ItemDataRole.UserRole, (offline_count, checked_ts))

        colors = get_online_status_colors()
        if total == 0:
            status_item.setForeground(colors['gray'])
        elif online == total:
            status_item.setForeground(colors['online'])
        elif online > 0:
            status_item.setForeground(colors['partial'])
        else:
            status_item.setForeground(colors['offline'])

        table.setItem(row, 1, status_item)

        # Column 2: Last Checked
        ts_item = QTableWidgetItem(checked_ts)
        table.setItem(row, 2, ts_item)

        # Re-enable sorting
        table.setSortingEnabled(True)

    def load_results(self, results: list[dict]) -> None:
        """Bulk-populate from a list of result dicts.

        Each dict must have keys: host_id, gallery_name, online, total, checked_ts.

        Args:
            results: List of result dictionaries.
        """
        for r in results:
            self.update_result(
                r['host_id'],
                r['gallery_name'],
                r['online'],
                r['total'],
                r['checked_ts'],
            )

    def activate_host(self, host_id: str) -> None:
        """Switch to the tab for the given host.

        Args:
            host_id: Host identifier whose tab should be shown.
        """
        if host_id in self._host_tabs:
            self.setCurrentWidget(self._host_tabs[host_id])

    def clear_all(self) -> None:
        """Remove all tabs and reset internal state."""
        while self.count():
            self.removeTab(0)
        self._host_tabs.clear()
        self._gallery_rows.clear()

    def _ensure_tab(self, host_id: str) -> QTableWidget:
        """Lazily create a tab for a host if it doesn't exist yet.

        Args:
            host_id: Host identifier string.

        Returns:
            The QTableWidget for this host.
        """
        if host_id in self._host_tabs:
            return self._host_tabs[host_id]

        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(['Name', 'Status', 'Last Checked'])
        table.setSortingEnabled(True)

        # Stretch the Name column to fill available space
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        self.addTab(table, host_id.upper())
        self._host_tabs[host_id] = table
        self._gallery_rows[host_id] = {}

        return table
