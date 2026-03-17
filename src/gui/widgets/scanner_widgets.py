"""
Scanner UI widgets for the LinkScannerDashboard.

Provides compact visual components for displaying scan status, controlling
scan parameters, and presenting per-host results.

Widgets:
    HostTableWidget: Left-panel per-host table with health bars
    ScanControlsWidget: Radio scan type + age/mode/host dropdowns
    GalleryResultsTable: Right-panel gallery results table
"""

from typing import Optional, Dict, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar,
    QComboBox, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
)
from PyQt6.QtCore import Qt, pyqtSignal

from src.gui.theme_manager import get_online_status_colors


# ============================================================================
# HostTableWidget
# ============================================================================

class HostTableWidget(QTableWidget):
    """Left-panel table showing per-host scan health summaries.

    Columns: Host | Health Bar | Count | %
    Clicking a row emits host_selected(host_id).
    During scans, health bars temporarily show scan progress.
    """

    host_selected = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(0, 4, parent)
        self.setHorizontalHeaderLabels(['Host', 'Health', 'Count', '%'])
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.verticalHeader().setVisible(False)
        self.setSortingEnabled(False)

        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(1, 80)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        self._host_ids: list[str] = []  # row index -> host_id
        self._host_rows: dict[str, int] = {}  # host_id -> row index
        self._health_data: dict[str, tuple[int, int]] = {}  # host_id -> (online, total)
        self._scanning: set[str] = set()  # host_ids currently being scanned

        self.currentCellChanged.connect(self._on_row_changed)

    def set_hosts(self, hosts: dict[str, dict]) -> None:
        """Populate the table with host data.

        Args:
            hosts: Dict of host_id -> {label, gallery_count, image_count, online_items, total_items}
        """
        self.setRowCount(0)
        self._host_ids.clear()
        self._host_rows.clear()
        self._health_data.clear()
        self._scanning.clear()

        colors = get_online_status_colors()

        for host_id, data in hosts.items():
            row = self.rowCount()
            self.insertRow(row)
            self._host_ids.append(host_id)
            self._host_rows[host_id] = row

            online = data.get('online_items', 0)
            total = data.get('total_items', 0)
            self._health_data[host_id] = (online, total)

            # Col 0: Host name
            name_item = QTableWidgetItem(data.get('label', host_id.upper()))
            self.setItem(row, 0, name_item)

            # Col 1: Health bar (centered in cell via container widget)
            bar = QProgressBar()
            bar.setFixedHeight(10)
            bar.setTextVisible(False)
            bar.setMaximum(max(total, 1))
            bar.setValue(online)
            self._apply_bar_color(bar, online, total, colors)
            if total > 0:
                bar.setToolTip(f"{online}/{total} items online")
            else:
                bar.setToolTip("Not yet scanned")
            container = QWidget()
            container_layout = QVBoxLayout(container)
            container_layout.setContentsMargins(2, 0, 2, 0)
            container_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            container_layout.addWidget(bar)
            self.setCellWidget(row, 1, container)

            # Col 2: Image count (gallery count in tooltip)
            image_count = data.get('image_count', 0)
            gallery_count = data.get('gallery_count', 0)
            count_item = QTableWidgetItem(str(image_count))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            count_item.setToolTip(f"{gallery_count} galleries")
            self.setItem(row, 2, count_item)

            # Col 3: Percentage
            if total > 0:
                pct = int(online * 100 / total)
                pct_item = QTableWidgetItem(f"{pct}%")
            else:
                pct_item = QTableWidgetItem("--")
            pct_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setItem(row, 3, pct_item)

    def select_host(self, host_id: str) -> None:
        """Select the row for the given host_id."""
        row = self._host_rows.get(host_id)
        if row is not None:
            self.selectRow(row)

    def get_selected_host_id(self) -> Optional[str]:
        """Return the host_id of the currently selected row, or None."""
        row = self.currentRow()
        if 0 <= row < len(self._host_ids):
            return self._host_ids[row]
        return None

    def _get_bar(self, row: int) -> Optional[QProgressBar]:
        """Get the QProgressBar from a row's container widget."""
        container = self.cellWidget(row, 1)
        if container:
            bar = container.findChild(QProgressBar)
            return bar
        return None

    def update_scan_progress(self, host_id: str, checked: int, total: int) -> None:
        """Temporarily show scan progress in a host's health bar."""
        row = self._host_rows.get(host_id)
        if row is None:
            return
        self._scanning.add(host_id)
        bar = self._get_bar(row)
        if bar:
            bar.setMaximum(total)
            bar.setValue(checked)
            colors = get_online_status_colors()
            bar.setStyleSheet(
                f'QProgressBar::chunk {{ background-color: {colors["online"].name()}; }}'
            )
            bar.setToolTip(f"Scanning: {checked}/{total}")

    def revert_to_health(self, host_id: str, online_items: int, total_items: int) -> None:
        """Revert a host's bar from scan progress back to health display."""
        row = self._host_rows.get(host_id)
        if row is None:
            return
        self._scanning.discard(host_id)
        self._health_data[host_id] = (online_items, total_items)
        bar = self._get_bar(row)
        if bar:
            colors = get_online_status_colors()
            bar.setMaximum(max(total_items, 1))
            bar.setValue(online_items)
            self._apply_bar_color(bar, online_items, total_items, colors)
            if total_items > 0:
                bar.setToolTip(f"{online_items}/{total_items} items online")
                pct = int(online_items * 100 / total_items)
                self.item(row, 3).setText(f"{pct}%")
            else:
                bar.setToolTip("Not yet scanned")
                self.item(row, 3).setText("--")

    def _apply_bar_color(self, bar: QProgressBar, online: int, total: int, colors: dict) -> None:
        if total == 0:
            color = colors['gray']
        else:
            pct = online * 100 / total
            if pct >= 80:
                color = colors['online']
            elif pct >= 50:
                color = colors['partial']
            else:
                color = colors['offline']
        bar.setStyleSheet(
            f'QProgressBar::chunk {{ background-color: {color.name()}; }}'
        )

    def _on_row_changed(self, current_row: int, current_col: int, prev_row: int, prev_col: int) -> None:
        if 0 <= current_row < len(self._host_ids):
            self.host_selected.emit(self._host_ids[current_row])


