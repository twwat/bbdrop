#!/usr/bin/env python3
"""
Image Status Dialog
Shows results of checking image online status on IMX.to
"""

import time
from typing import List, Dict, Any, Optional
from datetime import datetime

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QLabel, QProgressBar, QWidget,
    QAbstractItemView, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QFont

from src.gui.theme_manager import get_online_status_colors
from src.utils.logger import log


class NumericTableItem(QTableWidgetItem):
    """QTableWidgetItem subclass that sorts numerically instead of alphabetically."""

    def __lt__(self, other: QTableWidgetItem) -> bool:
        """Compare items numerically for sorting.

        Args:
            other: The other item to compare against

        Returns:
            True if this item's numeric value is less than other's
        """
        try:
            return int(self.text()) < int(other.text())
        except ValueError:
            return super().__lt__(other)


class ImageStatusDialog(QDialog):
    """Dialog showing image online status check results.

    Displays a sortable table with columns:
    - DB ID: Gallery database ID
    - Name: Gallery name
    - Images: Total image count
    - Online: Count of online images
    - Offline: Count of offline images
    - Status: Summary text (Online/Partial/Offline)

    Sorted by Offline count (descending) by default.
    """

    # Signal emitted when check is requested
    check_requested = pyqtSignal(list)  # List of gallery paths
    cancelled = pyqtSignal()  # Emitted when user cancels

    def __init__(self, parent=None):
        """Initialize the Image Status Dialog.

        Args:
            parent: Parent widget for the dialog
        """
        super().__init__(parent)
        self.setWindowTitle("Check Image Status - IMX.to")
        self.setModal(True)
        self.setMinimumSize(700, 400)
        self.resize(850, 500)
        self._center_on_parent()

        self._results: Dict[str, Dict[str, Any]] = {}
        self._spinner_index = 0
        self._setup_ui()

    def _center_on_parent(self) -> None:
        """Center dialog on parent window or screen."""
        parent_widget = self.parent()
        if parent_widget:
            # Center on parent window
            if hasattr(parent_widget, 'geometry'):
                parent_geo = parent_widget.geometry()
                dialog_geo = self.frameGeometry()
                x = parent_geo.x() + (parent_geo.width() - dialog_geo.width()) // 2
                y = parent_geo.y() + (parent_geo.height() - dialog_geo.height()) // 2
                self.move(x, y)
        else:
            # Center on screen if no parent
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

        # Header with summary
        self.summary_label = QLabel("Preparing to check image status...")
        self.summary_label.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(self.summary_label)

        # Progress bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Spinner layout (hidden by default)
        spinner_widget = QWidget()
        self.spinner_layout = QHBoxLayout(spinner_widget)
        self.spinner_layout.setContentsMargins(0, 0, 0, 0)

        # Animated dots spinner
        self._spinner_label = QLabel("")
        self._spinner_label.setFixedWidth(30)
        self._spinner_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        self.spinner_layout.addWidget(self._spinner_label)

        # Status text next to spinner
        self._spinner_status_label = QLabel("Checking image status...")
        self._spinner_status_label.setStyleSheet("font-style: italic;")
        self.spinner_layout.addWidget(self._spinner_status_label)
        self.spinner_layout.addStretch()

        # Timer for animation
        self._spinner_timer = QTimer(self)
        self._spinner_timer.timeout.connect(self._animate_spinner)

        layout.addWidget(spinner_widget)
        self._spinner_widget = spinner_widget
        self._spinner_widget.setVisible(False)

        # Results table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["DB ID", "Name", "Images", "Online", "Offline", "Status"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        # Configure columns
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # DB ID
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Name
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Images
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Online
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Offline
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Status

        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        # Cancel button (visible while running)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.cancel_btn.setVisible(False)
        button_layout.addWidget(self.cancel_btn)

        # Close button (visible when idle/complete)
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.close_btn)

        layout.addLayout(button_layout)

    def set_galleries(self, galleries: List[Dict[str, Any]]) -> None:
        """Set galleries to be checked and display in table.

        Args:
            galleries: List of dicts with keys: db_id, path, name, total_images
        """
        self.table.setRowCount(len(galleries))

        for row, gallery in enumerate(galleries):
            db_id = gallery.get('db_id', 0)
            name = gallery.get('name', '')
            total = gallery.get('total_images', 0)
            path = gallery.get('path', '')

            # DB ID
            id_item = QTableWidgetItem(str(db_id))
            id_item.setData(Qt.ItemDataRole.UserRole, path)
            id_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 0, id_item)

            # Name
            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.ItemDataRole.UserRole, path)
            self.table.setItem(row, 1, name_item)

            # Images (total) - use NumericTableItem for proper sorting
            images_item = NumericTableItem(str(total))
            images_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 2, images_item)

            # Online (pending) - use NumericTableItem for proper sorting
            online_item = NumericTableItem("0")
            online_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 3, online_item)

            # Offline (pending) - use NumericTableItem for proper sorting
            offline_item = NumericTableItem("0")
            offline_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 4, offline_item)

            # Status (pending)
            status_item = QTableWidgetItem("Pending...")
            self.table.setItem(row, 5, status_item)

        # Default sort by Offline column (column 4) descending
        self.table.sortItems(4, Qt.SortOrder.DescendingOrder)

    def _set_spinner_visible(self, visible: bool) -> None:
        """Show or hide the spinner animation.

        Args:
            visible: Whether to show the spinner
        """
        self._spinner_widget.setVisible(visible)
        if visible:
            self._spinner_timer.start(300)
        else:
            self._spinner_timer.stop()

    def _animate_spinner(self) -> None:
        """Animate spinner dots."""
        dots = [".", "..", "..."]
        self._spinner_index = (self._spinner_index + 1) % len(dots)
        self._spinner_label.setText(dots[self._spinner_index])

    def set_spinner_status(self, text: str) -> None:
        """Update spinner status text.

        Args:
            text: Status text to display next to the spinner
        """
        self._spinner_status_label.setText(text)

    def show_progress(self, visible: bool = True) -> None:
        """Show or hide the progress indicators.

        Args:
            visible: Whether to show the progress indicators
        """
        self.progress_bar.setVisible(visible)
        self._set_spinner_visible(visible)

        if visible:
            # Running state: Cancel visible, Close hidden
            self.cancel_btn.setVisible(True)
            self.cancel_btn.setEnabled(True)
            self.cancel_btn.setText("Cancel")
            self.close_btn.setVisible(False)
            self.progress_bar.setRange(0, 0)  # Indeterminate
            self.set_spinner_status("Checking image status...")
        else:
            # Complete state: Cancel hidden, Close visible
            self.cancel_btn.setVisible(False)
            self.close_btn.setVisible(True)

    def update_progress(self, current: int, total: int) -> None:
        """Update progress bar.

        Args:
            current: Current progress value
            total: Total progress value
        """
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)

    def show_quick_count(self, online: int, total: int) -> None:
        """Display quick count result as soon as it's available.

        Provides immediate feedback (2-3 seconds) rather than waiting
        for full response download (90+ seconds).

        Args:
            online: Number of images found online
            total: Total images submitted for checking
        """
        if total <= 0:
            return

        pct = (online * 100) // total
        offline = total - online

        # Update progress bar to show online/total
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(online)
        self.progress_bar.setVisible(True)

        if online == total:
            # All images online!
            self.summary_label.setText(f"All {total:,} images online (100%)")
            # Hide spinner - essentially done, just waiting for final results
            self._set_spinner_visible(False)
        else:
            # Some images offline - still downloading to identify which
            self.summary_label.setText(
                f"{online:,} / {total:,} online ({pct}%) — Identifying {offline:,} offline..."
            )
            # Keep spinner visible

    def set_results(self, results: Dict[str, Dict[str, Any]], elapsed_time: float = 0.0) -> None:
        """Set check results and update the table.

        Args:
            results: Dict keyed by gallery path with values containing:
                - db_id: int
                - name: str
                - total: int
                - online: int
                - offline: int
                - online_urls: List[str]
                - offline_urls: List[str]
            elapsed_time: Time taken for the check in seconds
        """
        _t0 = time.perf_counter()

        # Get theme-aware status colors at display time
        colors = get_online_status_colors()

        self._results = results
        self.progress_bar.setVisible(False)
        self._set_spinner_visible(False)

        # Show Close button now that we're done
        self.cancel_btn.setVisible(False)
        self.close_btn.setVisible(True)

        # Build path-to-row index BEFORE disabling updates
        # This avoids repeated item.data() calls in the main loop
        _t_index = time.perf_counter()
        path_to_row: Dict[str, int] = {}
        row_count = self.table.rowCount()
        for row in range(row_count):
            id_item = self.table.item(row, 0)
            if id_item:
                path = id_item.data(Qt.ItemDataRole.UserRole)
                if path:
                    path_to_row[path] = row
        _t_index_done = time.perf_counter()

        # Disable updates, sorting, AND signals for maximum performance
        self.table.setUpdatesEnabled(False)
        self.table.setSortingEnabled(False)
        self.table.blockSignals(True)

        # CRITICAL: Temporarily disable ResizeToContents mode
        # Each setText() triggers font metric calculations with ResizeToContents,
        # even when setUpdatesEnabled(False). This caused 50+ second freezes.
        # Switch to Fixed mode during batch update, then resize once at the end.
        header = self.table.horizontalHeader()
        original_modes = []
        for col in range(self.table.columnCount()):
            original_modes.append(header.sectionResizeMode(col))
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)

        try:
            _t1 = time.perf_counter()
            # Calculate aggregates
            total_galleries = 0
            total_images = 0
            total_online = 0
            total_offline = 0
            galleries_online = 0   # All images online
            galleries_partial = 0  # Some images online
            galleries_offline = 0  # No images online

            # Iterate over results dict directly (faster than iterating table rows)
            for path, result in results.items():
                row = path_to_row.get(path)
                if row is None:
                    continue

                total_galleries += 1
                online = result.get('online', 0)
                offline = result.get('offline', 0)
                total = result.get('total', 0)

                total_images += total
                total_online += online
                total_offline += offline

                # Count gallery status
                if total > 0:
                    if online == total:
                        galleries_online += 1
                    elif online == 0:
                        galleries_offline += 1
                    else:
                        galleries_partial += 1

                # Get items once per row (cache references)
                online_item = self.table.item(row, 3)
                offline_item = self.table.item(row, 4)
                status_item = self.table.item(row, 5)

                # Update Online column
                if online_item:
                    online_item.setText(str(online))

                # Update Offline column with red+bold styling if > 0
                if offline_item:
                    offline_item.setText(str(offline))
                    if offline > 0:
                        offline_item.setForeground(colors['offline'])
                        bold_font = QFont()
                        bold_font.setBold(True)
                        offline_item.setFont(bold_font)

                # Update Status column with color coding
                if status_item:
                    if total == 0:
                        status_text = "No images"
                        color = colors['gray']
                    elif online == total:
                        status_text = "Online"
                        color = colors['online']
                    elif online == 0:
                        status_text = "Offline"
                        color = colors['offline']
                    else:
                        status_text = "Partial"
                        color = colors['partial']

                    status_item.setText(status_text)
                    status_item.setForeground(color)

            _t2 = time.perf_counter()
            log(f"DEBUG TIMING set_results: index build took {(_t_index_done - _t_index)*1000:.1f}ms, "
                f"table loop took {(_t2 - _t1)*1000:.1f}ms for {len(results)} results",
                level="debug", category="status_check")

            # Build enhanced summary
            rate = total_images / elapsed_time if elapsed_time > 0 else 0
            img_pct = 100 * total_online // total_images if total_images else 0

            summary = f"Checked {total_galleries} galleries ({total_images} images)"
            if elapsed_time > 0:
                summary += f" in {elapsed_time:.1f}s ({rate:.0f}/s)"
            summary += f" - {total_online}/{total_images} online ({img_pct}%)"

            self.summary_label.setText(summary)

            # Add breakdown as tooltip
            breakdown = f"Galleries: {galleries_online} online, {galleries_partial} partial, {galleries_offline} offline"
            self.summary_label.setToolTip(breakdown)

        finally:
            # Restore column resize modes and trigger single resize
            for col, mode in enumerate(original_modes):
                header.setSectionResizeMode(col, mode)

            # Re-enable signals first, then updates and sorting
            self.table.blockSignals(False)
            _t3 = time.perf_counter()
            self.table.setUpdatesEnabled(True)
            _t4 = time.perf_counter()
            self.table.setSortingEnabled(True)
            _t5 = time.perf_counter()
            log(f"DEBUG TIMING set_results: setUpdatesEnabled took {(_t4 - _t3)*1000:.1f}ms, "
                f"setSortingEnabled took {(_t5 - _t4)*1000:.1f}ms, total: {(_t5 - _t0)*1000:.1f}ms",
                level="debug", category="status_check")

        # Sort by Offline column (column 4) descending after results are set
        self.table.sortItems(4, Qt.SortOrder.DescendingOrder)

    def _on_cancel(self) -> None:
        """Handle cancel button click."""
        self.cancelled.emit()
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("Cancelling...")

    def get_checked_timestamp(self) -> int:
        """Get current timestamp for storing in database.

        Returns:
            Current Unix timestamp as integer
        """
        return int(datetime.now().timestamp())

    def format_check_datetime(self, timestamp: int) -> str:
        """Format timestamp for display.

        Args:
            timestamp: Unix timestamp as integer

        Returns:
            Formatted datetime string in YYYY-MM-DD HH:MM format
        """
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")

    def closeEvent(self, event) -> None:
        """Handle dialog close - ensure timer is stopped.

        Args:
            event: The close event
        """
        self._spinner_timer.stop()
        super().closeEvent(event)

    def reject(self) -> None:
        """Handle dialog rejection (ESC key) - ensure timer is stopped."""
        self._spinner_timer.stop()
        super().reject()
