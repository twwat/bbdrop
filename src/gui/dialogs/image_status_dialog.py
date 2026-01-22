#!/usr/bin/env python3
"""
Image Status Dialog
Shows results of checking image online status on IMX.to
"""

import time
from typing import List, Dict, Any
from datetime import datetime

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QLabel, QProgressBar, QWidget, QFrame,
    QAbstractItemView, QApplication, QSizePolicy, QGroupBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPaintEvent

from src.gui.theme_manager import get_online_status_colors
from src.gui.icon_manager import get_icon
from src.utils.logger import log


class ProportionalBar(QWidget):
    """A progress bar that shows multiple colored segments proportionally.

    Can display 2 segments (online/offline for images) or 3 segments
    (online/partial/offline for galleries).
    """

    def __init__(self, parent=None):
        """Initialize the proportional bar.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.setMinimumHeight(20)
        self.setMaximumHeight(24)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        # Segment values (will be normalized to percentages)
        self._segments: List[tuple] = []  # List of (value, QColor)
        self._total = 0
        self._indeterminate = True
        self._animation_offset = 0

        # Animation timer for indeterminate state
        self._animation_timer = QTimer(self)
        self._animation_timer.timeout.connect(self._animate)

    def set_indeterminate(self, indeterminate: bool) -> None:
        """Set whether the bar shows indeterminate (pulsing) animation.

        Args:
            indeterminate: True for pulsing animation, False for segments
        """
        self._indeterminate = indeterminate
        if indeterminate:
            self._animation_timer.start(50)
        else:
            self._animation_timer.stop()
        self.update()

    def set_segments(self, segments: List[tuple]) -> None:
        """Set the colored segments to display.

        Args:
            segments: List of (value, QColor) tuples. Values are counts,
                     will be normalized to percentages automatically.
        """
        self._segments = segments
        self._total = sum(s[0] for s in segments)
        self._indeterminate = False
        self._animation_timer.stop()
        self.update()

    def _animate(self) -> None:
        """Animate the indeterminate state."""
        self._animation_offset = (self._animation_offset + 5) % 200
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the proportional bar.

        Args:
            event: Paint event
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        width = rect.width()
        height = rect.height()

        # Draw background
        bg_color = QColor("#3a3a3a") if self._is_dark_mode() else QColor("#e0e0e0")
        painter.fillRect(rect, bg_color)

        # Clip to widget bounds to prevent painting outside
        painter.setClipRect(rect)

        if self._indeterminate:
            # Draw pulsing animation
            pulse_color = QColor("#4a90d9")
            pulse_width = width // 3
            x = (self._animation_offset - 100) * width // 100
            painter.fillRect(x, 0, pulse_width, height, pulse_color)
        elif self._total > 0:
            # Draw proportional segments
            x = 0
            for i, (value, color) in enumerate(self._segments):
                segment_width = int(width * value / self._total)
                # Last non-zero segment takes remaining width to avoid rounding gaps
                if i == len(self._segments) - 1 or (
                    i < len(self._segments) - 1 and
                    all(s[0] == 0 for s in self._segments[i+1:])
                ):
                    segment_width = width - x
                if value > 0:
                    painter.fillRect(x, 0, segment_width, height, color)
                    x += segment_width

        # Draw border
        border_color = QColor("#555") if self._is_dark_mode() else QColor("#999")
        painter.setPen(border_color)
        painter.drawRect(0, 0, width - 1, height - 1)

        painter.end()

    def _is_dark_mode(self) -> bool:
        """Check if dark mode is active."""
        from src.gui.theme_manager import is_dark_mode
        return is_dark_mode()

    def stop_animation(self) -> None:
        """Stop any running animation."""
        self._animation_timer.stop()


class NumericTableItem(QTableWidgetItem):
    """QTableWidgetItem subclass that sorts numerically instead of alphabetically."""

    def __lt__(self, other: QTableWidgetItem) -> bool:
        """Compare items numerically for sorting."""
        try:
            # Check UserRole first for raw numeric value
            my_val = self.data(Qt.ItemDataRole.UserRole)
            other_val = other.data(Qt.ItemDataRole.UserRole)
            if my_val is not None and other_val is not None:
                return int(my_val) < int(other_val)
            return int(self.text()) < int(other.text())
        except (ValueError, TypeError):
            return super().__lt__(other)


class ImageStatusDialog(QDialog):
    """Dialog showing image online status check results.

    Features a two-bar display for images and galleries status,
    with a detailed statistics panel and results table.
    """

    check_requested = pyqtSignal(list)
    cancelled = pyqtSignal()

    def __init__(self, parent=None):
        """Initialize the Image Status Dialog."""
        super().__init__(parent)
        self.setWindowTitle("Check Image Status - IMX.to")
        self.setModal(True)
        self.setMinimumSize(750, 450)
        self.resize(900, 550)
        self._center_on_parent()

        self._results: Dict[str, Dict[str, Any]] = {}
        self._start_time: float = 0
        self._setup_ui()

    def _center_on_parent(self) -> None:
        """Center dialog on parent window or screen."""
        parent_widget = self.parent()
        if parent_widget and hasattr(parent_widget, 'geometry'):
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
        """Initialize the dialog UI with new layout."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Get theme colors
        self._colors = get_online_status_colors()

        # === Progress Section (QGroupBox) ===
        progress_group = QGroupBox("Progress")
        bars_layout = QGridLayout(progress_group)
        bars_layout.setContentsMargins(10, 10, 10, 10)
        bars_layout.setSpacing(8)

        # Images bar row
        images_label = QLabel("Images:")
        images_label.setFixedWidth(70)
        self.images_bar = ProportionalBar()
        self.images_status_label = QLabel("")
        self.images_status_label.setMinimumWidth(200)

        bars_layout.addWidget(images_label, 0, 0)
        bars_layout.addWidget(self.images_bar, 0, 1)
        bars_layout.addWidget(self.images_status_label, 0, 2)

        # Galleries bar row
        galleries_label = QLabel("Galleries:")
        galleries_label.setFixedWidth(70)
        self.galleries_bar = ProportionalBar()
        self.galleries_status_label = QLabel("")
        self.galleries_status_label.setMinimumWidth(200)

        bars_layout.addWidget(galleries_label, 1, 0)
        bars_layout.addWidget(self.galleries_bar, 1, 1)
        bars_layout.addWidget(self.galleries_status_label, 1, 2)

        # Elapsed time (top right)
        self.elapsed_label = QLabel("Elapsed: 0.0s")
        self.elapsed_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        bars_layout.addWidget(self.elapsed_label, 0, 3)

        # Spinner status
        self.spinner_label = QLabel("")
        self.spinner_label.setProperty("class", "status-muted")
        bars_layout.addWidget(self.spinner_label, 1, 3)

        bars_layout.setColumnStretch(1, 1)  # Bar column stretches
        layout.addWidget(progress_group)

        # Elapsed time timer
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.timeout.connect(self._update_elapsed)

        # === Summary Section with nested Galleries/Images QGroupBoxes ===
        summary_group = QGroupBox("Summary")
        summary_layout = QHBoxLayout(summary_group)
        summary_layout.setSpacing(10)
        summary_layout.setContentsMargins(5, 5, 5, 5)

        # --- Galleries sub-groupbox ---
        galleries_group = QGroupBox("Galleries")
        gal_layout = QGridLayout(galleries_group)
        gal_layout.setSpacing(4)
        gal_layout.setContentsMargins(10, 8, 10, 8)

        # Galleries: Checked row
        gal_layout.addWidget(QLabel("Checked:"), 0, 0)
        self.val_checked_galleries = QLabel("—")
        self.val_checked_galleries.setAlignment(Qt.AlignmentFlag.AlignRight)
        gal_layout.addWidget(self.val_checked_galleries, 0, 1)

        # Galleries: Online row
        gal_layout.addWidget(QLabel("Online:"), 1, 0)
        self.val_online_galleries = QLabel("—")
        self.val_online_galleries.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.val_online_galleries.setProperty("online-status", "online")
        self.pct_online_galleries = QLabel("")
        self.pct_online_galleries.setProperty("online-status", "online")
        gal_layout.addWidget(self.val_online_galleries, 1, 1)
        gal_layout.addWidget(self.pct_online_galleries, 1, 2)

        # Galleries: Partially Offline row
        gal_layout.addWidget(QLabel("Partially Offline:"), 2, 0)
        self.val_partial_galleries = QLabel("—")
        self.val_partial_galleries.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.val_partial_galleries.setProperty("online-status", "partial")
        self.pct_partial_galleries = QLabel("")
        self.pct_partial_galleries.setProperty("online-status", "partial")
        gal_layout.addWidget(self.val_partial_galleries, 2, 1)
        gal_layout.addWidget(self.pct_partial_galleries, 2, 2)

        # Galleries: Offline row
        gal_layout.addWidget(QLabel("Offline:"), 3, 0)
        self.val_offline_galleries = QLabel("—")
        self.val_offline_galleries.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.val_offline_galleries.setProperty("online-status", "offline")
        self.pct_offline_galleries = QLabel("")
        self.pct_offline_galleries.setProperty("online-status", "offline")
        gal_layout.addWidget(self.val_offline_galleries, 3, 1)
        gal_layout.addWidget(self.pct_offline_galleries, 3, 2)

        summary_layout.addWidget(galleries_group)

        # --- Images sub-groupbox ---
        images_group = QGroupBox("Images")
        img_layout = QGridLayout(images_group)
        img_layout.setSpacing(4)
        img_layout.setContentsMargins(10, 8, 10, 8)

        # Images: Checked row
        img_layout.addWidget(QLabel("Checked:"), 0, 0)
        self.val_checked_images = QLabel("—")
        self.val_checked_images.setAlignment(Qt.AlignmentFlag.AlignRight)
        img_layout.addWidget(self.val_checked_images, 0, 1)

        # Images: Online row
        img_layout.addWidget(QLabel("Online:"), 1, 0)
        self.val_online_images = QLabel("—")
        self.val_online_images.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.val_online_images.setProperty("online-status", "online")
        self.pct_online_images = QLabel("")
        self.pct_online_images.setProperty("online-status", "online")
        img_layout.addWidget(self.val_online_images, 1, 1)
        img_layout.addWidget(self.pct_online_images, 1, 2)

        # Images: Offline row
        img_layout.addWidget(QLabel("Offline:"), 2, 0)
        self.val_offline_images = QLabel("—")
        self.val_offline_images.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.val_offline_images.setProperty("online-status", "offline")
        self.pct_offline_images = QLabel("")
        self.pct_offline_images.setProperty("online-status", "offline")
        img_layout.addWidget(self.val_offline_images, 2, 1)
        img_layout.addWidget(self.pct_offline_images, 2, 2)

        summary_layout.addWidget(images_group)

        layout.addWidget(summary_group)

        # === Scan Results Section (QGroupBox) ===
        results_group = QGroupBox("Scan Results")
        results_layout = QVBoxLayout(results_group)
        results_layout.setContentsMargins(10, 10, 10, 10)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["ID", "Gallery Name", "Images", "Online", "Offline", "Status"])
        self.table.setColumnHidden(4, True)  # Hide Offline column (kept for sorting)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)  # Shorter rows
        self.table.setVisible(False)  # Hidden until scan complete

        results_layout.addWidget(self.table)
        layout.addWidget(results_group)

        # === Buttons ===
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.cancel_btn.setVisible(False)
        button_layout.addWidget(self.cancel_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.close_btn)

        layout.addLayout(button_layout)

        # Backward compatibility aliases for tests
        self._setup_stat_aliases()

    def _setup_stat_aliases(self) -> None:
        """Create backward-compatible stat widget aliases for tests."""
        class StatWrapper:
            """Wrapper to provide .value_label attribute."""
            def __init__(self, label: QLabel):
                self.value_label = label

        self.stat_galleries_scanned = StatWrapper(self.val_checked_galleries)
        self.stat_images_checked = StatWrapper(self.val_checked_images)
        self.stat_online_galleries = StatWrapper(self.val_online_galleries)
        self.stat_partial_galleries = StatWrapper(self.val_partial_galleries)
        self.stat_offline_galleries = StatWrapper(self.val_offline_galleries)
        self.stat_online_images = StatWrapper(self.val_online_images)
        self.stat_offline_images = StatWrapper(self.val_offline_images)

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

            id_item = QTableWidgetItem(str(db_id))
            id_item.setData(Qt.ItemDataRole.UserRole, path)
            id_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 0, id_item)

            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.ItemDataRole.UserRole, path)
            self.table.setItem(row, 1, name_item)

            images_item = NumericTableItem(str(total))
            images_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            images_item.setData(Qt.ItemDataRole.UserRole, total)
            self.table.setItem(row, 2, images_item)

            # Store total in UserRole+1 for formatting later
            online_item = NumericTableItem("—")
            online_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            online_item.setData(Qt.ItemDataRole.UserRole, 0)
            online_item.setData(Qt.ItemDataRole.UserRole + 1, total)  # Store total
            self.table.setItem(row, 3, online_item)

            offline_item = NumericTableItem("—")
            offline_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            offline_item.setData(Qt.ItemDataRole.UserRole, 0)
            offline_item.setData(Qt.ItemDataRole.UserRole + 1, total)  # Store total
            self.table.setItem(row, 4, offline_item)

            # Status column will be populated by set_results()
            # (table is hidden until then anyway)

        self.table.sortItems(4, Qt.SortOrder.DescendingOrder)

    def show_progress(self, visible: bool = True) -> None:
        """Show or hide the progress indicators.

        Args:
            visible: Whether to show the progress indicators
        """
        if visible:
            self.cancel_btn.setVisible(True)
            self.cancel_btn.setEnabled(True)
            self.cancel_btn.setText("Cancel")
            self.close_btn.setVisible(False)

            # Start with indeterminate bars
            self.images_bar.set_indeterminate(True)
            self.galleries_bar.set_indeterminate(True)
            self.images_status_label.setText("Scanning...")
            self.galleries_status_label.setText("Scanning...")
            self.spinner_label.setText("Checking image status...")

            # Start elapsed timer
            self._start_time = time.time()
            self._elapsed_timer.start(100)  # Update every 100ms
        else:
            self.cancel_btn.setVisible(False)
            self.close_btn.setVisible(True)
            self._elapsed_timer.stop()
            self.spinner_label.setText("")

    def _update_elapsed(self) -> None:
        """Update the elapsed time display."""
        if self._start_time > 0:
            elapsed = time.time() - self._start_time
            self.elapsed_label.setText(f"Elapsed: {elapsed:.1f}s")

    def update_progress(self, current: int, total: int) -> None:
        """Legacy method for progress updates.

        Progress is now shown via proportional bars and quick_count.
        This method exists for backward compatibility with the checker.

        Args:
            current: Current progress value (unused)
            total: Total progress value (unused)
        """
        pass  # Progress now communicated via show_quick_count() and set_results()

    def show_quick_count(self, online: int, total: int) -> None:
        """Display quick count result as soon as it's available.

        Args:
            online: Number of images found online
            total: Total images submitted for checking
        """
        if total <= 0:
            return

        offline = total - online
        pct = (online * 100) // total
        offline_pct = 100 - pct

        # Update images bar with green/red segments
        self.images_bar.set_segments([
            (online, self._colors["online"]),
            (offline, self._colors["offline"])
        ])

        # Update images status label
        self.images_status_label.setText(
            f"<span style='color:{self._colors['online'].name()}'>{online:,} online</span>, "
            f"<span style='color:{self._colors['offline'].name()}'>{offline:,} offline</span> "
            f"({pct}%)"
        )
        self.images_status_label.setTextFormat(Qt.TextFormat.RichText)

        # Update summary stats
        self.val_checked_images.setText(f"{total:,}")
        self.val_online_images.setText(f"{online:,}")
        self.pct_online_images.setText(f"({pct}%)")
        self.val_offline_images.setText(f"{offline:,}")
        self.pct_offline_images.setText(f"({offline_pct}%)")

        if online == total:
            # All online - can update galleries too
            galleries_count = self.table.rowCount()
            self.galleries_bar.set_segments([
                (galleries_count, self._colors["online"]),
                (0, self._colors["partial"]),
                (0, self._colors["offline"])
            ])
            self.galleries_status_label.setText(
                f"<span style='color:{self._colors['online'].name()}'>{galleries_count:,} online</span>"
            )
            self.galleries_status_label.setTextFormat(Qt.TextFormat.RichText)
            self.val_checked_galleries.setText(f"{galleries_count:,}")
            self.val_online_galleries.setText(f"{galleries_count:,}")
            self.pct_online_galleries.setText("(100%)")
            self.val_partial_galleries.setText("0")
            self.pct_partial_galleries.setText("(0%)")
            self.val_offline_galleries.setText("0")
            self.pct_offline_galleries.setText("(0%)")
            self.spinner_label.setText("All images online!")
        else:
            # Still scanning to identify which galleries have offline images
            self.spinner_label.setText(f"Identifying {offline:,} offline images...")

    def set_results(self, results: Dict[str, Dict[str, Any]], elapsed_time: float = 0.0) -> None:
        """Set check results and update the table.

        Args:
            results: Dict keyed by gallery path with check results
            elapsed_time: Time taken for the check in seconds
        """
        self._elapsed_timer.stop()
        colors = get_online_status_colors()
        self._results = results

        # Build path-to-row index
        path_to_row: Dict[str, int] = {}
        for row in range(self.table.rowCount()):
            id_item = self.table.item(row, 0)
            if id_item:
                path = id_item.data(Qt.ItemDataRole.UserRole)
                if path:
                    path_to_row[path] = row

        # Disable updates for performance
        self.table.setUpdatesEnabled(False)
        self.table.setSortingEnabled(False)
        self.table.blockSignals(True)

        header = self.table.horizontalHeader()
        original_modes = []
        for col in range(self.table.columnCount()):
            original_modes.append(header.sectionResizeMode(col))
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)

        try:
            # Calculate aggregates
            total_galleries = 0
            total_images = 0
            total_online = 0
            total_offline = 0
            galleries_online = 0
            galleries_partial = 0
            galleries_offline = 0

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

                if total > 0:
                    if online == total:
                        galleries_online += 1
                    elif online == 0:
                        galleries_offline += 1
                    else:
                        galleries_partial += 1

                # Update table cells with new format: "X/Y (Z%)"
                online_item = self.table.item(row, 3)
                offline_item = self.table.item(row, 4)
                status_item = self.table.item(row, 5)

                if online_item:
                    online_item.setData(Qt.ItemDataRole.UserRole, online)
                    if total > 0:
                        online_pct = online * 100 // total
                        online_item.setText(f"{online}/{total} ({online_pct}%)")
                        # Red if not 100%
                        if online < total:
                            online_item.setForeground(colors['offline'])
                            bold_font = QFont()
                            bold_font.setBold(True)
                            online_item.setFont(bold_font)
                    else:
                        online_item.setText("0/0 (0%)")
                        dim_color = QColor(128, 128, 128, 128)
                        online_item.setForeground(dim_color)

                # Update hidden offline column for sorting
                if offline_item:
                    offline_item.setData(Qt.ItemDataRole.UserRole, offline)
                    offline_item.setText(str(offline))

                # Update status with centered icon
                if total == 0:
                    self._set_centered_status(row, "No images", None, colors['gray'], 'No images')
                elif online == total:
                    self._set_centered_status(row, None, get_icon('status_online'), colors['online'], 'Online')
                else:
                    self._set_centered_status(row, None, get_icon('status_failed'), colors['offline'] if online == 0 else colors['partial'], 'Offline' if online == 0 else 'Partial')

            # Update galleries bar
            self.galleries_bar.set_segments([
                (galleries_online, colors['online']),
                (galleries_partial, colors['partial']),
                (galleries_offline, colors['offline'])
            ])

            # Update galleries status label
            gal_parts = []
            if galleries_online > 0:
                gal_parts.append(f"<span style='color:{colors['online'].name()}'>{galleries_online:,} online</span>")
            if galleries_partial > 0:
                gal_parts.append(f"<span style='color:{colors['partial'].name()}'>{galleries_partial:,} partial</span>")
            if galleries_offline > 0:
                gal_parts.append(f"<span style='color:{colors['offline'].name()}'>{galleries_offline:,} offline</span>")
            self.galleries_status_label.setText(", ".join(gal_parts))
            self.galleries_status_label.setTextFormat(Qt.TextFormat.RichText)

            # Update images bar (in case quick count wasn't available)
            self.images_bar.set_segments([
                (total_online, colors['online']),
                (total_offline, colors['offline'])
            ])

            img_pct = (total_online * 100 // total_images) if total_images else 0
            self.images_status_label.setText(
                f"<span style='color:{colors['online'].name()}'>{total_online:,} online</span>, "
                f"<span style='color:{colors['offline'].name()}'>{total_offline:,} offline</span> "
                f"({img_pct}%)"
            )
            self.images_status_label.setTextFormat(Qt.TextFormat.RichText)

            # Update all summary stats
            self.val_checked_galleries.setText(f"{total_galleries:,}")
            self.val_checked_images.setText(f"{total_images:,}")

            gal_total = total_galleries if total_galleries > 0 else 1
            self.val_online_galleries.setText(f"{galleries_online:,}")
            self.pct_online_galleries.setText(f"({galleries_online*100//gal_total}%)")
            self.val_partial_galleries.setText(f"{galleries_partial:,}")
            self.pct_partial_galleries.setText(f"({galleries_partial*100//gal_total}%)")
            self.val_offline_galleries.setText(f"{galleries_offline:,}")
            self.pct_offline_galleries.setText(f"({galleries_offline*100//gal_total}%)")

            img_total = total_images if total_images > 0 else 1
            self.val_online_images.setText(f"{total_online:,}")
            self.pct_online_images.setText(f"({total_online*100//img_total}%)")
            self.val_offline_images.setText(f"{total_offline:,}")
            self.pct_offline_images.setText(f"({total_offline*100//img_total}%)")

            # Update elapsed time with final value
            self.elapsed_label.setText(f"Elapsed: {elapsed_time:.1f}s")
            self.spinner_label.setText("Scan complete")

        finally:
            for col, mode in enumerate(original_modes):
                header.setSectionResizeMode(col, mode)

            self.table.blockSignals(False)
            self.table.setUpdatesEnabled(True)
            self.table.setSortingEnabled(True)

        # Sort and show table
        self.table.sortItems(4, Qt.SortOrder.DescendingOrder)
        self.table.setVisible(True)

        # Update buttons
        self.cancel_btn.setVisible(False)
        self.close_btn.setVisible(True)

    def _set_centered_status(self, row: int, text: str = None, icon: QIcon = None, color: QColor = None, status_type: str = None) -> None:
        """Set a centered status widget in the given row.

        Args:
            row: Table row index
            text: Text to display (if no icon)
            icon: Icon to display (takes precedence over text)
            color: Foreground color for text
            status_type: Status type for testing (e.g., 'Online', 'Partial', 'Offline', 'No images')
        """
        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if icon and not icon.isNull():
            label.setPixmap(icon.pixmap(16, 16))
        elif text:
            label.setText(text)
            if color:
                label.setStyleSheet(f"color: {color.name()};")

        # Store metadata for testing
        if status_type:
            label.setProperty("status_type", status_type)
        if color:
            label.setProperty("status_color", color)

        self.table.setCellWidget(row, 5, label)

    def _on_cancel(self) -> None:
        """Handle cancel button click."""
        self.cancelled.emit()
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("Cancelling...")

    def get_checked_timestamp(self) -> int:
        """Get current timestamp for storing in database."""
        return int(datetime.now().timestamp())

    def format_check_datetime(self, timestamp: int) -> str:
        """Format timestamp for display."""
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")

    def closeEvent(self, event) -> None:
        """Handle dialog close - ensure timers are stopped."""
        self._elapsed_timer.stop()
        self.images_bar.stop_animation()
        self.galleries_bar.stop_animation()
        super().closeEvent(event)

    def reject(self) -> None:
        """Handle dialog rejection (ESC key) - ensure timers are stopped."""
        self._elapsed_timer.stop()
        self.images_bar.stop_animation()
        self.galleries_bar.stop_animation()
        super().reject()
