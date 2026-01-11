#!/usr/bin/env python3
"""
Link Scanner Dashboard Dialog

Shows galleries with online status statistics and provides cumulative scanning
options to check galleries that haven't been scanned recently.
"""

from typing import Callable, Dict, List, Any, Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QDialogButtonBox, QGroupBox, QFrame,
    QApplication
)
from PyQt6.QtCore import Qt

from src.utils.logger import log


class LinkScannerDashboardDialog(QDialog):
    """Dashboard showing gallery online status statistics with cumulative scanning.

    Displays:
    - Status statistics (online/offline/partial/never) for galleries and images
    - Cumulative scan buttons (7+, 14+, 30+, etc.)
    - Quick action to rescan offline/partial only

    Attributes:
        queue_manager: Reference to the queue manager for database access
        on_scan_requested: Callback function to trigger scanning
    """

    # Cumulative time thresholds: (days, button_label, tooltip)
    SCAN_OPTIONS = [
        (7, 'Scan 7+ Days', 'Scan all galleries not checked in the last 7 days'),
        (14, 'Scan 14+ Days', 'Scan all galleries not checked in the last 14 days'),
        (30, 'Scan 30+ Days', 'Scan all galleries not checked in the last 30 days'),
        (60, 'Scan 60+ Days', 'Scan all galleries not checked in the last 60 days'),
        (90, 'Scan 90+ Days', 'Scan all galleries not checked in the last 90 days'),
        (365, 'Scan 1+ Year', 'Scan all galleries not checked in over a year'),
        (0, 'Scan All', 'Scan all completed galleries'),
    ]

    def __init__(
        self,
        parent=None,
        queue_manager=None,
        on_scan_requested: Optional[Callable[[List[str]], None]] = None
    ):
        """Initialize the Link Scanner Dashboard.

        Args:
            parent: Parent widget for the dialog
            queue_manager: Reference to queue manager for database access
            on_scan_requested: Callback function that accepts a list of gallery paths
                             to scan. Called when user clicks a Scan button.
        """
        super().__init__(parent)
        self.queue_manager = queue_manager
        self.on_scan_requested = on_scan_requested

        self.setWindowTitle("Link Scanner")
        self.setModal(True)
        self.setMinimumSize(500, 480)
        self.resize(560, 540)
        self._center_on_parent()

        self._stats: Dict[str, Any] = {}
        self._galleries_by_age: Dict[int, List[Dict[str, Any]]] = {}

        self._setup_ui()
        self._load_data()

    def _center_on_parent(self) -> None:
        """Center dialog on parent window or screen."""
        parent_widget = self.parent()
        if parent_widget:
            if hasattr(parent_widget, 'geometry'):
                parent_geo = parent_widget.geometry()
                dialog_geo = self.frameGeometry()
                x = parent_geo.x() + (parent_geo.width() - dialog_geo.width()) // 2
                y = parent_geo.y() + (parent_geo.height() - dialog_geo.height()) // 2
                self.move(x, y)
        else:
            screen = QApplication.primaryScreen()
            if screen:
                screen_geo = screen.geometry()
                dialog_geo = self.frameGeometry()
                x = (screen_geo.width() - dialog_geo.width()) // 2
                y = (screen_geo.height() - dialog_geo.height()) // 2
                self.move(x, y)

    def _setup_ui(self) -> None:
        """Initialize the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header
        header = QLabel(
            "Check the online status of your uploaded galleries.\n"
            "Scan options are cumulative - scanning \"7+ Days\" includes everything older."
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        # Statistics section
        stats_group = QGroupBox("Status Overview")
        stats_layout = QGridLayout(stats_group)
        stats_layout.setSpacing(8)

        # Gallery status row
        gallery_header = QLabel("<b>Galleries</b>")
        stats_layout.addWidget(gallery_header, 0, 0)

        self._gallery_online_label = QLabel("Online: 0")
        self._gallery_online_label.setStyleSheet("color: #27ae60;")  # Green
        stats_layout.addWidget(self._gallery_online_label, 0, 1)

        self._gallery_offline_label = QLabel("Offline: 0")
        self._gallery_offline_label.setStyleSheet("color: #e74c3c;")  # Red
        stats_layout.addWidget(self._gallery_offline_label, 0, 2)

        self._gallery_partial_label = QLabel("Partial: 0")
        self._gallery_partial_label.setStyleSheet("color: #f39c12;")  # Orange
        stats_layout.addWidget(self._gallery_partial_label, 0, 3)

        self._gallery_never_label = QLabel("Never: 0")
        self._gallery_never_label.setStyleSheet("color: #7f8c8d;")  # Gray
        stats_layout.addWidget(self._gallery_never_label, 0, 4)

        self._gallery_total_label = QLabel("Total: 0")
        stats_layout.addWidget(self._gallery_total_label, 0, 5)

        # Separator
        line1 = QFrame()
        line1.setFrameShape(QFrame.Shape.HLine)
        line1.setFrameShadow(QFrame.Shadow.Sunken)
        stats_layout.addWidget(line1, 1, 0, 1, 6)

        # Image count row (status is tracked at gallery level, not per-image)
        image_header = QLabel("<b>Images</b>")
        stats_layout.addWidget(image_header, 2, 0)

        self._image_total_label = QLabel("Total: 0")
        stats_layout.addWidget(self._image_total_label, 2, 1)

        # Note explaining image status tracking
        image_note = QLabel("(status tracked at gallery level)")
        image_note.setStyleSheet("color: #7f8c8d; font-style: italic;")
        stats_layout.addWidget(image_note, 2, 2, 1, 3)

        layout.addWidget(stats_group)

        # Scan options section
        scan_group = QGroupBox("Scan by Age")
        scan_layout = QGridLayout(scan_group)
        scan_layout.setSpacing(8)

        # Create scan buttons in a grid
        self._scan_buttons: Dict[int, QPushButton] = {}
        self._scan_count_labels: Dict[int, QLabel] = {}

        for i, (days, label, tooltip) in enumerate(self.SCAN_OPTIONS):
            row = i // 2
            col = (i % 2) * 2

            # Button
            btn = QPushButton(label)
            btn.setToolTip(tooltip)
            btn.setMinimumWidth(120)
            btn.setEnabled(False)
            btn.clicked.connect(lambda checked, d=days: self._on_scan_by_age(d))
            scan_layout.addWidget(btn, row, col)
            self._scan_buttons[days] = btn

            # Count label
            count_label = QLabel("(0)")
            count_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            scan_layout.addWidget(count_label, row, col + 1)
            self._scan_count_labels[days] = count_label

        layout.addWidget(scan_group)

        # Quick actions section
        actions_group = QGroupBox("Quick Actions")
        actions_layout = QHBoxLayout(actions_group)

        self._rescan_offline_btn = QPushButton("Rescan Offline/Partial Only")
        self._rescan_offline_btn.setToolTip(
            "Scan only galleries that are currently marked as offline or partial"
        )
        self._rescan_offline_btn.setEnabled(False)
        self._rescan_offline_btn.clicked.connect(self._on_rescan_offline)
        actions_layout.addWidget(self._rescan_offline_btn)

        self._rescan_never_btn = QPushButton("Scan Never Checked")
        self._rescan_never_btn.setToolTip("Scan galleries that have never been checked")
        self._rescan_never_btn.setEnabled(False)
        self._rescan_never_btn.clicked.connect(self._on_rescan_never)
        actions_layout.addWidget(self._rescan_never_btn)

        actions_layout.addStretch()

        layout.addWidget(actions_group)

        layout.addStretch()

        # Close button
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _load_data(self) -> None:
        """Load gallery data from database and update display."""
        if not self.queue_manager:
            self._gallery_total_label.setText("Total: N/A")
            return

        try:
            self._stats = self.queue_manager.store.get_link_scanner_stats()
        except Exception as e:
            log(f"Failed to load link scanner stats: {e}", level="error", category="ui")
            self._gallery_total_label.setText(f"Error: {e}")
            return

        # Update gallery statistics
        gallery_stats = self._stats.get('galleries', {})
        self._gallery_online_label.setText(f"Online: {gallery_stats.get('online', 0):,}")
        self._gallery_offline_label.setText(f"Offline: {gallery_stats.get('offline', 0):,}")
        self._gallery_partial_label.setText(f"Partial: {gallery_stats.get('partial', 0):,}")
        self._gallery_never_label.setText(f"Never: {gallery_stats.get('never', 0):,}")
        self._gallery_total_label.setText(f"Total: {gallery_stats.get('total', 0):,}")

        # Update image total count
        image_stats = self._stats.get('images', {})
        self._image_total_label.setText(f"Total: {image_stats.get('total', 0):,}")

        # Update cumulative scan counts
        cumulative_counts = self._stats.get('cumulative_counts', {})
        self._galleries_by_age = self._stats.get('galleries_by_age', {})

        for days, btn in self._scan_buttons.items():
            count = cumulative_counts.get(days, 0)
            self._scan_count_labels[days].setText(f"({count:,})")
            btn.setEnabled(count > 0)

        # Update quick action buttons
        offline_partial_count = gallery_stats.get('offline', 0) + gallery_stats.get('partial', 0)
        self._rescan_offline_btn.setEnabled(offline_partial_count > 0)
        self._rescan_offline_btn.setText(f"Rescan Offline/Partial ({offline_partial_count:,})")

        never_count = gallery_stats.get('never', 0)
        self._rescan_never_btn.setEnabled(never_count > 0)
        self._rescan_never_btn.setText(f"Scan Never Checked ({never_count:,})")

    def _on_scan_by_age(self, min_days: int) -> None:
        """Handle scan button click for cumulative age threshold.

        Args:
            min_days: Minimum age in days (0 = all galleries)
        """
        galleries = self._galleries_by_age.get(min_days, [])
        if not galleries:
            return

        paths = [g['path'] for g in galleries]
        count = len(paths)

        if min_days == 0:
            log(f"Link Scanner: Scanning all {count} galleries", level="info", category="ui")
        else:
            log(f"Link Scanner: Scanning {count} galleries ({min_days}+ days old)",
                level="info", category="ui")

        if self.on_scan_requested:
            self.accept()  # Close dashboard
            self.on_scan_requested(paths)

    def _on_rescan_offline(self) -> None:
        """Handle rescan offline/partial button click."""
        offline_galleries = self._stats.get('offline_partial_galleries', [])
        if not offline_galleries:
            return

        paths = [g['path'] for g in offline_galleries]
        count = len(paths)

        log(f"Link Scanner: Rescanning {count} offline/partial galleries",
            level="info", category="ui")

        if self.on_scan_requested:
            self.accept()
            self.on_scan_requested(paths)

    def _on_rescan_never(self) -> None:
        """Handle scan never-checked button click."""
        never_galleries = self._stats.get('never_checked_galleries', [])
        if not never_galleries:
            return

        paths = [g['path'] for g in never_galleries]
        count = len(paths)

        log(f"Link Scanner: Scanning {count} never-checked galleries",
            level="info", category="ui")

        if self.on_scan_requested:
            self.accept()
            self.on_scan_requested(paths)
