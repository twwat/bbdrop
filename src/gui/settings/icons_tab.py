"""Icons management settings tab — customize application icons."""

import os
import shutil

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QSplitter, QFileDialog, QDialog,
    QPlainTextEdit, QMessageBox, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

from src.gui.widgets.icon_drop_frame import IconDropFrame
from src.utils.logger import log
from src.gui.dialogs.message_factory import MessageBoxFactory, show_info, show_error, show_warning


class IconsTab(QWidget):
    """Self-contained Icons management settings tab.

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
        self.icon_data = {}  # Store full icon information
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        """Build the Icons management UI."""
        layout = QVBoxLayout(self)

        # Header info
        info_label = QLabel("Customize application icons. Single icons auto-adapt to themes, pairs give full control.")
        info_label.setWordWrap(True)
        info_label.setProperty("class", "tab-description")
        info_label.setMaximumHeight(40)  # Limit height to prevent it from taking too much space
        info_label.setSizePolicy(info_label.sizePolicy().horizontalPolicy(),
                                QSizePolicy.Policy.Fixed)  # Fixed vertical size policy
        layout.addWidget(info_label)

        # Add spacing to match QGroupBox margin in other tabs
        layout.addSpacing(8)

        # Create splitter for icon categories and preview
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        # Left side - Icon categories tree
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        category_group = QGroupBox("Icon Categories")
        category_layout = QVBoxLayout(category_group)

        self.icon_tree = QListWidget()
        self.icon_tree.itemSelectionChanged.connect(self.on_icon_selection_changed)
        category_layout.addWidget(self.icon_tree)

        left_layout.addWidget(category_group)
        splitter.addWidget(left_widget)

        # Right side - Icon details and customization
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        # Icon Details group
        details_group = QGroupBox("Icon Details")
        details_layout = QVBoxLayout(details_group)

        self.icon_name_label = QLabel("Select an icon to customize")
        self.icon_name_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        details_layout.addWidget(self.icon_name_label)

        self.icon_description_label = QLabel("")
        self.icon_description_label.setWordWrap(True)
        self.icon_description_label.setStyleSheet("color: #666; font-size: 11px; padding: 2px;")
        details_layout.addWidget(self.icon_description_label)

        right_layout.addWidget(details_group)

        # Light/Dark Icon Preview - REDESIGNED
        preview_group = QGroupBox("Icon Preview")
        preview_layout = QVBoxLayout(preview_group)

        # Create side-by-side preview boxes
        preview_boxes_layout = QHBoxLayout()

        # Light theme box
        light_box = QGroupBox("Light Theme")
        light_box_layout = QVBoxLayout(light_box)

        self.light_icon_frame = IconDropFrame('light')
        self.light_icon_frame.setFixedSize(100, 100)
        self.light_icon_frame.setStyleSheet("border: 2px dashed #ddd; background: #ffffff; border-radius: 8px;")
        self.light_icon_frame.icon_dropped.connect(lambda path: self.handle_icon_drop_variant(path, 'light'))
        light_frame_layout = QVBoxLayout(self.light_icon_frame)
        light_frame_layout.setContentsMargins(0, 0, 0, 0)

        self.light_icon_label = QLabel()
        self.light_icon_label.setFixedSize(96, 96)
        self.light_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.light_icon_label.setStyleSheet("border: none; background: transparent;")
        self.light_icon_label.setScaledContents(True)  # Ensure proper scaling
        light_frame_layout.addWidget(self.light_icon_label)

        light_box_layout.addWidget(self.light_icon_frame, 0, Qt.AlignmentFlag.AlignCenter)

        self.light_status_label = QLabel("No icon")
        self.light_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.light_status_label.setStyleSheet("font-size: 10px; color: #666; padding: 3px;")
        light_box_layout.addWidget(self.light_status_label)

        light_controls = QHBoxLayout()
        self.light_browse_btn = QPushButton("Browse")
        self.light_browse_btn.clicked.connect(lambda: self.browse_for_icon_variant('light'))
        self.light_browse_btn.setEnabled(False)
        light_controls.addWidget(self.light_browse_btn)

        self.light_reset_btn = QPushButton("Reset")
        self.light_reset_btn.clicked.connect(lambda: self.reset_icon_variant('light'))
        self.light_reset_btn.setEnabled(False)
        light_controls.addWidget(self.light_reset_btn)

        light_box_layout.addLayout(light_controls)
        preview_boxes_layout.addWidget(light_box)

        # Dark theme box - FIXED SIZE TO MATCH LIGHT
        dark_box = QGroupBox("Dark Theme")
        dark_box_layout = QVBoxLayout(dark_box)

        self.dark_icon_frame = IconDropFrame('dark')
        self.dark_icon_frame.setFixedSize(100, 100)  # Same size as light
        self.dark_icon_frame.setStyleSheet("border: 2px dashed #555; background: #2b2b2b; border-radius: 8px;")
        self.dark_icon_frame.icon_dropped.connect(lambda path: self.handle_icon_drop_variant(path, 'dark'))
        dark_frame_layout = QVBoxLayout(self.dark_icon_frame)
        dark_frame_layout.setContentsMargins(0, 0, 0, 0)

        self.dark_icon_label = QLabel()
        self.dark_icon_label.setFixedSize(96, 96)  # Same size as light
        self.dark_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dark_icon_label.setStyleSheet("border: none; background: transparent;")
        self.dark_icon_label.setScaledContents(True)  # Ensure proper scaling
        dark_frame_layout.addWidget(self.dark_icon_label)

        dark_box_layout.addWidget(self.dark_icon_frame, 0, Qt.AlignmentFlag.AlignCenter)

        self.dark_status_label = QLabel("No icon")
        self.dark_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dark_status_label.setStyleSheet("font-size: 10px; color: #666; padding: 3px;")
        dark_box_layout.addWidget(self.dark_status_label)

        dark_controls = QHBoxLayout()
        self.dark_browse_btn = QPushButton("Browse")
        self.dark_browse_btn.clicked.connect(lambda: self.browse_for_icon_variant('dark'))
        self.dark_browse_btn.setEnabled(False)
        dark_controls.addWidget(self.dark_browse_btn)

        self.dark_reset_btn = QPushButton("Reset")
        self.dark_reset_btn.clicked.connect(lambda: self.reset_icon_variant('dark'))
        self.dark_reset_btn.setEnabled(False)
        dark_controls.addWidget(self.dark_reset_btn)

        dark_box_layout.addLayout(dark_controls)
        preview_boxes_layout.addWidget(dark_box)

        preview_layout.addLayout(preview_boxes_layout)

        # Configuration indicator
        self.config_type_label = QLabel("Configuration: Unknown")
        self.config_type_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.config_type_label.setStyleSheet("font-weight: bold; font-size: 11px; color: #333; padding: 5px;")
        preview_layout.addWidget(self.config_type_label)

        right_layout.addWidget(preview_group)

        # Global Actions group (simplified)
        global_actions_group = QGroupBox("Global Actions")
        global_actions_layout = QVBoxLayout(global_actions_group)

        global_button_layout = QHBoxLayout()

        reset_all_btn = QPushButton("Reset All Icons")
        reset_all_btn.clicked.connect(self.reset_all_icons)
        global_button_layout.addWidget(reset_all_btn)

        validate_btn = QPushButton("Validate Icons")
        validate_btn.clicked.connect(self.validate_all_icons)
        global_button_layout.addWidget(validate_btn)

        global_actions_layout.addLayout(global_button_layout)
        right_layout.addWidget(global_actions_group)

        right_layout.addStretch()
        splitter.addWidget(right_widget)

        # Set splitter proportions
        splitter.setSizes([300, 500])

        # Initialize icon list
        self.populate_icon_list()

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def populate_icon_list(self):
        """Populate the icon list with all available icons."""
        # Get icon categories from the icon manager
        icon_categories = {
            "Status Icons": [
                ("status_completed", "Completed", "Gallery upload completed successfully"),
                ("status_failed", "Failed", "Gallery upload failed"),
                ("status_uploading", "Uploading", "Currently uploading gallery"),
                ("status_paused", "Paused", "Upload paused by user"),
                ("status_queued", "Queued", "Waiting in upload queue"),
                ("status_ready", "Ready", "Ready to start upload"),
                ("status_pending", "Pending", "Preparing for upload"),
                ("status_incomplete", "Incomplete", "Upload partially completed"),
                ("status_scan_failed", "Scan Failed", "Failed to scan gallery images"),
                ("status_scanning", "Scanning", "Currently scanning gallery"),
            ],
            "Action Icons": [
                ("action_start", "Start", "Start gallery upload"),
                ("action_stop", "Stop", "Stop current upload"),
                ("action_view", "View", "View gallery online"),
                ("action_view_error", "View Error", "View error details"),
                ("action_cancel", "Cancel", "Cancel upload"),
                ("action_resume", "Resume", "Resume paused upload"),
            ],
            "UI Icons": [
                ("templates", "Templates", "Template management icon"),
                ("credentials", "Credentials", "Login credentials icon"),
                ("main_window", "Main Window", "Application window icon"),
                ("app_icon", "Application", "Main application icon"),
            ]
        }

        self.icon_tree.clear()
        self.icon_data = {}  # Store full icon information

        for category, icons in icon_categories.items():
            # Add category header
            category_item = QListWidgetItem(f"=== {category} ===")
            category_item.setFlags(Qt.ItemFlag.NoItemFlags)  # Not selectable

            # Set theme-aware background color
            try:
                pal = self.palette()
                bg = pal.window().color()
                is_dark = (0.2126 * bg.redF() + 0.7152 * bg.greenF() + 0.0722 * bg.blueF()) < 0.5
                if is_dark:
                    category_item.setBackground(QColor(64, 64, 64))  # Dark theme
                else:
                    category_item.setBackground(QColor(240, 240, 240))  # Light theme
            except Exception:
                category_item.setBackground(QColor(240, 240, 240))  # Fallback

            font = category_item.font()
            font.setBold(True)
            category_item.setFont(font)
            self.icon_tree.addItem(category_item)

            # Add icons in category
            for icon_key, display_name, description in icons:
                item = QListWidgetItem(f"  {display_name}")
                item.setData(Qt.ItemDataRole.UserRole, icon_key)
                self.icon_tree.addItem(item)

                # Store full data
                self.icon_data[icon_key] = {
                    'display_name': display_name,
                    'description': description,
                    'category': category
                }

    def save_settings(self):
        """Save Icons tab settings and refresh main window icons."""
        try:
            from src.gui.icon_manager import get_icon_manager

            icon_manager = get_icon_manager()
            if icon_manager:
                # Refresh the icon cache to ensure changes are loaded
                icon_manager.refresh_cache()

                # Signal the main window to refresh all status icons
                if self.parent_window and hasattr(self.parent_window, 'refresh_all_status_icons'):
                    self.parent_window.refresh_all_status_icons()
                elif self.parent_window and hasattr(self.parent_window, '_update_all_status_icons'):
                    self.parent_window._update_all_status_icons()

                return True
            else:
                log("IconManager not available", level="warning", category="ui")
                return True

        except Exception as e:
            log(f"Error saving icons tab: {e}", level="error", category="settings")
            show_error(self, "Error", f"Failed to apply icon changes: {str(e)}")
            return False

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def on_icon_selection_changed(self):
        """Handle icon selection change - now updates both light and dark previews."""
        current_item = self.icon_tree.currentItem()
        if not current_item or not current_item.data(Qt.ItemDataRole.UserRole):
            # Category header or no selection - clear everything
            self.icon_name_label.setText("Select an icon to customize")
            self.icon_description_label.setText("")
            self.config_type_label.setText("Configuration: Unknown")

            # Clear light preview
            self.light_icon_label.clear()
            self.light_status_label.setText("No icon")
            self.light_browse_btn.setEnabled(False)
            self.light_reset_btn.setEnabled(False)

            # Clear dark preview
            self.dark_icon_label.clear()
            self.dark_status_label.setText("No icon")
            self.dark_browse_btn.setEnabled(False)
            self.dark_reset_btn.setEnabled(False)
            return

        icon_key = current_item.data(Qt.ItemDataRole.UserRole)
        icon_info = self.icon_data.get(icon_key, {})

        # Update basic info
        self.icon_name_label.setText(icon_info.get('display_name', icon_key))
        self.icon_description_label.setText(icon_info.get('description', ''))

        # Update both light and dark previews
        self.update_icon_previews_dual(icon_key)

        # Enable controls
        self.light_browse_btn.setEnabled(True)
        self.light_reset_btn.setEnabled(True)
        self.dark_browse_btn.setEnabled(True)
        self.dark_reset_btn.setEnabled(True)

    def update_selected_icon_preview(self, icon_key):
        """Update the preview of the selected icon."""
        try:
            from src.gui.icon_manager import get_icon_manager
            icon_manager = get_icon_manager()

            if not icon_manager:
                self.current_icon_label.setText("N/A")
                return

            # Get theme state from combo
            theme_text = self.theme_preview_combo.currentText()
            theme_mode = 'dark' if "Dark" in theme_text else 'light'
            is_selected = "Selected" in theme_text

            # Get icon based on current theme settings
            icon = icon_manager.get_icon(icon_key, theme_mode=theme_mode, is_selected=is_selected)

            if not icon.isNull():
                # Display icon
                pixmap = icon.pixmap(24, 24)
                self.current_icon_label.setPixmap(pixmap)
            else:
                self.current_icon_label.setText("Missing")

            # Update status information
            icon_config = icon_manager.ICON_MAP.get(icon_key, "Unknown")

            if isinstance(icon_config, str):
                self.theme_info_label.setText("Single icon (auto-adapt)")
                # Check if file exists
                icon_path = os.path.join(icon_manager.assets_dir, icon_config)
                if os.path.exists(icon_path):
                    self.default_status_label.setText("Using: Default file")
                else:
                    self.default_status_label.setText("Using: Qt fallback")
            elif isinstance(icon_config, list):
                self.theme_info_label.setText("Light/Dark pair")
                # Check if files exist
                light_exists = os.path.exists(os.path.join(icon_manager.assets_dir, icon_config[0]))
                dark_exists = len(icon_config) > 1 and os.path.exists(os.path.join(icon_manager.assets_dir, icon_config[1]))

                if light_exists and dark_exists:
                    self.default_status_label.setText("Using: Both files")
                elif light_exists:
                    self.default_status_label.setText("Using: Light only")
                else:
                    self.default_status_label.setText("Using: Qt fallback")
            else:
                self.theme_info_label.setText("Invalid config")
                self.default_status_label.setText("Using: Qt fallback")

        except Exception as e:
            log(f"Error updating icon preview: {e}", level="warning", category="ui")
            self.current_icon_label.setText("Error")

    def update_icon_previews(self):
        """Update all icon previews when theme changes (legacy compatibility)."""
        current_item = self.icon_tree.currentItem()
        if current_item and current_item.data(Qt.ItemDataRole.UserRole):
            icon_key = current_item.data(Qt.ItemDataRole.UserRole)
            self.update_icon_previews_dual(icon_key)

    def update_icon_previews_dual(self, icon_key):
        """Update both light and dark icon previews with proper state detection."""
        try:
            from src.gui.icon_manager import get_icon_manager
            icon_manager = get_icon_manager()

            if not icon_manager:
                self.light_status_label.setText("Manager unavailable")
                self.dark_status_label.setText("Manager unavailable")
                self.config_type_label.setText("Configuration: Error")
                return

            # Get icon configuration
            icon_config = icon_manager.ICON_MAP.get(icon_key, "Unknown")

            # Determine configuration type and update label
            if isinstance(icon_config, str):
                self.config_type_label.setText("Configuration: Single icon (auto-adapts)")
                self.config_type_label.setProperty("icon-config", "single")
                self.config_type_label.style().unpolish(self.config_type_label)
                self.config_type_label.style().polish(self.config_type_label)
            elif isinstance(icon_config, list):
                self.config_type_label.setText("Configuration: Light/Dark pair (manual control)")
                self.config_type_label.setProperty("icon-config", "pair")
                self.config_type_label.style().unpolish(self.config_type_label)
                self.config_type_label.style().polish(self.config_type_label)
            else:
                self.config_type_label.setText("Configuration: Invalid")
                self.config_type_label.setProperty("icon-config", "invalid")
                self.config_type_label.style().unpolish(self.config_type_label)
                self.config_type_label.style().polish(self.config_type_label)

            # Update light theme preview (unselected light theme)
            light_icon = icon_manager.get_icon(icon_key, theme_mode='light', is_selected=False, requested_size=96)
            if not light_icon.isNull():
                pixmap = light_icon.pixmap(96, 96)  # Match the label size
                self.light_icon_label.setPixmap(pixmap)

                # Check if this is inverted from original
                if isinstance(icon_config, str):
                    # Single icon - check if this would be inverted
                    self.light_status_label.setText("Original")
                    self.light_status_label.setProperty("icon-status", "available")
                    self.light_status_label.style().unpolish(self.light_status_label)
                    self.light_status_label.style().polish(self.light_status_label)
                else:
                    self.light_status_label.setText("Light variant")
                    self.light_status_label.setProperty("icon-status", "available")
                    self.light_status_label.style().unpolish(self.light_status_label)
                    self.light_status_label.style().polish(self.light_status_label)
            else:
                self.light_icon_label.setText("Missing")
                self.light_status_label.setText("Qt fallback")
                self.light_status_label.setProperty("icon-status", "fallback")
                self.light_status_label.style().unpolish(self.light_status_label)
                self.light_status_label.style().polish(self.light_status_label)

            # Update dark theme preview (unselected dark theme)
            dark_icon = icon_manager.get_icon(icon_key, theme_mode='dark', is_selected=False, requested_size=96)
            if not dark_icon.isNull():
                pixmap = dark_icon.pixmap(96, 96)  # Match the label size
                self.dark_icon_label.setPixmap(pixmap)

                # Check if this is inverted from original
                if isinstance(icon_config, str):
                    # Single icon - original file used directly
                    self.dark_status_label.setText("Original")
                    self.dark_status_label.setProperty("icon-status", "available")
                    self.dark_status_label.style().unpolish(self.dark_status_label)
                    self.dark_status_label.style().polish(self.dark_status_label)
                else:
                    self.dark_status_label.setText("Dark variant")
                    self.dark_status_label.setProperty("icon-status", "available")
                    self.dark_status_label.style().unpolish(self.dark_status_label)
                    self.dark_status_label.style().polish(self.dark_status_label)
            else:
                self.dark_icon_label.setText("Missing")
                self.dark_status_label.setText("Qt fallback")
                self.dark_status_label.setProperty("icon-status", "fallback")
                self.dark_status_label.style().unpolish(self.dark_status_label)
                self.dark_status_label.style().polish(self.dark_status_label)

            # Update reset button states based on whether icons are default
            self._update_reset_button_states(icon_key, icon_config)

        except Exception as e:
            log(f"Error updating dual icon previews: {e}", level="warning", category="ui")
            self.light_status_label.setText("Error")
            self.dark_status_label.setText("Error")
            self.config_type_label.setText("Configuration: Error")

    def _update_reset_button_states(self, icon_key, icon_config):
        """Update reset button states based on whether icons are at default state."""
        from src.gui.icon_manager import get_icon_manager

        icon_manager = get_icon_manager()
        if not icon_manager:
            return

        try:
            if isinstance(icon_config, str):
                # Single icon - check if file exists (custom) vs using default
                icon_path = os.path.join(icon_manager.assets_dir, icon_config)

                # Enable reset only if we have a backup (can actually restore)
                backup_exists = os.path.exists(icon_path + ".backup")

                self.light_reset_btn.setEnabled(backup_exists)
                self.dark_reset_btn.setEnabled(backup_exists)

            elif isinstance(icon_config, list):
                # Light/dark pair - check each file
                light_path = os.path.join(icon_manager.assets_dir, icon_config[0])
                dark_path = os.path.join(icon_manager.assets_dir, icon_config[1]) if len(icon_config) > 1 else None

                light_backup_exists = os.path.exists(light_path + ".backup")
                dark_backup_exists = bool(dark_path and os.path.exists(dark_path + ".backup"))

                self.light_reset_btn.setEnabled(light_backup_exists)
                self.dark_reset_btn.setEnabled(dark_backup_exists)
            else:
                # Invalid config
                self.light_reset_btn.setEnabled(False)
                self.dark_reset_btn.setEnabled(False)

        except Exception as e:
            log(f"Error updating reset button states: {e}", level="warning", category="ui")
            # Enable by default if we can't determine state
            self.light_reset_btn.setEnabled(True)
            self.dark_reset_btn.setEnabled(True)

    def handle_icon_drop(self, file_path):
        """Handle dropped icon file."""
        current_item = self.icon_tree.currentItem()
        if not current_item or not current_item.data(Qt.ItemDataRole.UserRole):
            show_warning(self, "No Icon Selected",
                              "Please select an icon from the list first.")
            return

        icon_key = current_item.data(Qt.ItemDataRole.UserRole)

        # Validate file type
        if not file_path.lower().endswith(('.png', '.ico', '.svg', '.jpg', '.jpeg')):
            show_warning(self, "Invalid File Type",
                              "Please select a valid image file (PNG, ICO, SVG, JPG).")
            return

        # Show confirmation
        confirmation_text = f"Replace the icon for '{self.icon_data[icon_key]['display_name']}' with the selected file?"
        detailed_text = f"File: {file_path}"

        if MessageBoxFactory.question(
            self, "Replace Icon", confirmation_text, detailed_text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self.replace_icon_file(icon_key, file_path)

    def handle_icon_drop_variant(self, file_path, variant):
        """Handle dropped icon file for specific variant (light/dark)."""
        current_item = self.icon_tree.currentItem()
        if not current_item or not current_item.data(Qt.ItemDataRole.UserRole):
            show_warning(self, "No Icon Selected",
                              "Please select an icon from the list first.")
            return

        icon_key = current_item.data(Qt.ItemDataRole.UserRole)

        # Validate file type
        if not file_path.lower().endswith(('.png', '.ico', '.svg', '.jpg', '.jpeg')):
            show_warning(self, "Invalid File Type",
                              "Please select a valid image file (PNG, ICO, SVG, JPG).")
            return

        # Show confirmation
        variant_name = "Light" if variant == 'light' else "Dark"
        confirmation_text = f"Replace the {variant_name.lower()} theme icon for '{self.icon_data[icon_key]['display_name']}' with the selected file?"
        detailed_text = f"File: {file_path}"

        if MessageBoxFactory.question(
            self, "Replace Icon", confirmation_text, detailed_text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self.replace_icon_file_variant(icon_key, file_path, variant)

    def browse_for_icon_variant(self, variant):
        """Browse for icon file for specific light/dark variant."""
        current_item = self.icon_tree.currentItem()
        if not current_item or not current_item.data(Qt.ItemDataRole.UserRole):
            return

        icon_key = current_item.data(Qt.ItemDataRole.UserRole)

        file_dialog = QFileDialog(self)
        file_dialog.setWindowTitle(f"Select {variant.title()} Theme Icon")
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        file_dialog.setNameFilter("Image files (*.png *.ico *.svg *.jpg *.jpeg)")

        if file_dialog.exec() == QFileDialog.DialogCode.Accepted:
            selected_files = file_dialog.selectedFiles()
            if selected_files:
                self.replace_icon_file_variant(icon_key, selected_files[0], variant)

    def browse_for_icon(self):
        """Browse for icon file (legacy compatibility - defaults to light variant)."""
        self.browse_for_icon_variant('light')

    def replace_icon_file(self, icon_key, new_file_path):
        """Replace an icon file with a new one."""
        try:
            from src.gui.icon_manager import get_icon_manager

            icon_manager = get_icon_manager()
            if not icon_manager:
                show_warning(self, "Error", "Icon manager not available.")
                return

            # Get current icon configuration
            icon_config = icon_manager.ICON_MAP.get(icon_key)
            if not icon_config:
                show_warning(self, "Error", f"Unknown icon key: {icon_key}")
                return

            # Determine target filename
            if isinstance(icon_config, str):
                target_filename = icon_config
            elif isinstance(icon_config, list) and len(icon_config) > 0:
                target_filename = icon_config[0]  # Replace light version for now
            else:
                show_warning(self, "Error", "Invalid icon configuration.")
                return

            target_path = os.path.join(icon_manager.assets_dir, target_filename)

            # Create backup if original exists
            if os.path.exists(target_path):
                backup_path = target_path + ".backup"
                shutil.copy2(target_path, backup_path)

            # Copy new file
            shutil.copy2(new_file_path, target_path)

            # Clear icon cache to force reload
            icon_manager.refresh_cache()

            # Update preview and refresh main window icons
            self.update_selected_icon_preview(icon_key)

            # Refresh main window if it exists
            if self.parent_window and hasattr(self.parent_window, 'refresh_icons'):
                self.parent_window.refresh_icons()

            # Don't mark tab as dirty - icon changes are saved immediately

            show_info(self, "Icon Updated",
                                  f"Icon '{self.icon_data[icon_key]['display_name']}' has been updated successfully.")

        except Exception as e:
            show_error(self, "Error", f"Failed to replace icon: {str(e)}")

    def replace_icon_file_variant(self, icon_key, new_file_path, variant):
        """Replace an icon file for a specific light/dark variant."""
        try:
            from src.gui.icon_manager import get_icon_manager

            icon_manager = get_icon_manager()
            if not icon_manager:
                show_warning(self, "Error", "Icon manager not available.")
                return

            # Get current icon configuration
            icon_config = icon_manager.ICON_MAP.get(icon_key)
            if not icon_config:
                show_warning(self, "Error", f"Unknown icon key: {icon_key}")
                return

            # Determine target filename based on variant and current config
            if isinstance(icon_config, str):
                # Single icon - create dark variant filename when needed
                if variant == 'light':
                    target_filename = icon_config
                else:  # dark variant
                    # Create dark variant filename (add -dark before extension)
                    base, ext = os.path.splitext(icon_config)
                    target_filename = f"{base}-dark{ext}"

                    # Always convert to light/dark pair for consistency
                    new_config = [icon_config, target_filename]
                    icon_manager.ICON_MAP[icon_key] = new_config
            elif isinstance(icon_config, list) and len(icon_config) >= 2:
                # Icon pair - choose based on variant
                if variant == 'light':
                    target_filename = icon_config[0]
                else:  # dark
                    target_filename = icon_config[1]
            elif isinstance(icon_config, list) and len(icon_config) == 1:
                # Single item list - treat as single icon
                target_filename = icon_config[0]
            else:
                show_warning(self, "Error", "Invalid icon configuration.")
                return

            target_path = os.path.join(icon_manager.assets_dir, target_filename)

            # Create backup if original exists
            if os.path.exists(target_path):
                backup_path = target_path + ".backup"
                shutil.copy2(target_path, backup_path)

            # Copy new file
            shutil.copy2(new_file_path, target_path)

            # Clear icon cache to force reload
            icon_manager.refresh_cache()

            # Update both previews and refresh main window icons
            self.update_icon_previews_dual(icon_key)

            # Refresh main window if it exists
            if self.parent_window and hasattr(self.parent_window, 'refresh_icons'):
                self.parent_window.refresh_icons()

            # Don't mark tab as dirty - icon changes are saved immediately

            variant_name = f"{variant.title()} theme"
            icon_name = self.icon_data[icon_key]['display_name']
            show_info(self, "Icon Updated",
                                  f"{variant_name} icon for '{icon_name}' has been updated successfully.")

        except Exception as e:
            show_error(self, "Error", f"Failed to replace {variant} icon: {str(e)}")

    def reset_icon_variant(self, variant):
        """Reset a specific light/dark icon variant to default."""
        current_item = self.icon_tree.currentItem()
        if not current_item or not current_item.data(Qt.ItemDataRole.UserRole):
            return

        icon_key = current_item.data(Qt.ItemDataRole.UserRole)
        icon_name = self.icon_data[icon_key]['display_name']
        variant_name = f"{variant.title()} theme"

        question_text = f"Reset the {variant_name.lower()} icon for '{icon_name}' to default?"

        if MessageBoxFactory.question(
            self, "Reset Icon Variant", question_text,
            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self.restore_default_icon_variant(icon_key, variant)

    def restore_default_icon_variant(self, icon_key, variant):
        """Restore a specific light/dark icon variant to its default state."""
        try:
            from src.gui.icon_manager import get_icon_manager

            icon_manager = get_icon_manager()
            if not icon_manager:
                return

            # Get current icon configuration
            icon_config = icon_manager.ICON_MAP.get(icon_key)
            if not icon_config:
                return

            # Determine target filename based on variant
            if isinstance(icon_config, str):
                # Single icon - reset applies to the single file
                target_filename = icon_config
            elif isinstance(icon_config, list):
                if variant == 'light' and len(icon_config) > 0:
                    target_filename = icon_config[0]
                elif variant == 'dark' and len(icon_config) > 1:
                    target_filename = icon_config[1]
                else:
                    show_info(self, "No Reset Needed",
                                          f"No {variant} variant defined for this icon.")
                    return
            else:
                return

            target_path = os.path.join(icon_manager.assets_dir, target_filename)
            backup_path = target_path + ".backup"

            restored = False
            if os.path.exists(backup_path):
                # Restore from backup
                shutil.move(backup_path, target_path)
                restored = True
            else:
                # No backup available - cannot reset to original
                show_warning(self, "Cannot Reset",
                                  f"No backup available for this icon. Original file was not backed up.\n\n"
                                  f"To reset, you'll need to manually restore the original {target_filename} file.")
                return

            if restored:
                # Clear icon cache to force reload
                icon_manager.refresh_cache()

                # Update both previews and refresh main window icons
                self.update_icon_previews_dual(icon_key)

                # Refresh main window if it exists
                if self.parent_window and hasattr(self.parent_window, 'refresh_icons'):
                    self.parent_window.refresh_icons()

                # Don't mark tab as dirty - reset is an immediate filesystem operation

                icon_name = self.icon_data[icon_key]['display_name']
                variant_name = f"{variant.title()} theme"
                show_info(self, "Icon Reset",
                                      f"{variant_name} icon for '{icon_name}' has been reset to default.")
            else:
                show_info(self, "No Changes",
                                      f"No custom {variant} icon found to reset.")

        except Exception as e:
            show_error(self, "Error", f"Failed to reset {variant} icon: {str(e)}")

    def reset_selected_icon(self):
        """Reset selected icon to default."""
        current_item = self.icon_tree.currentItem()
        if not current_item or not current_item.data(Qt.ItemDataRole.UserRole):
            return

        icon_key = current_item.data(Qt.ItemDataRole.UserRole)

        question_text = f"Reset the icon for '{self.icon_data[icon_key]['display_name']}' to default?"

        if MessageBoxFactory.question(
            self, "Reset Icon", question_text,
            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self.restore_default_icon(icon_key)

    def restore_default_icon(self, icon_key):
        """Restore an icon to its default state."""
        try:
            from src.gui.icon_manager import get_icon_manager

            icon_manager = get_icon_manager()
            if not icon_manager:
                return

            # Get current icon configuration
            icon_config = icon_manager.ICON_MAP.get(icon_key)
            if not icon_config:
                return

            # Determine target filename(s)
            filenames = []
            if isinstance(icon_config, str):
                filenames = [icon_config]
            elif isinstance(icon_config, list):
                filenames = icon_config

            # Restore from backup if available
            restored = False
            for filename in filenames:
                target_path = os.path.join(icon_manager.assets_dir, filename)
                backup_path = target_path + ".backup"

                if os.path.exists(backup_path):
                    os.rename(backup_path, target_path)
                    restored = True
                elif os.path.exists(target_path):
                    # If no backup, just remove custom file to use fallback
                    os.remove(target_path)
                    restored = True

            if restored:
                # Clear icon cache to force reload
                icon_manager.refresh_cache()

                # Update preview
                self.update_selected_icon_preview(icon_key)

                show_info(self, "Icon Reset",
                                      f"Icon '{self.icon_data[icon_key]['display_name']}' has been reset to default.")
            else:
                show_info(self, "No Changes",
                                      "No custom icon found to reset.")

        except Exception as e:
            show_error(self, "Error", f"Failed to reset icon: {str(e)}")

    def reset_all_icons(self):
        """Reset all icons to defaults."""
        if MessageBoxFactory.question(
            self, "Reset All Icons", "Reset ALL icons to their default state?",
            detailed_text="This will remove all custom icon files and restore defaults.",
            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            default_button=QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            try:
                from src.gui.icon_manager import get_icon_manager

                icon_manager = get_icon_manager()
                if not icon_manager:
                    return

                reset_count = 0
                for icon_key in icon_manager.ICON_MAP.keys():
                    try:
                        self.restore_default_icon(icon_key)
                        reset_count += 1
                    except Exception as e:
                        log(f"Failed to reset {icon_key}: {e}", level="warning", category="ui")

                # Update current preview if any
                current_item = self.icon_tree.currentItem()
                if current_item and current_item.data(Qt.ItemDataRole.UserRole):
                    icon_key = current_item.data(Qt.ItemDataRole.UserRole)
                    self.update_selected_icon_preview(icon_key)

                show_info(self, "Reset Complete",
                                      f"Reset {reset_count} icons to default state.")

            except Exception as e:
                show_error(self, "Error", f"Failed to reset icons: {str(e)}")

    def validate_all_icons(self):
        """Validate all icon files and show report."""
        try:
            from src.gui.icon_manager import get_icon_manager

            icon_manager = get_icon_manager()
            if not icon_manager:
                show_warning(self, "Error", "Icon manager not available.")
                return

            # Run validation
            result = icon_manager.validate_icons(report=False)

            # Show results in a dialog
            dialog = QDialog(self)
            dialog.setWindowTitle("Icon Validation Report")
            dialog.resize(500, 400)

            layout = QVBoxLayout(dialog)

            # Summary
            summary_label = QLabel(f"Total icons: {len(icon_manager.ICON_MAP)}\n"
                                 f"Found: {len(result['found'])}\n"
                                 f"Missing: {len(result['missing'])}")
            summary_label.setStyleSheet("font-weight: bold; padding: 10px;")
            layout.addWidget(summary_label)

            # Details
            details = QPlainTextEdit()
            details.setReadOnly(True)

            if result['found']:
                details.appendPlainText("=== FOUND ICONS ===")
                for item in result['found']:
                    details.appendPlainText(f"  {item}")
                details.appendPlainText("")

            if result['missing']:
                details.appendPlainText("=== MISSING ICONS ===")
                for item in result['missing']:
                    details.appendPlainText(f"  {item}")

            layout.addWidget(details)

            # Close button
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dialog.accept)
            layout.addWidget(close_btn)

            dialog.exec()

        except Exception as e:
            show_error(self, "Error", f"Failed to validate icons: {str(e)}")
