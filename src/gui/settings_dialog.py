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

import os
import sys
import configparser
import subprocess
from typing import List, Dict, Any, Optional

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QTabWidget, QPushButton, QCheckBox, QComboBox, QSpinBox, QSlider,
    QLabel, QGroupBox, QLineEdit, QMessageBox, QFileDialog,
    QListWidget, QListWidgetItem, QPlainTextEdit, QInputDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QButtonGroup, QFrame, QSplitter, QRadioButton, QApplication, QScrollArea,
    QProgressBar, QStackedWidget
)
from PyQt6.QtCore import Qt, QSettings, pyqtSignal, QTimer
from PyQt6.QtGui import QIcon, QFont, QColor, QTextCharFormat, QPixmap, QPainter, QPen, QDragEnterEvent, QDropEvent
from PyQt6.QtGui import QSyntaxHighlighter

# Import local modules
from bbdrop import load_user_defaults, get_config_path, encrypt_password, decrypt_password
from src.core.image_host_config import get_image_host_setting, save_image_host_setting
from src.utils.format_utils import timestamp, format_binary_size
from src.utils.logger import log
from src.gui.dialogs.message_factory import MessageBoxFactory, show_info, show_error, show_warning
from src.gui.settings.advanced_tab import AdvancedSettingsWidget
from src.gui.settings.archive_tab import ArchiveSettingsWidget


class TabIndex:
    """Named constants for settings tab indices to prevent index mismatch bugs."""
    GENERAL = 0
    IMAGE_HOSTS = 1
    FILE_HOSTS = 2
    TEMPLATES = 3
    IMAGE_SCAN = 4
    COVERS = 5
    HOOKS = 6
    PROXY = 7
    LOGS = 8
    ARCHIVE = 9
    ADVANCED = 10


