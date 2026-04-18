"""Dock-based layout management for BBDrop main window.

LayoutManager owns construction of all QDockWidget panels, applies preset
layouts via QMainWindow.saveState()/restoreState(), and provides Reset Layout.

See docs/superpowers/specs/2026-04-17-customizable-layout-design.md for design.
"""

from typing import TYPE_CHECKING

from PyQt6.QtCore import QByteArray, QObject, Qt, QSize
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.utils.logger import log

if TYPE_CHECKING:
    from src.gui.main_window import BBDropGUI


class LayoutManager(QObject):
    """Constructs and manages dock widgets for the BBDrop main window.

    The main window's Upload Queue is the central widget (not a dock).
    Six non-queue panels (Quick Settings, Hosts, Log, Progress, Info, Speed)
    are each wrapped in a QDockWidget and placed per the Classic default layout.

    Attributes:
        _mw: Reference to the main BBDropGUI window.
    """

    def __init__(self, main_window: "BBDropGUI"):
        super().__init__()
        self._mw = main_window

    def build(self) -> None:
        """Construct all dock widgets and place them in the Classic default layout.

        Assigns widget references on self._mw (e.g., mw.log_text, mw.worker_status_widget)
        so existing controllers and signal handlers find them unchanged.
        """
        mw = self._mw

        mw.setCentralWidget(self._build_queue_container())

        self.dock_quick_settings = self._wrap_dock(
            "Quick Settings", self._build_quick_settings_content(), "dock_quick_settings"
        )
        self.dock_hosts = self._wrap_dock(
            "Hosts", self._build_hosts_content(), "dock_hosts"
        )
        self.dock_log = self._wrap_dock(
            "Log", self._build_log_content(), "dock_log"
        )
        self.dock_progress = self._wrap_dock(
            "Current Tab Progress",
            self._build_progress_content(),
            "dock_progress",
        )
        self.dock_info = self._wrap_dock(
            "Info", self._build_info_content(), "dock_info"
        )
        self.dock_speed = self._wrap_dock(
            "Speed", self._build_speed_content(), "dock_speed"
        )

        # Disallow tab merging so dragging Progress/Info/Speed onto each other
        # can't accidentally combine them into a tab group. They show
        # unrelated stats and must remain independently visible at all times.
        from PyQt6.QtWidgets import QMainWindow
        mw.setDockOptions(
            QMainWindow.DockOption.AnimatedDocks
            | QMainWindow.DockOption.AllowNestedDocks
        )

        # Make the bottom dock area own both lower corners so Progress/Info/Speed
        # span the full window width — matching today's layout where they sit
        # below both the queue and the right-side panels.
        mw.setCorner(Qt.Corner.BottomLeftCorner, Qt.DockWidgetArea.BottomDockWidgetArea)
        mw.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.BottomDockWidgetArea)

        # Classic default placement
        mw.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock_quick_settings)
        mw.splitDockWidget(self.dock_quick_settings, self.dock_hosts, Qt.Orientation.Vertical)
        mw.splitDockWidget(self.dock_hosts, self.dock_log, Qt.Orientation.Vertical)

        # Bottom row: Progress | Info | Speed. Qt's dock layout is a binary
        # tree — with three peers, one pair must nest. Nest Progress+Info
        # (the pair that resizes together most naturally) so the Info|Speed
        # handle lives at the outer level and can resize those two cleanly
        # without cascading into Progress.
        mw.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.dock_progress)
        mw.splitDockWidget(self.dock_progress, self.dock_speed, Qt.Orientation.Horizontal)
        mw.splitDockWidget(self.dock_progress, self.dock_info, Qt.Orientation.Horizontal)

        # Give the bottom row explicit starting widths so nothing is pinned
        # at minimum on first launch. Without this, Qt gives them equal thirds.
        mw.resizeDocks(
            [self.dock_progress, self.dock_info, self.dock_speed],
            [600, 230, 230],
            Qt.Orientation.Horizontal,
        )

        # Start locked — edit mode is opt-in per session via View → Edit Layout.
        self.set_edit_mode(False)

    def _wrap_dock(
        self, title: str, content: QWidget, object_name: str
    ) -> QDockWidget:
        dock = QDockWidget(title, self._mw)
        dock.setObjectName(object_name)
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        dock.setWidget(content)
        return dock

    def _build_queue_container(self) -> QWidget:
        """Build the Upload Queue container (becomes the centralWidget)."""
        from src.gui.widgets.tabbed_gallery import TabbedGalleryWidget

        mw = self._mw

        # Left panel - Queue and controls (wider now)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        try:
            left_layout.setContentsMargins(0, 0, 0, 0)
            left_layout.setSpacing(6)
        except Exception as e:
            log(f"Exception in main_window: {e}", level="error", category="ui")
            raise

        # Queue section
        queue_group = QGroupBox("Upload Queue")
        queue_layout = QVBoxLayout(queue_group)
        try:
            queue_layout.setContentsMargins(10, 10, 10, 10)
            queue_layout.setSpacing(8)
        except Exception as e:
            log(f"Exception in main_window: {e}", level="error", category="ui")
            raise

        # Drag-and-drop is handled at the window level; no dedicated drop label
        # (Moved Browse button into controls row below)

        # Tabbed gallery widget (replaces single table)
        mw.gallery_table = TabbedGalleryWidget()
        mw.gallery_table.setProperty("class", "gallery-table")
        queue_layout.addWidget(mw.gallery_table, 1)  # Give it stretch priority

        # MILESTONE 4: Connect scroll handler for viewport-based lazy loading
        mw.gallery_table.table.verticalScrollBar().valueChanged.connect(mw._on_table_scrolled)

        # Header context menu for column visibility + persist widths/visibility
        # Access the internal table for header operations
        try:
            header = mw.gallery_table.table.horizontalHeader()
            header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            header.customContextMenuRequested.connect(mw.show_header_context_menu)
            header.sectionResized.connect(mw._on_header_section_resized)
            header.sectionMoved.connect(mw._on_header_section_moved)

        except Exception as e:
            log(f"Exception in main_window: {e}", level="error", category="ui")
            raise

        # Add keyboard shortcut hint
        shortcut_hint = QLabel(
            "💡 Tips: <b>Ctrl-C</b>: Copy BBCode | <b>F2</b>: Rename"
            " | <b>Ctrl</b>+<b>Tab</b>: Next Tab"
            " | <b>Drag-and-drop</b>: Add folders"
        )
        shortcut_hint.setProperty("class", "status-muted")
        shortcut_hint.setStyleSheet("font-size: 11px; color: #999999; font-style: italic;")
        #shortcut_hint.style().polish(shortcut_hint)
        shortcut_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        queue_layout.addWidget(shortcut_hint)

        # Queue controls
        controls_layout = QHBoxLayout()

        mw.start_all_btn = QPushButton("Start All")
        if not mw.start_all_btn.text().startswith(" "):
            mw.start_all_btn.setText(" " + mw.start_all_btn.text())
        mw.start_all_btn.clicked.connect(mw.start_all_uploads)
        mw.start_all_btn.setProperty("class", "main-action-btn")
        controls_layout.addWidget(mw.start_all_btn)

        mw.pause_all_btn = QPushButton("Pause All")
        if not mw.pause_all_btn.text().startswith(" "):
            mw.pause_all_btn.setText(" " + mw.pause_all_btn.text())
        mw.pause_all_btn.clicked.connect(mw.pause_all_uploads)
        mw.pause_all_btn.setProperty("class", "main-action-btn")
        controls_layout.addWidget(mw.pause_all_btn)

        mw.clear_completed_btn = QPushButton("Clear Completed")
        if not mw.clear_completed_btn.text().startswith(" "):
            mw.clear_completed_btn.setText(" " + mw.clear_completed_btn.text())
        mw.clear_completed_btn.clicked.connect(mw.clear_completed)
        mw.clear_completed_btn.setProperty("class", "main-action-btn")
        controls_layout.addWidget(mw.clear_completed_btn)

        # Browse button (moved here to be to the right of Clear Completed)
        mw.browse_btn = QPushButton(" Browse ")
        mw.browse_btn.clicked.connect(mw.browse_for_folders)
        mw.browse_btn.setProperty("class", "main-action-btn")
        controls_layout.addWidget(mw.browse_btn)

        queue_layout.addLayout(controls_layout)
        left_layout.addWidget(queue_group)

        # Set minimum width for left panel (Upload Queue)
        # Reduced to allow splitter to move further left (up to ~3/4 of window width)
        left_panel.setMinimumWidth(250)

        return left_panel

    def _build_quick_settings_content(self) -> QWidget:
        """Build the Quick Settings panel content."""
        from src.gui.widgets.adaptive_settings_panel import AdaptiveQuickSettingsPanel
        from src.gui.icon_manager import get_icon_manager
        from src.utils.paths import load_user_defaults

        mw = self._mw

        # Settings section — plain QGroupBox so the splitter isn't locked
        # by an inflated minimumSizeHint. The adaptive panel inside handles
        # compression gracefully (icon-only mode, row collapsing).
        mw.settings_group = QGroupBox("Quick Settings")
        mw.settings_group.setProperty("class", "settings-group")

        settings_layout = QVBoxLayout(mw.settings_group)
        settings_layout.setContentsMargins(5, 8, 5, 5)
        settings_layout.setSpacing(3)

        # Load defaults
        defaults = load_user_defaults()

        # Static 4-row grid: label | control
        qs_grid = QGridLayout()
        qs_grid.setContentsMargins(0, 0, 0, 0)
        qs_grid.setHorizontalSpacing(4)
        qs_grid.setVerticalSpacing(2)
        qs_grid.setColumnStretch(1, 1)

        # Row 0: Image Host
        qs_grid.addWidget(QLabel("<span style=\"font-weight: 600\">Image Host</span>:"), 0, 0)
        mw.image_host_combo = QComboBox()
        mw.image_host_combo.setToolTip("Default image host for new galleries")
        mw._populate_image_host_combo()
        saved_host = defaults.get('default_image_host', 'imx')
        for i in range(mw.image_host_combo.count()):
            if mw.image_host_combo.itemData(i) == saved_host:
                mw.image_host_combo.setCurrentIndex(i)
                break
        mw.image_host_combo.currentIndexChanged.connect(mw.on_setting_changed)
        mw.image_host_combo.currentIndexChanged.connect(mw._on_image_host_changed)
        qs_grid.addWidget(mw.image_host_combo, 0, 1)

        # Row 1: Thumb Size — combo for fixed-size hosts (IMX), spinbox for variable (Turbo)
        qs_grid.addWidget(QLabel("<span style=\"font-weight: 600\">Thumb Size</span>:"), 1, 0)
        mw.thumbnail_size_combo = QComboBox()
        mw.thumbnail_size_combo.addItems(["100x100", "180x180", "250x250", "300x300", "150x150"])
        mw.thumbnail_size_combo.setCurrentIndex(defaults.get('thumbnail_size', 3) - 1)
        mw.thumbnail_size_combo.currentIndexChanged.connect(mw.on_setting_changed)
        from PyQt6.QtWidgets import QSpinBox, QHBoxLayout as _HBox
        mw._thumb_size_spinbox = QSpinBox()
        mw._thumb_size_spinbox.setSuffix("px")
        mw._thumb_size_spinbox.setRange(150, 600)
        mw._thumb_size_spinbox.setValue(300)
        mw._thumb_size_spinbox.setVisible(False)
        mw._thumb_size_spinbox.valueChanged.connect(mw._on_thumb_spinbox_changed)
        _thumb_container = QWidget()
        _thumb_lay = _HBox(_thumb_container)
        _thumb_lay.setContentsMargins(0, 0, 0, 0)
        _thumb_lay.setSpacing(0)
        _thumb_lay.addWidget(mw.thumbnail_size_combo)
        _thumb_lay.addWidget(mw._thumb_size_spinbox)
        qs_grid.addWidget(_thumb_container, 1, 1)

        # Row 2: Thumb Format
        qs_grid.addWidget(QLabel("<span style=\"font-weight: 600\">Thumb Format</span>:"), 2, 0)
        mw.thumbnail_format_combo = QComboBox()
        mw.thumbnail_format_combo.addItems(["Fixed width", "Proportional", "Square", "Fixed height"])
        mw.thumbnail_format_combo.setCurrentIndex(defaults.get('thumbnail_format', 2) - 1)
        mw.thumbnail_format_combo.currentIndexChanged.connect(mw.on_setting_changed)
        qs_grid.addWidget(mw.thumbnail_format_combo, 2, 1)

        # Row 3: Template
        qs_grid.addWidget(QLabel("<span style=\"font-weight: 600\">Template</span>:"), 3, 0)
        mw.template_combo = QComboBox()
        mw.template_combo.setToolTip("Template to use for generating bbcode files")
        from src.utils.templates import load_templates
        templates = load_templates()
        for template_name in templates.keys():
            mw.template_combo.addItem(template_name)
        saved_template = defaults.get('template_name', 'default')
        template_index = mw.template_combo.findText(saved_template)
        if template_index >= 0:
            mw.template_combo.setCurrentIndex(template_index)
        mw.template_combo.currentIndexChanged.connect(mw.on_setting_changed)
        qs_grid.addWidget(mw.template_combo, 3, 1)

        # Watch template directory for changes and refresh dropdown automatically
        try:
            from PyQt6.QtCore import QFileSystemWatcher
            from src.utils.templates import get_template_path
            mw._template_watcher = QFileSystemWatcher([get_template_path()])
            mw._template_watcher.directoryChanged.connect(mw._on_templates_directory_changed)
        except Exception as e:
            log(f"Template watcher init failed: {e}", level="warning", category="startup")
            mw._template_watcher = None

        # Apply initial thumb control state based on default host
        mw._on_image_host_changed()

        settings_layout.addLayout(qs_grid)

        # Checkbox — hard minimum height so layout can never compress it
        mw.auto_start_upload_check = QCheckBox("Start uploads automatically")
        mw.auto_start_upload_check.setChecked(defaults.get('auto_start_upload', False))
        mw.auto_start_upload_check.setToolTip("Automatically start uploads when scanning completes instead of waiting for manual start")
        mw.auto_start_upload_check.setMinimumHeight(mw.auto_start_upload_check.sizeHint().height())
        mw.auto_start_upload_check.toggled.connect(mw.on_setting_changed)
        settings_layout.addWidget(mw.auto_start_upload_check)

        # Artifact storage location options (moved to dialog; keep hidden for persistence wiring)
        mw.store_in_uploaded_check = QCheckBox("Save artifacts in .uploaded folder")
        mw.store_in_uploaded_check.setChecked(defaults.get('store_in_uploaded', True))
        mw.store_in_uploaded_check.setVisible(False)
        mw.store_in_uploaded_check.toggled.connect(mw.on_setting_changed)

        mw.store_in_central_check = QCheckBox("Save artifacts in central store")
        mw.store_in_central_check.setChecked(defaults.get('store_in_central', True))
        mw.store_in_central_check.setVisible(False)
        mw.store_in_central_check.toggled.connect(mw.on_setting_changed)

        # Track central store path (from defaults)
        mw.central_store_path_value = defaults.get('central_store_path', None)

        # Comprehensive Settings button (will be added to horizontal layout below)
        mw.comprehensive_settings_btn = QPushButton(" Settings") # ⚙️
        if not mw.comprehensive_settings_btn.text().startswith(" "):
            mw.comprehensive_settings_btn.setText(" " + mw.comprehensive_settings_btn.text())
        mw.comprehensive_settings_btn.clicked.connect(mw.open_comprehensive_settings)
        mw.comprehensive_settings_btn.setMinimumHeight(30)
        mw.comprehensive_settings_btn.setMaximumHeight(34)
        mw.comprehensive_settings_btn.setProperty("class", "comprehensive-settings")
        # Note: Now added to horizontal layout with icon buttons (see below)

        # Manage templates and credentials buttons
        mw.manage_templates_btn = QPushButton("") # previously  QPushButton(" Templates")
        mw.manage_templates_btn.setToolTip("Manage BBCode templates for gallery output")
        mw.manage_credentials_btn = QPushButton("")
        mw.manage_credentials_btn.setToolTip("Configure image host settings and credentials")

        # Add icons if available

        try:
            icon_mgr = get_icon_manager()
            if icon_mgr:
                templates_icon = icon_mgr.get_icon('templates')
                if not templates_icon.isNull():
                    mw.manage_templates_btn.setIcon(templates_icon)
                    mw.manage_templates_btn.setIconSize(QSize(22, 22))

                imagehosts_icon = icon_mgr.get_icon('imagehosts')
                if not imagehosts_icon.isNull():
                    mw.manage_credentials_btn.setIcon(imagehosts_icon)
                    mw.manage_credentials_btn.setIconSize(QSize(22, 22))

                settings_icon = icon_mgr.get_icon('settings')
                if not settings_icon.isNull():
                    mw.comprehensive_settings_btn.setIcon(settings_icon)
                    mw.comprehensive_settings_btn.setIconSize(QSize(22, 22))

        except Exception as e:
            log(f"Exception in main_window: {e}", level="error", category="ui")
            raise
        mw.manage_templates_btn.clicked.connect(mw.manage_templates)
        mw.manage_credentials_btn.clicked.connect(mw.manage_credentials)

        for btn in [mw.manage_templates_btn, mw.manage_credentials_btn]:
            btn.setProperty("class", "quick-settings-btn")

        # Log viewer button (icon-only, small)
        mw.log_viewer_btn = QPushButton()
        mw.log_viewer_btn.setProperty("class", "log-viewer-btn")
        mw.log_viewer_btn.setToolTip("Open Log Viewer")
        try:
            icon_mgr = get_icon_manager()
            if icon_mgr:
                log_viewer_icon = icon_mgr.get_icon('log_viewer')
                if not log_viewer_icon.isNull():
                    mw.log_viewer_btn.setIcon(log_viewer_icon)
                    mw.log_viewer_btn.setIconSize(QSize(32, 20))
        except Exception as e:
            log(f"Exception in main_window: {e}", level="error", category="ui")
            raise
        mw.log_viewer_btn.clicked.connect(mw.open_log_viewer_popup)

        # Hooks button (opens comprehensive settings to Hooks tab)
        mw.hooks_btn = QPushButton()
        mw.hooks_btn.setProperty("class", "hooks-btn")
        mw.hooks_btn.setToolTip("Configure external application hooks")
        try:
            icon_mgr = get_icon_manager()
            if icon_mgr:
                hooks_icon = icon_mgr.get_icon('hooks')
                if not hooks_icon.isNull():
                    mw.hooks_btn.setIcon(hooks_icon)
                    mw.hooks_btn.setIconSize(QSize(22, 22))
        except Exception as e:
            log(f"Exception in main_window: {e}", level="error", category="ui")
            raise
        from src.gui.settings import TabIndex as _TabIndex
        mw.hooks_btn.clicked.connect(lambda: mw.open_comprehensive_settings(tab_index=_TabIndex.HOOKS))

        # File Hosts button (opens comprehensive settings to File Hosts tab)
        mw.file_hosts_btn = QPushButton("")
        mw.file_hosts_btn.setToolTip("Configure file host credentials and settings")
        try:
            icon_mgr = get_icon_manager()
            if icon_mgr:
                filehosts_icon = icon_mgr.get_icon('filehosts')
                if not filehosts_icon.isNull():
                    mw.file_hosts_btn.setIcon(filehosts_icon)
                    mw.file_hosts_btn.setIconSize(QSize(22, 22))
        except Exception as e:
            log(f"Exception in main_window: {e}", level="error", category="ui")
            raise
        mw.file_hosts_btn.clicked.connect(mw.manage_file_hosts)
        mw.file_hosts_btn.setProperty("class", "quick-settings-btn")

        # Theme toggle button (icon-only, small)
        mw.theme_toggle_btn = QPushButton()
        mw.theme_toggle_btn.setProperty("class", "theme-toggle-btn")
        # Set initial tooltip based on current theme
        current_theme = str(mw.settings.value('ui/theme', 'dark'))
        initial_tooltip = "Switch to Light Mode" if current_theme == 'dark' else "Switch to Dark Mode"
        mw.theme_toggle_btn.setToolTip(initial_tooltip)
        try:
            icon_mgr = get_icon_manager()
            if icon_mgr:
                theme_icon = icon_mgr.get_icon('toggle_theme')
                if not theme_icon.isNull():
                    mw.theme_toggle_btn.setIcon(theme_icon)
                    mw.theme_toggle_btn.setIconSize(QSize(22, 22))
        except Exception as e:
            log(f"Exception in main_window: {e}", level="error", category="ui")
            raise
        mw.theme_toggle_btn.clicked.connect(mw.toggle_theme)

        # Help button (opens help documentation dialog)
        mw.help_btn = QPushButton("")
        mw.help_btn.setToolTip("Open help documentation")
        try:
            icon_mgr = get_icon_manager()
            if icon_mgr:
                help_icon = icon_mgr.get_icon('help')
                if not help_icon.isNull():
                    mw.help_btn.setIcon(help_icon)
                    mw.help_btn.setIconSize(QSize(20, 20))
        except Exception as e:
            log(f"Exception in main_window: {e}", level="error", category="ui")
            raise
        mw.help_btn.clicked.connect(mw.open_help_dialog)
        mw.help_btn.setProperty("class", "quick-settings-btn")

        # Statistics button (opens statistics dialog)
        mw.statistics_btn = QPushButton("")
        mw.statistics_btn.setToolTip("View application statistics")
        try:
            icon_mgr = get_icon_manager()
            if icon_mgr:
                stats_icon = icon_mgr.get_icon('statistics')
                if not stats_icon.isNull():
                    mw.statistics_btn.setIcon(stats_icon)
                    mw.statistics_btn.setIconSize(QSize(20, 20))
        except Exception as e:
            log(f"Exception in main_window: {e}", level="error", category="ui")
            raise
        mw.statistics_btn.clicked.connect(mw.open_statistics_dialog)
        mw.statistics_btn.setProperty("class", "quick-settings-btn")

        # File Manager button (opens remote file manager dialog)
        mw.file_manager_btn = QPushButton("")
        mw.file_manager_btn.setToolTip("Browse and manage files on remote file hosts")
        try:
            icon_mgr = get_icon_manager()
            if icon_mgr:
                fm_icon = icon_mgr.get_icon('file_manager')
                if not fm_icon.isNull():
                    mw.file_manager_btn.setIcon(fm_icon)
                    mw.file_manager_btn.setIconSize(QSize(20, 20))
        except Exception as e:
            log(f"Exception loading file manager icon: {e}", level="error", category="ui")
            raise
        mw.file_manager_btn.clicked.connect(mw.open_file_manager_dialog)
        mw.file_manager_btn.setProperty("class", "quick-settings-btn")

        # Link Scanner button (opens link scanner dashboard)
        mw.link_scanner_btn = QPushButton("")
        mw.link_scanner_btn.setToolTip("Scan gallery links to check online status")
        try:
            icon_mgr = get_icon_manager()
            if icon_mgr:
                scan_icon = icon_mgr.get_icon('scan')
                if not scan_icon.isNull():
                    mw.link_scanner_btn.setIcon(scan_icon)
                    mw.link_scanner_btn.setIconSize(QSize(20, 20))
        except Exception as e:
            log(f"Exception loading scan icon: {e}", level="error", category="ui")
            raise
        mw.link_scanner_btn.clicked.connect(mw.open_link_scanner_dashboard)
        mw.link_scanner_btn.setProperty("class", "quick-settings-btn")

        # Create adaptive panel for quick settings buttons
        # Automatically adjusts layout based on available width AND height:
        # - Compact: 1 row, icon-only (when both dimensions constrained)
        # - Expanded: 2 rows with labels (when vertical or horizontal room available)
        mw.adaptive_settings_panel = AdaptiveQuickSettingsPanel()
        mw.adaptive_settings_panel.set_buttons(
            mw.comprehensive_settings_btn,
            mw.manage_credentials_btn,    # Credentials
            mw.manage_templates_btn,      # Templates
            mw.file_hosts_btn,            # File Hosts
            mw.hooks_btn,                 # Hooks
            mw.log_viewer_btn,            # Logs
            mw.help_btn,                  # Help
            mw.theme_toggle_btn,          # Theme
            mw.statistics_btn,            # Statistics
            mw.link_scanner_btn,          # Link Scanner
            mw.file_manager_btn           # File Manager
        )

        # Apply icons-only mode if setting is enabled
        icons_only = mw.settings.value('ui/quick_settings_icons_only', False, type=bool)
        mw.adaptive_settings_panel.set_icons_only_mode(icons_only)

        settings_layout.addWidget(mw.adaptive_settings_panel, 1)  # stretch=1, absorbs all shrink/grow

        # Stretch handled by addWidget(..., 1) above — adaptive panel absorbs all grow/shrink

        return mw.settings_group

    def _build_hosts_content(self) -> QWidget:
        """Build the Hosts (worker status) panel content.

        Note: mw.worker_status_widget is created EARLIER in BBDropGUI.__init__
        (before FileHostWorkerManager). Here we just place it in a group box
        and wire its signals.
        """
        mw = self._mw

        # Worker Status section (add between settings and log)
        # Note: worker_status_widget was created early in __init__ before FileHostWorkerManager
        worker_status_group = QGroupBox("Hosts")
        worker_status_layout = QVBoxLayout(worker_status_group)
        worker_status_layout.setContentsMargins(5, 5, 5, 5)

        # Minimal margins — QGroupBox provides the framing
        mw.worker_status_widget.layout().setContentsMargins(0, 2, 0, 0)
        mw.worker_status_widget.layout().setSpacing(0)
        # Remove table border so it blends with the group box
        mw.worker_status_widget.status_table.setFrameShape(QFrame.Shape.NoFrame)

        # Add the already-created worker status widget to the layout
        worker_status_layout.addWidget(mw.worker_status_widget)

        # Connect worker status widget signals
        mw.worker_status_widget.open_settings_tab_requested.connect(mw.open_comprehensive_settings)
        mw.worker_status_widget.open_host_config_requested.connect(mw._open_host_config_from_worker)
        mw.worker_status_widget.image_host_enabled_changed.connect(mw._on_image_host_enabled_changed)
        mw.worker_status_widget.file_host_enabled_changed.connect(mw._on_file_host_enabled_changed)
        mw.worker_status_widget.primary_host_change_requested.connect(mw._set_primary_image_host)
        mw.worker_status_widget.cover_host_change_requested.connect(mw._set_cover_image_host)
        mw.worker_status_widget.browse_files_requested.connect(mw.open_file_manager_dialog)

        # Worker monitoring started in showEvent() to avoid blocking startup
        # with database queries from _populate_initial_metrics()

        # Set minimum height for worker status group
        worker_status_group.setMinimumHeight(150)
        worker_status_group.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Minimum
        )

        return worker_status_group

    def _build_log_content(self) -> QWidget:
        """Build the Log panel content."""
        mw = self._mw

        # Log section (add first)
        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout(log_group)
        try:
            log_layout.setContentsMargins(5, 10, 5, 5)  # Reduced left/right/bottom by 3px
            log_layout.setSpacing(8)
        except Exception as e:
            log(f"Exception in main_window: {e}", level="error", category="ui")
            raise

        # Use QListWidget instead of QTextEdit for simpler, more reliable log display
        from src.gui.widgets.custom_widgets import CopyableLogListWidget
        mw.log_text = CopyableLogListWidget()
        mw.log_text.setAlternatingRowColors(False)
        mw.log_text.setSelectionMode(CopyableLogListWidget.SelectionMode.ExtendedSelection)

        # Set monospace font
        _log_font = QFont("Consolas", 9)
        _log_font.setStyleHint(QFont.StyleHint.Monospace)
        mw.log_text.setFont(_log_font)

        # Scrolling behavior
        mw.log_text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        mw.log_text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Double-click to open popout viewer
        try:
            mw.log_text.doubleClicked.connect(mw.open_log_viewer_popup)
        except Exception as e:
            log(f"Exception in main_window: {e}", level="error", category="ui")
            raise

        # QListWidget manages items differently than QTextEdit - no document() method needed
        # The item count is naturally limited by memory, not a block count setting
        log_layout.addWidget(mw.log_text)

        return log_group

    def _build_progress_content(self) -> QWidget:
        """Build the Current Tab Progress panel content."""
        from src.gui.widgets.custom_widgets import OverallProgressWidget

        mw = self._mw

        # Current tab progress group (left)
        progress_group = QGroupBox("Current Tab Progress")
        progress_layout = QVBoxLayout(progress_group)
        try:
            progress_layout.setContentsMargins(10, 10, 10, 10)
            progress_layout.setSpacing(8)
        except Exception as e:
            log(f"Exception in main_window: {e}", level="error", category="ui")
            raise

        overall_layout = QHBoxLayout()
        overall_layout.addWidget(QLabel("Progress:"))
        mw.overall_progress = OverallProgressWidget()
        mw.overall_progress.setProgressProperty("status", "ready")
        overall_layout.addWidget(mw.overall_progress)
        progress_layout.addLayout(overall_layout)

        # Statistics
        mw.stats_label = QLabel("Ready to upload galleries")
        mw.stats_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mw.stats_label.setStyleSheet("font-style: italic;")  # Let styles.qss handle the color
        progress_layout.addWidget(mw.stats_label)

        # Keep bottom short like the original progress box
        progress_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        progress_group.setProperty("class", "progress-group")

        return progress_group

    def _build_info_content(self) -> QWidget:
        """Build the Info (stats) panel content."""
        mw = self._mw

        # Help group (right) -> repurpose as Stats details
        stats_group = QGroupBox("Info")
        stats_layout = QGridLayout(stats_group)
        try:
            stats_layout.setContentsMargins(10, 8, 10, 8)
            stats_layout.setHorizontalSpacing(10)
            stats_layout.setVerticalSpacing(6)
        except Exception as e:
            log(f"Exception in main_window: {e}", level="error", category="ui")
            raise

        # Detailed stats labels (split into label and value for right-aligned values)
        mw.stats_unnamed_text_label = QLabel("Unnamed galleries:")
        mw.stats_unnamed_value_label = QLabel("0")

        # Make unnamed galleries labels clickable
        mw.stats_unnamed_text_label.setCursor(Qt.CursorShape.PointingHandCursor)
        mw.stats_unnamed_value_label.setCursor(Qt.CursorShape.PointingHandCursor)
        mw.stats_unnamed_text_label.setToolTip("Click to view unrenamed galleries")
        mw.stats_unnamed_value_label.setToolTip("Click to view unrenamed galleries")
        mw.stats_unnamed_text_label.mousePressEvent = lambda e: mw.open_unrenamed_galleries_dialog()
        mw.stats_unnamed_value_label.mousePressEvent = lambda e: mw.open_unrenamed_galleries_dialog()

        mw.stats_total_galleries_text_label = QLabel("Galleries uploaded:")
        mw.stats_total_galleries_value_label = QLabel("0")
        mw.stats_total_images_text_label = QLabel("Images uploaded:")
        mw.stats_total_images_value_label = QLabel("0")
        for lbl in (
            mw.stats_unnamed_value_label,
            mw.stats_total_galleries_value_label,
            mw.stats_total_images_value_label,
        ):
            try:
                lbl.setProperty("class", "console")
            except Exception as e:
                log(f"Exception in main_window: {e}", level="error", category="ui")
                raise
            try:
                lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            except Exception as e:
                log(f"Exception in main_window: {e}", level="error", category="ui")
                raise
        # Arrange in two columns, three rows
        stats_layout.addWidget(mw.stats_unnamed_text_label, 0, 0)
        stats_layout.addWidget(mw.stats_unnamed_value_label, 0, 1)
        stats_layout.addWidget(mw.stats_total_galleries_text_label, 1, 0)
        stats_layout.addWidget(mw.stats_total_galleries_value_label, 1, 1)
        stats_layout.addWidget(mw.stats_total_images_text_label, 2, 0)
        stats_layout.addWidget(mw.stats_total_images_value_label, 2, 1)
        #stats_layout.addWidget(mw.stats_current_speed_label, 1, 1)
        #stats_layout.addWidget(mw.stats_fastest_speed_label, 2, 1)

        # Dock-friendly sizing: allow user to resize the dock freely
        stats_group.setMinimumWidth(230)
        stats_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        stats_group.setProperty("class", "stats-group")

        return stats_group

    def _build_speed_content(self) -> QWidget:
        """Build the Speed panel content."""
        mw = self._mw

        speed_group = QGroupBox("Speed")
        speed_layout = QGridLayout(speed_group)
        try:
            speed_layout.setContentsMargins(10, 10, 10, 10)
            speed_layout.setHorizontalSpacing(12)
            speed_layout.setVerticalSpacing(8)
        except Exception as e:
            log(f"Exception in main_window: {e}", level="error", category="ui")
            raise

        # Detailed speed labels (split into label and value for right-aligned values)
        mw.speed_current_text_label = QLabel("Current:")
        mw.speed_current_value_label = QLabel("0.0 KiB/s")
        mw.speed_fastest_text_label = QLabel("Fastest:")
        mw.speed_fastest_value_label = QLabel("0.0 KiB/s")
        mw.speed_transferred_text_label = QLabel("Transferred:")
        mw.speed_transferred_value_label = QLabel("0 B")
        for lbl in (
            mw.speed_current_value_label,
            mw.speed_fastest_value_label,
            mw.speed_transferred_value_label,
        ):
            try:
                lbl.setProperty("class", "console")
            except Exception as e:
                log(f"Exception in main_window: {e}", level="error", category="ui")
                raise
            try:
                lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            except Exception as e:
                log(f"Exception in main_window: {e}", level="error", category="ui")
                raise

        # Make current transfer speed value 1px larger than others
        try:
            mw.speed_current_value_label.setProperty("class", "console-large")
        except Exception as e:
            log(f"Exception in main_window: {e}", level="error", category="ui")
            raise

        speed_layout.addWidget(mw.speed_current_text_label, 0, 0)
        speed_layout.addWidget(mw.speed_current_value_label, 0, 1)
        speed_layout.addWidget(mw.speed_fastest_text_label, 1, 0)
        speed_layout.addWidget(mw.speed_fastest_value_label, 1, 1)
        speed_layout.addWidget(mw.speed_transferred_text_label, 2, 0)
        speed_layout.addWidget(mw.speed_transferred_value_label, 2, 1)

        # Dock-friendly sizing: allow user to resize the dock freely
        speed_group.setMinimumWidth(230)
        speed_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        speed_group.setProperty("class", "speed-group")

        return speed_group

    def apply_preset(self, name: str) -> None:
        """Apply a named preset from layout_presets.PRESETS.

        Args:
            name: One of "classic", "focused_queue", "two_column".

        Raises:
            KeyError: If name is not a known preset.
        """
        from src.gui.layout_presets import PRESETS

        payload_b64 = PRESETS[name]  # raises KeyError on unknown name
        if not payload_b64:
            log(
                f"Preset '{name}' has no captured payload; skipping apply",
                level="warning",
                category="ui",
            )
            return

        state = QByteArray.fromBase64(payload_b64)
        if not self._mw.restoreState(state):
            log(
                f"Preset '{name}' could not be applied (restoreState returned False); "
                "current layout unchanged",
                level="warning",
                category="ui",
            )

    def reset_layout(self) -> None:
        """Restore the Classic default layout."""
        self.apply_preset("classic")

    def set_edit_mode(self, enabled: bool) -> None:
        """Toggle layout edit mode for all six docks.

        Locked (default): dock title bars are hidden and drag/float/close
        features disabled. The inner QGroupBox title is the only label;
        accidental drags or closes can't happen. Splitter handles between
        docks remain functional (Qt provides no API to hide them).

        Edit: Qt's default title bar is restored with close/float buttons,
        and all three dock features (Movable | Floatable | Closable) are
        re-enabled so the user can rearrange.

        Args:
            enabled: True to enter edit mode, False to lock.
        """
        self._edit_mode = enabled

        if enabled:
            features = (
                QDockWidget.DockWidgetFeature.DockWidgetMovable
                | QDockWidget.DockWidgetFeature.DockWidgetFloatable
                | QDockWidget.DockWidgetFeature.DockWidgetClosable
            )
        else:
            features = QDockWidget.DockWidgetFeature.NoDockWidgetFeatures

        for dock in (
            self.dock_quick_settings,
            self.dock_hosts,
            self.dock_log,
            self.dock_progress,
            self.dock_info,
            self.dock_speed,
        ):
            dock.setFeatures(features)
            if enabled:
                dock.setTitleBarWidget(None)
            else:
                dock.setTitleBarWidget(QWidget())

    def _dev_print_layout_state(self) -> None:
        """TEMPORARY — remove once Task 6 captures all preset payloads.

        Captures the current QMainWindow saveState() as base64, then:
        - copies it to the system clipboard so it can be pasted anywhere
        - logs it to the app log so it is visible in the Log panel
        - prints it to stdout as a fallback when a terminal is attached
        """
        from PyQt6.QtWidgets import QApplication

        state = self._mw.saveState()
        b64 = bytes(QByteArray(state).toBase64()).decode()

        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(b64)

        log(f"LAYOUT STATE (copied to clipboard): {b64}", level="info", category="ui")
        print(f"LAYOUT STATE: {b64}")
