"""General settings tab — application-wide preferences, storage, and theme."""

import os
import sys
import configparser

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QCheckBox, QComboBox,
    QSpinBox, QLabel, QLineEdit, QPushButton, QRadioButton, QFileDialog,
    QMessageBox, QProgressDialog, QApplication,
)
from PyQt6.QtCore import Qt, pyqtSignal

from bbdrop import (
    load_user_defaults, get_config_path,
    get_central_store_base_path, get_default_central_store_base_path,
    get_project_root, get_base_path,
)
from src.gui.widgets.info_button import InfoButton
from src.utils.logger import log


class GeneralTab(QWidget):
    """Self-contained General settings tab.

    Emits *dirty* whenever any control value changes so the orchestrator
    can track unsaved state without knowing the internals.
    """

    dirty = pyqtSignal()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, parent_window=None, settings=None, parent=None):
        super().__init__(parent)
        self.parent_window = parent_window
        self.settings = settings  # QSettings instance
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        desc = QLabel(
            "Application-wide preferences including storage location, "
            "theme, and automation behavior."
        )
        desc.setWordWrap(True)
        desc.setProperty("class", "tab-description")
        layout.addWidget(desc)

        # Load defaults
        defaults = load_user_defaults()

        # --- General Options group ---
        general_group = QGroupBox("General Options")
        general_layout = QGridLayout(general_group)

        self.confirm_delete_check = QCheckBox("Confirm when removing galleries")
        self.confirm_delete_check.setChecked(defaults.get('confirm_delete', True))
        self.confirm_delete_check.setToolTip("Show confirmation dialog before removing a gallery")
        general_layout.addWidget(self.confirm_delete_check, 0, 0)

        regen_row = QHBoxLayout()
        self.auto_regenerate_bbcode_check = QCheckBox("Auto-regenerate artifacts when data changes")
        self.auto_regenerate_bbcode_check.setChecked(defaults.get('auto_regenerate_bbcode', True))
        self.auto_regenerate_bbcode_check.setToolTip(
            "Automatically regenerate BBCode when template, gallery name, or custom fields change"
        )
        regen_row.addWidget(self.auto_regenerate_bbcode_check)
        regen_row.addWidget(InfoButton(
            "<b>Artifacts</b> are the JSON and BBCode files generated after "
            "a gallery finishes uploading. They contain image URLs, thumbnail "
            "URLs, and formatted BBCode.<br><br>"
            "When enabled, these files are automatically regenerated whenever "
            "you change the template, gallery name, or custom field values."
        ))
        regen_row.addStretch()
        general_layout.addLayout(regen_row, 1, 0)

        self.auto_start_upload_check = QCheckBox("Start uploads automatically")
        self.auto_start_upload_check.setChecked(defaults.get('auto_start_upload', False))
        self.auto_start_upload_check.setToolTip(
            "Automatically start uploads when scanning completes instead of waiting for manual start"
        )
        general_layout.addWidget(self.auto_start_upload_check, 2, 0)

        self.auto_clear_completed_check = QCheckBox("Clear completed items automatically")
        self.auto_clear_completed_check.setChecked(defaults.get('auto_clear_completed', False))
        self.auto_clear_completed_check.setToolTip("Automatically remove completed galleries from the queue")
        general_layout.addWidget(self.auto_clear_completed_check, 3, 0)

        self.check_updates_checkbox = QCheckBox("Check for updates on startup")
        self.check_updates_checkbox.setChecked(defaults.get('check_updates_on_startup', True))
        self.check_updates_checkbox.setToolTip(
            "Automatically check for new versions when the application starts"
        )
        general_layout.addWidget(self.check_updates_checkbox, 4, 0)

        # --- Central Storage group ---
        storage_group = QGroupBox("Central Storage")
        storage_layout = QGridLayout(storage_group)

        location_label = QLabel(
            "<b>Choose location to save data</b> "
            "<i>(database, artifacts, settings, etc.)</i>"
        )
        storage_layout.addWidget(location_label, 2, 0, 1, 3)

        # Get ACTUAL current path from QSettings (source of truth)
        current_path = get_base_path()
        home_path = get_default_central_store_base_path()
        app_root = get_project_root()
        portable_path = os.path.join(app_root, '.bbdrop')

        # Radio buttons — display home with ~ for brevity
        home_display = home_path.replace(os.path.expanduser("~"), "~")
        self.home_radio = QRadioButton(f"Home folder: {home_display}")
        self.home_radio.setToolTip("Store data in your home directory")
        self.portable_radio = QRadioButton(f"App folder (portable): {portable_path}")
        self.portable_radio.setToolTip("Store data alongside the application for portable use")
        self.custom_radio = QRadioButton("Custom location:")
        self.custom_radio.setToolTip("Store data in a custom directory")

        # Determine which radio to check based on ACTUAL current path
        current_norm = os.path.normpath(current_path)
        home_norm = os.path.normpath(home_path)
        portable_norm = os.path.normpath(portable_path)

        if current_norm == portable_norm:
            self.portable_radio.setChecked(True)
            storage_mode = 'portable'
        elif current_norm == home_norm:
            self.home_radio.setChecked(True)
            storage_mode = 'home'
        else:
            self.custom_radio.setChecked(True)
            storage_mode = 'custom'

        # Custom path input and browse button
        self.path_edit = QLineEdit(current_path if storage_mode == 'custom' else '')
        self.path_edit.setReadOnly(True)
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.setToolTip("Browse for custom data directory")
        self.browse_btn.clicked.connect(self._browse_central_store)

        # Layout radio buttons and custom path controls
        storage_layout.addWidget(self.home_radio, 3, 0, 1, 3)
        storage_layout.addWidget(self.portable_radio, 4, 0, 1, 3)
        storage_layout.addWidget(self.custom_radio, 5, 0)
        storage_layout.addWidget(self.path_edit, 5, 1)
        storage_layout.addWidget(self.browse_btn, 5, 2)

        # Enable/disable custom path controls based on radio selection
        def update_custom_path_controls():
            is_custom = self.custom_radio.isChecked()
            self.path_edit.setReadOnly(not is_custom)
            self.browse_btn.setEnabled(is_custom)
            if not is_custom:
                self.path_edit.clear()

        self.home_radio.toggled.connect(update_custom_path_controls)
        self.portable_radio.toggled.connect(update_custom_path_controls)
        self.custom_radio.toggled.connect(update_custom_path_controls)

        # Initialize custom path controls state
        update_custom_path_controls()

        # --- Gallery Artifacts group ---
        artifacts_group = QGroupBox("Gallery Artifacts")
        artifacts_layout = QVBoxLayout(artifacts_group)
        artifacts_info_row = QHBoxLayout()
        artifacts_info = QLabel("JSON / BBcode files containing uploaded gallery details.")
        artifacts_info.setWordWrap(True)
        artifacts_info.setStyleSheet("color: #666; font-style: italic;")
        artifacts_info_row.addWidget(artifacts_info)
        artifacts_info_row.addWidget(InfoButton(
            "<b>Gallery subfolder:</b> Creates a <code>.uploaded</code> folder "
            "inside each gallery's directory with that gallery's artifacts. "
            "Useful if you organize by folder and want results alongside source images.<br><br>"
            "<b>Central storage:</b> Saves all artifacts in one location "
            "(your chosen data directory). Useful for browsing all upload "
            "results in one place.<br><br>"
            "You can enable both &mdash; artifacts are saved to each location independently."
        ))
        artifacts_layout.addLayout(artifacts_info_row)

        self.store_in_uploaded_check = QCheckBox(
            "Save artifacts in '.uploaded' subfolder within the gallery"
        )
        self.store_in_uploaded_check.setToolTip("Save BBCode in the uploaded folder for each gallery")
        self.store_in_uploaded_check.setChecked(defaults.get('store_in_uploaded', True))
        artifacts_layout.addWidget(self.store_in_uploaded_check)

        self.store_in_central_check = QCheckBox("Save artifacts in central storage")
        self.store_in_central_check.setToolTip("Save all BBCode in a central location")
        self.store_in_central_check.setChecked(defaults.get('store_in_central', True))
        artifacts_layout.addWidget(self.store_in_central_check)

        # --- Appearance / Theme group ---
        theme_group = QGroupBox("Appearance / Theme")
        theme_layout = QGridLayout(theme_group)

        # Theme setting
        self.theme_combo = QComboBox()
        self.theme_combo.setToolTip("Select light or dark UI theme")
        self.theme_combo.addItems(["light", "dark"])

        if self.parent_window and hasattr(self.parent_window, 'settings'):
            current_theme = self.parent_window.settings.value('ui/theme', 'dark')
            index = self.theme_combo.findText(current_theme)
            if index >= 0:
                self.theme_combo.setCurrentIndex(index)

        theme_label = QLabel("<b>Theme mode</b>:")
        theme_layout.addWidget(theme_label, 0, 0)
        theme_layout.addWidget(self.theme_combo, 0, 1)

        # Font size setting
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(6, 24)
        self.font_size_spin.setSuffix(" pt")
        self.font_size_spin.setToolTip(
            "Base font size for the interface (affects table, labels, buttons)"
        )

        if self.parent_window and hasattr(self.parent_window, 'settings'):
            current_font_size = int(self.parent_window.settings.value('ui/font_size', 9))
            self.font_size_spin.setValue(current_font_size)
        else:
            self.font_size_spin.setValue(9)

        font_label = QLabel("<b>Text size</b>:")
        theme_layout.addWidget(font_label, 1, 0)
        theme_layout.addWidget(self.font_size_spin, 1, 1)

        # Icons-only mode for quick settings buttons
        qs_row = QHBoxLayout()
        self.quick_settings_icons_only_check = QCheckBox(
            "Show icons only on quick settings buttons"
        )
        self.quick_settings_icons_only_check.setToolTip(
            "When enabled, quick settings buttons will always show icons only,\n"
            "regardless of available space (overrides adaptive text display)"
        )

        if self.parent_window and hasattr(self.parent_window, 'settings'):
            icons_only = self.parent_window.settings.value(
                'ui/quick_settings_icons_only', False, type=bool
            )
            self.quick_settings_icons_only_check.setChecked(icons_only)

        qs_row.addWidget(self.quick_settings_icons_only_check)
        qs_row.addWidget(InfoButton(
            "Quick settings are the buttons in the toolbar area of the main "
            "window (pause, bandwidth limit, theme toggle, etc.). By default "
            "they show text labels when space allows. This forces them to "
            "always show just icons."
        ))
        qs_row.addStretch()
        theme_layout.addLayout(qs_row, 2, 0, 1, 2)

        # Show file host logos in worker table
        self.show_worker_logos_check = QCheckBox(
            "Show file host logos in upload workers table"
        )
        self.show_worker_logos_check.setToolTip(
            "When enabled, shows file host logos instead of text names\n"
            "in the upload workers status table"
        )

        if self.parent_window and hasattr(self.parent_window, 'settings'):
            show_logos = self.parent_window.settings.value(
                'ui/show_worker_logos', True, type=bool
            )
            self.show_worker_logos_check.setChecked(show_logos)

        theme_layout.addWidget(self.show_worker_logos_check, 3, 0, 1, 2)

        # Set column stretch for 50/50 split
        theme_layout.setColumnStretch(0, 1)
        theme_layout.setColumnStretch(1, 1)

        # --- Assemble 2x2 grid ---
        grid_layout = QGridLayout()
        grid_layout.setVerticalSpacing(12)
        grid_layout.addWidget(general_group, 0, 0)     # Top left
        grid_layout.addWidget(theme_group, 0, 1)        # Top right
        grid_layout.addWidget(storage_group, 1, 0)      # Row 1 left
        grid_layout.addWidget(artifacts_group, 1, 1)     # Row 1 right

        grid_layout.setColumnStretch(0, 50)
        grid_layout.setColumnStretch(1, 50)

        layout.addLayout(grid_layout)
        layout.addStretch()

        # --- Connect change signals to dirty ---
        self.confirm_delete_check.toggled.connect(self.dirty.emit)
        self.auto_regenerate_bbcode_check.toggled.connect(self.dirty.emit)
        self.auto_start_upload_check.toggled.connect(self.dirty.emit)
        self.auto_clear_completed_check.toggled.connect(self.dirty.emit)
        self.check_updates_checkbox.toggled.connect(self.dirty.emit)
        self.store_in_uploaded_check.toggled.connect(self.dirty.emit)
        self.store_in_central_check.toggled.connect(self.dirty.emit)
        self.home_radio.toggled.connect(self.dirty.emit)
        self.portable_radio.toggled.connect(self.dirty.emit)
        self.custom_radio.toggled.connect(self.dirty.emit)
        self.path_edit.textChanged.connect(self.dirty.emit)
        self.theme_combo.currentIndexChanged.connect(self.dirty.emit)
        self.font_size_spin.valueChanged.connect(self.dirty.emit)
        self.quick_settings_icons_only_check.toggled.connect(self.dirty.emit)
        self.show_worker_logos_check.toggled.connect(self.dirty.emit)

    # ------------------------------------------------------------------
    # Browse / directory selection helpers
    # ------------------------------------------------------------------

    def _browse_central_store(self):
        """Browse for central store directory."""
        current_path = self.path_edit.text() or get_default_central_store_base_path()

        dialog = QFileDialog(self)
        dialog.setWindowTitle("Select Central Store Directory")
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        dialog.setDirectory(current_path)

        dialog.fileSelected.connect(self._handle_directory_selected)
        dialog.open()

    def _handle_directory_selected(self, directory):
        """Handle selected directory."""
        if directory:
            self.custom_radio.setChecked(True)
            self.path_edit.setText(directory)
            self.dirty.emit()

    # ------------------------------------------------------------------
    # Load / Reload
    # ------------------------------------------------------------------

    def load_settings(self):
        """Load general settings from INI + QSettings.

        Called during initial dialog construction.  The setup_ui already
        reads defaults, so this is intentionally a no-op unless the tab
        needs a full re-read later.
        """
        pass  # values are loaded during _setup_ui

    def reload_settings(self):
        """Reload General tab form values from saved settings (discard changes)."""
        defaults = load_user_defaults()

        self.confirm_delete_check.setChecked(defaults.get('confirm_delete', True))
        self.auto_regenerate_bbcode_check.setChecked(defaults.get('auto_regenerate_bbcode', True))
        self.auto_start_upload_check.setChecked(defaults.get('auto_start_upload', False))
        self.auto_clear_completed_check.setChecked(defaults.get('auto_clear_completed', False))
        self.check_updates_checkbox.setChecked(defaults.get('check_updates_on_startup', True))

        self.store_in_uploaded_check.setChecked(defaults.get('store_in_uploaded', True))
        self.store_in_central_check.setChecked(defaults.get('store_in_central', True))

        current_path = defaults.get('central_store_path') or get_central_store_base_path()
        self.path_edit.setText(current_path)

        if self.parent_window and hasattr(self.parent_window, 'settings'):
            current_theme = self.parent_window.settings.value('ui/theme', 'dark')
            index = self.theme_combo.findText(current_theme)
            if index >= 0:
                self.theme_combo.setCurrentIndex(index)

        if self.parent_window and hasattr(self.parent_window, 'settings'):
            current_font_size = int(self.parent_window.settings.value('ui/font_size', 9))
            self.font_size_spin.setValue(current_font_size)

    def reset_to_defaults(self):
        """Reset General-tab controls to their default values."""
        self.confirm_delete_check.setChecked(True)
        self.store_in_uploaded_check.setChecked(True)
        self.store_in_central_check.setChecked(True)
        self.theme_combo.setCurrentText("dark")
        self.font_size_spin.setValue(9)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save_settings(self):
        """Persist General tab values to INI + QSettings.

        Returns True on success, False on error.
        """
        try:
            config = configparser.ConfigParser()
            config_file = get_config_path()

            if os.path.exists(config_file):
                config.read(config_file, encoding='utf-8')

            if 'UPLOAD' not in config:
                config.add_section('UPLOAD')
            if 'DEFAULTS' not in config:
                config.add_section('DEFAULTS')

            # General settings
            config.set('DEFAULTS', 'confirm_delete', str(self.confirm_delete_check.isChecked()))
            config.set('DEFAULTS', 'auto_regenerate_bbcode', str(self.auto_regenerate_bbcode_check.isChecked()))
            config.set('DEFAULTS', 'auto_start_upload', str(self.auto_start_upload_check.isChecked()))
            config.set('DEFAULTS', 'auto_clear_completed', str(self.auto_clear_completed_check.isChecked()))
            config.set('DEFAULTS', 'check_updates_on_startup', str(self.check_updates_checkbox.isChecked()))
            config.set('DEFAULTS', 'store_in_uploaded', str(self.store_in_uploaded_check.isChecked()))
            config.set('DEFAULTS', 'store_in_central', str(self.store_in_central_check.isChecked()))

            # Determine storage mode and path
            current_active_path = get_central_store_base_path()

            new_path = None
            storage_mode = 'home'

            if self.home_radio.isChecked():
                storage_mode = 'home'
                new_path = get_default_central_store_base_path()
            elif self.portable_radio.isChecked():
                storage_mode = 'portable'
                app_root = get_project_root()
                new_path = os.path.join(app_root, '.bbdrop')
            elif self.custom_radio.isChecked():
                storage_mode = 'custom'
                new_path = self.path_edit.text().strip()

            # Check if path is actually changing
            if new_path and os.path.normpath(new_path) != os.path.normpath(current_active_path):
                # Check if NEW location already has a config file
                new_config_file = os.path.join(new_path, 'bbdrop.ini')
                if os.path.exists(new_config_file):
                    conflict_msg = QMessageBox(self)
                    conflict_msg.setIcon(QMessageBox.Icon.Warning)
                    conflict_msg.setWindowTitle("Existing Configuration Found")
                    conflict_msg.setText(
                        f"The new location already contains an bbdrop.ini file:\n{new_config_file}"
                    )
                    conflict_msg.setInformativeText("How would you like to handle this?")

                    keep_btn = conflict_msg.addButton("Keep Existing", QMessageBox.ButtonRole.YesRole)
                    overwrite_btn = conflict_msg.addButton("Overwrite with Current", QMessageBox.ButtonRole.NoRole)
                    cancel_btn = conflict_msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)

                    conflict_msg.setDefaultButton(keep_btn)
                    conflict_msg.exec()

                    if conflict_msg.clickedButton() == cancel_btn:
                        return True
                    elif conflict_msg.clickedButton() == keep_btn:
                        if self.parent_window and hasattr(self.parent_window, 'settings'):
                            if storage_mode == 'home':
                                self.parent_window.settings.remove("config/base_path")
                            else:
                                self.parent_window.settings.setValue("config/base_path", new_path)
                        QMessageBox.information(
                            self, "Restart Required",
                            "Please restart the application to use the new storage location."
                        )
                        return True
                    # else: overwrite — continue with migration logic below

                # Path is changing — handle migration
                if os.path.exists(current_active_path):
                    msg_box = QMessageBox(self)
                    msg_box.setIcon(QMessageBox.Icon.Question)
                    msg_box.setWindowTitle("Storage Location Change")
                    msg_box.setText(
                        f"You're changing the data location from:\n"
                        f"{current_active_path}\nto:\n{new_path}"
                    )
                    msg_box.setInformativeText(
                        "Would you like to migrate your existing data?\n\n"
                        "Note: The application will need to restart after migration."
                    )

                    yes_btn = msg_box.addButton("Yes - Migrate & Restart", QMessageBox.ButtonRole.YesRole)
                    no_btn = msg_box.addButton("No - Fresh Start", QMessageBox.ButtonRole.NoRole)
                    cancel_btn = msg_box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)

                    msg_box.setDefaultButton(yes_btn)
                    msg_box.exec()

                    if msg_box.clickedButton() == cancel_btn:
                        return True

                    # CRITICAL: Save base path to QSettings FIRST
                    if self.parent_window and hasattr(self.parent_window, 'settings'):
                        if storage_mode == 'home':
                            self.parent_window.settings.remove("config/base_path")
                        else:
                            self.parent_window.settings.setValue("config/base_path", new_path)

                    # Save new settings to INI file in NEW location
                    config.set('DEFAULTS', 'storage_mode', storage_mode)
                    config.set('DEFAULTS', 'central_store_path', new_path)
                    new_config_file = os.path.join(new_path, 'bbdrop.ini')
                    os.makedirs(new_path, exist_ok=True)
                    with open(new_config_file, 'w', encoding='utf-8') as f:
                        config.write(f)

                    if msg_box.clickedButton() == yes_btn:
                        self._perform_migration_and_restart(current_active_path, new_path)
                    else:
                        QMessageBox.information(
                            self, "Restart Required",
                            "Please restart the application to use the new storage location."
                        )
                else:
                    # Old path doesn't exist, just save
                    if self.parent_window and hasattr(self.parent_window, 'settings'):
                        if storage_mode == 'home':
                            self.parent_window.settings.remove("config/base_path")
                        else:
                            self.parent_window.settings.setValue("config/base_path", new_path)

                    config.set('DEFAULTS', 'storage_mode', storage_mode)
                    config.set('DEFAULTS', 'central_store_path', new_path)
                    new_config_file = os.path.join(new_path, 'bbdrop.ini')
                    os.makedirs(new_path, exist_ok=True)
                    with open(new_config_file, 'w', encoding='utf-8') as f:
                        config.write(f)
            else:
                # Path not changing, just save other settings
                config.set('DEFAULTS', 'storage_mode', storage_mode)
                if new_path:
                    config.set('DEFAULTS', 'central_store_path', new_path)
                with open(config_file, 'w', encoding='utf-8') as f:
                    config.write(f)

                # CRITICAL: Save base path to QSettings for bootstrap
                if self.parent_window and hasattr(self.parent_window, 'settings'):
                    if storage_mode == 'home':
                        self.parent_window.settings.remove("config/base_path")
                    elif new_path:
                        self.parent_window.settings.setValue("config/base_path", new_path)

            # Update parent GUI controls
            if self.parent_window:
                if hasattr(self.parent_window, 'confirm_delete_check'):
                    self.parent_window.confirm_delete_check.setChecked(self.confirm_delete_check.isChecked())
                if hasattr(self.parent_window, 'store_in_uploaded_check'):
                    self.parent_window.store_in_uploaded_check.setChecked(self.store_in_uploaded_check.isChecked())
                if hasattr(self.parent_window, 'store_in_central_check'):
                    self.parent_window.store_in_central_check.setChecked(self.store_in_central_check.isChecked())
                if storage_mode == 'custom':
                    self.parent_window.central_store_path_value = new_path

                # Save theme and font size to QSettings
                if hasattr(self.parent_window, 'settings'):
                    font_size = self.font_size_spin.value()
                    theme = self.theme_combo.currentText()
                    self.parent_window.settings.setValue('ui/theme', theme)
                    self.parent_window.settings.setValue('ui/font_size', font_size)

                    # Save icons-only setting
                    icons_only = self.quick_settings_icons_only_check.isChecked()
                    self.parent_window.settings.setValue('ui/quick_settings_icons_only', icons_only)

                    # Apply to adaptive panel immediately
                    if hasattr(self.parent_window, 'adaptive_settings_panel'):
                        self.parent_window.adaptive_settings_panel.set_icons_only_mode(icons_only)

                    # Save worker logos setting
                    show_logos = self.show_worker_logos_check.isChecked()
                    self.parent_window.settings.setValue('ui/show_worker_logos', show_logos)

                    # Apply theme and font size immediately
                    self.parent_window.apply_theme(theme)
                    if hasattr(self.parent_window, 'theme_toggle_btn'):
                        tooltip = "Switch to light theme" if theme == 'dark' else "Switch to dark theme"
                        self.parent_window.theme_toggle_btn.setToolTip(tooltip)
                    if hasattr(self.parent_window, 'apply_font_size'):
                        self.parent_window.apply_font_size(font_size)

            return True
        except Exception as e:
            log(f"Error saving general settings: {e}", level="warning", category="settings")
            return False

    # ------------------------------------------------------------------
    # Migration helper
    # ------------------------------------------------------------------

    def _perform_migration_and_restart(self, old_path, new_path):
        """Perform migration of data and restart the application."""
        import shutil
        import subprocess

        progress = QProgressDialog("Migrating data...", None, 0, 5, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setCancelButton(None)
        progress.setValue(0)

        try:
            os.makedirs(new_path, exist_ok=True)

            # Close database connection if parent has one
            if self.parent_window and hasattr(self.parent_window, 'queue_manager'):
                progress.setLabelText("Closing database connection...")
                try:
                    self.parent_window.queue_manager.shutdown()
                except (AttributeError, RuntimeError):
                    pass

            progress.setValue(1)

            # Migrate database files
            progress.setLabelText("Migrating database...")
            for db_file in ['bbdrop.db', 'bbdrop.db-shm', 'bbdrop.db-wal']:
                old_db = os.path.join(old_path, db_file)
                new_db = os.path.join(new_path, db_file)
                if os.path.exists(old_db):
                    shutil.copy2(old_db, new_db)

            progress.setValue(2)

            # Migrate templates
            progress.setLabelText("Migrating templates...")
            old_templates = os.path.join(old_path, 'templates')
            new_templates = os.path.join(new_path, 'templates')
            if os.path.exists(old_templates):
                if os.path.exists(new_templates):
                    shutil.rmtree(new_templates)
                shutil.copytree(old_templates, new_templates)

            progress.setValue(3)

            # Migrate galleries
            progress.setLabelText("Migrating galleries...")
            old_galleries = os.path.join(old_path, 'galleries')
            new_galleries = os.path.join(new_path, 'galleries')
            if os.path.exists(old_galleries):
                if os.path.exists(new_galleries):
                    shutil.rmtree(new_galleries)
                shutil.copytree(old_galleries, new_galleries)

            progress.setValue(4)

            # Migrate logs
            progress.setLabelText("Migrating logs...")
            old_logs = os.path.join(old_path, 'logs')
            new_logs = os.path.join(new_path, 'logs')
            if os.path.exists(old_logs):
                if os.path.exists(new_logs):
                    shutil.rmtree(new_logs)
                shutil.copytree(old_logs, new_logs)

            progress.setValue(5)
            progress.close()

            # Show success and restart
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setWindowTitle("Migration Complete")
            msg.setText(f"Data successfully migrated to:\n{new_path}")
            msg.setInformativeText("The application will now restart to use the new location.")
            msg.exec()

            # Restart the application
            if self.parent_window:
                self.parent_window.close()
            python = sys.executable
            subprocess.Popen([python, "bbdrop.py", "--gui"])
            QApplication.quit()

        except Exception as e:
            progress.close()
            QMessageBox.critical(
                self, "Migration Failed",
                f"Failed to migrate data: {str(e)}\n\n"
                "The settings have been saved but data was not migrated.\n"
                "Please manually copy your data or revert the settings."
            )