class IconDropFrame(QFrame):
    """Drop-enabled frame for icon files"""
    
    icon_dropped = pyqtSignal(str)  # Emits file path when icon is dropped
    
    def __init__(self, variant_type):
        super().__init__()
        self.variant_type = variant_type
        self.setAcceptDrops(True)
        
    def dragEnterEvent(self, event: QDragEnterEvent | None) -> None:
        """Handle drag enter event"""
        if event is None:
            return
        mime_data = event.mimeData()
        if mime_data and mime_data.hasUrls():
            urls = mime_data.urls()
            if len(urls) == 1:
                file_path = urls[0].toLocalFile()
                if file_path.lower().endswith(('.png', '.ico', '.svg', '.jpg', '.jpeg')):
                    event.acceptProposedAction()
                    return
        event.ignore()
        
    def dropEvent(self, event: QDropEvent | None) -> None:
        """Handle drop event"""
        if event is None:
            return
        mime_data = event.mimeData()
        if not mime_data:
            if event:
                event.ignore()
            return
        urls = mime_data.urls()
        if len(urls) == 1:
            file_path = urls[0].toLocalFile()
            if file_path.lower().endswith(('.png', '.ico', '.svg', '.jpg', '.jpeg')):
                self.icon_dropped.emit(file_path)
                event.acceptProposedAction()
                return
        event.ignore()


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

    def _load_advanced_settings(self):
        """Load advanced settings from INI file and QSettings."""
        from bbdrop import get_config_path

        config = configparser.ConfigParser()
        config_file = get_config_path()
        values = {}

        if os.path.exists(config_file):
            config.read(config_file, encoding='utf-8')
            if config.has_section('Advanced'):
                for key, value in config.items('Advanced'):
                    # Convert string values back to appropriate types
                    if value.lower() in ('true', 'false'):
                        values[key] = value.lower() == 'true'
                    else:
                        try:
                            values[key] = int(value)
                        except ValueError:
                            try:
                                values[key] = float(value)
                            except ValueError:
                                values[key] = value

        # Load bandwidth settings from QSettings (where BandwidthManager stores them)
        qsettings = QSettings("BBDropUploader", "Settings")
        alpha_up = qsettings.value("bandwidth/alpha_up", None)
        alpha_down = qsettings.value("bandwidth/alpha_down", None)
        if alpha_up is not None:
            values["bandwidth/alpha_up"] = float(alpha_up)
        if alpha_down is not None:
            values["bandwidth/alpha_down"] = float(alpha_down)

        if values:
            self.advanced_widget.set_values(values)

    def _save_proxy_settings(self):
        """Save proxy settings.

        The ProxySettingsWidget handles its own persistence via ProxyStorage,
        so this just marks the tab as clean.
        """
        return True

    def _save_advanced_settings(self):
        """Save advanced settings to INI file (only non-default values).

        Bandwidth settings are also saved to QSettings for BandwidthManager.
        """
        from bbdrop import get_config_path

        config = configparser.ConfigParser()
        config_file = get_config_path()

        if os.path.exists(config_file):
            config.read(config_file, encoding='utf-8')

        # Remove existing Advanced section and recreate with current values
        if config.has_section('Advanced'):
            config.remove_section('Advanced')

        all_values = self.advanced_widget.get_values()
        non_defaults = self.advanced_widget.get_non_default_values()

        # Save non-defaults to INI (excluding bandwidth settings which use QSettings)
        non_bandwidth_settings = {k: v for k, v in non_defaults.items()
                                  if not k.startswith('bandwidth/')}
        if non_bandwidth_settings:
            config.add_section('Advanced')
            for key, value in non_bandwidth_settings.items():
                config.set('Advanced', key, str(value))

        with open(config_file, 'w', encoding='utf-8') as f:
            config.write(f)

        # Save bandwidth settings to QSettings (for BandwidthManager)
        alpha_up = all_values.get('bandwidth/alpha_up', 0.6)
        alpha_down = all_values.get('bandwidth/alpha_down', 0.15)

        qsettings = QSettings("BBDropUploader", "Settings")
        qsettings.setValue("bandwidth/alpha_up", alpha_up)
        qsettings.setValue("bandwidth/alpha_down", alpha_down)

        # Update the running BandwidthManager if available
        if self.parent() and hasattr(self.parent(), 'worker_signal_handler'):
            handler = self.parent().worker_signal_handler
            if hasattr(handler, 'bandwidth_manager'):
                handler.bandwidth_manager.update_smoothing(alpha_up, alpha_down)

        return True

    def _save_archive_settings(self):
        """Save archive settings to INI file."""
        from bbdrop import get_config_path

        config = configparser.ConfigParser()
        config_file = get_config_path()

        if os.path.exists(config_file):
            config.read(config_file, encoding='utf-8')

        if not config.has_section('DEFAULTS'):
            config.add_section('DEFAULTS')

        # Get settings from widget
        archive_settings = self.archive_widget.get_settings()

        # Save to DEFAULTS section
        config.set('DEFAULTS', 'archive_format', archive_settings['archive_format'])
        config.set('DEFAULTS', 'archive_compression', archive_settings['archive_compression'])
        config.set('DEFAULTS', 'archive_split_enabled', str(archive_settings['archive_split_enabled']))
        config.set('DEFAULTS', 'archive_split_size_mb', str(archive_settings['archive_split_size_mb']))

        with open(config_file, 'w', encoding='utf-8') as f:
            config.write(f)

        return True

    def _load_archive_settings(self):
        """Load archive settings from user defaults."""
        settings = load_user_defaults()
        self.archive_widget.load_settings(settings)

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
        self._load_file_hosts_settings()
        # Load advanced settings
        self._load_advanced_settings()
        # Load archive settings
        self._load_archive_settings()

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

    def _load_file_hosts_settings(self):
        """Load file hosts settings from INI file and encrypted credentials from QSettings"""
        try:
            # Check if widget exists
            if not hasattr(self, 'file_hosts_widget') or not self.file_hosts_widget:
                return

            from src.core.file_host_config import get_config_manager
            from bbdrop import get_credential, decrypt_password

            config = configparser.ConfigParser()
            config_file = get_config_path()

            if os.path.exists(config_file):
                config.read(config_file, encoding='utf-8')

            # Prepare settings dict
            settings_dict = {
                'global_limit': 3,
                'per_host_limit': 2,
                'hosts': {}
            }

            # Load connection limits
            if 'FILE_HOSTS' in config:
                settings_dict['global_limit'] = config.getint('FILE_HOSTS', 'global_limit', fallback=3)
                settings_dict['per_host_limit'] = config.getint('FILE_HOSTS', 'per_host_limit', fallback=2)

            # Load per-host settings
            config_manager = get_config_manager()
            for host_id in config_manager.hosts.keys():
                # Use new API for layered config (INI → JSON defaults → hardcoded)
                from src.core.file_host_config import get_file_host_setting

                host_settings = {
                    'enabled': get_file_host_setting(host_id, 'enabled', 'bool'),
                    'credentials': '',
                    'trigger': get_file_host_setting(host_id, 'trigger', 'str')  # Single string value
                }

                # Load encrypted credentials from QSettings
                encrypted_creds = get_credential(f'file_host_{host_id}_credentials')
                if encrypted_creds:
                    decrypted = decrypt_password(encrypted_creds)
                    if decrypted:
                        host_settings['credentials'] = decrypted

                settings_dict['hosts'][host_id] = host_settings

            # Apply settings to widget
            self.file_hosts_widget.load_settings(settings_dict)

        except Exception as e:
            import traceback
            log(f"Failed to load file hosts settings: {e}", level="error", category="settings")
            traceback.print_exc()

    def _save_file_hosts_settings(self):
        """Save file hosts settings to INI file and encrypt credentials to QSettings"""
        try:
            # Get settings from widget if available
            if not hasattr(self, 'file_hosts_widget') or not self.file_hosts_widget:
                return

            from bbdrop import set_credential, encrypt_password

            config = configparser.ConfigParser()
            config_file = get_config_path()

            if os.path.exists(config_file):
                config.read(config_file, encoding='utf-8')

            if 'FILE_HOSTS' not in config:
                config.add_section('FILE_HOSTS')

            # Get settings from widget
            widget_settings = self.file_hosts_widget.get_settings()

            # Save connection limits
            config.set('FILE_HOSTS', 'global_limit', str(widget_settings['global_limit']))
            config.set('FILE_HOSTS', 'per_host_limit', str(widget_settings['per_host_limit']))

            # Save per-host settings using new API
            from src.core.file_host_config import save_file_host_setting
            for host_id, host_settings in widget_settings['hosts'].items():
                # Save enabled state and trigger (single string value)
                save_file_host_setting(host_id, 'enabled', host_settings['enabled'])
                save_file_host_setting(host_id, 'trigger', host_settings['trigger'])

                # Save encrypted credentials to QSettings
                creds_text = host_settings.get('credentials', '')
                if creds_text:
                    encrypted = encrypt_password(creds_text)
                    set_credential(f'file_host_{host_id}_credentials', encrypted)
                else:
                    # Clear credentials if empty
                    set_credential(f'file_host_{host_id}_credentials', '')

            # Write INI file
            with open(config_file, 'w', encoding='utf-8') as f:
                config.write(f)

        except Exception as e:
            log(f"Failed to save file hosts settings: {e}", level="warning", category="settings")

    def save_settings(self):
        """Save all settings (legacy bulk-save — prefer per-tab save_current_tab)."""
        try:
            # Save general tab via its own widget
            if hasattr(self, 'general_tab'):
                self.general_tab.save_settings()

            if self.parent_window:
                # Save scanning settings
                self._save_scanning_settings()

                # Save external apps settings
                if hasattr(self, 'hooks_tab'):
                    self.hooks_tab.save_settings()

                # Save file hosts settings
                self._save_file_hosts_settings()

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
            # Show brief success message in status or log
            #print(f"Applied changes for {tab_name} tab")
    
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
                return self._save_image_hosts_tab()
            elif current_index == TabIndex.FILE_HOSTS:
                self._save_file_hosts_settings()
                return True
            elif current_index == TabIndex.TEMPLATES:
                return self.templates_tab.save_settings()
            elif current_index == TabIndex.LOGS:
                return self._save_logs_tab()
            elif current_index == TabIndex.IMAGE_SCAN:
                return self.scanning_tab.save_settings()
            elif current_index == TabIndex.COVERS:
                return self.covers_tab.save_settings()
            elif current_index == TabIndex.HOOKS:
                return self.hooks_tab.save_settings()
            elif current_index == TabIndex.PROXY:
                return self._save_proxy_settings()
            elif current_index == TabIndex.ADVANCED:
                return self._save_advanced_settings()
            elif current_index == TabIndex.ARCHIVE:
                return self._save_archive_settings()
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
        has_template_changes = (
            hasattr(self, 'templates_tab')
            and self.templates_tab.has_pending_changes()
        )

        if has_template_changes:
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Question)
            msg_box.setWindowTitle("Unsaved Changes")
            msg_box.setText("You have unsaved template changes. Do you want to save them before closing?")
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

        # Also check if Templates tab has pending changes
        if hasattr(self, 'templates_tab') and self.templates_tab.has_pending_changes():
            has_unsaved = True

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

    def _save_image_hosts_tab(self):
        """Save Image Hosts tab settings"""
        try:
            if hasattr(self, 'image_hosts_widget') and self.image_hosts_widget:
                results = self.image_hosts_widget.save()
                # Check if any batch size changed to trigger pool refresh
                for old_batch, new_batch in results:
                    if old_batch != new_batch and self.parent_window and hasattr(self.parent_window, 'uploader'):
                        try:
                            self.parent_window.uploader.refresh_session_pool()
                        except Exception as e:
                            log(f"Failed to refresh connection pool: {e}", level="warning", category="settings")
                        break  # Only need to refresh once
            if self.parent_window and hasattr(self.parent_window, 'refresh_image_host_combo'):
                self.parent_window.refresh_image_host_combo()
            return True
        except Exception as e:
            log(f"Error saving Image Hosts tab: {e}", level="warning", category="settings")
            return False

    def _save_upload_tab(self):
        """Save Upload/Credentials tab settings only"""
        try:
            # Credentials are saved through their individual button handlers
            # This tab doesn't have bulk settings to save
            return True
        except Exception as e:
            log(f"Error saving upload settings: {e}", level="warning", category="settings")
            return False

    def _save_tabs_tab(self):
        """Save Tabs tab settings only (delegated to TabsTab widget)."""
        if hasattr(self, 'tabs_tab'):
            return self.tabs_tab.save_settings()
        return True
    
    def _save_icons_tab(self):
        """Save Icons tab settings (delegated to IconsTab widget)."""
        if hasattr(self, 'icons_tab'):
            return self.icons_tab.save_settings()
        return True
    
    def _save_logs_tab(self):
        """Save Logs tab settings"""
        try:
            if hasattr(self, 'log_settings_widget'):
                self.log_settings_widget.save_settings()
                # Cache refresh and re-rendering handled by main_window._handle_settings_dialog_result()
            return True
        except Exception as e:
            log(f"Error saving logs tab: {e}", level="warning", category="settings")
            return False



