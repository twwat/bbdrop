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
    QProgressBar,
    QSizePolicy,
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

    def __init__(self, parent=None, host_id: Optional[str] = None):
        super().__init__(parent)
        self.setWindowTitle("File Manager")
        self.setModal(False)
        self.setMinimumSize(900, 600)
        self.resize(1100, 700)
        self._center_on_parent()

        self._setup_ui()

        # Initialize status-timer slot before anything can call show_status.
        # _restore_state() below triggers setCurrentIndex on the host combo,
        # which fires _on_host_changed → set_host → show_status synchronously,
        # so _status_timer must already exist by then.
        self._status_timer: Optional[QTimer] = None

        # Controller handles all logic
        self._controller = FileManagerController(self)

        # Wire signals
        self._connect_signals()

        # Keyboard shortcuts
        self._setup_shortcuts()

        # Settings persistence
        self._settings = QSettings("BBDropUploader", "BBDropGUI")
        self._restore_state()

        # Pre-select requested host if provided (overrides restored last-host).
        # Block signals so this doesn't trigger an extra _on_host_changed call —
        # the QTimer.singleShot below will fire once on the final (preselected)
        # state.
        if host_id:
            idx = self._host_combo.findData(host_id)
            if idx >= 0:
                self._host_combo.blockSignals(True)
                self._host_combo.setCurrentIndex(idx)
                self._host_combo.blockSignals(False)

        # Auto-select first available host
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

        self._storage_bar = QProgressBar()
        self._storage_bar.setMinimumWidth(280)
        self._storage_bar.setMaximumHeight(20)
        self._storage_bar.setMaximum(100)
        self._storage_bar.setValue(0)
        self._storage_bar.setTextVisible(True)
        self._storage_bar.setFormat("")
        self._storage_bar.setProperty("class", "storage-bar")
        self._storage_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._storage_bar.setVisible(False)
        top_layout.addWidget(self._storage_bar)

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
        self.folder_tree.children_requested.connect(c.load_children)
        self.folder_tree.files_dropped.connect(c.on_files_dropped)

        # File list
        self.file_list.file_double_clicked.connect(c.on_file_double_clicked)
        self.file_list.selection_changed.connect(c.on_selection_changed)
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

        # Filedot-style properties + flag actions
        self.toolbar.properties_clicked.connect(c.edit_properties_selected)
        self.toolbar.set_public_clicked.connect(c.set_public_selected)
        self.toolbar.set_premium_clicked.connect(c.set_premium_selected)

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
        """Handle toolbar filter input changes."""
        self._apply_filter(text)

    def reapply_filter(self):
        """Re-apply the current filter — called after file list updates."""
        self._apply_filter(self.toolbar.get_filter_text())

    def _apply_filter(self, text: str):
        """Client-side filter — hide non-matching rows."""
        text = (text or "").lower()
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
        # Pass the current selection so we can open the specific file's
        # web page instead of dumping the user onto /myfiles.
        menu.addAction(
            "Open in Browser",
            lambda: self.open_in_browser(selected),
        )

        menu.exec(pos)

    # ------------------------------------------------------------------
    # Public API (called by controller)
    # ------------------------------------------------------------------

    def update_account_info(self, info: dict):
        """Update account info display — storage bar + adjacent label."""
        from src.utils.format_utils import format_binary_size

        # --- Storage bar ---
        storage_total = info.get("storage_total")
        storage_left = info.get("storage_left")
        storage_used_direct = info.get("storage_used")

        total = int(storage_total) if storage_total else 0
        left = int(storage_left) if storage_left else 0

        # Filedot returns storage_used directly; compute left from it if needed
        if storage_used_direct is not None and not storage_total:
            # Only used available — can't fill the bar meaningfully; hide it
            total = 0
            left = 0

        has_storage = total > 0 and left >= 0 and left <= total
        if has_storage:
            used = total - left
            percent_used = int((used / total) * 100)
            percent_free = 100 - percent_used

            left_formatted = format_binary_size(left)
            total_formatted = format_binary_size(total)
            used_formatted = format_binary_size(used)

            compact_format = self._format_storage_compact(left, total)

            self._storage_bar.setValue(percent_free)
            self._storage_bar.setFormat(compact_format)

            tooltip = (
                f"Storage: {left_formatted} free / {total_formatted} total\n"
                f"Used: {used_formatted} ({percent_used}%)"
            )
            self._storage_bar.setToolTip(tooltip)

            # Color coding matching file_hosts_tab
            if percent_used >= 90:
                self._storage_bar.setProperty("storage_status", "low")
            elif percent_used >= 75:
                self._storage_bar.setProperty("storage_status", "medium")
            else:
                self._storage_bar.setProperty("storage_status", "plenty")

            self._storage_bar.style().unpolish(self._storage_bar)
            self._storage_bar.style().polish(self._storage_bar)
            self._storage_bar.setVisible(True)
        else:
            self._storage_bar.setVisible(False)

        # --- Adjacent label: premium status + expiry ---
        label_parts = []
        is_premium = info.get("is_premium")
        if is_premium is not None:
            label_parts.append("Premium" if is_premium else "Free")
        expires = info.get("account_expires")
        if expires:
            label_parts.append(f"Expires: {expires}")
        self._account_label.setText("  |  ".join(label_parts) if label_parts else "")

    def _format_storage_compact(self, left: int, total: int) -> str:
        """Return compact storage string, e.g. '15.2 GiB free'."""
        from src.utils.format_utils import format_binary_size
        if total <= 0:
            return "N/A"
        return f"{format_binary_size(left)} free"

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
        self.file_list.restore_column_widths(self._settings)
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
        self.file_list.save_column_widths(self._settings)
        host_id = self._host_combo.currentData()
        if host_id:
            self._settings.setValue("last_host", host_id)
        self._settings.endGroup()

    # ------------------------------------------------------------------
    # Open in browser
    # ------------------------------------------------------------------

    # Per-host URL builders for the "Open in Browser" action. When exactly
    # one file is selected we open its public file page; otherwise we fall
    # back to the host's "my files" dashboard. The domains differ across
    # the K2S family even though they share an API client.
    _MYFILES_URLS = {
        "keep2share": "https://k2s.cc/myfiles",
        "fileboom": "https://fboom.me/myfiles",
        "tezfiles": "https://tezfiles.com/myfiles",
        "rapidgator": "https://rapidgator.net/myfiles",
        "katfile": "https://katfile.cloud/?op=my_files",
        "filespace": "https://filespace.com/?op=my_files",
        "filedot": "https://filedot.to/?op=my_files",
    }
    _FILE_URL_BUILDERS = {
        "keep2share": lambda fid: f"https://k2s.cc/file/{fid}",
        "fileboom": lambda fid: f"https://fboom.me/file/{fid}",
        "tezfiles": lambda fid: f"https://tezfiles.com/file/{fid}",
        "rapidgator": lambda fid: f"https://rapidgator.net/file/{fid}",
        "katfile": lambda fid: f"https://katfile.cloud/{fid}",
        "filespace": lambda fid: f"https://filespace.com/{fid}",
        "filedot": lambda fid: f"https://filedot.to/{fid}",
    }

    def open_in_browser(self, selected=None):
        """Open the selected file's web page, or fall back to /myfiles.

        Args:
            selected: Optional list of FileInfo. When it contains exactly
                one non-folder entry, we open that file's public page
                (useful to verify the listing is still live). Any other
                shape — empty, multi-select, folder, or None — falls
                through to the host's my-files dashboard.
        """
        import webbrowser

        host_id = self._host_combo.currentData()
        if not host_id:
            return

        if selected and len(selected) == 1 and not selected[0].is_folder:
            builder = self._FILE_URL_BUILDERS.get(host_id)
            if builder:
                webbrowser.open(builder(selected[0].id))
                return

        url = self._MYFILES_URLS.get(host_id, "")
        if url:
            webbrowser.open(url)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        self._save_state()
        self._controller.shutdown()
        super().closeEvent(event)
