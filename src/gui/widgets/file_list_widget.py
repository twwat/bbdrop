"""File list widget for the file manager.

Displays files and folders in a sortable, multi-select table with pagination.
Columns adapt to host capabilities (e.g. download count only for RapidGator).
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtCore import QSettings
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
COL_GALLERY = 5
COL_DOWNLOADS = 6
COL_LAST_DL = 7

_NUM_COLUMNS = 8


class FileListWidget(QWidget):
    """Right-pane file/folder listing table with pagination."""

    file_double_clicked = pyqtSignal(object)        # FileInfo
    selection_changed = pyqtSignal(list)             # List[FileInfo]
    page_requested = pyqtSignal(int)                 # page number
    context_menu_requested = pyqtSignal(object, object)  # QPoint, List[FileInfo]

    def __init__(self, parent=None):
        super().__init__(parent)

        self._files: List[FileInfo] = []
        self._gallery_map: dict[str, str] = {}   # file_id -> gallery name
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
        self._table.setColumnCount(_NUM_COLUMNS)
        self._table.setHorizontalHeaderLabels(
            ["Name", "Size", "Date", "Access", "Status", "Gallery", "Downloads", "Last DL"]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setDragEnabled(True)
        self._table.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setSortingEnabled(False)  # We handle sorting via API

        header = self._table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setDefaultSectionSize(100)
        self._table.setColumnWidth(COL_NAME, 280)
        self._table.setColumnWidth(COL_SIZE, 80)
        self._table.setColumnWidth(COL_DATE, 130)
        self._table.setColumnWidth(COL_ACCESS, 70)
        self._table.setColumnWidth(COL_STATUS, 90)
        self._table.setColumnWidth(COL_GALLERY, 160)
        self._table.setColumnWidth(COL_DOWNLOADS, 90)
        self._table.setColumnWidth(COL_LAST_DL, 130)
        header.setMinimumSectionSize(40)
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

    def save_column_widths(self, settings: QSettings) -> None:
        header = self._table.horizontalHeader()
        widths = [header.sectionSize(i) for i in range(_NUM_COLUMNS)]
        settings.setValue("file_list_col_widths", widths)

    def restore_column_widths(self, settings: QSettings) -> None:
        widths = settings.value("file_list_col_widths")
        if not widths:
            return
        try:
            for i, w in enumerate(widths):
                if i < _NUM_COLUMNS:
                    self._table.setColumnWidth(i, int(w))
        except (TypeError, ValueError):
            pass

    def set_gallery_map(self, mapping: dict) -> None:
        """Set the file_id -> gallery_name lookup used by the Gallery column.

        Controller calls this before (or right after) set_files with the
        result of file_manager_cache_store.lookup_galleries().
        """
        self._gallery_map = dict(mapping or {})

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

            # Size: folder rows show nb_files/nb_folders/size_files summary
            size_text = _format_size_cell(fi)
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

            # Gallery (cross-ref)
            gallery_name = self._gallery_map.get(fi.id, "")
            self._table.setItem(row, COL_GALLERY, QTableWidgetItem(gallery_name))

            # Downloads — try several known key names so any host that
            # exposes a counter populates the column without a code change.
            m = fi.metadata
            dl = (m.get("nb_downloads") if m else None) \
                or (m.get("downloads") if m else None) \
                or (m.get("download_count") if m else None)
            dl_text = str(dl) if dl not in (None, "") else ""
            dl_item = QTableWidgetItem(dl_text)
            dl_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, COL_DOWNLOADS, dl_item)

            # Last DL — K2S stashes it under extended_info.date_download_last.
            last = _extract_last_downloaded(m)
            self._table.setItem(row, COL_LAST_DL, QTableWidgetItem(last))

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
        """Show/hide a loading state.

        When the table is empty we surface a visible "Loading…" hint in
        the status label so the user knows a fetch is in flight rather
        than seeing a blank pane. When cached rows are already showing
        we deliberately leave the status alone — a silent background
        revalidation shouldn't overwrite the item-count readout.

        Callers normally follow set_loading(False) with set_files(...)
        or clear(), both of which overwrite the status. The empty-table
        branch in the ``not loading`` path is a safety net for error
        cases (worker exception, cancelled fetch) where neither runs —
        without it, "Loading…" would linger forever.
        """
        self._table.setEnabled(not loading)
        if loading and self._table.rowCount() == 0:
            self._status_label.setText("Loading…")
        elif not loading and self._table.rowCount() == 0:
            self._status_label.setText("")

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


# ---------------------------------------------------------------------------
# Module-level helpers (not methods — used by set_files and testable directly)
# ---------------------------------------------------------------------------

def _format_size_cell(fi) -> str:
    """Render the Size column text: a byte size for files, a content
    summary for folders (file count + folder count + aggregate size) when
    the host provided those numbers."""
    if not fi.is_folder:
        return format_binary_size(fi.size)

    m = fi.metadata or {}
    nb_files = m.get("nb_files")
    nb_folders = m.get("nb_folders")
    size_files = m.get("size_files")
    parts = []
    if nb_files is not None:
        parts.append(f"{nb_files} files")
    if nb_folders:
        parts.append(f"{nb_folders} folders")
    if size_files:
        parts.append(format_binary_size(int(size_files)))
    return " · ".join(parts)


def _extract_last_downloaded(metadata: dict) -> str:
    """Find the last-downloaded timestamp wherever a host might have stashed it.

    Checks top-level and nested extended_info for known key names. Returns
    a short string or empty string."""
    if not metadata:
        return ""
    # Top-level fallbacks first.
    for key in ("last_downloaded", "date_download_last"):
        val = metadata.get(key)
        if val:
            return str(val)
    # K2S nests it under extended_info.
    ext = metadata.get("extended_info") or {}
    for key in ("date_download_last", "last_downloaded"):
        val = ext.get(key) if isinstance(ext, dict) else None
        if val:
            return str(val)
    return ""
