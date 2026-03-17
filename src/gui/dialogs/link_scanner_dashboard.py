"""Link Scanner Dashboard

Non-modal dashboard for multi-host link scanning. Left-right split layout
with host table, gallery results table, scan controls with radio buttons,
and an overall progress bar.
"""

from typing import Optional, Dict, Any, List

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QProgressBar,
    QDialogButtonBox, QApplication, QSplitter,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

from src.gui.widgets.scanner_widgets import (
    HostTableWidget,
    ScanControlsWidget,
    GalleryResultsTable,
)
from src.gui.theme_manager import get_online_status_colors
from src.utils.logger import log


# Host display labels (host_id -> human-readable short name)
HOST_LABELS: Dict[str, str] = {
    'imx': 'IMX.to',
    'turbo': 'TurboImageHost',
    'pixhost': 'Pixhost',
    'rapidgator': 'Rapidgator',
    'keep2share': 'Keep2Share',
    'fileboom': 'FileBoom',
    'tezfiles': 'TezFiles',
    'filedot': 'Filedot',
    'filespace': 'Filespace',
    'katfile': 'Katfile',
}


class LinkScannerDashboard(QDialog):
    """Non-modal dashboard for multi-host link status scanning.

    Layout:
        1. Header text (muted description)
        2. Overall progress bar (hidden when idle)
        3. ScanControlsWidget (radio buttons, dropdowns, start/stop)
        4. QSplitter: HostTableWidget (1/3) | GalleryResultsTable (2/3)
        5. Close button
    """

    _progress_signal = pyqtSignal(str, str, int, int)
    _complete_signal = pyqtSignal(dict)

    def __init__(self, parent=None, queue_manager=None, coordinator=None):
        super().__init__(parent)
        self.queue_manager = queue_manager
        self._coordinator = coordinator
        self._scan_checked: Dict[str, int] = {}
        self._scan_totals: Dict[str, int] = {}
        self._host_data: Dict[str, dict] = {}  # host_id -> {label, gallery_count, ...}

        self.setWindowTitle("Link Scanner")
        self.setModal(False)
        self.setMinimumSize(750, 550)
        self.resize(900, 650)
        self._center_on_parent()

        self._progress_signal.connect(self._on_scan_progress)
        self._complete_signal.connect(self._on_scan_complete)

        self._setup_ui()
        self._load_initial_data()

    def _center_on_parent(self) -> None:
        parent_widget = self.parent()
        if parent_widget and hasattr(parent_widget, 'geometry'):
            pg = parent_widget.geometry()
            dg = self.frameGeometry()
            self.move(
                pg.x() + (pg.width() - dg.width()) // 2,
                pg.y() + (pg.height() - dg.height()) // 2,
            )
        else:
            screen = QApplication.primaryScreen()
            if screen:
                sg = screen.geometry()
                dg = self.frameGeometry()
                self.move(
                    (sg.width() - dg.width()) // 2,
                    (sg.height() - dg.height()) // 2,
                )

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Header text
        self._header_label = QLabel(
            "Scan gallery links across all hosts to check which content is still online. "
            "Offline content will be flagged for re-upload in a future update."
        )
        self._header_label.setWordWrap(True)
        self._header_label.setStyleSheet("color: palette(placeholder-text);")
        layout.addWidget(self._header_label)

        # Overall progress bar (hidden when idle)
        self._overall_bar = QProgressBar()
        self._overall_bar.setValue(0)
        colors = get_online_status_colors()
        self._overall_bar.setStyleSheet(
            f'QProgressBar::chunk {{ background-color: {colors["online"].name()}; }}'
        )
        self._overall_bar.hide()
        layout.addWidget(self._overall_bar)

        # Controls
        self._controls = ScanControlsWidget()
        self._controls.scan_requested.connect(self._on_scan_requested)
        self._controls.stop_requested.connect(self._on_stop_requested)
        layout.addWidget(self._controls)

        # Splitter: host table (1/3) | gallery table (2/3)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._host_table = HostTableWidget()
        self._host_table.host_selected.connect(self._on_host_selected)
        splitter.addWidget(self._host_table)

        self._gallery_table = GalleryResultsTable()
        splitter.addWidget(self._gallery_table)

        splitter.setStretchFactor(0, 1)  # 1/3
        splitter.setStretchFactor(1, 2)  # 2/3
        layout.addWidget(splitter, stretch=1)

        # Close button
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.close)
        layout.addWidget(button_box)

        # Sync host dropdown changes back to host table
        self._controls._host_combo.currentIndexChanged.connect(self._on_host_dropdown_changed)

    def _load_initial_data(self) -> None:
        if not self.queue_manager:
            return

        store = self.queue_manager.store

        try:
            hosts_with_uploads = store.get_hosts_with_uploads()
        except Exception as e:
            log(f"Failed to load hosts: {e}", level="error", category="scanner")
            return

        if not hosts_with_uploads:
            return

        try:
            scan_stats = store.get_scan_stats_by_host()
        except Exception:
            scan_stats = {}

        # Build host data dict for the host table
        hosts_dict = {}
        for (host_type, host_id), counts in hosts_with_uploads.items():
            label = HOST_LABELS.get(host_id, host_id.upper())
            stats = scan_stats.get((host_type, host_id))
            online = stats.get('total_online', 0) if stats else 0
            total = stats.get('total_items', 0) if stats else 0

            hosts_dict[host_id] = {
                'label': label,
                'gallery_count': counts['gallery_count'],
                'image_count': counts['image_count'],
                'online_items': online,
                'total_items': total,
            }

        self._host_data = hosts_dict
        self._host_table.set_hosts(hosts_dict)
        self._controls.set_hosts(list(hosts_dict.keys()))

    def _on_host_selected(self, host_id: str) -> None:
        """Host table row clicked — sync dropdown and reload gallery table."""
        self._controls.select_host(host_id)
        self._reload_gallery_table(host_id)

    def _on_host_dropdown_changed(self) -> None:
        """Host dropdown changed — sync host table selection."""
        host_id = self._controls.get_host_filter()
        if host_id:  # Not "All Hosts"
            self._host_table.select_host(host_id)

    def _reload_gallery_table(self, host_id: str) -> None:
        """Reload the gallery table for the given host."""
        self._gallery_table.clear_rows()
        if not self.queue_manager:
            return
        try:
            gallery_data = self.queue_manager.store.get_galleries_for_dashboard()
            if gallery_data:
                filtered = [r for r in gallery_data if r.get('host_id') == host_id]
                self._gallery_table.load_results(filtered)
        except Exception:
            pass

    def _on_scan_requested(self, age_days: int, host_filter: str, scan_type: str, age_mode: str) -> None:
        self._overall_bar.setValue(0)
        self._overall_bar.show()
        self._controls.set_scanning(True)
        self._scan_checked.clear()
        self._scan_totals.clear()

        log(f"Scan requested: type={scan_type}, age={age_days}, host={host_filter or 'all'}, mode={age_mode}",
            level="info", category="scanner")

        if self._coordinator:
            try:
                gallery_data = self._gather_scan_data(age_days, host_filter, scan_type, age_mode)
                self._coordinator.start_scan(
                    gallery_data.get('image_galleries', []),
                    gallery_data.get('file_uploads', []),
                )
            except Exception as e:
                log(f"Failed to start scan: {e}", level="error", category="scanner")
                self._overall_bar.hide()
                self._controls.set_scanning(False)

    def _gather_scan_data(self, age_days: int, host_filter: str, scan_type: str, age_mode: str) -> Dict[str, Any]:
        if not self.queue_manager:
            return {'image_galleries': [], 'file_uploads': []}
        try:
            return self.queue_manager.store.get_galleries_for_scan(
                age_days, host_filter, scan_type, age_mode=age_mode
            )
        except Exception as e:
            log(f"Error gathering scan data: {e}", level="error", category="scanner")
            return {'image_galleries': [], 'file_uploads': []}

    def _on_stop_requested(self) -> None:
        if self._coordinator:
            self._coordinator.cancel()

    def _on_scan_progress(self, host_type: str, host_id: str, checked: int, total: int) -> None:
        """Handle scan progress (always called on GUI thread via signal)."""
        self._host_table.update_scan_progress(host_id, checked, total)

        self._scan_checked[host_id] = checked
        self._scan_totals[host_id] = total

        overall_checked = sum(self._scan_checked.values())
        overall_total = sum(self._scan_totals.values())
        self._overall_bar.setMaximum(max(overall_total, 1))
        self._overall_bar.setValue(overall_checked)

    def _on_scan_complete(self, summary: Dict[str, Any]) -> None:
        """Handle scan completion (always called on GUI thread via signal)."""
        elapsed = summary.get('elapsed', 0)
        total = summary.get('total_galleries', 0)
        log(f"Scan complete: {total} galleries in {elapsed:.1f}s", level="info", category="scanner")

        self._overall_bar.hide()
        self._controls.set_scanning(False)

        # Revert host bars to health and refresh data
        QTimer.singleShot(100, self._refresh_after_scan)

    def _refresh_after_scan(self) -> None:
        """Reload all data after scan completion."""
        self._gallery_table.clear_rows()
        self._host_data.clear()
        self._load_initial_data()