class LogViewerDialog(QDialog):
    """Popout viewer for application logs."""
    def __init__(self, initial_text: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Log Viewer")
        self.setModal(False)
        self.resize(1000, 720)

        self.follow_enabled = True

        layout = QVBoxLayout(self)

        # Prepare logger and settings (used by both tabs)
        try:
            from src.utils.logging import get_logger as _get_logger
            self._logger: Any = _get_logger()
            settings = self._logger.get_settings()
        except Exception:
            self._logger = None
            settings = {
                'enabled': True,
                'rotation': 'daily',
                'backup_count': 7,
                'compress': True,
                'max_bytes': 10485760,
                'level_file': 'INFO',
                'level_gui': 'INFO',
            }

        # Build Settings tab content
        header = QGroupBox("Log Settings")
        grid = QGridLayout(header)

        self.chk_enabled = QCheckBox("Enable file logging")
        self.chk_enabled.setChecked(bool(settings.get('enabled', True)))
        grid.addWidget(self.chk_enabled, 0, 0, 1, 2)

        self.cmb_rotation = QComboBox()
        self.cmb_rotation.addItems(["daily", "size"])
        try:
            idx = ["daily", "size"].index(str(settings.get('rotation', 'daily')).lower())
        except Exception:
            idx = 0
        self.cmb_rotation.setCurrentIndex(idx)
        grid.addWidget(QLabel("Rotation:"), 1, 0)
        grid.addWidget(self.cmb_rotation, 1, 1)

        self.spn_backup = QSpinBox()
        self.spn_backup.setRange(0, 3650)
        self.spn_backup.setValue(int(settings.get('backup_count', 7)))
        grid.addWidget(QLabel("<span style='font-weight: 600'>Backups to keep</span>:"), 1, 2)
        grid.addWidget(self.spn_backup, 1, 3)

        self.chk_compress = QCheckBox("Compress rotated logs (.gz)")
        self.chk_compress.setChecked(bool(settings.get('compress', True)))
        grid.addWidget(self.chk_compress, 2, 0, 1, 2)

        self.spn_max_bytes = QSpinBox()
        self.spn_max_bytes.setRange(1024, 1024 * 1024 * 1024)
        self.spn_max_bytes.setSingleStep(1024 * 1024)
        self.spn_max_bytes.setValue(int(settings.get('max_bytes', 10485760)))
        grid.addWidget(QLabel("<span style='font-weight: 600'>Max size (bytes, size mode)</span>:"), 2, 2)
        grid.addWidget(self.spn_max_bytes, 2, 3)

        self.cmb_gui_level = QComboBox()
        levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        self.cmb_gui_level.addItems(levels)
        try:
            self.cmb_gui_level.setCurrentIndex(levels.index(str(settings.get('level_gui', 'INFO')).upper()))
        except Exception:
            pass
        grid.addWidget(QLabel("GUI level:"), 3, 0)
        grid.addWidget(self.cmb_gui_level, 3, 1)

        self.cmb_file_level = QComboBox()
        self.cmb_file_level.addItems(levels)
        try:
            self.cmb_file_level.setCurrentIndex(levels.index(str(settings.get('level_file', 'INFO')).upper()))
        except Exception:
            pass
        grid.addWidget(QLabel("File level:"), 3, 2)
        grid.addWidget(self.cmb_file_level, 3, 3)

        buttons_row = QHBoxLayout()
        self.btn_apply = QPushButton("Apply Settings")
        self.btn_open_dir = QPushButton("Open Logs Folder")
        buttons_row.addWidget(self.btn_apply)
        buttons_row.addWidget(self.btn_open_dir)
        grid.addLayout(buttons_row, 4, 0, 1, 4)

        # Add the settings to the layout
        layout.addWidget(header)
        
        # Add log content viewer
        log_group = QGroupBox("Log Content")
        log_layout = QVBoxLayout(log_group)
        
        # Log text area
        self.log_text = QPlainTextEdit()
        self.log_text.setPlainText(initial_text)
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        
        # Follow checkbox
        self.follow_check = QCheckBox("Follow log updates")
        self.follow_check.setChecked(True)
        log_layout.addWidget(self.follow_check)
        
        layout.addWidget(log_group)
        
        # Connect signals
        self.btn_apply.clicked.connect(self.apply_settings)
        self.btn_open_dir.clicked.connect(self.open_logs_folder)
        
    def apply_settings(self):
        """Apply log settings"""
        # Implementation would go here
        pass
        
    def open_logs_folder(self):
        """Open the logs folder"""
        # Implementation would go here
        pass
