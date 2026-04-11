"""Toolbar and filter bar for the file manager.

Provides navigation buttons (back, up, root, refresh), action buttons
(new folder, delete, rename), a filter field, and a breadcrumb display.
Buttons are enabled/disabled based on FileManagerCapabilities.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.network.file_manager.client import FileManagerCapabilities


class FileManagerToolbar(QWidget):
    """Navigation + action toolbar for the file manager."""

    # Navigation signals
    back_clicked = pyqtSignal()
    up_clicked = pyqtSignal()
    root_clicked = pyqtSignal()
    refresh_clicked = pyqtSignal()

    # Action signals
    new_folder_clicked = pyqtSignal()
    delete_clicked = pyqtSignal()
    rename_clicked = pyqtSignal()
    move_clicked = pyqtSignal()
    copy_clicked = pyqtSignal()
    copy_link_clicked = pyqtSignal()
    change_access_clicked = pyqtSignal()
    trash_toggled = pyqtSignal(bool)        # True = show trash
    trash_restore_clicked = pyqtSignal()
    trash_empty_clicked = pyqtSignal()

    # Filter
    filter_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Row 1: Navigation + filter
        nav_layout = QHBoxLayout()
        nav_layout.setSpacing(4)

        self._btn_back = QPushButton("<")
        self._btn_back.setToolTip("Back")
        self._btn_back.setFixedWidth(30)
        self._btn_back.clicked.connect(self.back_clicked)
        nav_layout.addWidget(self._btn_back)

        self._btn_up = QPushButton("^")
        self._btn_up.setToolTip("Up one level")
        self._btn_up.setFixedWidth(30)
        self._btn_up.clicked.connect(self.up_clicked)
        nav_layout.addWidget(self._btn_up)

        self._btn_root = QPushButton("/")
        self._btn_root.setToolTip("Go to root")
        self._btn_root.setFixedWidth(30)
        self._btn_root.clicked.connect(self.root_clicked)
        nav_layout.addWidget(self._btn_root)

        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.setToolTip("Refresh current folder")
        self._btn_refresh.clicked.connect(self.refresh_clicked)
        nav_layout.addWidget(self._btn_refresh)

        nav_layout.addStretch()

        self._filter_input = QLineEdit()
        self._filter_input.setPlaceholderText("Filter...")
        self._filter_input.setClearButtonEnabled(True)
        self._filter_input.setMaximumWidth(200)
        self._filter_input.textChanged.connect(self.filter_changed)
        nav_layout.addWidget(self._filter_input)

        layout.addLayout(nav_layout)

        # Row 2: Breadcrumb
        self._breadcrumb = QLabel("/")
        self._breadcrumb.setStyleSheet("color: palette(placeholder-text); padding: 2px 4px;")
        layout.addWidget(self._breadcrumb)

        # Row 3: Actions
        action_layout = QHBoxLayout()
        action_layout.setSpacing(4)

        self._btn_new_folder = QPushButton("+ New Folder")
        self._btn_new_folder.clicked.connect(self.new_folder_clicked)
        action_layout.addWidget(self._btn_new_folder)

        self._btn_rename = QPushButton("Rename")
        self._btn_rename.clicked.connect(self.rename_clicked)
        self._btn_rename.setEnabled(False)
        action_layout.addWidget(self._btn_rename)

        self._btn_move = QPushButton("Move To...")
        self._btn_move.clicked.connect(self.move_clicked)
        self._btn_move.setEnabled(False)
        action_layout.addWidget(self._btn_move)

        self._btn_copy_link = QPushButton("Copy Link")
        self._btn_copy_link.clicked.connect(self.copy_link_clicked)
        self._btn_copy_link.setEnabled(False)
        action_layout.addWidget(self._btn_copy_link)

        self._btn_copy = QPushButton("Copy To...")
        self._btn_copy.clicked.connect(self.copy_clicked)
        self._btn_copy.setEnabled(False)
        action_layout.addWidget(self._btn_copy)

        self._btn_change_access = QPushButton("Access")
        self._btn_change_access.clicked.connect(self.change_access_clicked)
        self._btn_change_access.setEnabled(False)
        action_layout.addWidget(self._btn_change_access)

        self._btn_delete = QPushButton("Delete")
        self._btn_delete.clicked.connect(self.delete_clicked)
        self._btn_delete.setEnabled(False)
        action_layout.addWidget(self._btn_delete)

        action_layout.addStretch()

        # Trash toggle (RapidGator only — hidden by default)
        self._btn_trash = QPushButton("Trash")
        self._btn_trash.setCheckable(True)
        self._btn_trash.toggled.connect(self.trash_toggled)
        self._btn_trash.setVisible(False)
        action_layout.addWidget(self._btn_trash)

        self._btn_trash_restore = QPushButton("Restore")
        self._btn_trash_restore.clicked.connect(self.trash_restore_clicked)
        self._btn_trash_restore.setVisible(False)
        self._btn_trash_restore.setEnabled(False)
        action_layout.addWidget(self._btn_trash_restore)

        self._btn_trash_empty = QPushButton("Empty Trash")
        self._btn_trash_empty.clicked.connect(self.trash_empty_clicked)
        self._btn_trash_empty.setVisible(False)
        action_layout.addWidget(self._btn_trash_empty)

        layout.addLayout(action_layout)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_capabilities(self, caps: FileManagerCapabilities):
        """Show/hide action buttons based on host capabilities."""
        self._btn_new_folder.setVisible(caps.can_create_folder)
        self._btn_rename.setVisible(caps.can_rename)
        self._btn_move.setVisible(caps.can_move)
        self._btn_copy.setVisible(caps.can_copy)
        self._btn_delete.setVisible(caps.can_delete)
        self._btn_copy_link.setVisible(caps.can_get_download_link)
        self._btn_change_access.setVisible(caps.can_change_access)
        self._btn_trash.setVisible(caps.can_trash)
        self._btn_trash_restore.setVisible(caps.can_trash)
        self._btn_trash_empty.setVisible(caps.can_trash)
        # Reset trash toggle when switching hosts
        if not caps.can_trash and self._btn_trash.isChecked():
            self._btn_trash.setChecked(False)

    def update_selection(self, selected_count: int, has_files: bool = False):
        """Enable/disable action buttons based on selection."""
        has_selection = selected_count > 0
        single_selection = selected_count == 1
        in_trash = self._btn_trash.isChecked()

        self._btn_rename.setEnabled(single_selection and not in_trash)
        self._btn_move.setEnabled(has_selection and not in_trash)
        self._btn_copy.setEnabled(has_selection and not in_trash)
        self._btn_delete.setEnabled(has_selection and not in_trash)
        self._btn_copy_link.setEnabled(single_selection and has_files and not in_trash)
        self._btn_change_access.setEnabled(has_selection and not in_trash)
        self._btn_trash_restore.setEnabled(has_selection and in_trash)

    def set_breadcrumb(self, path_parts: list[tuple[str, str]]):
        """Update breadcrumb display.

        Args:
            path_parts: List of (folder_id, folder_name) tuples.
        """
        if not path_parts:
            self._breadcrumb.setText("/")
            return
        parts = [name for fid, name in path_parts if fid != "/"]
        if parts:
            self._breadcrumb.setText("/ " + " / ".join(parts))
        else:
            self._breadcrumb.setText("/")

    def set_navigation_enabled(self, can_back: bool, can_up: bool):
        """Enable/disable back and up buttons."""
        self._btn_back.setEnabled(can_back)
        self._btn_up.setEnabled(can_up)

    def clear_filter(self):
        self._filter_input.clear()

    def get_filter_text(self) -> str:
        return self._filter_input.text()
