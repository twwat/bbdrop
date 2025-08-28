#!/usr/bin/env python3
"""
Log Viewer Dialog for imxup application
Provides log viewing, filtering, and configuration capabilities
"""

import os
from typing import Dict

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QGridLayout, QCheckBox,
    QComboBox, QSpinBox, QLabel, QPushButton, QTabWidget, QWidget,
    QPlainTextEdit, QLineEdit, QDialogButtonBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextDocument


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
            self._logger = _get_logger()
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
        grid.addWidget(QLabel("Backups to keep:"), 1, 2)
        grid.addWidget(self.spn_backup, 1, 3)

        self.chk_compress = QCheckBox("Compress rotated logs (.gz)")
        self.chk_compress.setChecked(bool(settings.get('compress', True)))
        grid.addWidget(self.chk_compress, 2, 0, 1, 2)

        self.spn_max_bytes = QSpinBox()
        self.spn_max_bytes.setRange(1024, 1024 * 1024 * 1024)
        self.spn_max_bytes.setSingleStep(1024 * 1024)
        self.spn_max_bytes.setValue(int(settings.get('max_bytes', 10485760)))
        grid.addWidget(QLabel("Max size (bytes, size mode):"), 2, 2)
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

        # Category toggles section
        cats = [
            ("uploads", "Uploads"),
            ("auth", "Authentication"),
            ("network", "Network"),
            ("ui", "UI"),
            ("queue", "Queue"),
            ("general", "General"),
        ]
        row = 5
        for cat_key, cat_label in cats:
            try:
                gui_key = f"cats_gui_{cat_key}"
                file_key = f"cats_file_{cat_key}"
                chk_gui = QCheckBox(f"Show {cat_label} in GUI log")
                chk_file = QCheckBox(f"Write {cat_label} to file log")
                chk_gui.setObjectName(gui_key)
                chk_file.setObjectName(file_key)
                chk_gui.setChecked(bool(settings.get(gui_key, True)))
                chk_file.setChecked(bool(settings.get(file_key, True)))
                grid.addWidget(chk_gui, row, 0, 1, 2)
                grid.addWidget(chk_file, row, 2, 1, 2)
                row += 1
            except Exception:
                pass

        # Upload success modes
        grid.addWidget(QLabel("Upload success detail (GUI):"), row, 0)
        self.cmb_gui_upload_mode = QComboBox()
        self.cmb_gui_upload_mode.addItems(["none", "file", "gallery", "both"])
        try:
            self.cmb_gui_upload_mode.setCurrentText(str(settings.get("upload_success_mode_gui", "gallery")))
        except Exception:
            pass
        grid.addWidget(self.cmb_gui_upload_mode, row, 1)
        grid.addWidget(QLabel("Upload success detail (File):"), row, 2)
        self.cmb_file_upload_mode = QComboBox()
        self.cmb_file_upload_mode.addItems(["none", "file", "gallery", "both"])
        try:
            self.cmb_file_upload_mode.setCurrentText(str(settings.get("upload_success_mode_file", "gallery")))
        except Exception:
            pass
        grid.addWidget(self.cmb_file_upload_mode, row, 3)
        row += 1

        def on_apply():
            if not self._logger:
                return
            try:
                # Collect category toggles
                cat_kwargs = {}
                for cat_key, _label in cats:
                    gui_key = f"cats_gui_{cat_key}"
                    file_key = f"cats_file_{cat_key}"
                    w_gui = header.findChild(QCheckBox, gui_key)
                    w_file = header.findChild(QCheckBox, file_key)
                    if w_gui is not None:
                        cat_kwargs[gui_key] = w_gui.isChecked()
                    if w_file is not None:
                        cat_kwargs[file_key] = w_file.isChecked()
                self._logger.update_settings(
                    enabled=self.chk_enabled.isChecked(),
                    rotation=self.cmb_rotation.currentText().lower(),
                    backup_count=self.spn_backup.value(),
                    compress=self.chk_compress.isChecked(),
                    max_bytes=self.spn_max_bytes.value(),
                    level_gui=self.cmb_gui_level.currentText(),
                    level_file=self.cmb_file_level.currentText(),
                    upload_success_mode_gui=self.cmb_gui_upload_mode.currentText(),
                    upload_success_mode_file=self.cmb_file_upload_mode.currentText(),
                    **cat_kwargs,
                )
                # Reload log content to reflect format changes
                try:
                    self.log_view.setPlainText(self._logger.read_current_log(tail_bytes=2 * 1024 * 1024))
                except Exception:
                    pass
            except Exception:
                pass

        def on_open_dir():
            try:
                from PyQt6.QtGui import QDesktopServices
                from PyQt6.QtCore import QUrl
                logs_dir = self._logger.get_logs_dir() if self._logger else None
                if logs_dir and os.path.exists(logs_dir):
                    QDesktopServices.openUrl(QUrl.fromLocalFile(logs_dir))
            except Exception:
                pass

        self.btn_apply.clicked.connect(on_apply)
        self.btn_open_dir.clicked.connect(on_open_dir)

        # Build Logs tab
        logs_container = QWidget()
        logs_vbox = QVBoxLayout(logs_container)

        # Toolbar row
        toolbar = QHBoxLayout()
        self.cmb_file_select = QComboBox()
        self.cmb_tail = QComboBox()
        self.cmb_tail.addItems(["128 KB", "512 KB", "2 MB", "Full"])
        self.cmb_tail.setCurrentIndex(2)
        self.chk_follow = QCheckBox("Follow")
        self.chk_follow.setChecked(True)
        self.btn_refresh = QPushButton("Refresh")
        self.btn_clear = QPushButton("Clear View")
        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("Find...")
        self.btn_find = QPushButton("Find Next")
        toolbar.addWidget(QLabel("File:"))
        toolbar.addWidget(self.cmb_file_select, 2)
        toolbar.addWidget(QLabel("Tail:"))
        toolbar.addWidget(self.cmb_tail)
        toolbar.addStretch()
        toolbar.addWidget(self.chk_follow)
        toolbar.addWidget(self.btn_refresh)
        toolbar.addWidget(self.btn_clear)
        toolbar.addWidget(self.find_input, 1)
        toolbar.addWidget(self.btn_find)
        logs_vbox.addLayout(toolbar)

        # Filters row (separate line): 1 x 6
        self._filters_row: Dict[str, QCheckBox] = {}
        filters_bar = QHBoxLayout()
        filters_bar.addWidget(QLabel("View:"))
        for cat_key, cat_label in cats:
            cb = QCheckBox(cat_label)
            cb.setChecked(True)
            self._filters_row[cat_key] = cb
            filters_bar.addWidget(cb)
        filters_bar.addStretch()
        logs_vbox.addLayout(filters_bar)

        # Body: log view only (filters moved to toolbar)
        body_hbox = QHBoxLayout()
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        try:
            self.log_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        except Exception:
            pass
        self.log_view.setProperty("class", "console")
        body_hbox.addWidget(self.log_view, 1)
        logs_vbox.addLayout(body_hbox)

        # Tabs: Logs | Settings
        tabs = QTabWidget(self)
        # Settings tab
        settings_container = QWidget()
        sc_vbox = QVBoxLayout(settings_container)
        sc_vbox.addWidget(header)
        sc_vbox.addStretch()
        tabs.addTab(logs_container, "Logs")
        tabs.addTab(settings_container, "Log Settings")
        layout.addWidget(tabs)

        # Populate initial log content via loader (with tail selection default)
        def _tail_bytes_from_choice(text: str) -> int | None:
            t = (text or "").lower()
            if "full" in t:
                return None
            if "128" in t:
                return 128 * 1024
            if "512" in t:
                return 512 * 1024
            return 2 * 1024 * 1024

        def _normalize_dates(block: str) -> str:
            if not block:
                return ""
            try:
                from datetime import datetime as _dt
                today = _dt.now().strftime("%Y-%m-%d ")
                lines = block.splitlines()
                out = []
                for line in lines:
                    if len(line) >= 8 and line[2:3] == ":" and line[5:6] == ":":
                        out.append(today + line)
                    else:
                        out.append(line)
                return "\n".join(out)
            except Exception:
                return block

        def _load_logs_list():
            self.cmb_file_select.clear()
            self.cmb_file_select.addItem("Current (imxup.log)", userData="__current__")
            try:
                if self._logger:
                    logs_dir = self._logger.get_logs_dir()
                    files = []
                    for name in os.listdir(logs_dir):
                        if name.startswith("imxup.log"):
                            files.append(name)
                    files.sort(reverse=True)
                    for name in files:
                        self.cmb_file_select.addItem(name, userData=os.path.join(logs_dir, name))
            except Exception:
                pass

        def _read_selected_file() -> str:
            # Read according to file selection and tail size
            tail = _tail_bytes_from_choice(self.cmb_tail.currentText())
            try:
                if self.cmb_file_select.currentData() == "__current__" and self._logger:
                    return self._logger.read_current_log(tail_bytes=tail) or ""
                # Else fallback to reading the selected path
                path = self.cmb_file_select.currentData()
                if not path:
                    return ""
                if str(path).endswith(".gz"):
                    import gzip
                    with gzip.open(path, "rb") as f:
                        data = f.read()
                    if tail:
                        data = data[-int(tail):]
                    return data.decode("utf-8", errors="replace")
                else:
                    if tail and os.path.exists(path):
                        size = os.path.getsize(path)
                        with open(path, "rb") as f:
                            if size > tail:
                                f.seek(-tail, os.SEEK_END)
                            data = f.read()
                        return data.decode("utf-8", errors="replace")
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        return f.read()
            except Exception:
                return ""

        def _apply_initial_content():
            try:
                block = initial_text or _read_selected_file()
            except Exception:
                block = initial_text
            norm = _normalize_dates(block)
            self.log_view.setPlainText(norm)

        _load_logs_list()
        _apply_initial_content()

        # Wire toolbar actions
        def _strip_datetime_prefix(s: str) -> str:
            try:
                t = s.lstrip()
                # YYYY-MM-DD HH:MM:SS
                if len(t) >= 19 and t[4] == '-' and t[7] == '-' and t[10] == ' ' and t[13] == ':' and t[16] == ':':
                    return t[19:].lstrip()
                # HH:MM:SS
                if len(t) >= 8 and t[2] == ':' and t[5] == ':':
                    return t[8:].lstrip()
                return s
            except Exception:
                return s

        def _filter_block_by_view_cats(block: str) -> str:
            if not block:
                return ""
            try:
                lines = block.splitlines()
                out = []
                for line in lines:
                    # Extract token after optional date/time prefix
                    head = _strip_datetime_prefix(line)
                    cat = "general"
                    if head.startswith("[") and "]" in head:
                        token = head[1:head.find("]")]
                        cat = token.split(":")[0] or "general"
                    if cat in self._filters_row and not self._filters_row[cat].isChecked():
                        continue
                    out.append(line)
                return "\n".join(out)
            except Exception:
                return block

        def on_refresh():
            text = _normalize_dates(_read_selected_file())
            text = _filter_block_by_view_cats(text)
            self.log_view.setPlainText(text)

        self.btn_refresh.clicked.connect(on_refresh)
        self.cmb_file_select.currentIndexChanged.connect(on_refresh)
        self.cmb_tail.currentIndexChanged.connect(on_refresh)

        # Changing view filters should refilter the current view
        def on_filter_changed(_=None):
            # Re-apply filtering to current content by simulating a refresh
            on_refresh()
        # Bind filters row checkboxes
        for _key, cb in self._filters_row.items():
            try:
                cb.toggled.connect(on_filter_changed)
            except Exception:
                pass

        def on_clear():
            self.log_view.clear()
        self.btn_clear.clicked.connect(on_clear)

        def on_follow_toggle(_=None):
            self.follow_enabled = self.chk_follow.isChecked()
        self.chk_follow.toggled.connect(on_follow_toggle)

        # Find functionality
        def on_find_next():
            pattern = (self.find_input.text() or "").strip()
            if not pattern:
                return
            doc: QTextDocument = self.log_view.document()
            cursor = self.log_view.textCursor()
            # Move one char to avoid matching the same selection
            if cursor.hasSelection():
                cursor.setPosition(cursor.selectionEnd())
            found = doc.find(pattern, cursor)
            if not found.isNull():
                self.log_view.setTextCursor(found)
                self.log_view.ensureCursorVisible()
        self.btn_find.clicked.connect(on_find_next)
        self.find_input.returnPressed.connect(on_find_next)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

    def append_message(self, message: str):
        try:
            # Determine category like [uploads], [uploads:file], [auth], etc.
            category = "general"
            head = message
            try:
                parts = message.split(" ", 1)
                if len(parts) > 1 and parts[0].count(":") == 2:
                    head = parts[1]
                if head.startswith("[") and "]" in head:
                    token = head[1:head.find("]")]
                    category = token.split(":")[0] or "general"
            except Exception:
                pass
            # Apply viewer-only filters
            # Apply viewer-only filters (toolbar row)
            if category in getattr(self, '_filters_row', {}) and not self._filters_row[category].isChecked():
                return
            # Ensure date is visible in the log viewer if time-only
            from datetime import datetime as _dt
            if isinstance(message, str) and len(message) >= 9 and message[2:3] == ":":
                today = _dt.now().strftime("%Y-%m-%d ")
                line = today + message
            else:
                line = message
            # Append and optionally follow
            self.log_view.appendPlainText(line)
            if self.follow_enabled:
                cursor = self.log_view.textCursor()
                cursor.movePosition(cursor.MoveOperation.End)
                self.log_view.setTextCursor(cursor)
                self.log_view.ensureCursorVisible()
        except Exception:
            pass