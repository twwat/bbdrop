"""External Apps (Hooks) settings tab -- configure programs to run on gallery events."""

import configparser
import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QCheckBox,
    QRadioButton, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QDialog, QApplication,
    QSplitter,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFontDatabase

from bbdrop import get_config_path
from src.gui.widgets.info_button import InfoButton
from src.utils.logger import log


class HooksTab(QWidget):
    """Self-contained External Apps (Hooks) settings tab.

    Emits *dirty* whenever any control value changes so the orchestrator
    can track unsaved state without knowing the internals.
    """

    dirty = pyqtSignal()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self.load_settings()

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        """Build the External Apps settings UI."""
        layout = QVBoxLayout(self)

        # Intro text
        intro_row = QHBoxLayout()
        intro_label = QLabel(
            "Run external programs at different stages of gallery processing. "
            "Programs can output JSON to populate ext1-4 fields for use in templates."
        )
        intro_label.setWordWrap(True)
        intro_label.setProperty("class", "tab-description")
        intro_row.addWidget(intro_label)
        intro_row.addWidget(InfoButton(
            "<b>How hooks work:</b><br><br>"
            "A hook runs a command-line program at a specific stage of gallery "
            "processing. The command can include <code>%variables</code> that "
            "get replaced with gallery data (path, name, image count, etc.).<br><br>"
            "The program's stdout can output JSON &mdash; you map JSON keys to "
            "<code>ext1</code>&ndash;<code>ext4</code> fields, which then become "
            "available in your BBCode templates as <code>%ext1</code> through "
            "<code>%ext4</code>.<br><br>"
            "<b>Common use case:</b> Run a script that uploads the gallery ZIP "
            "to a filehost and outputs "
            "<code>{\"download_url\": \"https://...\"}</code>. Map that to ext1, "
            "then use <code>%ext1</code> in your BBCode template."
        ))
        layout.addLayout(intro_row)

        # Execution mode
        exec_mode_group = QGroupBox("Execution Mode")
        exec_mode_layout = QHBoxLayout(exec_mode_group)
        self.hooks_parallel_radio = QRadioButton("Run hooks in parallel")
        self.hooks_parallel_radio.setToolTip("Run all hooks simultaneously")
        self.hooks_sequential_radio = QRadioButton("Run hooks sequentially")
        self.hooks_sequential_radio.setToolTip("Run hooks one at a time in order")
        self.hooks_parallel_radio.setChecked(True)
        exec_mode_layout.addWidget(self.hooks_parallel_radio)
        exec_mode_layout.addWidget(self.hooks_sequential_radio)
        exec_mode_layout.addStretch()
        layout.addWidget(exec_mode_group)

        # Create hook sections
        self._create_hook_section(layout, "On Gallery Added", "added")
        self._create_hook_section(layout, "On Gallery Started", "started")
        self._create_hook_section(layout, "On Gallery Completed", "completed")

        layout.addStretch()

        # Connect signals to mark tab as dirty
        self.hooks_parallel_radio.toggled.connect(lambda: self.dirty.emit())
        self.hooks_sequential_radio.toggled.connect(lambda: self.dirty.emit())
        for hook_type in ['added', 'started', 'completed']:
            getattr(self, f'hook_{hook_type}_enabled').toggled.connect(lambda: self.dirty.emit())
            getattr(self, f'hook_{hook_type}_command').textChanged.connect(lambda: self.dirty.emit())
            getattr(self, f'hook_{hook_type}_show_console').toggled.connect(lambda: self.dirty.emit())

    # ------------------------------------------------------------------
    # Hook section builder
    # ------------------------------------------------------------------

    def _create_hook_section(self, parent_layout, title, hook_type):
        """Create a compact section for configuring a single hook."""
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        hook_titles = {
            'added': 'added to the queue',
            'started': 'started',
            'completed': 'finished uploading',
        }

        # Top row: Enable checkbox + Configure button
        top_row = QHBoxLayout()
        enable_check = QCheckBox(
            f"Enable hook: called when galleries are {hook_titles.get(hook_type, hook_type.title())}"
        )
        enable_check.setToolTip("Enable this hook")
        setattr(self, f'hook_{hook_type}_enabled', enable_check)
        top_row.addWidget(enable_check, 2)

        # Configure button
        configure_btn = QPushButton("Configure Hook")
        configure_btn.setToolTip(
            f"Configure and test '{hook_titles.get(hook_type, hook_type.title())}' hook "
            "- set up command, test execution, and map JSON output"
        )
        configure_btn.clicked.connect(lambda: self._show_json_mapping_dialog(hook_type))
        top_row.addWidget(configure_btn, 1)

        layout.addLayout(top_row)

        # Command row with monospace font
        command_layout = QHBoxLayout()
        command_layout.addWidget(QLabel("Command:"))

        command_input = QLineEdit()
        command_input.setToolTip("Command to run (use %variables for gallery data)")
        command_input.setPlaceholderText('python script.py "%p" or muh.py gofile "%z"')
        mono_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        command_input.setFont(mono_font)
        setattr(self, f'hook_{hook_type}_command', command_input)
        command_layout.addWidget(command_input, 1)
        layout.addLayout(command_layout)

        # Hidden storage for settings
        show_console_check = QCheckBox()
        show_console_check.setVisible(False)
        setattr(self, f'hook_{hook_type}_show_console', show_console_check)

        for i in range(1, 5):
            key_input = QLineEdit()
            key_input.setVisible(False)
            setattr(self, f'hook_{hook_type}_key{i}', key_input)

        parent_layout.addWidget(group)

    # ------------------------------------------------------------------
    # Variable helpers
    # ------------------------------------------------------------------

    def _get_available_vars(self, hook_type):
        """Get available variables for a hook type."""
        base_vars = "%N, %T, %p, %C, %s, %t, %z, %e1-%e4, %c1-%c4"
        if hook_type == "completed":
            return f"{base_vars}, %g, %j, %b"
        return base_vars

    def _browse_for_program(self, hook_type):
        """Browse for executable program."""
        from PyQt6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Program",
            "",
            "Executables (*.exe *.bat *.cmd *.py);;All Files (*.*)",
        )
        if file_path:
            command_input = getattr(self, f'hook_{hook_type}_command')
            command_input.setText(f'"{file_path}"')

    def _show_variable_menu(self, hook_type):
        """Show menu to insert variable at cursor position."""
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QCursor

        menu = QMenu(self)

        variables = [
            ("%N", "Gallery name"),
            ("%T", "Tab name"),
            ("%p", "Gallery folder path"),
            ("%C", "Number of images"),
            ("%z", "ZIP archive path (created on demand)"),
        ]

        if hook_type == "completed":
            variables.extend([
                ("%g", "Gallery ID"),
                ("%j", "JSON artifact path"),
                ("%b", "BBCode artifact path"),
            ])

        for var, desc in variables:
            action = menu.addAction(f"{var}  -  {desc}")
            action.triggered.connect(lambda checked, v=var: self._insert_variable(hook_type, v))

        menu.exec(QCursor.pos())

    def _insert_variable(self, hook_type, variable):
        """Insert variable at cursor position in command input."""
        command_input = getattr(self, f'hook_{hook_type}_command')
        cursor_pos = command_input.cursorPosition()
        current_text = command_input.text()
        new_text = current_text[:cursor_pos] + variable + current_text[cursor_pos:]
        command_input.setText(new_text)
        command_input.setCursorPosition(cursor_pos + len(variable))
        command_input.setFocus()

    # ------------------------------------------------------------------
    # JSON mapping dialog (Configure Hook)
    # ------------------------------------------------------------------

    def _show_json_mapping_dialog(self, hook_type):
        """Show dialog for configuring JSON key mappings."""
        from PyQt6.QtWidgets import QTextEdit
        from src.gui.widgets.auto_complete_text_edit import AutoCompleteTextEdit
        from src.gui.widgets.command_highlighter import CommandHighlighter

        # Map hook types to friendly names
        hook_names = {
            'added': 'On Gallery Added',
            'started': 'On Gallery Started',
            'completed': 'On Gallery Completed',
        }

        dialog = QDialog(self)
        dialog.setWindowTitle(
            f"Command Builder & JSON Mapper - {hook_names.get(hook_type, hook_type.title())}"
        )
        dialog.setModal(True)
        dialog.resize(850, 750)

        layout = QVBoxLayout(dialog)

        # Command Builder section
        command_group = QGroupBox(
            f"Command Builder - {hook_names.get(hook_type, hook_type.title())}"
        )
        command_layout = QVBoxLayout(command_group)

        # Command input with helper
        command_input_layout = QHBoxLayout()
        command_label = QLabel("Command Template:")
        command_label.setStyleSheet("font-weight: bold;")
        command_input_layout.addWidget(command_label)

        insert_var_btn = QPushButton("Insert % Variable \u25bc")
        insert_var_btn.setToolTip("Insert a variable at cursor position (or type % to see options)")
        command_input_layout.addWidget(insert_var_btn)

        test_btn = QPushButton("\u25b6 Run Test Command")
        test_btn.setToolTip("Execute the command with test data")
        test_btn.setStyleSheet("font-weight: bold;")
        command_input_layout.addWidget(test_btn)

        command_input_layout.addStretch()
        command_layout.addLayout(command_input_layout)

        # Variable definitions
        base_variables = [
            ("%N", "Gallery name"),
            ("%T", "Tab name"),
            ("%p", "Gallery folder path"),
            ("%C", "Number of images"),
            ("%s", "Gallery size in bytes"),
            ("%t", "Template name"),
            ("%z", "ZIP archive path (created on demand)"),
            ("", ""),  # Separator
            ("%e1", "ext1 field value"),
            ("%e2", "ext2 field value"),
            ("%e3", "ext3 field value"),
            ("%e4", "ext4 field value"),
            ("", ""),  # Separator
            ("%c1", "custom1 field value"),
            ("%c2", "custom2 field value"),
            ("%c3", "custom3 field value"),
            ("%c4", "custom4 field value"),
        ]

        if hook_type == "completed":
            base_variables.insert(4, ("%g", "Gallery ID"))
            base_variables.insert(5, ("%j", "JSON artifact path"))
            base_variables.insert(6, ("%b", "BBCode artifact path"))

        # AutoCompleteTextEdit from extracted widget
        command_input = AutoCompleteTextEdit(base_variables, dialog)
        current_command = getattr(self, f'hook_{hook_type}_command').text()
        command_input.setPlainText(current_command)
        command_input.setPlaceholderText(
            'e.g., python script.py "%p" "%N"\nor: C:\\program.exe "%g" --output "%j"'
        )

        mono_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        mono_font.setPointSize(11)
        command_input.setFont(mono_font)
        command_input.setMaximumHeight(120)
        command_input.setObjectName("commandInput")
        command_layout.addWidget(command_input)

        def show_var_menu():
            from PyQt6.QtWidgets import QMenu
            from PyQt6.QtGui import QCursor

            menu = QMenu(dialog)
            for var, desc in base_variables:
                if not var:
                    menu.addSeparator()
                else:
                    action = menu.addAction(f"{var}  -  {desc}")
                    action.triggered.connect(
                        lambda checked, v=var: insert_variable_in_dialog(v)
                    )
            menu.exec(QCursor.pos())

        def insert_variable_in_dialog(variable):
            cursor = command_input.textCursor()
            cursor.insertText(variable)
            command_input.setFocus()

        insert_var_btn.clicked.connect(show_var_menu)

        # Preview section
        preview_label = QLabel("Preview (with test data):")
        preview_label.setStyleSheet("font-weight: bold; margin-top: 8px;")
        command_layout.addWidget(preview_label)

        preview_display = QTextEdit()
        preview_display.setReadOnly(True)
        preview_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        preview_font.setPointSize(10)
        preview_display.setFont(preview_font)
        preview_display.setObjectName("commandPreview")
        preview_display.setMaximumHeight(80)
        command_layout.addWidget(preview_display)

        layout.addWidget(command_group)

        # Create test zip file for hook testing
        import tempfile
        import zipfile

        test_zip_path = None

        def create_test_zip():
            """Create a small test zip file with a dummy text file for hook testing."""
            nonlocal test_zip_path
            if test_zip_path and os.path.exists(test_zip_path):
                return test_zip_path
            try:
                temp_dir = tempfile.gettempdir()
                test_zip_path = os.path.join(temp_dir, 'hook_test_gallery.zip')
                with zipfile.ZipFile(test_zip_path, 'w', zipfile.ZIP_STORED) as zf:
                    zf.writestr('test_image.txt', 'This is a test file for hook testing.\n' * 10)
                return test_zip_path
            except Exception as e:
                log(f"Failed to create test zip: {e}", level="warning", category="hooks")
                return ''

        def cleanup_test_zip():
            """Clean up the test zip file when dialog closes."""
            nonlocal test_zip_path
            if test_zip_path and os.path.exists(test_zip_path):
                try:
                    os.remove(test_zip_path)
                except Exception:
                    pass

        dialog.finished.connect(cleanup_test_zip)

        # Color definitions matching CommandHighlighter
        GALLERY_COLOR = '#2980b9'   # Blue
        UPLOAD_COLOR = '#27ae60'    # Green
        EXT_COLOR = '#e67e22'       # Orange
        CUSTOM_COLOR = '#9b59b6'    # Purple

        def update_preview():
            command = command_input.toPlainText()
            zip_path = create_test_zip()

            substitutions_with_colors = [
                ('%e1', 'val1', EXT_COLOR),
                ('%e2', 'val2', EXT_COLOR),
                ('%e3', 'val3', EXT_COLOR),
                ('%e4', 'val4', EXT_COLOR),
                ('%c1', 'cval1', CUSTOM_COLOR),
                ('%c2', 'cval2', CUSTOM_COLOR),
                ('%c3', 'cval3', CUSTOM_COLOR),
                ('%c4', 'cval4', CUSTOM_COLOR),
                ('%N', 'Test Gallery', GALLERY_COLOR),
                ('%T', 'Main', GALLERY_COLOR),
                ('%p', 'C:\\test\\path', GALLERY_COLOR),
                ('%C', '10', GALLERY_COLOR),
                ('%s', '1048576', GALLERY_COLOR),
                ('%t', 'default', GALLERY_COLOR),
                ('%z', zip_path, UPLOAD_COLOR),
            ]

            if hook_type == "completed":
                substitutions_with_colors.extend([
                    ('%g', 'TEST123', UPLOAD_COLOR),
                    ('%j', 'C:\\test\\artifact.json', UPLOAD_COLOR),
                    ('%b', 'C:\\test\\bbcode.txt', UPLOAD_COLOR),
                ])

            substitutions_with_colors.sort(key=lambda x: len(x[0]), reverse=True)
            substitutions = {var: val for var, val, _ in substitutions_with_colors}

            preview_command = command
            for var, value in sorted(substitutions.items(), key=lambda x: len(x[0]), reverse=True):
                preview_command = preview_command.replace(var, value)

            html_preview = command
            html_preview = html_preview.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            for var, value, color in substitutions_with_colors:
                escaped_value = value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                colored_value = (
                    f'<span style="color: {color}; font-weight: bold;">{escaped_value}</span>'
                )
                html_preview = html_preview.replace(var, colored_value)

            preview_display.setHtml(
                f'<pre style="margin: 0; white-space: pre-wrap;">{html_preview}</pre>'
            )

        # Apply CommandHighlighter from extracted widget
        CommandHighlighter(command_input.document())

        command_input.textChanged.connect(update_preview)
        update_preview()

        # JSON Key Mapping section
        mapping_group = QGroupBox("JSON Key Mappings")
        mapping_layout = QVBoxLayout(mapping_group)
        mapping_layout.setSpacing(4)

        mapping_info = QLabel(
            "Map program output to ext1-4 columns to make data available in "
            "bbcode template (e.g. download links from filehosts)."
        )
        mapping_info.setStyleSheet("font-size: 10px;")
        mapping_layout.addWidget(mapping_info)

        key_inputs = {}
        for row in range(1):
            row_layout = QHBoxLayout()
            row_layout.setSpacing(8)
            for col in range(4):
                i = row * 2 + col + 1
                label = QLabel(f"<b>ext{i}</b>:")
                label.setMinimumWidth(35)
                row_layout.addWidget(label)
                key_input = QLineEdit()
                current_value = getattr(self, f'hook_{hook_type}_key{i}').text()
                key_input.setText(current_value)
                key_inputs[f'ext{i}'] = key_input
                row_layout.addWidget(key_input, 1)
            mapping_layout.addLayout(row_layout)

        mapping_group.setMaximumHeight(110)
        layout.addWidget(mapping_group)

        # Console/execution options
        options_layout = QHBoxLayout()
        show_console_check = QCheckBox("Show console window when executing")
        show_console_check.setToolTip(
            "If enabled, a console window will appear when the command runs (Windows only)"
        )
        current_show_console = getattr(self, f'hook_{hook_type}_show_console').isChecked()
        show_console_check.setChecked(current_show_console)
        options_layout.addWidget(show_console_check)
        options_layout.addStretch()
        layout.addLayout(options_layout)

        # Test section
        test_group = QGroupBox("Test Output")
        test_layout = QVBoxLayout(test_group)

        results_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Table widget for JSON results (left side)
        table_container = QWidget()
        table_layout_inner = QVBoxLayout(table_container)
        table_layout_inner.setContentsMargins(0, 0, 0, 0)

        results_table = QTableWidget()
        results_table.setColumnCount(2)
        results_table.setHorizontalHeaderLabels(["Key", "Value"])
        header_font = results_table.horizontalHeader().font()
        header_font.setPointSize(header_font.pointSize() + 1)
        header_font.setBold(True)
        results_table.horizontalHeader().setFont(header_font)
        results_table.horizontalHeader().setStretchLastSection(True)
        results_table.setAlternatingRowColors(True)
        results_table.setVisible(False)
        table_layout_inner.addWidget(results_table)

        results_splitter.addWidget(table_container)

        # Text output widget for raw output (right side)
        from PyQt6.QtWidgets import QTextEdit

        output_container = QWidget()
        output_layout = QVBoxLayout(output_container)
        output_layout.setContentsMargins(0, 0, 0, 0)

        test_output = QTextEdit()
        test_output.setReadOnly(True)
        test_output.setPlaceholderText(
            "Click '\u25b6 Run Test Command' button above to execute and see output..."
        )
        test_output_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        test_output.setFont(test_output_font)
        output_layout.addWidget(test_output)

        results_splitter.addWidget(output_container)
        results_splitter.setSizes([300, 500])

        def run_test():
            import subprocess
            import json

            test_command = preview_display.toPlainText()

            if not test_command or not command_input.toPlainText():
                test_output.setPlainText("Error: No command configured")
                results_table.setVisible(False)
                return

            try:
                test_output.setText(f"Running: {test_command}\n\nPlease wait...")
                QApplication.processEvents()

                import shlex
                try:
                    command_parts = shlex.split(test_command)
                except ValueError as e:
                    test_output.setText(
                        f"ERROR: Invalid command syntax: {e}\n\n"
                        "Command must use proper quoting for arguments with spaces."
                    )
                    return

                result = subprocess.run(
                    command_parts,
                    shell=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                output_text = (
                    f"=== STDOUT ===\n{result.stdout if result.stdout else '(empty)'}\n\n"
                )
                if result.stderr:
                    output_text += f"=== STDERR ===\n{result.stderr}\n\n"

                if result.stdout.strip():
                    is_json = False
                    try:
                        json_data = json.loads(result.stdout.strip())
                        is_json = True

                        # Check if JSON indicates an error response
                        is_error_response = False
                        error_message = None

                        if isinstance(json_data, dict):
                            if 'error' in json_data and 'status' in json_data:
                                if json_data.get('status') in ['failed', 'error', 'fail']:
                                    is_error_response = True
                                    error_message = json_data.get('error', 'Unknown error')
                            elif 'error' in json_data and not any(
                                k in json_data for k in ['url', 'link', 'data', 'result', 'success']
                            ):
                                is_error_response = True
                                error_message = json_data.get('error', 'Unknown error')
                            elif (
                                json_data.get('status') in ['failed', 'error', 'fail']
                                and 'message' in json_data
                            ):
                                is_error_response = True
                                error_message = json_data.get('message', 'Unknown error')
                            elif json_data.get('success') is False and 'error' in json_data:
                                is_error_response = True
                                error_message = json_data.get('error', 'Unknown error')

                        if is_error_response:
                            from PyQt6.QtWidgets import QMessageBox

                            results_table.setVisible(False)
                            output_text += "Command returned an error response\n\n"
                            test_output.setPlainText(output_text)

                            QMessageBox.critical(
                                dialog,
                                "External App Test Failed",
                                f"The external application returned an error:\n\n{error_message}",
                            )
                            return

                        results_table.setRowCount(0)
                        for key, value in json_data.items():
                            row_position = results_table.rowCount()
                            results_table.insertRow(row_position)

                            key_item = QTableWidgetItem(str(key))
                            key_item.setToolTip(str(key))
                            results_table.setItem(row_position, 0, key_item)

                            if isinstance(value, (dict, list)):
                                value_text = json.dumps(value, indent=2)
                            else:
                                value_text = str(value)

                            value_item = QTableWidgetItem(value_text)
                            value_item.setToolTip(value_text)
                            results_table.setItem(row_position, 1, value_item)

                        results_table.resizeColumnsToContents()

                        if results_table.rowCount() > 0:
                            results_table.setVisible(True)
                            output_text += "Valid JSON detected and parsed in left panel\n\n"
                        else:
                            results_table.setVisible(False)
                            output_text += "JSON was valid but empty\n\n"

                        test_output.setPlainText(output_text)

                    except json.JSONDecodeError:
                        is_json = False
                        results_table.setVisible(False)

                        from src.processing.hook_output_parser import detect_stdout_values

                        detected_values = detect_stdout_values(result.stdout)

                        if detected_values:
                            output_text += f"Found {len(detected_values)} value(s) in output\n\n"
                            for det in detected_values:
                                type_label = det['type'].upper()
                                if det['type'] in ('url', 'path'):
                                    output_text += f"  {type_label}[{det['index']}]: {det['value']}\n"
                                else:
                                    output_text += f"  {det['key']}: {det['value']}\n"
                            output_text += "\n"
                        else:
                            output_text += "No recognizable patterns found in output\n\n"
                            detected_values = None

                        test_output.setPlainText(output_text)

                    # Show interactive mapper dialog
                    from src.gui.dialogs.hook_mapper_dialog import HookMapperDialog

                    if is_json and json_data:
                        mapper = HookMapperDialog(
                            detected_values=None,
                            is_json=True,
                            json_data=json_data,
                            parent=dialog,
                        )
                        if mapper.exec() == QDialog.DialogCode.Accepted:
                            for ext_field, info in mapper.get_mappings().items():
                                key_inputs[ext_field].setText(info['key'])
                    elif not is_json and detected_values:
                        mapper = HookMapperDialog(
                            detected_values=detected_values,
                            is_json=False,
                            parent=dialog,
                        )
                        if mapper.exec() == QDialog.DialogCode.Accepted:
                            for ext_field, info in mapper.get_mappings().items():
                                key_inputs[ext_field].setText(info['key'])

                else:
                    results_table.setVisible(False)
                    test_output.setPlainText(output_text + "Command produced no stdout")

            except subprocess.TimeoutExpired:
                results_table.setVisible(False)
                test_output.setPlainText("Error: Command timed out after 30 seconds")
            except Exception as e:
                results_table.setVisible(False)
                test_output.setPlainText(f"Error: {e}")

        test_btn.clicked.connect(run_test)
        test_layout.addWidget(results_splitter)
        layout.addWidget(test_group)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        save_btn = QPushButton("Save")
        save_btn.setDefault(True)

        def save_mapping():
            new_command = command_input.toPlainText().strip()
            getattr(self, f'hook_{hook_type}_command').setText(new_command)
            getattr(self, f'hook_{hook_type}_show_console').setChecked(show_console_check.isChecked())
            for i in range(1, 5):
                key = f'ext{i}'
                value = key_inputs[key].text().strip()
                getattr(self, f'hook_{hook_type}_key{i}').setText(value)
            self.dirty.emit()
            dialog.accept()

        save_btn.clicked.connect(save_mapping)
        button_layout.addWidget(save_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

        dialog.exec()

    # ------------------------------------------------------------------
    # Settings persistence
    # ------------------------------------------------------------------

    def load_settings(self):
        """Load external apps settings from INI file."""
        try:
            config = configparser.ConfigParser()
            config_file = get_config_path()

            if os.path.exists(config_file):
                config.read(config_file, encoding='utf-8')
            else:
                log(
                    f"Config file does not exist: {config_file}",
                    level="warning",
                    category="settings",
                )
                return

            if 'EXTERNAL_APPS' not in config:
                log(
                    "No EXTERNAL_APPS section in config, using defaults",
                    level="debug",
                    category="settings",
                )
                return

            # Block signals during loading
            controls = [self.hooks_parallel_radio, self.hooks_sequential_radio]
            for hook_type in ['added', 'started', 'completed']:
                controls.extend([
                    getattr(self, f'hook_{hook_type}_enabled'),
                    getattr(self, f'hook_{hook_type}_command'),
                    getattr(self, f'hook_{hook_type}_show_console'),
                ])

            for control in controls:
                control.blockSignals(True)

            parallel = config.getboolean('EXTERNAL_APPS', 'parallel_execution', fallback=True)
            if parallel:
                self.hooks_parallel_radio.setChecked(True)
            else:
                self.hooks_sequential_radio.setChecked(True)

            for hook_type in ['added', 'started', 'completed']:
                enabled = config.getboolean(
                    'EXTERNAL_APPS', f'hook_{hook_type}_enabled', fallback=False
                )
                command = config.get('EXTERNAL_APPS', f'hook_{hook_type}_command', fallback='')
                show_console = config.getboolean(
                    'EXTERNAL_APPS', f'hook_{hook_type}_show_console', fallback=False
                )

                getattr(self, f'hook_{hook_type}_enabled').setChecked(enabled)
                getattr(self, f'hook_{hook_type}_command').setText(command)
                getattr(self, f'hook_{hook_type}_show_console').setChecked(show_console)

                for i in range(1, 5):
                    key_mapping = config.get(
                        'EXTERNAL_APPS', f'hook_{hook_type}_key{i}', fallback=''
                    )
                    getattr(self, f'hook_{hook_type}_key{i}').setText(key_mapping)

            for control in controls:
                control.blockSignals(False)

        except Exception as e:
            import traceback
            log(
                f"Failed to load external apps settings: {e}",
                level="error",
                category="settings",
            )
            traceback.print_exc()

    def save_settings(self):
        """Save external apps settings to INI file."""
        try:
            config = configparser.ConfigParser()
            config_file = get_config_path()

            if os.path.exists(config_file):
                config.read(config_file, encoding='utf-8')

            if 'EXTERNAL_APPS' not in config:
                config.add_section('EXTERNAL_APPS')

            config.set(
                'EXTERNAL_APPS',
                'parallel_execution',
                str(self.hooks_parallel_radio.isChecked()),
            )

            for hook_type in ['added', 'started', 'completed']:
                enabled = getattr(self, f'hook_{hook_type}_enabled').isChecked()
                command = getattr(self, f'hook_{hook_type}_command').text()
                show_console = getattr(self, f'hook_{hook_type}_show_console').isChecked()

                escaped_command = command.replace('%', '%%')

                config.set('EXTERNAL_APPS', f'hook_{hook_type}_enabled', str(enabled))
                config.set('EXTERNAL_APPS', f'hook_{hook_type}_command', escaped_command)
                config.set('EXTERNAL_APPS', f'hook_{hook_type}_show_console', str(show_console))

                for i in range(1, 5):
                    key_mapping = getattr(self, f'hook_{hook_type}_key{i}').text()
                    config.set('EXTERNAL_APPS', f'hook_{hook_type}_key{i}', key_mapping)

            with open(config_file, 'w', encoding='utf-8') as f:
                config.write(f)

            return True

        except Exception as e:
            log(
                f"Failed to save external apps settings: {e}",
                level="warning",
                category="settings",
            )
            return False

    def reload_settings(self):
        """Reload settings from disk, discarding any unsaved changes."""
        self.load_settings()

    def reset_to_defaults(self):
        """Reset all hooks settings to their defaults."""
        # Block signals during reset
        controls = [self.hooks_parallel_radio, self.hooks_sequential_radio]
        for hook_type in ['added', 'started', 'completed']:
            controls.extend([
                getattr(self, f'hook_{hook_type}_enabled'),
                getattr(self, f'hook_{hook_type}_command'),
                getattr(self, f'hook_{hook_type}_show_console'),
            ])

        for control in controls:
            control.blockSignals(True)

        self.hooks_parallel_radio.setChecked(True)

        for hook_type in ['added', 'started', 'completed']:
            getattr(self, f'hook_{hook_type}_enabled').setChecked(False)
            getattr(self, f'hook_{hook_type}_command').setText('')
            getattr(self, f'hook_{hook_type}_show_console').setChecked(False)
            for i in range(1, 5):
                getattr(self, f'hook_{hook_type}_key{i}').setText('')

        for control in controls:
            control.blockSignals(False)