# ============================================================================
# Task 10: ScanControlsWidget
# ============================================================================

class ScanControlsWidget(QWidget):
    """Control panel with scan type radios, age/mode/host dropdowns, and info buttons.

    Signal scan_requested carries (age_days, host_filter, scan_type, age_mode).
    """

    scan_requested = pyqtSignal(int, str, str, str)
    stop_requested = pyqtSignal()

    _AGE_OPTIONS = [
        ('All', 0),
        ('7+ days', 7),
        ('14+ days', 14),
        ('30+ days', 30),
        ('60+ days', 60),
        ('90+ days', 90),
    ]

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        from src.gui.widgets.info_button import InfoButton
        from PyQt6.QtWidgets import QRadioButton, QButtonGroup

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Row 1: Scan type radios + info button
        row1 = QHBoxLayout()
        self._scan_type_group = QButtonGroup(self)

        self._stale_radio = QRadioButton("Stale")
        self._unchecked_radio = QRadioButton("Unchecked")
        self._problems_radio = QRadioButton("Problems")
        self._stale_radio.setChecked(True)

        self._scan_type_group.addButton(self._stale_radio)
        self._scan_type_group.addButton(self._unchecked_radio)
        self._scan_type_group.addButton(self._problems_radio)

        row1.addWidget(self._stale_radio)
        row1.addWidget(self._unchecked_radio)
        row1.addWidget(self._problems_radio)
        row1.addWidget(InfoButton(
            "<b>Stale</b> — Rescan galleries not checked within the age threshold.<br>"
            "<b>Unchecked</b> — Scan galleries that have never been checked.<br>"
            "<b>Problems</b> — Rescan galleries with known offline or partial content."
        ))
        row1.addStretch()
        layout.addLayout(row1)

        # Row 2: Age + Age Mode + Host + buttons
        row2 = QHBoxLayout()

        self._age_combo = QComboBox()
        for label, days in self._AGE_OPTIONS:
            self._age_combo.addItem(label, days)
        self._age_combo.setCurrentIndex(3)  # default: 30+ days
        self._age_combo.currentIndexChanged.connect(self._on_age_changed)
        row2.addWidget(self._age_combo)
        row2.addWidget(InfoButton(
            "Only include galleries matching this age threshold. "
            "'All' scans everything regardless of age."
        ))

        self._age_mode_combo = QComboBox()
        self._age_mode_combo.addItem("Last Scan", "last_scan")
        self._age_mode_combo.addItem("Upload Age", "upload")
        row2.addWidget(self._age_mode_combo)
        row2.addWidget(InfoButton(
            "<b>Last Scan</b> — filter by when the gallery was last checked on the target host.<br>"
            "<b>Upload Age</b> — filter by when the gallery was originally uploaded."
        ))

        self._host_combo = QComboBox()
        self._host_combo.addItem('All Hosts', '')
        row2.addWidget(self._host_combo)
        row2.addWidget(InfoButton(
            "Choose which host to scan. Matches the selected host in the table. "
            "Use 'All Hosts' to scan everything."
        ))

        self._start_btn = QPushButton('Start Scan')
        self._start_btn.clicked.connect(self._on_start)
        row2.addWidget(self._start_btn)

        self._stop_btn = QPushButton('Stop')
        self._stop_btn.setFixedWidth(60)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._on_stop)
        row2.addWidget(self._stop_btn)

        layout.addLayout(row2)

    def get_scan_type(self) -> str:
        if self._unchecked_radio.isChecked():
            return 'unchecked'
        elif self._problems_radio.isChecked():
            return 'problems'
        return 'age'

    def set_hosts(self, host_ids: list[str]) -> None:
        self._host_combo.clear()
        self._host_combo.addItem('All Hosts', '')
        for hid in host_ids:
            self._host_combo.addItem(hid, hid)

    def select_host(self, host_id: str) -> None:
        """Set the host dropdown to the given host_id."""
        idx = self._host_combo.findData(host_id)
        if idx >= 0:
            self._host_combo.setCurrentIndex(idx)

    def get_host_filter(self) -> str:
        return self._host_combo.currentData() or ''

    def set_scanning(self, scanning: bool) -> None:
        """Toggle controls enabled/disabled during scan."""
        self._start_btn.setEnabled(not scanning)
        self._stop_btn.setEnabled(scanning)
        self._age_combo.setEnabled(not scanning)
        # Age mode stays disabled when "All" is selected even after scan ends
        if not scanning:
            self._age_mode_combo.setEnabled(self._age_combo.currentData() != 0)
        else:
            self._age_mode_combo.setEnabled(False)
        self._host_combo.setEnabled(not scanning)
        self._stale_radio.setEnabled(not scanning)
        self._unchecked_radio.setEnabled(not scanning)
        self._problems_radio.setEnabled(not scanning)

    def _on_age_changed(self) -> None:
        """Disable age mode when 'All' is selected (age_days=0 skips filtering)."""
        self._age_mode_combo.setEnabled(self._age_combo.currentData() != 0)

    def _on_start(self) -> None:
        age_days = self._age_combo.currentData()
        host_filter = self.get_host_filter()
        scan_type = self.get_scan_type()
        age_mode = self._age_mode_combo.currentData()
        self.scan_requested.emit(age_days, host_filter, scan_type, age_mode)

    def _on_stop(self) -> None:
        self._stop_btn.setEnabled(False)
        self.stop_requested.emit()


