#!/usr/bin/env python3
"""
Settings management module for bbdrop GUI
Contains all settings-related dialogs and configuration management

SETTINGS STORAGE ARCHITECTURE:
==============================
This application uses TWO separate settings storage systems with clear separation of concerns:

1. QSettings (Qt's built-in system) - FOR UI STATE ONLY:
   - Window geometry/position
   - Column widths/visibility
   - Splitter positions
   - Last active tab
   - Theme choice
   - Font size
   - Sort order
   - Any transient "where did I leave the UI" state

   Location: Platform-specific (Windows Registry, macOS plist, Linux conf files)
   Managed by: Qt automatically via QSettings("BBDropUploader", "BBDropGUI")

2. INI File (~/.bbdrop/bbdrop.ini) - FOR USER CONFIGURATION:
   - Credentials (username, password, API key)
   - Templates
   - Scanning settings (fast scan, sampling, exclusions, etc.)
   - Upload behavior (timeouts, retries, batch size)
   - Storage paths
   - Auto-start/auto-clear preferences
   - Thumbnail settings

   Location: ~/.bbdrop/bbdrop.ini (portable, human-editable)
   Managed by: ConfigParser (manual read/write)

WHY THIS SEPARATION:
- Portability: INI file can be copied to other machines
- Transparency: Users can manually edit INI settings
- Qt Best Practice: QSettings handles platform-specific UI state
- Clear semantics: "How it looks" (QSettings) vs "How it behaves" (INI)
"""

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QMessageBox,
    QListWidget, QListWidgetItem, QApplication, QStackedWidget
)
from PyQt6.QtCore import QSettings

from src.core.image_host_config import save_image_host_setting
from src.utils.logger import log
from src.gui.settings.advanced_tab import AdvancedSettingsWidget
from src.gui.settings.archive_tab import ArchiveSettingsWidget
from src.gui.settings.tab_index import TabIndex

# HostTestDialog moved to src/gui/settings/host_test_dialog.py
# Re-exported here for backward compatibility
from src.gui.settings.host_test_dialog import HostTestDialog  # noqa: F401


