"""
Interactive dialog for mapping detected hook output values to ext1-4 fields.

Shows all detected values (URLs, paths, key-value pairs) with:
- Checkboxes to select which values to map
- Editable "Save as" key fields (defaults to URL[1], PATH[1], json_key, etc.)
- Expandable sub-components for URLs and paths (.filename, .domain, etc.)
- Dropdown to assign each selected value to ext1/ext2/ext3/ext4
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QScrollArea, QWidget,
    QCheckBox, QLineEdit, QComboBox, QLabel,
    QPushButton, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontDatabase

from src.processing.hook_output_parser import (
    get_available_components, extract_component
)


class HookMapperDialog(QDialog):
    """Dialog for mapping detected hook output values to ext fields."""

    def __init__(self, detected_values, is_json=False, json_data=None, parent=None):
        """
        Args:
            detected_values: list from detect_stdout_values() for plain text,
                            or None if JSON
            is_json: True if output was valid JSON
            json_data: parsed JSON dict (when is_json=True)
            parent: parent widget
        """
        super().__init__(parent)
        self.setWindowTitle("Map Hook Output")
        self.setMinimumWidth(550)
        self.setMinimumHeight(300)

        self.is_json = is_json
        self.items = []
        self.result_mappings = {}

        layout = QVBoxLayout(self)

        # Header
        if is_json:
            header = QLabel("Detected values from JSON output:")
        else:
            header = QLabel("Detected values from output:")
        header.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(header)

        # Scrollable area for detected values
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(scroll_widget)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll, 1)

        # Populate items
        if is_json and json_data:
            self._populate_json_items(json_data)
        elif detected_values:
            self._populate_detected_items(detected_values)

        # Footer
        footer = QHBoxLayout()
        self.count_label = QLabel("Selected: 0 values")
        footer.addWidget(self.count_label)
        footer.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        footer.addWidget(cancel_btn)

        save_btn = QPushButton("Save Mappings")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save_and_accept)
        footer.addWidget(save_btn)

        layout.addLayout(footer)
        self._update_count()

    def _populate_json_items(self, json_data):
        """Add items for JSON key-value pairs."""
        if not isinstance(json_data, dict):
            return
        for key, value in json_data.items():
            if isinstance(value, (dict, list)):
                display = str(value)[:100]
            else:
                display = str(value)
            self._add_item(
                label=f"{key}  (JSON key)",
                value_display=display,
                default_key=key,
                extract_rule=key,
                value_type='data',
                checked=True,
            )

    def _populate_detected_items(self, detected_values):
        """Add items for plain-text detected values."""
        for det in detected_values:
            type_label = det['type'].upper()
            if det['type'] in ('url', 'path'):
                placeholder = f"{type_label}[{det['index']}]"
                label = placeholder
                default_key = placeholder
                extract_rule = placeholder
            else:
                label = f"{det['key']}  (key-value)"
                default_key = det['key']
                extract_rule = det['key']

            self._add_item(
                label=label,
                value_display=det['value'],
                default_key=default_key,
                extract_rule=extract_rule,
                value_type=det['type'],
                checked=(det['type'] == 'url'),
            )

            # Add sub-components for URLs and paths
            if det['type'] in ('url', 'path'):
                components = get_available_components(det['type'])
                for comp in components:
                    comp_value = extract_component(
                        det['value'], det['type'], comp['key']
                    )
                    if comp_value:
                        comp_placeholder = f"{type_label}[{det['index']}].{comp['key']}"
                        self._add_item(
                            label=f"    {comp['label']}",
                            value_display=comp_value,
                            default_key=comp_placeholder,
                            extract_rule=comp_placeholder,
                            value_type=det['type'],
                            checked=False,
                            indent=True,
                        )

    def _add_item(self, label, value_display, default_key, extract_rule,
                  value_type, checked=False, indent=False):
        """Add a single mappable item row."""
        frame = QFrame()
        if not indent:
            frame.setFrameShape(QFrame.Shape.StyledPanel)
            frame.setStyleSheet("QFrame { margin-bottom: 2px; }")

        row_layout = QVBoxLayout(frame)
        row_layout.setContentsMargins(12 if not indent else 32, 4, 8, 4)
        row_layout.setSpacing(2)

        # Top row: checkbox + ext slot dropdown
        top = QHBoxLayout()
        cb = QCheckBox(label)
        cb.setChecked(checked)
        cb.stateChanged.connect(self._update_count)
        top.addWidget(cb)
        top.addStretch()

        slot_combo = QComboBox()
        slot_combo.addItems(["auto", "ext1", "ext2", "ext3", "ext4", "skip"])
        slot_combo.setFixedWidth(70)
        slot_combo.setToolTip("Which ext field to map this value to")
        top.addWidget(slot_combo)
        row_layout.addLayout(top)

        # Value display
        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        val_label = QLabel(value_display)
        val_label.setFont(mono)
        val_label.setStyleSheet("color: #666; padding-left: 24px;")
        val_label.setWordWrap(True)
        if len(value_display) > 80:
            val_label.setToolTip(value_display)
            val_label.setText(value_display[:77] + "...")
        row_layout.addWidget(val_label)

        # Key name row
        key_row = QHBoxLayout()
        key_label = QLabel("Save as:")
        key_label.setStyleSheet("padding-left: 24px; font-size: 10px;")
        key_row.addWidget(key_label)
        key_input = QLineEdit(default_key)
        key_input.setMaximumWidth(200)
        key_input.setStyleSheet("font-size: 10px;")
        key_row.addWidget(key_input)
        key_row.addStretch()
        row_layout.addLayout(key_row)

        self.scroll_layout.addWidget(frame)

        item_data = {
            'checkbox': cb,
            'key_input': key_input,
            'slot_combo': slot_combo,
            'extract_rule': extract_rule,
            'value_type': value_type,
            'indent': indent,
        }
        self.items.append(item_data)
        return item_data

    def _update_count(self):
        checked = sum(1 for item in self.items if item['checkbox'].isChecked())
        self.count_label.setText(f"Selected: {checked} value(s)")

    def _save_and_accept(self):
        """Build result mappings and accept dialog."""
        self.result_mappings = {}
        checked_items = [item for item in self.items if item['checkbox'].isChecked()]

        auto_counter = 1
        for item in checked_items:
            slot = item['slot_combo'].currentText()
            key_name = item['key_input'].text().strip()
            if not key_name:
                continue

            if slot == 'skip':
                continue
            elif slot == 'auto':
                while f'ext{auto_counter}' in self.result_mappings and auto_counter <= 4:
                    auto_counter += 1
                if auto_counter > 4:
                    continue
                slot = f'ext{auto_counter}'
                auto_counter += 1

            self.result_mappings[slot] = {
                'key': key_name,
                'extract': item['extract_rule'],
            }

        self.accept()

    def get_mappings(self):
        """Return the user's chosen mappings after dialog closes."""
        return self.result_mappings
