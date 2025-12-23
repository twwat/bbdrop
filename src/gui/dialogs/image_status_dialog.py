#!/usr/bin/env python3
"""
Image Status Dialog
Shows results of checking image online status on IMX.to
"""

from typing import List, Dict, Any, Optional
from datetime import datetime

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QLabel, QProgressBar, QWidget,
    QAbstractItemView, QTreeWidget, QTreeWidgetItem, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

from src.utils.logger import log


class ImageStatusDialog(QDialog):
    """Dialog showing image online status check results.

    Displays a sortable table with columns:
    - DB ID: Gallery database ID
    - Name: Gallery name
    - Images: Total image count
    - Online: Count of online images
    - Offline: Count of offline images
    - Status: Summary text (Online/Partial/Offline with counts)

    For partial status galleries, shows expandable per-image details.
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
        self.summary_label = QLabel("Select galleries and click 'Check Status' to verify images are online.")
        self.summary_label.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(self.summary_label)

        # Progress bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

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
        self.table.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.table)

        # Details panel for offline images (hidden by default)
        self.details_widget = QWidget()
        details_layout = QVBoxLayout(self.details_widget)
        details_layout.setContentsMargins(0, 0, 0, 0)

        self.details_label = QLabel("Offline Images:")
        self.details_label.setStyleSheet("font-weight: bold;")
        details_layout.addWidget(self.details_label)

        self.details_tree = QTreeWidget()
        self.details_tree.setHeaderLabels(["Gallery", "Offline Image URLs"])
        self.details_tree.setAlternatingRowColors(True)
        self.details_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.details_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        details_layout.addWidget(self.details_tree)

        self.details_widget.setVisible(False)
        layout.addWidget(self.details_widget)

        # Buttons
        button_layout = QHBoxLayout()

        self.toggle_details_btn = QPushButton("Show Offline Details")
        self.toggle_details_btn.setEnabled(False)
        self.toggle_details_btn.clicked.connect(self._toggle_details)
        button_layout.addWidget(self.toggle_details_btn)

        button_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.cancel_btn.setVisible(False)  # Hidden until check starts
        button_layout.addWidget(self.cancel_btn)

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

            # Images (total)
            images_item = QTableWidgetItem(str(total))
            images_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 2, images_item)

            # Online (pending)
            online_item = QTableWidgetItem("...")
            online_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 3, online_item)

            # Offline (pending)
            offline_item = QTableWidgetItem("...")
            offline_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 4, offline_item)

            # Status (pending)
            status_item = QTableWidgetItem("Pending...")
            self.table.setItem(row, 5, status_item)

    def show_progress(self, visible: bool = True) -> None:
        """Show or hide the progress bar.

        Args:
            visible: Whether to show the progress bar
        """
        self.progress_bar.setVisible(visible)
        self.cancel_btn.setVisible(visible)
        if visible:
            self.cancel_btn.setEnabled(True)
            self.cancel_btn.setText("Cancel")
            self.progress_bar.setRange(0, 0)  # Indeterminate

    def update_progress(self, current: int, total: int) -> None:
        """Update progress bar.

        Args:
            current: Current progress value
            total: Total progress value
        """
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)

    def set_results(self, results: Dict[str, Dict[str, Any]]) -> None:
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
        """
        self._results = results
        self.progress_bar.setVisible(False)
        self.cancel_btn.setVisible(False)

        # Update table with results
        total_galleries = 0
        total_online = 0
        total_offline = 0
        has_offline = False

        for row in range(self.table.rowCount()):
            id_item = self.table.item(row, 0)
            if not id_item:
                continue

            path = id_item.data(Qt.ItemDataRole.UserRole)
            if path not in results:
                continue

            result = results[path]
            total_galleries += 1
            online = result.get('online', 0)
            offline = result.get('offline', 0)
            total = result.get('total', 0)

            total_online += online
            total_offline += offline

            if offline > 0:
                has_offline = True

            # Update Online column
            online_item = self.table.item(row, 3)
            if online_item:
                online_item.setText(str(online))

            # Update Offline column
            offline_item = self.table.item(row, 4)
            if offline_item:
                offline_item.setText(str(offline))

            # Update Status column with color coding
            status_item = self.table.item(row, 5)
            if status_item:
                if total == 0:
                    status_text = "No images"
                    color = QColor(128, 128, 128)  # Gray
                elif online == total:
                    status_text = f"Online ({online}/{total})"
                    color = QColor(0, 128, 0)  # Green
                elif online == 0:
                    status_text = f"Offline (0/{total})"
                    color = QColor(200, 0, 0)  # Red
                else:
                    status_text = f"Partial ({online}/{total})"
                    color = QColor(200, 150, 0)  # Yellow/Orange

                status_item.setText(status_text)
                status_item.setForeground(color)

        # Update summary
        self.summary_label.setText(
            f"Checked {total_galleries} galleries: "
            f"{total_online} images online, {total_offline} offline"
        )

        # Enable details button if there are offline images
        self.toggle_details_btn.setEnabled(has_offline)

        # Populate details tree with offline URLs
        self._populate_details_tree()

    def _populate_details_tree(self) -> None:
        """Populate the details tree with offline image URLs."""
        self.details_tree.clear()

        for path, result in self._results.items():
            offline_urls = result.get('offline_urls', [])
            if not offline_urls:
                continue

            gallery_name = result.get('name', path)

            # Create gallery item
            gallery_item = QTreeWidgetItem([gallery_name, f"{len(offline_urls)} offline"])
            gallery_item.setExpanded(True)

            # Add offline URLs as children
            for url in offline_urls:
                url_item = QTreeWidgetItem(["", url])
                gallery_item.addChild(url_item)

            self.details_tree.addTopLevelItem(gallery_item)

    def _toggle_details(self) -> None:
        """Toggle visibility of the details panel."""
        visible = not self.details_widget.isVisible()
        self.details_widget.setVisible(visible)
        self.toggle_details_btn.setText("Hide Offline Details" if visible else "Show Offline Details")

        # Resize dialog to accommodate details
        if visible:
            self.resize(self.width(), 650)
        else:
            self.resize(self.width(), 500)

    def _on_cancel(self) -> None:
        """Handle cancel button click."""
        self.cancelled.emit()
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("Cancelling...")

    def _on_item_double_clicked(self, item: QTableWidgetItem) -> None:
        """Handle double-click on table item.

        Args:
            item: The table widget item that was double-clicked
        """
        row = item.row()
        id_item = self.table.item(row, 0)
        if not id_item:
            return

        path = id_item.data(Qt.ItemDataRole.UserRole)
        if path in self._results:
            result = self._results[path]
            offline_urls = result.get('offline_urls', [])
            if offline_urls:
                # Show details and expand to this gallery
                if not self.details_widget.isVisible():
                    self._toggle_details()

                # Find and select the gallery in the tree
                gallery_name = result.get('name', path)
                for i in range(self.details_tree.topLevelItemCount()):
                    tree_item = self.details_tree.topLevelItem(i)
                    if tree_item and tree_item.text(0) == gallery_name:
                        self.details_tree.setCurrentItem(tree_item)
                        tree_item.setExpanded(True)
                        break

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
