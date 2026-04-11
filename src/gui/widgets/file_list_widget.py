"""File list widget for the file manager.

Displays files and folders in a sortable, multi-select table with pagination.
Columns adapt to host capabilities (e.g. download count only for RapidGator).
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.network.file_manager.client import FileInfo, FileListResult, FileManagerCapabilities
from src.utils.format_utils import format_binary_size


# Column indices
COL_NAME = 0
COL_SIZE = 1
COL_DATE = 2
COL_ACCESS = 3
COL_STATUS = 4


class FileListWidget(QWidget):
    """Right-pane file/folder listing table with pagination."""

    file_double_clicked = pyqtSignal(object)        # FileInfo
    selection_changed = pyqtSignal(list)             # List[FileInfo]
    page_requested = pyqtSignal(int)                 # page number
    context_menu_requested = pyqtSignal(object, object)  # QPoint, List[FileInfo]

    def __init__(self, parent=None):
        super().__init__(parent)

        self._files: List[FileInfo] = []
        self._current_page = 1
        self._total_pages = 1
        self._total_items = 0
        self._per_page = 100
        self._sort_by = "name"
        self._sort_dir = "asc"

        self._folder_icon = self.style().standardIcon(
            self.style().StandardPixmap.SP_DirIcon
        )
        self._file_icon = self.style().standardIcon(
            self.style().StandardPixmap.SP_FileIcon
        )

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["Name", "Size", "Date", "Access", "Status"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setDragEnabled(True)
        self._table.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setSortingEnabled(False)  # We handle sorting via API

        header = self._table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_SIZE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_DATE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_ACCESS, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeMode.ResizeToContents)
        header.sectionClicked.connect(self._on_header_clicked)

        self._table.doubleClicked.connect(self._on_double_click)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)

        layout.addWidget(self._table)

        # Pagination bar
        pag_layout = QHBoxLayout()
        pag_layout.setContentsMargins(4, 0, 4, 0)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: palette(placeholder-text);")
        pag_layout.addWidget(self._status_label)

        pag_layout.addStretch()

        self._btn_prev = QPushButton("<")
        self._btn_prev.setFixedWidth(30)
        self._btn_prev.clicked.connect(lambda: self.page_requested.emit(self._current_page - 1))
        pag_layout.addWidget(self._btn_prev)

        self._page_label = QLabel("1 / 1")
        pag_layout.addWidget(self._page_label)

        self._btn_next = QPushButton(">")
        self._btn_next.setFixedWidth(30)
        self._btn_next.clicked.connect(lambda: self.page_requested.emit(self._current_page + 1))
        pag_layout.addWidget(self._btn_next)

        layout.addLayout(pag_layout)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_files(self, result: FileListResult):
        """Populate the table from an API response."""
        self._files = result.files
        self._current_page = result.page
        self._per_page = result.per_page
        self._total_items = result.total
        self._total_pages = max(1, (result.total + result.per_page - 1) // result.per_page)

        self._table.setRowCount(0)
        self._table.setRowCount(len(result.files))

        for row, fi in enumerate(result.files):
            # Name
            name_item = QTableWidgetItem(fi.name)
            name_item.setIcon(self._folder_icon if fi.is_folder else self._file_icon)
            name_item.setData(Qt.ItemDataRole.UserRole, fi)
            self._table.setItem(row, COL_NAME, name_item)

            # Size
            size_text = "" if fi.is_folder else format_binary_size(fi.size)
            size_item = QTableWidgetItem(size_text)
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, COL_SIZE, size_item)

            # Date
            date_text = fi.created.strftime("%Y-%m-%d %H:%M") if fi.created else ""
            self._table.setItem(row, COL_DATE, QTableWidgetItem(date_text))

            # Access
            self._table.setItem(row, COL_ACCESS, QTableWidgetItem(fi.access))

            # Status
            status_text = "Available" if fi.is_available else "Unavailable"
            status_item = QTableWidgetItem(status_text)
            if not fi.is_available:
                status_item.setForeground(Qt.GlobalColor.red)
            self._table.setItem(row, COL_STATUS, status_item)

        # Update pagination
        self._page_label.setText(f"{self._current_page} / {self._total_pages}")
        self._btn_prev.setEnabled(self._current_page > 1)
        self._btn_next.setEnabled(self._current_page < self._total_pages)
        status_parts = [f"{self._total_items} items"]
        if self._total_pages > 1:
            status_parts.append("sort applies to current page only")
        self._status_label.setText("  •  ".join(status_parts))

    def get_selected_files(self) -> List[FileInfo]:
        """Return FileInfo objects for all selected rows."""
        selected = []
        for index in self._table.selectionModel().selectedRows():
            item = self._table.item(index.row(), COL_NAME)
            if item:
                fi = item.data(Qt.ItemDataRole.UserRole)
                if fi:
                    selected.append(fi)
        return selected

    def clear(self):
        self._table.setRowCount(0)
        self._files = []
        self._status_label.setText("")
        self._page_label.setText("1 / 1")
        self._btn_prev.setEnabled(False)
        self._btn_next.setEnabled(False)

    def set_loading(self, loading: bool):
        """Show/hide a loading state."""
        self._table.setEnabled(not loading)

    # ------------------------------------------------------------------
    # Sort column mapping
    # ------------------------------------------------------------------

    _COLUMN_SORT_MAP = {
        COL_NAME: "name",
        COL_SIZE: "size",
        COL_DATE: "date_created",
        COL_ACCESS: "access",
    }

    def _on_header_clicked(self, logical_index: int):
        sort_key = self._COLUMN_SORT_MAP.get(logical_index)
        if not sort_key:
            return
        if sort_key == self._sort_by:
            self._sort_dir = "desc" if self._sort_dir == "asc" else "asc"
        else:
            self._sort_by = sort_key
            self._sort_dir = "asc"
        self._resort_current_files()

    def _resort_current_files(self):
        """Sort the currently loaded files client-side and repopulate the table.

        Folders always stay grouped at the top, with files below.
        Sort direction applies within each group.
        """
        if not self._files:
            return

        reverse = self._sort_dir == "desc"

        def inner_key(fi):
            if self._sort_by == "name":
                return fi.name.lower()
            if self._sort_by == "size":
                return fi.size or 0
            if self._sort_by == "date_created":
                return fi.created.timestamp() if fi.created else 0.0
            if self._sort_by == "access":
                return (fi.access or "").lower()
            return fi.name.lower()

        folders = sorted((f for f in self._files if f.is_folder), key=inner_key, reverse=reverse)
        files = sorted((f for f in self._files if not f.is_folder), key=inner_key, reverse=reverse)

        # Let set_files be the single source of truth for self._files
        result = FileListResult(
            files=folders + files,
            total=self._total_items,
            page=self._current_page,
            per_page=self._per_page,
        )
        self.set_files(result)

    # ------------------------------------------------------------------
    # Interaction handlers
    # ------------------------------------------------------------------

    def _on_double_click(self, index):
        item = self._table.item(index.row(), COL_NAME)
        if item:
            fi = item.data(Qt.ItemDataRole.UserRole)
            if fi:
                self.file_double_clicked.emit(fi)

    def _on_selection_changed(self):
        self.selection_changed.emit(self.get_selected_files())

    def _on_context_menu(self, pos):
        selected = self.get_selected_files()
        global_pos = self._table.viewport().mapToGlobal(pos)
        self.context_menu_requested.emit(global_pos, selected)