class ComprehensiveSettingsDialog(QDialog):
    """Comprehensive settings dialog with tabbed interface"""

    def __init__(self, parent=None, file_host_manager=None):
        super().__init__(parent)
        self.parent_window = parent
        self.file_host_manager = file_host_manager

        # Track dirty state per tab
        self.tab_dirty_states = {}
        self.current_tab_index = 0

        # Initialize QSettings for storing test results and cache
        self.settings = QSettings("BBDropUploader", "BBDropGUI")

        self.setup_ui()
        self.load_settings()
        
    def setup_ui(self):
        """Setup the tabbed settings interface"""
        self.setWindowTitle("Settings & Preferences")
        self.setModal(True)
        self.resize(1010, 670)
        self.setMinimumSize(850, 550)

        # Restore saved geometry or center on parent
        saved_geometry = self.settings.value('settings_dialog/geometry')
        if saved_geometry:
            self.restoreGeometry(saved_geometry)
        else:
            self._center_on_parent()
        
        layout = QVBoxLayout(self)
        
        # Create sidebar navigation + content stack
        nav_content_layout = QHBoxLayout()

        # Left sidebar navigation
        self.nav_list = QListWidget()
        self.nav_list.setFixedWidth(160)
        self.nav_list.setSpacing(1)
        self.nav_list.currentRowChanged.connect(self.on_tab_changed)
        self.nav_list.setStyleSheet("""
            QListWidget {
                border: none;
                border-right: 1px solid palette(mid);
                background: palette(window);
                outline: none;
            }
            QListWidget::item {
                padding: 6px 12px;
                border-radius: 0px;
            }
            QListWidget::item:selected {
                background: palette(highlight);
                color: palette(highlighted-text);
            }
            QListWidget::item:hover:!selected {
                background: palette(midlight);
            }
        """)
        nav_content_layout.addWidget(self.nav_list)

        # Right content area
        self.stack_widget = QStackedWidget()
        nav_content_layout.addWidget(self.stack_widget)

        layout.addLayout(nav_content_layout)

        # Create tabs
        self.setup_general_tab()
        self.setup_image_hosts_tab()
        self.setup_file_hosts_tab()
        self.setup_templates_tab()
        self.setup_tabs_tab()  # Create widgets but don't add tab
        self.setup_icons_tab()  # Create widgets but don't add tab
        self.setup_scanning_tab()
        self.setup_covers_tab()
        self.setup_external_apps_tab()
        self.setup_proxy_tab()
        self.setup_logs_tab()
        self.setup_archive_tab()
        self.setup_advanced_tab()

        # Buttons
        button_layout = QHBoxLayout()
        
        # Reset button on the left
        self.reset_btn = QPushButton("Reset to Defaults")
        self.reset_btn.clicked.connect(self.reset_to_defaults)
        button_layout.addWidget(self.reset_btn)
        
        button_layout.addStretch()
        
        # Standard button order: OK, Apply, Cancel
        self.ok_btn = QPushButton("OK")
        self.ok_btn.clicked.connect(self.save_and_close)
        button_layout.addWidget(self.ok_btn)
        
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.clicked.connect(self.apply_current_tab)
        self.apply_btn.setEnabled(False)  # Initially disabled
        button_layout.addWidget(self.apply_btn)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.on_cancel_clicked)
        button_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(button_layout)
        
    def _add_settings_page(self, widget, label, icon=None):
        """Add a settings page to the sidebar navigation.

        Args:
            widget: The page widget to display when selected.
            label: Text label for the sidebar item.
            icon: Optional QIcon for the sidebar item.
        """
        item = QListWidgetItem(label)
        if icon and not icon.isNull():
            item.setIcon(icon)
        self.nav_list.addItem(item)
        self.stack_widget.addWidget(widget)

    def setup_general_tab(self):
        """Setup the General settings tab (delegated to GeneralTab widget)."""
        from src.gui.settings.general_tab import GeneralTab
        self.general_tab = GeneralTab(parent_window=self.parent_window, settings=self.settings)
        self.general_tab.dirty.connect(lambda: self.mark_tab_dirty(TabIndex.GENERAL))
        self._add_settings_page(self.general_tab, "General")

    def setup_image_hosts_tab(self):
        """Setup the Image Hosts tab using dedicated widget"""
        from src.gui.settings.image_hosts_tab import ImageHostsSettingsWidget

        self.image_hosts_widget = ImageHostsSettingsWidget(self)
        self.image_hosts_widget.settings_changed.connect(lambda: self.mark_tab_dirty(TabIndex.IMAGE_HOSTS))
        # Live-refresh the main window's host combo when hosts are enabled/disabled
        if self.parent_window and hasattr(self.parent_window, 'refresh_image_host_combo'):
            self.image_hosts_widget.settings_changed.connect(self.parent_window.refresh_image_host_combo)
        self._add_settings_page(self.image_hosts_widget, "Image Hosts")

    def setup_templates_tab(self):
        """Setup the Templates tab (delegated to TemplatesTab widget)."""
        from src.gui.settings.templates_tab import TemplatesTab
        self.templates_tab = TemplatesTab(parent_window=self.parent_window)
        self.templates_tab.dirty.connect(lambda: self.mark_tab_dirty(TabIndex.TEMPLATES))
        self._add_settings_page(self.templates_tab, "BBCode templates")
        
    def setup_tabs_tab(self):
        """Setup the Tabs management tab (delegated to TabsTab widget)."""
        from src.gui.settings.tabs_tab import TabsTab
        self.tabs_tab = TabsTab(parent_window=self.parent_window)
        self.tabs_tab.dirty.connect(lambda: self.mark_tab_dirty(TabIndex.GENERAL))
        # Tab management temporarily hidden while deciding on functionality
        # self._add_settings_page(self.tabs_tab, "Tabs")
    
    def setup_logs_tab(self):
        """Setup the Logs tab with log settings"""
        from src.gui.settings.log_tab import LogSettingsWidget
        self.log_settings_widget = LogSettingsWidget(self)
        self.log_settings_widget.settings_changed.connect(lambda: self.mark_tab_dirty(TabIndex.LOGS))
        self.log_settings_widget.load_settings()  # Load current settings
        self._add_settings_page(self.log_settings_widget, "Logging")
        
    def setup_scanning_tab(self):
        """Setup the Image Scanning tab (delegated to ScanningTab widget)."""
        from src.gui.settings.scanning_tab import ScanningTab
        self.scanning_tab = ScanningTab()
        self.scanning_tab.dirty.connect(
            lambda: self.mark_tab_dirty(TabIndex.IMAGE_SCAN)
        )
        self._add_settings_page(self.scanning_tab, "Image Scanner")

    def setup_covers_tab(self):
        """Setup the Cover Photos settings tab (delegated to CoversTab widget)."""
        from src.gui.settings.covers_tab import CoversTab
        self.covers_tab = CoversTab(settings=self.settings)
        self.covers_tab.dirty.connect(lambda: self.mark_tab_dirty(TabIndex.COVERS))
        self._add_settings_page(self.covers_tab, "Cover Photos")

        # Sync cover gallery changes between Image Hosts tab and Covers tab
        if hasattr(self, 'image_hosts_widget'):
            self.image_hosts_widget.cover_gallery_changed.connect(
                self.covers_tab.on_external_cover_gallery_change
            )

    def setup_external_apps_tab(self):
        """Setup the External Apps tab (delegated to HooksTab widget)."""
        from src.gui.settings.hooks_tab import HooksTab
        self.hooks_tab = HooksTab()
        self.hooks_tab.dirty.connect(lambda: self.mark_tab_dirty(TabIndex.HOOKS))
        self._add_settings_page(self.hooks_tab, "App Hooks")

    # ===== File Host Settings (Widget-based) =====

    def setup_file_hosts_tab(self):
        """Setup the File Hosts tab using dedicated widget"""
        from src.gui.settings.file_hosts_tab import FileHostsSettingsWidget

        if not self.file_host_manager:
            # No manager available - show error
            error_widget = QWidget()
            layout = QVBoxLayout(error_widget)
            error_label = QLabel("File host manager not available. Please restart the application.")
            error_label.setWordWrap(True)
            error_label.setStyleSheet("color: red; font-weight: bold;")
            layout.addWidget(error_label)
            layout.addStretch()
            self._add_settings_page(error_widget, "File Hosts")
            return

        # Create file hosts widget (no signals - reads from QSettings cache)
        self.file_hosts_widget = FileHostsSettingsWidget(self, self.file_host_manager)


        # Add tab
        self._add_settings_page(self.file_hosts_widget, "File Hosts")

    def setup_proxy_tab(self):
        """Setup the Proxy settings tab."""
        from src.gui.settings.proxy_tab import ProxySettingsWidget

        self.proxy_widget = ProxySettingsWidget(self)
        self.proxy_widget.settings_changed.connect(lambda: self.mark_tab_dirty(TabIndex.PROXY))
        self._add_settings_page(self.proxy_widget, "Proxy Servers")

    def setup_advanced_tab(self):
        """Setup the Advanced settings tab."""
        self.advanced_widget = AdvancedSettingsWidget()
        self.advanced_widget.settings_changed.connect(lambda: self.mark_tab_dirty(TabIndex.ADVANCED))
        self._add_settings_page(self.advanced_widget, "Advanced")

    def setup_archive_tab(self):
        """Setup the Archive settings tab."""
        self.archive_widget = ArchiveSettingsWidget()
        self.archive_widget.settings_changed.connect(lambda: self.mark_tab_dirty(TabIndex.ARCHIVE))
        self._add_settings_page(self.archive_widget, "Zip Archives")

    def setup_icons_tab(self):
        """Setup the Icons management tab (delegated to IconsTab widget)."""
        from src.gui.settings.icons_tab import IconsTab
        self.icons_tab = IconsTab(parent_window=self.parent_window)
        self.icons_tab.dirty.connect(lambda: self.mark_tab_dirty(TabIndex.GENERAL))
        # Icons management temporarily hidden while deciding on functionality
        # self._add_settings_page(self.icons_tab, "Icons")

    def _center_on_parent(self):
        """Center dialog on parent window or screen"""
        if self.parent():
            # Center on parent window
            parent_geo = self.parent().geometry()
            dialog_geo = self.frameGeometry()
            x = parent_geo.x() + (parent_geo.width() - dialog_geo.width()) // 2
            y = parent_geo.y() + (parent_geo.height() - dialog_geo.height()) // 2
            self.move(x, y)
        else:
            # Center on screen if no parent
            screen = QApplication.primaryScreen()
            if screen:
                screen_geo = screen.geometry()
                dialog_geo = self.frameGeometry()
                x = (screen_geo.width() - dialog_geo.width()) // 2
                y = (screen_geo.height() - dialog_geo.height()) // 2
                self.move(x, y)

    def load_settings(self):
        """Load current settings"""
        # Settings are loaded in setup_ui for each tab
        # Load scanning settings from INI
        self.scanning_tab.load_settings()
        # Load tabs settings
        self._load_tabs_settings()
        # Load external apps settings
        self._load_external_apps_settings()
        # Load file hosts settings
        if hasattr(self, 'file_hosts_widget') and self.file_hosts_widget:
            self.file_hosts_widget.load_from_config()
        # Load advanced settings
        self.advanced_widget.load_from_config()
        # Load archive settings
        self.archive_widget.load_from_config()

    def _load_tabs_settings(self):
        """Load tabs settings if available"""
        try:
            if hasattr(self, 'tabs_tab'):
                self.tabs_tab.load_settings()
        except Exception as e:
            # Silently skip any errors since tabs functionality may be hidden
            pass

    def _load_external_apps_settings(self):
        """Load external apps settings from INI file (delegated to HooksTab)."""
        if hasattr(self, 'hooks_tab'):
            self.hooks_tab.load_settings()

    def save_settings(self):
        """Save all settings (legacy bulk-save — prefer per-tab save_current_tab)."""
        try:
            # Save general tab via its own widget
            if hasattr(self, 'general_tab'):
                self.general_tab.save_settings()

            if self.parent_window:
                # Save scanning settings
                if hasattr(self, 'scanning_tab'):
                    self.scanning_tab.save_settings()

                # Save external apps settings
                if hasattr(self, 'hooks_tab'):
                    self.hooks_tab.save_settings()

                # Save file hosts settings
                if hasattr(self, 'file_hosts_widget') and self.file_hosts_widget:
                    self.file_hosts_widget.save_to_config()

                # Save tabs settings
                self._save_tabs_settings()

            return True
        except Exception as e:
            # Create non-blocking error message
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Critical)
            msg_box.setWindowTitle("Error")
            msg_box.setText(f"Failed to save settings: {str(e)}")
            msg_box.open()
            return False
    
    def _save_tabs_settings(self):
        """Save tabs settings (delegated to TabsTab widget)."""
        if hasattr(self, 'tabs_tab'):
            self.tabs_tab.save_settings()

    def _save_external_apps_settings(self):
        """Save external apps settings to INI file (delegated to HooksTab)."""
        if hasattr(self, 'hooks_tab'):
            self.hooks_tab.save_settings()

    def _reset_tabs_settings(self):
        """Reset tabs settings to defaults (delegated to TabsTab widget)."""
        if hasattr(self, 'tabs_tab'):
            self.tabs_tab.reset_to_defaults()
            
    def reset_to_defaults(self):
        """Reset all settings to defaults"""
        # Create a non-blocking message box
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Reset Settings")
        msg_box.setText("Are you sure you want to reset all settings to defaults?")
        msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg_box.setDefaultButton(QMessageBox.StandardButton.No)
        
        # Connect to slot for non-blocking execution
        msg_box.finished.connect(lambda result: self._handle_reset_confirmation(result))
        msg_box.open()
    
    def _handle_reset_confirmation(self, result):
        """Handle the reset confirmation result"""
        if result == QMessageBox.StandardButton.Yes:
            # Reset image host settings via config system
            save_image_host_setting('imx', 'thumbnail_size', 3)      # 250x250
            save_image_host_setting('imx', 'thumbnail_format', 2)    # Proportional
            save_image_host_setting('imx', 'max_retries', 3)
            save_image_host_setting('imx', 'parallel_batch_size', 4)
            save_image_host_setting('imx', 'upload_connect_timeout', 30)
            save_image_host_setting('imx', 'upload_read_timeout', 120)
            save_image_host_setting('imx', 'auto_rename', True)

            # Refresh Image Hosts tab if it exists
            if hasattr(self, 'image_hosts_widget') and self.image_hosts_widget:
                for panel in self.image_hosts_widget.panels.values():
                    # Rebuild panel UI to reflect reset values
                    panel.max_retries_slider.setValue(3)
                    panel.batch_size_slider.setValue(4)
                    panel.connect_timeout_slider.setValue(30)
                    panel.read_timeout_slider.setValue(120)
                    panel.thumbnail_size_combo.setCurrentIndex(2)
                    panel.thumbnail_format_combo.setCurrentIndex(1)
                    if hasattr(panel, 'auto_rename_check'):
                        panel.auto_rename_check.setChecked(True)

            # Reset general tab
            if hasattr(self, 'general_tab'):
                self.general_tab.reset_to_defaults()
            
            # Reset scanning
            if hasattr(self, 'scanning_tab'):
                self.scanning_tab.reset_to_defaults()
            
            # Reset tabs settings
            self._reset_tabs_settings()
            
    def save_and_close(self):
        """Save settings and close dialog"""
        # Check for unsaved changes in current tab first
        if self.has_unsaved_changes():
            # Save current tab
            if not self.save_current_tab():
                return  # Failed to save, stay open
            self.mark_tab_clean()
        
        # Check all other tabs for unsaved changes
        unsaved_tabs = []
        for i in range(self.stack_widget.count()):
            if i != self.current_tab_index and self.tab_dirty_states.get(i, False):
                unsaved_tabs.append((i, self.nav_list.item(i).text()))

        if unsaved_tabs:
            # Ask user about unsaved changes in other tabs
            tab_names = ", ".join([name for _, name in unsaved_tabs])
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Question)
            msg_box.setWindowTitle("Unsaved Changes")
            msg_box.setText(f"You have unsaved changes in other tabs: {tab_names}")
            msg_box.setInformativeText("Do you want to save all changes before closing?")

            save_all_btn = msg_box.addButton("Save All", QMessageBox.ButtonRole.AcceptRole)
            discard_btn = msg_box.addButton("Discard All", QMessageBox.ButtonRole.DestructiveRole)
            cancel_btn = msg_box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)

            msg_box.setDefaultButton(save_all_btn)
            result = msg_box.exec()

            if msg_box.clickedButton() == save_all_btn:
                # Save all dirty tabs
                for tab_index, _ in unsaved_tabs:
                    old_index = self.current_tab_index
                    self.current_tab_index = tab_index
                    if not self.save_current_tab():
                        self.current_tab_index = old_index
                        return  # Failed to save, stay open
                    self.mark_tab_clean(tab_index)
                    self.current_tab_index = old_index
            elif msg_box.clickedButton() == cancel_btn:
                return  # Cancel, stay open
            # Discard - just continue to close
        
        self.accept()
    
    def on_tab_changed(self, new_index):
        """Handle tab change - check for unsaved changes first"""
        if hasattr(self, 'current_tab_index') and self.current_tab_index != new_index:
            if self.has_unsaved_changes(self.current_tab_index):
                # Block the tab change and ask user about unsaved changes
                self.nav_list.blockSignals(True)
                self.nav_list.setCurrentRow(self.current_tab_index)
                self.nav_list.blockSignals(False)

                self._ask_about_unsaved_changes(
                    lambda: self._change_to_tab(new_index),
                    lambda: None  # Stay on current tab
                )
                return

        # No unsaved changes or same tab, proceed with change
        self.stack_widget.setCurrentIndex(new_index)
        self.current_tab_index = new_index
        self._update_apply_button()
    
    def _change_to_tab(self, new_index):
        """Actually change to the new tab after handling unsaved changes"""
        self.current_tab_index = new_index
        self.nav_list.blockSignals(True)
        self.nav_list.setCurrentRow(new_index)
        self.nav_list.blockSignals(False)
        self.stack_widget.setCurrentIndex(new_index)
        self._update_apply_button()
    
    def has_unsaved_changes(self, tab_index=None):
        """Check if the specified tab (or current tab) has unsaved changes"""
        if tab_index is None:
            tab_index = self.stack_widget.currentIndex()

        return self.tab_dirty_states.get(tab_index, False)

    def mark_tab_dirty(self, tab_index=None):
        """Mark a tab as having unsaved changes"""
        if tab_index is None:
            tab_index = self.stack_widget.currentIndex()

        self.tab_dirty_states[tab_index] = True
        self._update_apply_button()

    def mark_tab_clean(self, tab_index=None):
        """Mark a tab as having no unsaved changes"""
        if tab_index is None:
            tab_index = self.stack_widget.currentIndex()

        self.tab_dirty_states[tab_index] = False
        self._update_apply_button()
    
    def _update_apply_button(self):
        """Update Apply button state based on current tab's dirty state"""
        if hasattr(self, 'apply_btn'):
            self.apply_btn.setEnabled(self.has_unsaved_changes())
    
    def apply_current_tab(self):
        """Apply changes for the current tab only"""
        current_index = self.stack_widget.currentIndex()
        tab_name = self.nav_list.item(current_index).text()
        
        if self.save_current_tab():
            self.mark_tab_clean(current_index)
    
    def save_current_tab(self):
        """Save only the current tab's settings"""
        current_index = self.stack_widget.currentIndex()

        try:
            # NOTE: Tabs and Icons tabs are created but not added to tab widget
            # Actual tab order: General(0), Image Hosts(1), File Hosts(2), Templates(3),
            #                   Image Scan(4), Covers(5), Hooks(6), Proxy(7), Logs(8),
            #                   Archive(9), Advanced(10)
            if current_index == TabIndex.GENERAL:
                return self.general_tab.save_settings()
            elif current_index == TabIndex.IMAGE_HOSTS:
                return self.image_hosts_widget.save_to_config()
            elif current_index == TabIndex.FILE_HOSTS:
                if hasattr(self, 'file_hosts_widget') and self.file_hosts_widget:
                    self.file_hosts_widget.save_to_config()
                return True
            elif current_index == TabIndex.TEMPLATES:
                return self.templates_tab.save_settings()
            elif current_index == TabIndex.LOGS:
                return self.log_settings_widget.save_to_config()
            elif current_index == TabIndex.IMAGE_SCAN:
                return self.scanning_tab.save_settings()
            elif current_index == TabIndex.COVERS:
                return self.covers_tab.save_settings()
            elif current_index == TabIndex.HOOKS:
                return self.hooks_tab.save_settings()
            elif current_index == TabIndex.PROXY:
                # ProxySettingsWidget handles its own persistence via ProxyStorage
                return True
            elif current_index == TabIndex.ADVANCED:
                return self.advanced_widget.save_to_config(parent_window=self.parent_window)
            elif current_index == TabIndex.ARCHIVE:
                return self.archive_widget.save_to_config()
            else:
                return True
        except Exception as e:
            log(f"Error saving tab {current_index}: {e}", level="warning", category="settings")
            return False
    
    def on_cancel_clicked(self):
        """Handle cancel button click - check for unsaved changes first"""
        self._check_unsaved_changes_before_close(lambda: self.reject())
    
    def _check_unsaved_changes_before_close(self, close_callback):
        """Check for unsaved changes and handle closing"""
        has_any_changes = any(self.tab_dirty_states.get(i, False) for i in range(self.stack_widget.count()))

        if has_any_changes:
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Question)
            msg_box.setWindowTitle("Unsaved Changes")
            msg_box.setText("You have unsaved changes. Do you want to save them before closing?")
            msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
            msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)
            msg_box.finished.connect(lambda result: self._handle_unsaved_changes_result(result, close_callback))
            msg_box.open()
        else:
            # No unsaved changes, proceed with close
            close_callback()

    def _handle_unsaved_changes_result(self, result, close_callback):
        """Handle the result of unsaved changes dialog"""
        if result == QMessageBox.StandardButton.Yes:
            # Commit pending template changes, then close
            if hasattr(self, 'templates_tab'):
                self.templates_tab.commit_all_changes()
            close_callback()
        elif result == QMessageBox.StandardButton.No:
            # Discard changes and close
            if hasattr(self, 'templates_tab'):
                self.templates_tab.discard_all_changes()
            close_callback()
        # Cancel - do nothing (dialog stays open)
    
    def closeEvent(self, event):
        """Handle dialog closing with unsaved changes check"""
        # Save dialog geometry for next open
        self.settings.setValue('settings_dialog/geometry', self.saveGeometry())

        # Check for unsaved changes in any tab
        has_unsaved = False
        for i in range(self.stack_widget.count()):
            if self.tab_dirty_states.get(i, False):
                has_unsaved = True
                break

        if has_unsaved:
            # Use the same logic as save_and_close but for close
            event.ignore()  # Prevent immediate close
            self._handle_close_with_unsaved_changes()
        else:
            # No unsaved changes, proceed with normal close
            event.accept()
    
    def _handle_close_with_unsaved_changes(self):
        """Handle close with unsaved changes - reuse save_and_close logic"""
        # Check for unsaved changes in current tab first
        if self.has_unsaved_changes():
            # Save current tab
            if not self.save_current_tab():
                return  # Failed to save, stay open
            self.mark_tab_clean()
        
        # Check all other tabs for unsaved changes
        unsaved_tabs = []
        for i in range(self.stack_widget.count()):
            if i != self.current_tab_index and self.tab_dirty_states.get(i, False):
                unsaved_tabs.append((i, self.nav_list.item(i).text()))

        if unsaved_tabs:
            # Ask user about unsaved changes in other tabs
            tab_names = ", ".join([name for _, name in unsaved_tabs])
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Question)
            msg_box.setWindowTitle("Unsaved Changes")
            msg_box.setText(f"You have unsaved changes in other tabs: {tab_names}")
            msg_box.setInformativeText("Do you want to save all changes before closing?")

            save_all_btn = msg_box.addButton("Save All", QMessageBox.ButtonRole.AcceptRole)
            discard_btn = msg_box.addButton("Discard All", QMessageBox.ButtonRole.DestructiveRole)
            cancel_btn = msg_box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            
            msg_box.setDefaultButton(save_all_btn)
            msg_box.finished.connect(lambda result: self._handle_close_unsaved_result(result, msg_box.clickedButton(), save_all_btn, discard_btn, cancel_btn))
            msg_box.open()
        else:
            # No other unsaved tabs, proceed with close
            self.accept()
    
    def _handle_close_unsaved_result(self, result, clicked_button, save_all_btn, discard_btn, cancel_btn):
        """Handle result of close unsaved changes dialog"""
        if clicked_button == save_all_btn:
            # Save all dirty tabs
            unsaved_tabs = []
            for i in range(self.stack_widget.count()):
                if i != self.current_tab_index and self.tab_dirty_states.get(i, False):
                    unsaved_tabs.append((i, self.nav_list.item(i).text()))

            for tab_index, _ in unsaved_tabs:
                old_index = self.current_tab_index
                self.current_tab_index = tab_index
                if not self.save_current_tab():
                    self.current_tab_index = old_index
                    return  # Failed to save, stay open
                self.mark_tab_clean(tab_index)
                self.current_tab_index = old_index
            
            # All saved successfully, close
            self.accept()
        elif clicked_button == discard_btn:
            # Discard all changes and close
            self.accept()
        # Cancel - do nothing, stay open
    
    def _ask_about_unsaved_changes(self, save_callback, cancel_callback):
        """Ask user about unsaved changes with save/discard/cancel options"""
        current_index = self.stack_widget.currentIndex()
        tab_name = self.nav_list.item(current_index).text()
        
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Question)
        msg_box.setWindowTitle("Unsaved Changes")
        msg_box.setText(f"You have unsaved changes in the '{tab_name}' tab.")
        msg_box.setInformativeText("Do you want to save your changes before switching tabs?")
        
        save_btn = msg_box.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
        discard_btn = msg_box.addButton("Discard", QMessageBox.ButtonRole.DestructiveRole)
        cancel_btn = msg_box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        
        msg_box.setDefaultButton(save_btn)
        
        # Use exec() for blocking dialog instead of open() with signals
        result = msg_box.exec()
        clicked_button = msg_box.clickedButton()
        
        if clicked_button == save_btn:
            # Save current tab first, then proceed
            if self.save_current_tab():
                self.mark_tab_clean()
                save_callback()
        elif clicked_button == discard_btn:
            # Discard changes by reloading the tab and proceed
            self._reload_current_tab()
            self.mark_tab_clean()
            save_callback()
        # Cancel button - do nothing, stay on current tab
    
    def _reload_current_tab(self):
        """Reload current tab's form values from saved settings (discard changes)"""
        current_index = self.stack_widget.currentIndex()
        
        if current_index == TabIndex.GENERAL:
            self.general_tab.reload_settings()
        elif current_index == TabIndex.IMAGE_SCAN:
            self.scanning_tab.reload_settings()
        elif current_index == TabIndex.COVERS:
            self.covers_tab.reload_settings()
        elif current_index == TabIndex.HOOKS:
            self.hooks_tab.reload_settings()
        elif current_index == TabIndex.TEMPLATES:
            self.templates_tab.reload_settings()
        # Other tabs don't have form controls that need reloading