# ============================================================================
# _StatusSortItem (shared helper)
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


# ============================================================================
# GalleryResultsTable
# ============================================================================

class GalleryResultsTable(QTableWidget):
    """Right-panel table showing gallery scan results for a single host.

    Columns: Name, Status, Last Checked, Upload Date.
    No tabs — the dashboard repopulates this table when the host changes.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(0, 4, parent)
        self.setHorizontalHeaderLabels(['Name', 'Status', 'Last Checked', 'Upload Date'])
        self.setSortingEnabled(True)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

    def load_results(self, results: list[dict]) -> None:
        """Populate table from result dicts.

        Each dict: gallery_name, online (int|None), total (int|None), checked_ts, upload_ts.
        """
        self.setSortingEnabled(False)
        self.setRowCount(0)

        colors = get_online_status_colors()
        for r in results:
            row = self.rowCount()
            self.insertRow(row)

            self.setItem(row, 0, QTableWidgetItem(r['gallery_name']))

            online = r['online']
            total = r['total']
            if online is None:
                status_item = _StatusSortItem('Unchecked')
                status_item.setData(Qt.ItemDataRole.UserRole, (0, ''))
                status_item.setForeground(colors['gray'])
            else:
                status_item = _StatusSortItem(f'{online}/{total}')
                offline_count = total - online
                status_item.setData(Qt.ItemDataRole.UserRole, (offline_count, r['checked_ts']))
                if total == 0:
                    status_item.setForeground(colors['gray'])
                elif online == total:
                    status_item.setForeground(colors['online'])
                elif online > 0:
                    status_item.setForeground(colors['partial'])
                else:
                    status_item.setForeground(colors['offline'])
            self.setItem(row, 1, status_item)

            self.setItem(row, 2, QTableWidgetItem(r['checked_ts']))
            self.setItem(row, 3, QTableWidgetItem(r.get('upload_ts', '')))

        self.setSortingEnabled(True)

    def clear_rows(self) -> None:
        self.setSortingEnabled(False)
        self.setRowCount(0)
        self.setSortingEnabled(True)
