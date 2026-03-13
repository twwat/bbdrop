"""Link Scanner Dashboard

Non-modal dashboard for multi-host link scanning. Displays per-host summary
cards, scan controls, inline progress, and tabbed results. Replaces the
original modal LinkScannerDashboardDialog.
"""

from typing import Optional, Dict, Any, List

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QStackedWidget, QDialogButtonBox, QApplication
)
from PyQt6.QtCore import Qt, QTimer

from src.gui.widgets.scanner_widgets import (
    HostSummaryCard,
    ScanControlsWidget,
    ScanProgressWidget,
    HostResultsTabWidget,
)
from src.utils.logger import log


# Host display labels (host_id -> human-readable short name)
HOST_LABELS: Dict[str, str] = {
    'imx': 'IMX',
    'turbo': 'Turbo',
    'rapidgator': 'RG',
    'keep2share': 'K2S',
    'fileboom': 'FBoom',
    'tezfiles': 'Tez',
    'filedot': 'Fdot',
    'filespace': 'Fspc',
}


class LinkScannerDashboard(QDialog):
    """Non-modal dashboard for multi-host link status scanning.

    Assembles:
        1. HostSummaryCards (top row) — one per host with uploads
        2. ScanControls / ScanProgress (middle, swapped via QStackedWidget)
        3. HostResultsTabs (bottom) — per-host sortable result tables
    """

    def __init__(self, parent=None, queue_manager=None, coordinator=None):
        super().__init__(parent)
        self.queue_manager = queue_manager
        self._coordinator = coordinator
        self._summary_cards: Dict[str, HostSummaryCard] = {}
        self._scan_totals: Dict[str, int] = {}
        self._overall_checked = 0
        self._overall_total = 0

        self.setWindowTitle("Link Scanner")
        self.setModal(False)
        self.setMinimumSize(650, 550)
        self.resize(750, 650)
        self._center_on_parent()

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
        layout.setSpacing(10)

        # Summary cards row
        self._cards_layout = QHBoxLayout()
        self._cards_layout.setSpacing(8)
        self._cards_layout.addStretch()
        layout.addLayout(self._cards_layout)

        # Control / Progress stack
        self._control_stack = QStackedWidget()

        self._controls = ScanControlsWidget()
        self._controls.scan_requested.connect(self._on_scan_requested)
        self._control_stack.addWidget(self._controls)

        self._progress = ScanProgressWidget()
        self._progress.stop_requested.connect(self._on_stop_requested)
        self._control_stack.addWidget(self._progress)

        self._control_stack.setCurrentWidget(self._controls)
        layout.addWidget(self._control_stack)

        # Results tabs
        self._results_tabs = HostResultsTabWidget()
        layout.addWidget(self._results_tabs, stretch=1)

        # Close button
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.close)
        layout.addWidget(button_box)

    def _load_initial_data(self) -> None:
        if not self.queue_manager:
            return

        try:
            stats = self.queue_manager.store.get_scan_stats_by_host()
        except Exception as e:
            log(f"Failed to load scan stats: {e}", level="error", category="scanner")
            return

        host_ids = []
        for (host_type, host_id), data in stats.items():
            label = HOST_LABELS.get(host_id, host_id.upper())
            card = HostSummaryCard(host_id=host_id, host_label=label)
            card.update_stats(
                total_galleries=data.get('total_galleries', 0),
                online_items=data.get('total_online', 0),
                total_items=data.get('total_items', 0),
            )
            card.host_clicked.connect(self._on_host_card_clicked)

            self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)
            self._summary_cards[host_id] = card
            host_ids.append(host_id)

        self._controls.set_hosts(host_ids)

    def _on_scan_requested(self, age_days: int, host_filter: str, scan_type: str) -> None:
        self._progress.reset()
        self._control_stack.setCurrentWidget(self._progress)
        self._overall_checked = 0
        self._overall_total = 0

        log(f"Scan requested: type={scan_type}, age={age_days}, host={host_filter or 'all'}",
            level="info", category="scanner")

        if self._coordinator:
            try:
                gallery_data = self._gather_scan_data(age_days, host_filter, scan_type)
                self._coordinator.start_scan(
                    gallery_data.get('image_galleries', []),
                    gallery_data.get('file_uploads', []),
                )
            except Exception as e:
                log(f"Failed to start scan: {e}", level="error", category="scanner")
                self._control_stack.setCurrentWidget(self._controls)

    def _gather_scan_data(self, age_days: int, host_filter: str, scan_type: str) -> Dict[str, Any]:
        if not self.queue_manager:
            return {'image_galleries': [], 'file_uploads': []}

        try:
            return self.queue_manager.store.get_galleries_for_scan(age_days, host_filter, scan_type)
        except Exception as e:
            log(f"Error gathering scan data: {e}", level="error", category="scanner")
            return {'image_galleries': [], 'file_uploads': []}

    def _on_stop_requested(self) -> None:
        if self._coordinator:
            self._coordinator.cancel()

    def _on_scan_progress(self, host_type: str, host_id: str, checked: int, total: int) -> None:
        self._progress.update_progress(host_id, checked, total)
        self._scan_totals[host_id] = total
        self._overall_total = sum(self._scan_totals.values())
        self._progress.set_overall(checked, total)

    def _on_scan_complete(self, summary: Dict[str, Any]) -> None:
        elapsed = summary.get('elapsed', 0)
        total = summary.get('total_galleries', 0)
        log(f"Scan complete: {total} galleries in {elapsed:.1f}s", level="info", category="scanner")

        self._control_stack.setCurrentWidget(self._controls)
        QTimer.singleShot(100, self._refresh_after_scan)

    def _refresh_after_scan(self) -> None:
        self._load_initial_data()

    def _on_host_card_clicked(self, host_id: str) -> None:
        self._results_tabs.activate_host(host_id)
