"""File Manager Dialog.

Non-modal dialog for browsing and managing files on remote file hosts.
Layout: host selector + account bar on top, toolbar, then a split pane
with folder tree (left) and file list (right).
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QVBoxLayout,
)

from PyQt6.QtCore import QSettings

from src.gui.file_manager_controller import FileManagerController
from src.gui.widgets.file_list_widget import FileListWidget
from src.gui.widgets.file_manager_toolbar import FileManagerToolbar
from src.gui.widgets.folder_tree_widget import FolderTreeWidget
from src.network.file_manager.factory import get_supported_hosts
from src.core.host_registry import get_display_name
from src.utils.logger import log


class FileManagerDialog(QDialog):
    """Non-modal file manager dialog for remote file hosts.

    The dialog is a layout shell — all logic lives in FileManagerController.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("File Manager")
        self.setModal(False)
        self.setMinimumSize(900, 600)
        self.resize(1100, 700)
        self._center_on_parent()

        self._setup_ui()

        # Controller handles all logic
        self._controller = FileManagerController(self)

        # Wire signals
        self._connect_signals()

        # Keyboard shortcuts
        self._setup_shortcuts()

        # Settings persistence
        self._settings = QSettings("BBDropUploader", "BBDropGUI")
        self._restore_state()

        # Auto-select first available host
        self._status_timer: Optional[QTimer] = None
        if self._host_combo.count() > 0:
            QTimer.singleShot(0, self._on_host_changed)

    def _center_on_parent(self):
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

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # -- Top bar: host selector + account info --
        top_layout = QHBoxLayout()

        top_layout.addWidget(QLabel("Host:"))
        self._host_combo = QComboBox()
        self._host_combo.setMinimumWidth(160)
        for host_id in get_supported_hosts():
            display = get_display_name(host_id)
            self._host_combo.addItem(display, host_id)
        top_layout.addWidget(self._host_combo)

        top_layout.addSpacing(16)

        self._account_label = QLabel("")
        self._account_label.setStyleSheet("color: palette(placeholder-text);")
        top_layout.addWidget(self._account_label)

        top_layout.addStretch()

        layout.addLayout(top_layout)

        # -- Toolbar --
        self.toolbar = FileManagerToolbar()
        layout.addWidget(self.toolbar)

        # -- Split pane: folder tree | file list --
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.folder_tree = FolderTreeWidget()
        self.folder_tree.setMinimumWidth(180)
        self.folder_tree.setMaximumWidth(350)
        splitter.addWidget(self.folder_tree)

        self.file_list = FileListWidget()
        splitter.addWidget(self.file_list)

        splitter.setStretchFactor(0, 0)  # tree: fixed
        splitter.setStretchFactor(1, 1)  # list: stretch
        splitter.setSizes([220, 780])

        layout.addWidget(splitter, 1)

        # -- Status bar --
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(
            "color: palette(placeholder-text); padding: 2px 4px;"
        )
        layout.addWidget(self._status_label)

    def _connect_signals(self):
        c = self._controller

        # Host switching
        self._host_combo.currentIndexChanged.connect(self._on_host_changed)

        # Folder tree
        self.folder_tree.folder_selected.connect(c.navigate_to)
        self.folder_tree.files_dropped.connect(c.on_files_dropped)

        # File list
        self.file_list.file_double_clicked.connect(c.on_file_double_clicked)
        self.file_list.selection_changed.connect(c.on_selection_changed)
        self.file_list.sort_requested.connect(c.on_sort_requested)
        self.file_list.page_requested.connect(c.on_page_requested)
        self.file_list.context_menu_requested.connect(self._show_context_menu)

        # Toolbar navigation
        self.toolbar.back_clicked.connect(c.go_back)
        self.toolbar.up_clicked.connect(c.go_up)
        self.toolbar.root_clicked.connect(c.go_root)
        self.toolbar.refresh_clicked.connect(c.refresh)

        # Toolbar actions
        self.toolbar.new_folder_clicked.connect(c.create_folder)
        self.toolbar.delete_clicked.connect(c.delete_selected)
        self.toolbar.rename_clicked.connect(c.rename_selected)
        self.toolbar.move_clicked.connect(c.move_selected)
        self.toolbar.copy_clicked.connect(c.copy_selected)
        self.toolbar.copy_link_clicked.connect(c.copy_link)
        self.toolbar.change_access_clicked.connect(c.change_access)

        # Trash actions
        self.toolbar.trash_toggled.connect(c.toggle_trash)
        self.toolbar.trash_restore_clicked.connect(c.trash_restore)
        self.toolbar.trash_empty_clicked.connect(c.trash_empty)

        # Toolbar filter
        self.toolbar.filter_changed.connect(self._on_filter_changed)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_host_changed(self):
        host_id = self._host_combo.currentData()
        if host_id:
            self._controller.set_host(host_id)

    def _on_filter_changed(self, text: str):
        """Client-side filter — hide non-matching rows."""
        text = text.lower()
        table = self.file_list._table
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item:
                name = item.text().lower()
                table.setRowHidden(row, bool(text) and text not in name)

    def _show_context_menu(self, pos, selected):
        """Show right-click context menu for files."""
        if not selected:
            return

        from PyQt6.QtWidgets import QMenu

        menu = QMenu(self)
        c = self._controller
        caps = self._controller._capabilities.get(self._controller._current_host)

        if len(selected) == 1:
            fi = selected[0]
            if fi.is_folder:
                menu.addAction("Open", lambda: c.on_file_double_clicked(fi))
                menu.addSeparator()

            if caps and caps.can_rename:
                menu.addAction("Rename", c.rename_selected)

            if not fi.is_folder and caps and caps.can_get_download_link:
                menu.addAction("Copy Link", c.copy_link)

            menu.addAction("Details", lambda: c.show_file_details(selected))

        if caps and caps.can_move and not c._in_trash:
            menu.addAction("Move To...", c.move_selected)

        if caps and caps.can_copy and not c._in_trash:
            menu.addAction("Copy To...", c.copy_selected)

        if caps and caps.can_change_access and not c._in_trash:
            menu.addAction("Change Access", c.change_access)

        menu.addSeparator()

        if c._in_trash:
            if caps and caps.can_trash:
                menu.addAction("Restore", c.trash_restore)
        elif caps and caps.can_delete:
            delete_action = menu.addAction("Delete", c.delete_selected)
            delete_action.setShortcut("Delete")

        menu.addSeparator()
        menu.addAction("Open in Browser", self.open_in_browser)

        menu.exec(pos)

    # ------------------------------------------------------------------
    # Public API (called by controller)
    # ------------------------------------------------------------------

    def update_account_info(self, info: dict):
        """Update account info display."""
        from src.utils.format_utils import format_binary_size
        parts = []

        # RapidGator storage info
        storage_total = info.get("storage_total")
        storage_left = info.get("storage_left")
        if storage_total and storage_left:
            used = int(storage_total) - int(storage_left)
            parts.append(f"Storage: {format_binary_size(used)} / {format_binary_size(int(storage_total))}")
        elif storage_left:
            parts.append(f"Storage free: {format_binary_size(int(storage_left))}")

        # K2S traffic
        traffic = info.get("available_traffic")
        if traffic:
            parts.append(f"Traffic: {format_binary_size(int(traffic))}")

        # Account expiry
        expires = info.get("account_expires")
        if expires:
            parts.append(f"Expires: {expires}")

        # Premium status
        is_premium = info.get("is_premium")
        if is_premium is not None:
            parts.append("Premium" if is_premium else "Free")

        self._account_label.setText("  |  ".join(parts) if parts else "")

    def show_status(self, message: str, error: bool = False):
        """Show a status message that auto-clears."""
        color = "red" if error else "palette(placeholder-text)"
        self._status_label.setStyleSheet(f"color: {color}; padding: 2px 4px;")
        self._status_label.setText(message)

        # Auto-clear after 5 seconds
        if self._status_timer:
            self._status_timer.stop()
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(lambda: self._status_label.setText(""))
        self._status_timer.start(5000)

    # ------------------------------------------------------------------
    # Keyboard shortcuts
    # ------------------------------------------------------------------

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Delete"), self).activated.connect(
            self._controller.delete_selected
        )
        QShortcut(QKeySequence("F2"), self).activated.connect(
            self._controller.rename_selected
        )
        QShortcut(QKeySequence("F5"), self).activated.connect(
            self._controller.refresh
        )
        QShortcut(QKeySequence("Ctrl+C"), self).activated.connect(
            self._controller.copy_link
        )
        QShortcut(QKeySequence("Backspace"), self).activated.connect(
            self._controller.go_back
        )
        QShortcut(QKeySequence("Alt+Up"), self).activated.connect(
            self._controller.go_up
        )

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _restore_state(self):
        self._settings.beginGroup("FileManager")
        geo = self._settings.value("geometry")
        if geo:
            self.restoreGeometry(geo)
        splitter_state = self._settings.value("splitter")
        if splitter_state:
            splitter = self.findChild(QSplitter)
            if splitter:
                splitter.restoreState(splitter_state)
        last_host = self._settings.value("last_host")
        if last_host:
            idx = self._host_combo.findData(last_host)
            if idx >= 0:
                self._host_combo.setCurrentIndex(idx)
        self._settings.endGroup()

    def _save_state(self):
        self._settings.beginGroup("FileManager")
        self._settings.setValue("geometry", self.saveGeometry())
        splitter = self.findChild(QSplitter)
        if splitter:
            self._settings.setValue("splitter", splitter.saveState())
        host_id = self._host_combo.currentData()
        if host_id:
            self._settings.setValue("last_host", host_id)
        self._settings.endGroup()

    # ------------------------------------------------------------------
    # Open in browser
    # ------------------------------------------------------------------

    def open_in_browser(self, file_id: str = ""):
        """Open the host's web file manager in the default browser."""
        import webbrowser

        host_id = self._host_combo.currentData()
        urls = {
            "keep2share": "https://k2s.cc/myfiles",
            "fileboom": "https://fboom.me/myfiles",
            "tezfiles": "https://tezfiles.com/myfiles",
            "rapidgator": "https://rapidgator.net/myfiles",
            "katfile": "https://katfile.cloud/?op=my_files",
            "filespace": "https://filespace.com/?op=my_files",
            "filedot": "https://filedot.to/?op=my_files",
        }
        url = urls.get(host_id, "")
        if url:
            webbrowser.open(url)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        self._save_state()
        self._controller.shutdown()
        super().closeEvent(event)
