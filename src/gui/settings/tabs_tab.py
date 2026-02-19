"""Tabs management settings tab — create, rename, reorder, and hide gallery tabs."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QHBoxLayout, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QLabel, QPushButton, QComboBox, QCheckBox, QSplitter,
    QInputDialog, QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

from src.utils.logger import log
from src.gui.dialogs.message_factory import show_info, show_error, show_warning


class TabsTab(QWidget):
    """Self-contained Tabs management settings tab.

    Emits *dirty* whenever a control value changes so the orchestrator
    can track unsaved state without knowing the internals.
    """

    dirty = pyqtSignal()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, parent_window=None, parent=None):
        super().__init__(parent)
        self.parent_window = parent_window

        # Initialize tab manager reference
        self.tab_manager = None
        if self.parent_window and hasattr(self.parent_window, 'tab_manager'):
            self.tab_manager = self.parent_window.tab_manager

        self._setup_ui()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        """Build the Tabs management UI."""
        layout = QVBoxLayout(self)

        desc = QLabel("Create, rename, reorder, and hide gallery tabs.")
        desc.setWordWrap(True)
        desc.setProperty("class", "tab-description")
        layout.addWidget(desc)

        # Create splitter for better layout
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        # Left side - Tab management
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        # Tab list group
        tab_list_group = QGroupBox("Tab Management")
        tab_list_layout = QVBoxLayout(tab_list_group)

        # Tab table
        self.tabs_table = QTableWidget()
        self.tabs_table.setColumnCount(4)
        self.tabs_table.setHorizontalHeaderLabels(["Name", "Type", "Count", "Hidden"])
        self.tabs_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tabs_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tabs_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tabs_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.tabs_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabs_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabs_table.itemSelectionChanged.connect(self.on_tab_selection_changed)
        tab_list_layout.addWidget(self.tabs_table)

        # Tab action buttons
        tab_buttons_layout = QHBoxLayout()

        self.create_tab_btn = QPushButton("Create Tab")
        self.create_tab_btn.setToolTip("Create a new gallery tab")
        self.create_tab_btn.clicked.connect(self.create_new_tab)
        tab_buttons_layout.addWidget(self.create_tab_btn)

        self.rename_tab_btn = QPushButton("Rename")
        self.rename_tab_btn.setToolTip("Rename the selected tab")
        self.rename_tab_btn.clicked.connect(self.rename_selected_tab)
        self.rename_tab_btn.setEnabled(False)
        tab_buttons_layout.addWidget(self.rename_tab_btn)

        self.delete_tab_btn = QPushButton("Delete")
        self.delete_tab_btn.setToolTip("Delete the selected tab and its galleries")
        self.delete_tab_btn.clicked.connect(self.delete_selected_tab)
        self.delete_tab_btn.setEnabled(False)
        tab_buttons_layout.addWidget(self.delete_tab_btn)

        tab_buttons_layout.addStretch()

        self.move_tab_up_btn = QPushButton("Move Up")
        self.move_tab_up_btn.setToolTip("Move tab up in order")
        self.move_tab_up_btn.clicked.connect(self.move_tab_up)
        self.move_tab_up_btn.setEnabled(False)
        tab_buttons_layout.addWidget(self.move_tab_up_btn)

        self.move_tab_down_btn = QPushButton("Move Down")
        self.move_tab_down_btn.setToolTip("Move tab down in order")
        self.move_tab_down_btn.clicked.connect(self.move_tab_down)
        self.move_tab_down_btn.setEnabled(False)
        tab_buttons_layout.addWidget(self.move_tab_down_btn)

        tab_list_layout.addLayout(tab_buttons_layout)
        left_layout.addWidget(tab_list_group)

        # Tab preferences group
        tab_prefs_group = QGroupBox("Tab Preferences")
        tab_prefs_layout = QGridLayout(tab_prefs_group)

        # Default tab for new galleries
        tab_prefs_layout.addWidget(QLabel("Default tab for new galleries:"), 0, 0)
        self.default_tab_combo = QComboBox()
        self.default_tab_combo.setToolTip("Select which tab is active on startup")
        self.default_tab_combo.currentTextChanged.connect(self.on_default_tab_changed)
        tab_prefs_layout.addWidget(self.default_tab_combo, 0, 1)

        # Hide/Show selected tab
        self.hide_tab_check = QCheckBox("Hide selected tab")
        self.hide_tab_check.setToolTip("Hide the selected tab from the main window")
        self.hide_tab_check.setEnabled(False)
        self.hide_tab_check.toggled.connect(self.on_hide_tab_toggled)
        tab_prefs_layout.addWidget(self.hide_tab_check, 1, 0, 1, 2)

        # Reset tab order button
        self.reset_order_btn = QPushButton("Reset to Default Order")
        self.reset_order_btn.setToolTip("Reset tabs to default order")
        self.reset_order_btn.clicked.connect(self.reset_tab_order)
        tab_prefs_layout.addWidget(self.reset_order_btn, 2, 0, 1, 2)

        left_layout.addWidget(tab_prefs_group)
        left_layout.addStretch()

        # Add to splitter
        splitter.addWidget(left_widget)
        splitter.setSizes([700])  # Single widget takes full space

        # Load current tabs and settings
        self.load_settings()

    # ------------------------------------------------------------------
    # Load / save / reset
    # ------------------------------------------------------------------

    def load_settings(self):
        """Load current tabs and settings."""
        # Clear existing table
        self.tabs_table.setRowCount(0)

        if not self.tab_manager:
            # Show message if no tab manager available
            self.tabs_table.setRowCount(1)
            item = QTableWidgetItem("Tab management not available")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.tabs_table.setItem(0, 0, item)
            self._disable_tab_controls()
            return

        try:
            # Load all tabs (including hidden)
            tabs = self.tab_manager.get_all_tabs(include_hidden=True)

            # Populate table
            self.tabs_table.setRowCount(len(tabs))
            for row, tab in enumerate(tabs):
                # Name
                name_item = QTableWidgetItem(tab.name)
                name_item.setData(Qt.ItemDataRole.UserRole, tab)  # Store tab info
                self.tabs_table.setItem(row, 0, name_item)

                # Type
                type_item = QTableWidgetItem(tab.tab_type.capitalize())
                if tab.tab_type == 'system':
                    type_item.setBackground(QColor("#f0f8ff"))
                self.tabs_table.setItem(row, 1, type_item)

                # Gallery count
                count_item = QTableWidgetItem(str(tab.gallery_count))
                count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tabs_table.setItem(row, 2, count_item)

                # Hidden status
                hidden_item = QTableWidgetItem("Yes" if tab.is_hidden else "No")
                hidden_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if tab.is_hidden:
                    hidden_item.setBackground(QColor("#ffe6e6"))
                self.tabs_table.setItem(row, 3, hidden_item)

            # Update default tab combo
            self.default_tab_combo.clear()
            visible_tabs = [tab.name for tab in tabs if not tab.is_hidden]
            self.default_tab_combo.addItems(visible_tabs)

            # Set current default tab
            current_default = self.tab_manager.last_active_tab
            index = self.default_tab_combo.findText(current_default)
            if index >= 0:
                self.default_tab_combo.setCurrentIndex(index)

        except Exception as e:
            log(f"Error loading tabs settings: {e}", level="error", category="settings")
            self._disable_tab_controls()

    def save_settings(self):
        """Save Tabs tab settings only."""
        try:
            # TabManager automatically persists settings through QSettings.
            # No additional saving needed here as all tab operations
            # in the UI immediately update the TabManager which handles persistence.
            return True
        except Exception as e:
            log(f"Error saving tab settings: {e}", level="warning", category="settings")
            return False

    def reset_to_defaults(self):
        """Reset tabs settings to defaults."""
        try:
            if self.tab_manager:
                self.tab_manager.reset_tab_order()
                self.tab_manager.last_active_tab = "Main"
                self.load_settings()
        except Exception as e:
            log(f"Failed to reset tabs settings: {e}", level="warning", category="settings")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _disable_tab_controls(self):
        """Disable all tab management controls."""
        controls = [
            self.create_tab_btn, self.rename_tab_btn, self.delete_tab_btn,
            self.move_tab_up_btn, self.move_tab_down_btn, self.hide_tab_check,
            self.reset_order_btn
        ]
        for control in controls:
            control.setEnabled(False)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def on_tab_selection_changed(self):
        """Handle tab selection change."""
        selected_items = self.tabs_table.selectedItems()
        if not selected_items or not self.tab_manager:
            self._update_tab_buttons(None)
            return

        # Get selected tab info
        row = selected_items[0].row()
        name_item = self.tabs_table.item(row, 0)
        tab_info = name_item.data(Qt.ItemDataRole.UserRole)

        self._update_tab_buttons(tab_info)

    def _update_tab_buttons(self, tab_info):
        """Update tab action buttons based on selection."""
        if not tab_info:
            self.rename_tab_btn.setEnabled(False)
            self.delete_tab_btn.setEnabled(False)
            self.move_tab_up_btn.setEnabled(False)
            self.move_tab_down_btn.setEnabled(False)
            self.hide_tab_check.setEnabled(False)
            return

        # Can only edit user tabs (not system tabs)
        is_user_tab = tab_info.tab_type == 'user'
        can_delete = is_user_tab and tab_info.name not in ['Main']

        self.rename_tab_btn.setEnabled(is_user_tab)
        self.delete_tab_btn.setEnabled(can_delete)

        # Movement buttons - can move any tab
        current_row = self.tabs_table.currentRow()
        can_move_up = current_row > 0
        can_move_down = current_row < (self.tabs_table.rowCount() - 1)

        self.move_tab_up_btn.setEnabled(can_move_up)
        self.move_tab_down_btn.setEnabled(can_move_down)

        # Hide/show functionality
        self.hide_tab_check.setEnabled(True)
        self.hide_tab_check.blockSignals(True)
        self.hide_tab_check.setChecked(tab_info.is_hidden)
        self.hide_tab_check.blockSignals(False)

    def create_new_tab(self):
        """Create a new user tab."""
        if not self.tab_manager:
            return

        # Get tab name from user
        name, ok = QInputDialog.getText(self, "Create New Tab", "Tab name:")
        if not ok or not name.strip():
            return

        name = name.strip()

        try:
            # Create tab using TabManager
            self.tab_manager.create_tab(name)

            # Refresh the display
            self.load_settings()

            # Select the new tab
            for row in range(self.tabs_table.rowCount()):
                item = self.tabs_table.item(row, 0)
                if item and item.text() == name:
                    self.tabs_table.selectRow(row)
                    break

            # Show success message
            show_info(self, "Success", f"Tab '{name}' created successfully!")

        except ValueError as e:
            # Show error message
            show_error(self, "Error", str(e))

    def rename_selected_tab(self):
        """Rename the selected tab."""
        if not self.tab_manager:
            return

        current_row = self.tabs_table.currentRow()
        if current_row < 0:
            return

        name_item = self.tabs_table.item(current_row, 0)
        tab_info = name_item.data(Qt.ItemDataRole.UserRole)

        if not tab_info or tab_info.tab_type != 'user':
            return

        # Get new name from user
        new_name, ok = QInputDialog.getText(
            self, "Rename Tab", "New name:", text=tab_info.name
        )
        if not ok or not new_name.strip() or new_name.strip() == tab_info.name:
            return

        new_name = new_name.strip()

        try:
            # Rename using TabManager
            success = self.tab_manager.update_tab(tab_info.name, new_name=new_name)

            if success:
                # Refresh the display
                self.load_settings()

                # Show success message
                show_info(self, "Success", f"Tab renamed to '{new_name}' successfully!")

        except ValueError as e:
            # Show error message
            show_error(self, "Error", str(e))

    def delete_selected_tab(self):
        """Delete the selected tab."""
        if not self.tab_manager:
            return

        current_row = self.tabs_table.currentRow()
        if current_row < 0:
            return

        name_item = self.tabs_table.item(current_row, 0)
        tab_info = name_item.data(Qt.ItemDataRole.UserRole)

        if not tab_info or tab_info.tab_type != 'user':
            return

        # Don't allow deleting Main
        if tab_info.name in ['Main']:
            show_warning(self, "Cannot Delete", f"Cannot delete the {tab_info.name} tab.")
            return

        # Confirm deletion
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Question)
        msg_box.setWindowTitle("Confirm Delete")
        msg_box.setText(f"Delete tab '{tab_info.name}'?\n\n"
                       f"All galleries in this tab will be moved to the Main tab.")
        msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg_box.setDefaultButton(QMessageBox.StandardButton.No)

        # Use non-blocking approach - keep existing pattern for async behavior
        msg_box.finished.connect(lambda result: self._handle_delete_confirmation(result, tab_info))
        msg_box.open()

    def _handle_delete_confirmation(self, result, tab_info):
        """Handle tab deletion confirmation."""
        if result != QMessageBox.StandardButton.Yes:
            return

        try:
            # Delete using TabManager
            success, gallery_count = self.tab_manager.delete_tab(tab_info.name, "Main")

            if success:
                # Refresh the display
                self.load_settings()

                # Show success message
                success_text = f"Tab '{tab_info.name}' deleted successfully!\n{gallery_count} galleries moved to Main tab."
                show_info(self, "Success", success_text)

        except ValueError as e:
            # Show error message
            show_error(self, "Error", str(e))

    def move_tab_up(self):
        """Move selected tab up in display order."""
        self._move_tab(-1)

    def move_tab_down(self):
        """Move selected tab down in display order."""
        self._move_tab(1)

    def _move_tab(self, direction):
        """Move tab up (-1) or down (1) in display order."""
        if not self.tab_manager:
            return

        current_row = self.tabs_table.currentRow()
        if current_row < 0:
            return

        new_row = current_row + direction
        if new_row < 0 or new_row >= self.tabs_table.rowCount():
            return

        # Get current custom ordering
        custom_order = self.tab_manager.get_custom_tab_order()

        # Get tab names at current and target positions
        current_tab_name = self.tabs_table.item(current_row, 0).text()
        target_tab_name = self.tabs_table.item(new_row, 0).text()

        # Assign new order values
        if not custom_order:
            # Create initial ordering based on current table order
            for row in range(self.tabs_table.rowCount()):
                tab_name = self.tabs_table.item(row, 0).text()
                custom_order[tab_name] = row * 10  # Leave gaps for insertion

        # Swap the order values
        current_order = custom_order.get(current_tab_name, current_row * 10)
        target_order = custom_order.get(target_tab_name, new_row * 10)

        custom_order[current_tab_name] = target_order
        custom_order[target_tab_name] = current_order

        # Apply the new ordering
        self.tab_manager.set_custom_tab_order(custom_order)

        # Refresh display and maintain selection
        self.load_settings()
        self.tabs_table.selectRow(new_row)

    def reset_tab_order(self):
        """Reset tab order to database defaults."""
        if not self.tab_manager:
            return

        # Confirm reset
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Question)
        msg_box.setWindowTitle("Reset Tab Order")
        msg_box.setText("Reset tab order to defaults?")
        msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg_box.setDefaultButton(QMessageBox.StandardButton.No)

        # Use non-blocking approach
        msg_box.finished.connect(self._handle_reset_order_confirmation)
        msg_box.open()

    def _handle_reset_order_confirmation(self, result):
        """Handle reset order confirmation."""
        if result == QMessageBox.StandardButton.Yes:
            self.tab_manager.reset_tab_order()
            self.load_settings()

    def on_default_tab_changed(self, tab_name):
        """Handle default tab selection change."""
        if self.tab_manager and tab_name:
            self.tab_manager.last_active_tab = tab_name

    def on_hide_tab_toggled(self, hidden):
        """Handle hide/show tab toggle."""
        if not self.tab_manager:
            return

        current_row = self.tabs_table.currentRow()
        if current_row < 0:
            return

        name_item = self.tabs_table.item(current_row, 0)
        tab_name = name_item.text()

        # Update tab visibility
        self.tab_manager.set_tab_hidden(tab_name, hidden)

        # Refresh display
        self.load_settings()
