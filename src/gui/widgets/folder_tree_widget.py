"""Folder tree widget for the file manager.

Displays a navigable folder hierarchy in a QTreeWidget. Folders are
lazy-loaded — children are fetched on expand. Emits folder_selected
when the user clicks a folder.
"""

from __future__ import annotations

from collections import deque
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent, QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.network.file_manager.client import FileInfo, FolderListResult


# Sentinel item placed inside unexpanded folders to show the expand arrow
_PLACEHOLDER = "__placeholder__"


class FolderTreeWidget(QWidget):
    """Left-pane folder tree for the file manager."""

    folder_selected = pyqtSignal(str, str)   # folder_id, folder_name
    children_requested = pyqtSignal(str, str)  # folder_id, folder_name
    files_dropped = pyqtSignal(str)            # dest_folder_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._folder_icon = self.style().standardIcon(
            self.style().StandardPixmap.SP_DirIcon
        )
        self._open_icon = self.style().standardIcon(
            self.style().StandardPixmap.SP_DirOpenIcon
        )

        self._tree = _DroppableTree(self)
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setAnimated(True)
        self._tree.setIndentation(16)
        self._tree.setAcceptDrops(True)
        self._tree.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.itemExpanded.connect(self._on_item_expanded)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._tree)

        # Track which folders have been loaded
        self._loaded_folders: set[str] = set()
        # Pending expand requests (folder_id -> tree item)
        self._pending_expands: dict[str, QTreeWidgetItem] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_root(self):
        """Initialize the tree with a root "/" node."""
        self._tree.clear()
        self._loaded_folders.clear()
        self._pending_expands.clear()

        root = QTreeWidgetItem(self._tree, ["/"])
        root.setData(0, Qt.ItemDataRole.UserRole, "/")
        root.setIcon(0, self._folder_icon)
        self._loaded_folders.add("/")
        root.setExpanded(True)

    def populate_children(self, parent_id: str, folders: list[FileInfo]):
        """Fill in children for a folder after API response.

        Args:
            parent_id: The folder whose children were loaded.
            folders: List of child folder FileInfo items.
        """
        parent_item = self._find_item(parent_id)
        if not parent_item:
            return

        # Filter out parent-directory sentinel entries some hosts surface
        # (e.g. Filedot returns ".." rows for non-root folders). The tree
        # already represents the hierarchy visually, so ".." would be
        # confusing here; file-list navigation uses the toolbar's Up button.
        folders = [f for f in folders if f.name != ".."]

        # Diff: only remove children that aren't in the new list.
        # Keep matching children in place to preserve their expanded/loaded state.
        new_ids = {f.id for f in folders}
        for i in range(parent_item.childCount() - 1, -1, -1):
            child = parent_item.child(i)
            if not child:
                continue
            cid = child.data(0, Qt.ItemDataRole.UserRole)
            # Remove placeholders and any children not in the new list
            if cid == _PLACEHOLDER or cid not in new_ids:
                parent_item.removeChild(child)

        # Track which IDs already exist so we don't duplicate them
        existing_ids = set()
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if child:
                cid = child.data(0, Qt.ItemDataRole.UserRole)
                if cid and cid != _PLACEHOLDER:
                    existing_ids.add(cid)

        # Add new children (skip ones already present to preserve their state)
        for folder in sorted(folders, key=lambda f: f.name.lower()):
            if folder.id in existing_ids:
                continue
            child = QTreeWidgetItem(parent_item, [folder.name])
            child.setData(0, Qt.ItemDataRole.UserRole, folder.id)
            child.setIcon(0, self._folder_icon)
            # Add placeholder so the expand arrow shows
            placeholder = QTreeWidgetItem(child)
            placeholder.setData(0, Qt.ItemDataRole.UserRole, _PLACEHOLDER)

        self._loaded_folders.add(parent_id)

        # If this was a pending expand, expand it now
        if parent_id in self._pending_expands:
            del self._pending_expands[parent_id]

    def select_folder(self, folder_id: str):
        """Programmatically select a folder in the tree."""
        item = self._find_item(folder_id)
        if item:
            self._tree.setCurrentItem(item)

    def get_selected_folder_id(self) -> Optional[str]:
        """Return the currently selected folder ID."""
        item = self._tree.currentItem()
        if item:
            fid = item.data(0, Qt.ItemDataRole.UserRole)
            return fid if fid != _PLACEHOLDER else None
        return None

    # ------------------------------------------------------------------
    # Signals from tree
    # ------------------------------------------------------------------

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        folder_id = item.data(0, Qt.ItemDataRole.UserRole)
        if folder_id and folder_id != _PLACEHOLDER:
            self.folder_selected.emit(folder_id, item.text(0))

    def _on_item_expanded(self, item: QTreeWidgetItem):
        folder_id = item.data(0, Qt.ItemDataRole.UserRole)
        if folder_id and folder_id != _PLACEHOLDER and folder_id not in self._loaded_folders:
            self._pending_expands[folder_id] = item
            # Reveal the invisible placeholder as a "Loading…" row so the
            # user sees feedback during slow fetches (Filedot scraping can
            # take several seconds). populate_children removes placeholders
            # when real children arrive.
            for i in range(item.childCount()):
                child = item.child(i)
                if child and child.data(0, Qt.ItemDataRole.UserRole) == _PLACEHOLDER:
                    child.setText(0, "Loading…")
                    font = child.font(0)
                    font.setItalic(True)
                    child.setFont(0, font)
                    child.setFlags(child.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                    break
            # Only request children — don't navigate
            self.children_requested.emit(folder_id, item.text(0))

    def get_item_path(self, folder_id: str) -> list[tuple[str, str]]:
        """Build the full breadcrumb path from root to the given folder.

        Returns:
            List of (folder_id, folder_name) from root to target,
            or empty list if folder not found in tree.
        """
        item = self._find_item(folder_id)
        if not item:
            return []
        path = []
        while item:
            fid = item.data(0, Qt.ItemDataRole.UserRole)
            if fid and fid != _PLACEHOLDER:
                path.append((fid, item.text(0)))
            item = item.parent()
        path.reverse()
        return path

    def needs_children(self, folder_id: str) -> bool:
        """Check if a folder's children haven't been loaded yet."""
        return folder_id not in self._loaded_folders

    def show_error(self, parent_id: str, message: str = "") -> None:
        """Convert the transient Loading… placeholder into an error row.

        Called by the controller when a list_folders fetch fails so the
        tree doesn't lie about being mid-fetch forever. ``_loaded_folders``
        is intentionally left untouched — collapsing and re-expanding the
        folder re-runs _on_item_expanded, which restores the placeholder
        to "Loading…" and retries.
        """
        parent_item = self._find_item(parent_id)
        if not parent_item:
            return
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if not child:
                continue
            if child.data(0, Qt.ItemDataRole.UserRole) != _PLACEHOLDER:
                continue
            text = "Failed to load"
            if message:
                # Keep the row compact — full message is in the status bar.
                short = message.splitlines()[0][:80]
                text = f"Failed to load — {short}"
            child.setText(0, text)
            # No explicit colour: italic alone distinguishes the row, and
            # the status bar already carries the red error message. Avoids
            # hardcoding a colour that would miss the light/dark tokens.
            font = child.font(0)
            font.setItalic(True)
            child.setFont(0, font)
            child.setFlags(child.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            break

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _find_item(self, folder_id: str) -> Optional[QTreeWidgetItem]:
        """Find a tree item by folder ID (BFS)."""
        root = self._tree.invisibleRootItem()
        queue = deque(root.child(i) for i in range(root.childCount()))
        while queue:
            item = queue.popleft()
            if item is None:
                continue
            if item.data(0, Qt.ItemDataRole.UserRole) == folder_id:
                return item
            for i in range(item.childCount()):
                queue.append(item.child(i))
        return None


class _DroppableTree(QTreeWidget):
    """QTreeWidget subclass that accepts drops from the file list."""

    def __init__(self, owner: FolderTreeWidget):
        super().__init__(owner)
        self._owner = owner

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasFormat("application/x-qabstractitemmodeldatalist"):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent):
        item = self.itemAt(event.position().toPoint())
        if item:
            fid = item.data(0, Qt.ItemDataRole.UserRole)
            if fid and fid != _PLACEHOLDER:
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        item = self.itemAt(event.position().toPoint())
        if item:
            fid = item.data(0, Qt.ItemDataRole.UserRole)
            if fid and fid != _PLACEHOLDER:
                self._owner.files_dropped.emit(fid)
                event.acceptProposedAction()
                return
        event.ignore()
