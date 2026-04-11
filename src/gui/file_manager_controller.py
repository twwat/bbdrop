"""Controller for the file manager dialog.

Bridges the GUI widgets with the background worker. Handles navigation
state, caching, and operation dispatch. All business logic lives here —
the dialog is a pure layout shell.
"""

from __future__ import annotations

import time
import uuid
from collections import OrderedDict
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from PyQt6.QtCore import QObject, QTimer, Qt
from PyQt6.QtWidgets import QApplication, QInputDialog, QMessageBox

from src.network.file_manager.client import (
    BatchResult,
    FileInfo,
    FileListResult,
    FileManagerCapabilities,
    FolderListResult,
    OperationResult,
)
from src.network.file_manager.factory import get_supported_hosts, is_host_supported
from src.processing.file_manager_worker import FileManagerWorker
from src.utils.logger import log

if TYPE_CHECKING:
    from src.gui.dialogs.file_manager_dialog import FileManagerDialog

# Cache TTL in seconds and max size (LRU eviction when exceeded)
_CACHE_TTL = 60.0
_CACHE_MAX_ENTRIES = 256


class FileManagerController(QObject):
    """Orchestrates file manager operations between GUI and worker."""

    _TRASH_KEY = "__trash__"  # sentinel folder-id for trash view

    def __init__(self, dialog: 'FileManagerDialog'):
        super().__init__(dialog)
        self._dialog = dialog

        # State per host
        self._current_host: Optional[str] = None
        self._current_folder: str = "/"
        self._current_page: int = 1
        self._sort_by: str = "name"
        self._sort_dir: str = "asc"
        self._per_page: int = 100

        # Navigation history (per host)
        self._history: Dict[str, List[str]] = {}      # host_id -> [folder_ids]
        self._host_folder: Dict[str, str] = {}         # host_id -> last folder
        self._capabilities: Dict[str, FileManagerCapabilities] = {}

        # Cache: (host_id, folder_id) -> (FileListResult, timestamp)
        self._file_cache: "OrderedDict[Tuple[str, str], Tuple[FileListResult, float]]" = OrderedDict()
        # Folder tree cache: (host_id, parent_id) -> (List[FileInfo], timestamp)
        self._folder_cache: "OrderedDict[Tuple[str, str], Tuple[List[FileInfo], float]]" = OrderedDict()

        # Breadcrumb: current path as [(id, name), ...]
        self._breadcrumb: List[Tuple[str, str]] = []
        self._in_trash: bool = False

        # Worker
        self._worker = FileManagerWorker()
        self._worker.files_loaded.connect(self._on_files_loaded)
        self._worker.folders_loaded.connect(self._on_folders_loaded)
        self._worker.file_info_loaded.connect(self._on_file_info_loaded)
        self._worker.operation_complete.connect(self._on_operation_complete)
        self._worker.account_info_loaded.connect(self._on_account_info)
        self._worker.error.connect(self._on_error)
        self._worker.loading.connect(self._on_loading)
        self._worker.start()

        # Pending operation tracking
        self._pending_ops: Dict[str, str] = {}  # op_id -> action name
        self._pending_folder_parents: Dict[str, Tuple[str, str]] = {}  # op_id -> (host_id, parent_id)
        self._pending_file_folders: Dict[str, Tuple[str, str]] = {}   # op_id -> (host_id, folder_id)

        # Error popup dedup/throttle
        self._last_error_key: Optional[Tuple[str, str]] = None
        self._last_error_time: float = 0.0

    def shutdown(self):
        """Stop the worker thread."""
        self._worker.stop()
        self._worker.wait(3000)

    # ------------------------------------------------------------------
    # Host switching
    # ------------------------------------------------------------------

    def set_host(self, host_id: str):
        """Switch to a different host."""
        if host_id == self._current_host:
            return

        self._current_host = host_id
        self._pending_ops.clear()
        self._pending_folder_parents.clear()
        self._pending_file_folders.clear()

        # Restore last folder for this host, or start at root
        self._current_folder = self._host_folder.get(host_id, "/")
        self._current_page = 1
        self._breadcrumb = [("/", "/")]

        # Get capabilities (may be cached)
        if host_id in self._capabilities:
            self._dialog.toolbar.update_capabilities(self._capabilities[host_id])
        else:
            caps = self._get_client_capabilities(host_id)
            if caps:
                self._capabilities[host_id] = caps
                self._dialog.toolbar.update_capabilities(caps)

        # Load root
        self._dialog.folder_tree.set_root()
        self._load_folder_tree("/")
        self._load_files()
        self._load_account_info()

    def _get_client_capabilities(self, host_id: str) -> Optional[FileManagerCapabilities]:
        """Synchronously get capabilities (they're static per client type)."""
        try:
            from src.network.file_manager.factory import create_file_manager_client
            client = create_file_manager_client(host_id)
            return client.get_capabilities()
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def load_children(self, folder_id: str, _folder_name: str = ""):
        """Load children for a folder in the tree without navigating.

        The second arg matches the children_requested signal signature but
        is not used — the tree widget already knows the folder's name.
        """
        if not self._current_host:
            return
        if self._dialog.folder_tree.needs_children(folder_id):
            self._load_folder_tree(folder_id)

    def navigate_to(self, folder_id: str, folder_name: str = ""):
        """Navigate into a folder."""
        if not self._current_host:
            return

        # Push to history (only if actually moving to a different folder)
        if folder_id != self._current_folder:
            history = self._history.setdefault(self._current_host, [])
            history.append(self._current_folder)

        self._current_folder = folder_id
        self._current_page = 1
        self._host_folder[self._current_host] = folder_id

        # Build breadcrumb from tree hierarchy (handles siblings correctly)
        if folder_id == "/":
            self._breadcrumb = [("/", "/")]
        else:
            tree_path = self._dialog.folder_tree.get_item_path(folder_id)
            if tree_path:
                self._breadcrumb = tree_path
            else:
                # Fallback for folders not in tree (e.g. file list double-click)
                self._breadcrumb.append((folder_id, folder_name or folder_id))

        self._update_nav_state()
        self._load_files()

        # Load folder tree children if needed
        if self._dialog.folder_tree.needs_children(folder_id):
            self._load_folder_tree(folder_id)

        self._dialog.folder_tree.select_folder(folder_id)

    def go_back(self):
        """Navigate to previous folder in history."""
        if not self._current_host:
            return
        history = self._history.get(self._current_host, [])
        if history:
            prev = history.pop()
            self._current_folder = prev
            self._current_page = 1
            self._host_folder[self._current_host] = prev

            # Rebuild breadcrumb from tree hierarchy
            tree_path = self._dialog.folder_tree.get_item_path(prev)
            self._breadcrumb = tree_path if tree_path else [("/", "/")]

            self._update_nav_state()
            self._load_files()
            self._dialog.folder_tree.select_folder(prev)

    def go_up(self):
        """Navigate to parent folder."""
        if self._current_folder == "/":
            return
        # Use breadcrumb to find parent
        if len(self._breadcrumb) > 1:
            parent_id = self._breadcrumb[-2][0]
            history = self._history.setdefault(self._current_host, [])
            history.append(self._current_folder)
            self._current_folder = parent_id
            self._current_page = 1
            self._host_folder[self._current_host] = parent_id
            tree_path = self._dialog.folder_tree.get_item_path(parent_id)
            self._breadcrumb = tree_path if tree_path else [("/", "/")]
            self._update_nav_state()
            self._load_files()
            self._dialog.folder_tree.select_folder(parent_id)
        else:
            self.navigate_to("/", "/")

    def go_root(self):
        """Navigate to root folder."""
        self.navigate_to("/", "/")

    def refresh(self):
        """Reload current folder (bypass cache)."""
        self._invalidate_cache(self._current_folder)
        if self._in_trash:
            self._load_trash()
        else:
            self._load_files()
            self._load_folder_tree(self._current_folder)

    def _update_nav_state(self):
        history = self._history.get(self._current_host, [])
        self._dialog.toolbar.set_navigation_enabled(
            can_back=len(history) > 0,
            can_up=self._current_folder != "/",
        )
        self._dialog.toolbar.set_breadcrumb(self._breadcrumb)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_files(self):
        """Request file listing for current folder.

        Shows cached data immediately for instant navigation. Only
        refreshes in the background when the cache is older than TTL,
        so repeated navigation to recently-visited folders is free.
        """
        if not self._current_host:
            return

        # Show cached data immediately if available
        cache_key = (self._current_host, self._current_folder)
        cached = self._file_cache.get(cache_key)
        if cached:
            self._dialog.file_list.set_files(cached[0])
            self._dialog.reapply_filter()
            # Skip background fetch if cache is still fresh
            if (time.time() - cached[1]) < _CACHE_TTL:
                return

        # Fetch fresh data
        self._submit("list_files", {
            "folder_id": self._current_folder,
            "page": self._current_page,
            "per_page": self._per_page,
            "sort_by": self._sort_by,
            "sort_dir": self._sort_dir,
        }, file_folder=(self._current_host, self._current_folder))

    def _load_folder_tree(self, parent_id: str):
        """Request folder listing for tree.

        Shows cached data immediately. Only refreshes from the API when
        the cache is older than TTL, so expanding recently-loaded folders
        is free and doesn't disturb already-expanded subtree state.
        """
        if not self._current_host:
            return

        # Show cached data immediately if available
        cache_key = (self._current_host, parent_id)
        cached = self._folder_cache.get(cache_key)
        if cached:
            self._dialog.folder_tree.populate_children(parent_id, cached[0])
            # Skip background fetch if cache is still fresh
            if (time.time() - cached[1]) < _CACHE_TTL:
                return

        self._submit("list_folders", {"parent_id": parent_id},
                     folder_parent=(self._current_host, parent_id))

    def _load_account_info(self):
        """Request account info for current host."""
        if not self._current_host:
            return
        self._submit("account_info", {})

    # ------------------------------------------------------------------
    # Operation dispatch
    # ------------------------------------------------------------------

    def _submit(self, action: str, params: dict,
                file_folder: Optional[Tuple[str, str]] = None,
                folder_parent: Optional[Tuple[str, str]] = None) -> str:
        """Submit an operation to the worker.

        Pending map assignment must happen BEFORE the worker enqueue to
        avoid a race where the worker processes the op and emits the
        response signal before the main thread gets to record the mapping.

        Args:
            action: Worker action name.
            params: Action-specific params.
            file_folder: If this is a file-list request, (host_id, folder_id)
                to track for display gating and caching.
            folder_parent: If this is a folder-list request, (host_id, parent_id)
                to track for the same reasons.
        """
        op_id = str(uuid.uuid4())[:8]
        self._pending_ops[op_id] = action
        if file_folder is not None:
            self._pending_file_folders[op_id] = file_folder
        if folder_parent is not None:
            self._pending_folder_parents[op_id] = folder_parent
        self._worker.submit({
            "op_id": op_id,
            "action": action,
            "host_id": self._current_host,
            **params,
        })
        return op_id

    # ------------------------------------------------------------------
    # User actions
    # ------------------------------------------------------------------

    def on_file_double_clicked(self, fi: FileInfo):
        """Handle double-click on file/folder."""
        if fi.is_folder:
            self.navigate_to(fi.id, fi.name)
        else:
            self.show_file_details([fi])

    def on_page_requested(self, page: int):
        if page < 1:
            return
        self._current_page = page
        # Note: the file cache key doesn't include page, so different pages
        # overwrite each other. Acceptable for now — most hosts return all
        # files on page 1 with high per_page limits.
        self._load_files()

    def on_selection_changed(self, selected: list):
        has_files = any(not fi.is_folder for fi in selected)
        self._dialog.toolbar.update_selection(len(selected), has_files)

    def on_files_dropped(self, dest_folder_id: str):
        """Handle files dropped onto a folder in the tree."""
        selected = self._dialog.file_list.get_selected_files()
        if not selected:
            return
        ids = [fi.id for fi in selected]
        self._submit("move", {
            "item_ids": ids,
            "dest_folder_id": dest_folder_id,
        })

    def create_folder(self):
        """Prompt user and create a new folder."""
        name, ok = QInputDialog.getText(
            self._dialog, "New Folder", "Folder name:"
        )
        if ok and name.strip():
            self._submit("create_folder", {
                "name": name.strip(),
                "parent_id": self._current_folder,
            })

    def rename_selected(self):
        """Rename the single selected item."""
        selected = self._dialog.file_list.get_selected_files()
        if len(selected) != 1:
            return

        fi = selected[0]
        new_name, ok = QInputDialog.getText(
            self._dialog, "Rename", "New name:", text=fi.name
        )
        if ok and new_name.strip() and new_name.strip() != fi.name:
            self._submit("rename", {
                "item_id": fi.id,
                "new_name": new_name.strip(),
            })

    def delete_selected(self):
        """Delete selected items after confirmation."""
        selected = self._dialog.file_list.get_selected_files()
        if not selected:
            return

        names = [fi.name for fi in selected[:5]]
        if len(selected) > 5:
            names.append(f"... and {len(selected) - 5} more")

        reply = QMessageBox.question(
            self._dialog,
            "Delete",
            f"Delete {len(selected)} item(s)?\n\n" + "\n".join(names),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            ids = [fi.id for fi in selected]
            self._submit("delete", {"item_ids": ids})

    def move_selected(self):
        """Move selected items — prompt for destination folder."""
        selected = self._dialog.file_list.get_selected_files()
        if not selected:
            return

        dest, ok = QInputDialog.getText(
            self._dialog, "Move To", "Destination folder ID (or '/' for root):",
            text="/",
        )
        if ok and dest.strip():
            ids = [fi.id for fi in selected]
            self._submit("move", {
                "item_ids": ids,
                "dest_folder_id": dest.strip(),
            })

    def copy_link(self):
        """Copy download link for selected file."""
        selected = self._dialog.file_list.get_selected_files()
        if len(selected) != 1 or selected[0].is_folder:
            return
        self._submit("get_download_link", {"file_id": selected[0].id})

    def change_access(self):
        """Change access level for selected items."""
        selected = self._dialog.file_list.get_selected_files()
        if not selected:
            return

        access, ok = QInputDialog.getItem(
            self._dialog, "Change Access", "Access level:",
            ["public", "premium", "private"], 0, False,
        )
        if ok:
            ids = [fi.id for fi in selected]
            self._submit("change_access", {
                "item_ids": ids,
                "access": access,
            })

    def copy_selected(self):
        """Copy selected items to a destination folder."""
        selected = self._dialog.file_list.get_selected_files()
        if not selected:
            return

        dest, ok = QInputDialog.getText(
            self._dialog, "Copy To", "Destination folder ID (or '/' for root):",
            text="/",
        )
        if ok and dest.strip():
            ids = [fi.id for fi in selected]
            self._submit("copy", {
                "item_ids": ids,
                "dest_folder_id": dest.strip(),
            })

    # ------------------------------------------------------------------
    # Trash operations
    # ------------------------------------------------------------------

    def toggle_trash(self, show_trash: bool):
        """Toggle between normal view and trash view."""
        self._in_trash = show_trash
        if show_trash:
            self._load_trash()
        else:
            self._load_files()

    def _load_trash(self):
        """Load trash contents.

        Shows cached trash data immediately, then refreshes in background.
        """
        if not self._current_host:
            return

        # Show cached trash if available
        cache_key = (self._current_host, self._TRASH_KEY)
        cached = self._file_cache.get(cache_key)
        if cached:
            self._dialog.file_list.set_files(cached[0])
            self._dialog.reapply_filter()
            if (time.time() - cached[1]) < _CACHE_TTL:
                return

        self._submit("trash_list", {
            "page": self._current_page,
            "per_page": self._per_page,
        }, file_folder=(self._current_host, self._TRASH_KEY))

    def trash_restore(self):
        """Restore selected items from trash."""
        selected = self._dialog.file_list.get_selected_files()
        if not selected:
            return
        ids = [fi.id for fi in selected]
        self._submit("trash_restore", {"file_ids": ids})

    def trash_empty(self):
        """Permanently delete all items in trash."""
        reply = QMessageBox.question(
            self._dialog,
            "Empty Trash",
            "Permanently delete ALL items in trash?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._submit("trash_empty", {})

    def show_file_details(self, files: list):
        """Show file details dialog."""
        if not files:
            return
        from src.gui.dialogs.file_details_dialog import FileDetailsDialog
        dlg = FileDetailsDialog(files, parent=self._dialog)
        dlg.exec()

    # ------------------------------------------------------------------
    # Worker signal handlers
    # ------------------------------------------------------------------

    def _on_files_loaded(self, op_id: str, result: FileListResult):
        self._pending_ops.pop(op_id, None)
        request = self._pending_file_folders.pop(op_id, None)

        # Always cache the response under the host/folder it was actually for,
        # so future navigation to that host+folder is instant.
        if request:
            request_host, request_folder = request
            self._cache_put(self._file_cache, (request_host, request_folder), (result, time.time()))

            # Only update the display if we're still looking at that view.
            # The "view" is trash mode or the current folder.
            current_view_folder = self._TRASH_KEY if self._in_trash else self._current_folder
            if request_host == self._current_host and request_folder == current_view_folder:
                self._dialog.file_list.set_files(result)
                self._dialog.reapply_filter()

    def _on_folders_loaded(self, op_id: str, result: FolderListResult):
        self._pending_ops.pop(op_id, None)
        request = self._pending_folder_parents.pop(op_id, None)

        if not request:
            # No pending mapping — we can't know host/parent for sure.
            # Don't cache or display anything to avoid polluting state.
            return

        request_host, parent_id = request

        # Always cache (so browsing is instant next time)
        self._cache_put(self._folder_cache, (request_host, parent_id), (result.folders, time.time()))

        # Only update the tree if we're still on that host
        if request_host == self._current_host:
            self._dialog.folder_tree.populate_children(parent_id, result.folders)

    def _on_file_info_loaded(self, op_id: str, files: list):
        self._pending_ops.pop(op_id, None)
        if files:
            self.show_file_details(files)

    def _on_operation_complete(self, op_id: str, result):
        action = self._pending_ops.pop(op_id, "")

        if isinstance(result, OperationResult):
            if result.success:
                # Copy link to clipboard
                if action == "get_download_link" and result.message:
                    clipboard = QApplication.clipboard()
                    if clipboard:
                        clipboard.setText(result.message)
                        self._dialog.show_status("Link copied to clipboard")
                    return

                self._dialog.show_status(result.message or "Done")
                # Refresh after mutations
                if action in ("create_folder", "rename"):
                    self.refresh()
            else:
                self._dialog.show_status(f"Error: {result.message}", error=True)

        elif isinstance(result, BatchResult):
            if result.all_succeeded:
                self._dialog.show_status(
                    f"{len(result.succeeded)} item(s) {action}d"
                )
            else:
                failed_count = len(result.failed)
                self._dialog.show_status(
                    f"{len(result.succeeded)} succeeded, {failed_count} failed",
                    error=True,
                )
            # Refresh after batch mutations
            self.refresh()

    def _on_account_info(self, op_id: str, info: dict):
        self._pending_ops.pop(op_id, None)
        self._dialog.update_account_info(info)

    def _on_error(self, op_id: str, message: str):
        action = self._pending_ops.pop(op_id, "unknown")
        self._pending_folder_parents.pop(op_id, None)
        self._pending_file_folders.pop(op_id, None)
        log(f"File manager error [{action}]: {message}",
            level="error", category="file_manager")
        self._dialog.show_status(f"Error: {message}", error=True)

        # Throttle popups: suppress identical errors within 3 seconds
        now = time.time()
        key = (action, message)
        if key == self._last_error_key and (now - self._last_error_time) < 3.0:
            return
        self._last_error_key = key
        self._last_error_time = now
        QMessageBox.warning(
            self._dialog,
            "File Manager Error",
            f"Operation '{action}' failed:\n\n{message}",
        )

    def _on_loading(self, is_loading: bool):
        self._dialog.file_list.set_loading(is_loading)

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def _cache_put(self, cache: OrderedDict, key, value):
        """Insert a cache entry with LRU eviction."""
        if key in cache:
            cache.move_to_end(key)
        cache[key] = value
        while len(cache) > _CACHE_MAX_ENTRIES:
            cache.popitem(last=False)

    def _invalidate_cache(self, folder_id: str):
        """Remove cached data for a folder."""
        if self._current_host:
            key = (self._current_host, folder_id)
            self._file_cache.pop(key, None)
            self._folder_cache.pop(key, None)

