"""Folder tree widget for the file manager.

Displays a navigable folder hierarchy in a QTreeWidget. Folders are
lazy-loaded — children are fetched on expand. Emits folder_selected
when the user clicks a folder.
"""

from __future__ import annotations

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

    folder_selected = pyqtSignal(str, str)  # folder_id, folder_name
    files_dropped = pyqtSignal(str)        # dest_folder_id

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
        root.setExpanded(True)
        self._loaded_folders.add("/")

    def populate_children(self, parent_id: str, folders: list[FileInfo]):
        """Fill in children for a folder after API response.

        Args:
            parent_id: The folder whose children were loaded.
            folders: List of child folder FileInfo items.
        """
        parent_item = self._find_item(parent_id)
        if not parent_item:
            return

        # Remove placeholder
        for i in range(parent_item.childCount() - 1, -1, -1):
            child = parent_item.child(i)
            if child and child.data(0, Qt.ItemDataRole.UserRole) == _PLACEHOLDER:
                parent_item.removeChild(child)

        # Add children
        for folder in sorted(folders, key=lambda f: f.name.lower()):
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
            # Signal that we need to load children — controller listens
            self.folder_selected.emit(folder_id, item.text(0))

    def needs_children(self, folder_id: str) -> bool:
        """Check if a folder's children haven't been loaded yet."""
        return folder_id not in self._loaded_folders

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _find_item(self, folder_id: str) -> Optional[QTreeWidgetItem]:
        """Find a tree item by folder ID (BFS)."""
        root = self._tree.invisibleRootItem()
        stack = [root.child(i) for i in range(root.childCount())]
        while stack:
            item = stack.pop(0)
            if item is None:
                continue
            if item.data(0, Qt.ItemDataRole.UserRole) == folder_id:
                return item
            for i in range(item.childCount()):
                stack.append(item.child(i))
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
