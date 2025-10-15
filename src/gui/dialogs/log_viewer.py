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
    QTableWidget, QTableWidgetItem, QLineEdit, QDialogButtonBox, QHeaderView, QAbstractItemView
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from src.gui.widgets.custom_widgets import CopyableLogTableWidget


class LogViewerDialog(QDialog):
    """Popout viewer for application logs."""
    def __init__(self, initial_text: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Log Viewer")
        self.setModal(False)
        self.resize(1000, 720)

        self.follow_enabled = True

        layout = QVBoxLayout(self)

        # Prepare logger for reading logs
        try:
            from src.utils.logging import get_logger as _get_logger
            self._logger = _get_logger()
        except Exception:
            self._logger = None

        # Build Logs UI
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

        # Filters row
        self._filters_row: Dict[str, QCheckBox] = {}
        filters_bar = QHBoxLayout()
        filters_bar.addWidget(QLabel("View:"))
        cats = [
            ("uploads", "Uploads"),
            ("auth", "Auth"),
            ("network", "Network"),
            ("ui", "UI"),
            ("queue", "Queue"),
            ("renaming", "Renaming"),
            ("fileio", "FileIO"),
            ("db", "DB"),
            ("timing", "Timing"),
            ("general", "General"),
        ]
        for cat_key, cat_label in cats:
            cb = QCheckBox(cat_label)
            cb.setChecked(True)
            self._filters_row[cat_key] = cb
            filters_bar.addWidget(cb)
        filters_bar.addStretch()
        logs_vbox.addLayout(filters_bar)

        # Body: log view table with timestamp, category, message columns
        body_hbox = QHBoxLayout()
        self.log_view = QTableWidget()
        self.log_view.setColumnCount(3)
        self.log_view.setHorizontalHeaderLabels(["Timestamp", "Category", "Message"])
        self.log_view.setAlternatingRowColors(True)
        self.log_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.log_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.log_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # Keep vertical header visible but style it like regular cells
        self.log_view.verticalHeader().setVisible(True)
        # Enable grid with semi-transparent styling
        self.log_view.setShowGrid(True)
        # Set monospace font
        _log_font = QFont("Consolas", 9)
        _log_font.setStyleHint(QFont.StyleHint.Monospace)
        self.log_view.setFont(_log_font)
        # Column sizing
        header = self.log_view.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Timestamp
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Category
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # Message
        self.log_view.setProperty("class", "log-viewer")

        # Apply inline stylesheet for semi-transparent gridlines
        # Get theme mode from palette
        from PyQt6.QtWidgets import QApplication
        palette = QApplication.palette()
        theme_mode = 'dark' if palette.window().color().lightness() < 128 else 'light'
        gridline_color = "rgba(102, 102, 102, 0.2)" if theme_mode == 'dark' else "rgba(204, 204, 204, 0.2)"
        self.log_view.setStyleSheet(f"""
            QTableWidget {{
                gridline-color: {gridline_color};
            }}
        """)

        body_hbox.addWidget(self.log_view, 1)
        logs_vbox.addLayout(body_hbox)

        # Just show the logs tab (no tabs needed)
        layout.addWidget(logs_container)

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

        def _parse_log_line(line: str) -> tuple:
            """Parse a log line into (timestamp, category, message)"""
            try:
                # Check for timestamp at start: YYYY-MM-DD HH:MM:SS
                if len(line) >= 19 and line[4] == '-' and line[7] == '-' and line[10] == ' ' and line[13] == ':' and line[16] == ':':
                    timestamp = line[:19]
                    rest = line[20:].lstrip()
                else:
                    timestamp = ""
                    rest = line

                # Extract category from [category] or [category:subtype]
                category = "general"
                if rest.startswith("[") and "]" in rest:
                    close_idx = rest.find("]")
                    tag = rest[1:close_idx]
                    # Split on : to get category
                    category = tag.split(":")[0] if ":" in tag else tag
                    message = rest[close_idx + 1:].lstrip()
                else:
                    message = rest

                return timestamp, category, message
            except Exception:
                return "", "general", line

        def _apply_initial_content():
            try:
                block = initial_text or _read_selected_file()
            except Exception:
                block = initial_text
            norm = _normalize_dates(block)
            # Add lines in reverse order (newest first)
            self.log_view.setRowCount(0)
            if norm:
                lines = norm.splitlines()
                for idx, line in enumerate(reversed(lines), 1):
                    timestamp, category, message = _parse_log_line(line)
                    row = self.log_view.rowCount()
                    self.log_view.insertRow(row)
                    self.log_view.setVerticalHeaderItem(row, QTableWidgetItem(str(idx)))
                    self.log_view.setItem(row, 0, QTableWidgetItem(timestamp))
                    self.log_view.setItem(row, 1, QTableWidgetItem(category))
                    self.log_view.setItem(row, 2, QTableWidgetItem(message))

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
            # Add lines in reverse order (newest first)
            self.log_view.setRowCount(0)
            if text:
                lines = text.splitlines()
                for idx, line in enumerate(reversed(lines), 1):
                    timestamp, category, message = _parse_log_line(line)
                    row = self.log_view.rowCount()
                    self.log_view.insertRow(row)
                    self.log_view.setVerticalHeaderItem(row, QTableWidgetItem(str(idx)))
                    self.log_view.setItem(row, 0, QTableWidgetItem(timestamp))
                    self.log_view.setItem(row, 1, QTableWidgetItem(category))
                    self.log_view.setItem(row, 2, QTableWidgetItem(message))

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
            self.log_view.setRowCount(0)
        self.btn_clear.clicked.connect(on_clear)

        def on_follow_toggle(_=None):
            self.follow_enabled = self.chk_follow.isChecked()
        self.chk_follow.toggled.connect(on_follow_toggle)

        # Find functionality - search through table rows
        self._last_find_row = -1
        def on_find_next():
            pattern = (self.find_input.text() or "").strip().lower()
            if not pattern:
                return

            # Start from next row after last find, or from top
            start_row = self._last_find_row + 1
            if start_row >= self.log_view.rowCount():
                start_row = 0

            # Search through all rows starting from start_row
            for i in range(self.log_view.rowCount()):
                row = (start_row + i) % self.log_view.rowCount()
                # Check all columns for match
                for col in range(3):
                    item = self.log_view.item(row, col)
                    if item and pattern in item.text().lower():
                        # Found match - select row and scroll to it
                        self.log_view.selectRow(row)
                        self.log_view.scrollToItem(item)
                        self._last_find_row = row
                        return
            # No match found - wrap to beginning
            self._last_find_row = -1

        self.btn_find.clicked.connect(on_find_next)
        self.find_input.returnPressed.connect(on_find_next)

        # Bottom button row
        button_layout = QHBoxLayout()
        log_settings_btn = QPushButton("Log Settings")
        log_settings_btn.clicked.connect(self.open_log_settings)
        button_layout.addWidget(log_settings_btn)
        button_layout.addStretch()

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        button_layout.addWidget(button_box)
        layout.addLayout(button_layout)

    def open_log_settings(self):
        """Open comprehensive settings to the Log tab"""
        try:
            # Get main window by traversing parent chain
            widget = self.parent()
            main_window = None
            while widget:
                if hasattr(widget, 'open_comprehensive_settings'):
                    main_window = widget
                    break
                widget = widget.parent() if hasattr(widget, 'parent') else None

            if main_window:
                # Open settings to Log tab (index 5) - keep this dialog open
                main_window.open_comprehensive_settings(tab_index=5)
        except Exception as e:
            # Debug: print error if settings don't open
            print(f"Error opening log settings: {e}")
            import traceback
            traceback.print_exc()

    def append_message(self, message: str):
        try:
            # Ensure date is visible in the log viewer if time-only
            from datetime import datetime as _dt
            if isinstance(message, str) and len(message) >= 9 and message[2:3] == ":":
                today = _dt.now().strftime("%Y-%m-%d ")
                line = today + message
            else:
                line = message

            # Parse the log line
            timestamp, category, msg_text = self._parse_log_line_for_append(line)

            # Apply viewer-only filters (toolbar row)
            if category in getattr(self, '_filters_row', {}) and not self._filters_row[category].isChecked():
                return

            # Prepend to table (newest first) and renumber all rows
            self.log_view.insertRow(0)
            # Update row numbers for all rows
            for row in range(self.log_view.rowCount()):
                self.log_view.setVerticalHeaderItem(row, QTableWidgetItem(str(row + 1)))
            # Set data for new row
            self.log_view.setItem(0, 0, QTableWidgetItem(timestamp))
            self.log_view.setItem(0, 1, QTableWidgetItem(category))
            self.log_view.setItem(0, 2, QTableWidgetItem(msg_text))

            # Scroll to top if follow enabled
            if self.follow_enabled:
                self.log_view.scrollToTop()
        except Exception:
            pass

    def _parse_log_line_for_append(self, line: str) -> tuple:
        """Parse a log line for append_message"""
        try:
            # Check for timestamp at start: YYYY-MM-DD HH:MM:SS
            if len(line) >= 19 and line[4] == '-' and line[7] == '-' and line[10] == ' ' and line[13] == ':' and line[16] == ':':
                timestamp = line[:19]
                rest = line[20:].lstrip()
            else:
                timestamp = ""
                rest = line

            # Extract category from [category] or [category:subtype]
            category = "general"
            if rest.startswith("[") and "]" in rest:
                close_idx = rest.find("]")
                tag = rest[1:close_idx]
                # Split on : to get category
                category = tag.split(":")[0] if ":" in tag else tag
                message = rest[close_idx + 1:].lstrip()
            else:
                message = rest

            return timestamp, category, message
        except Exception:
            return "", "general", line