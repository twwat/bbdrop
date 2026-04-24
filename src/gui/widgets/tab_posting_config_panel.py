"""Tab posting config panel — v2 multi-destination model.

Shows a list of (Forum, Target, Template) destination rows using
ForumTargetPicker for target selection. Separate section for trigger
settings (trigger_mode, enabled). Behavioral policies (update_mode,
manual_edit_handling, stale_triggers) are now global — see Settings → Forums.

TabPostingConfigDialog(conn, tab_id, parent) — public API, unchanged.
TabPostingConfigPanel(conn, tab_id, parent) — embeddable panel.
"""

from __future__ import annotations

import sqlite3
from typing import Optional

from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFrame, QGroupBox,
    QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

import src.storage.forum_posting as fp
from src.gui.widgets.forum_target_picker import ForumTargetPicker
from src.utils.templates import load_templates


class _DestinationRow(QFrame):
    """One (forum+target → template) row in the tab config list."""

    def __init__(self, conn, destination: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._dest_id: Optional[int] = destination.get("id") if destination else None
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._build(destination or {})

    def _build(self, dest: dict):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)

        self._picker = ForumTargetPicker(self._conn)
        if dest.get("forum_fk") and dest.get("target_id"):
            self._picker.set_targets([{
                "forum_fk": dest["forum_fk"],
                "forum_name": dest.get("forum_name", ""),
                "target_id": dest["target_id"],
                "kind": dest["kind"],
                "name": dest.get("target_name") or dest.get("target_id", ""),
            }])
        layout.addWidget(self._picker, 1)

        self._template_combo = QComboBox()
        self._template_combo.setMinimumWidth(140)
        for name in load_templates().keys():
            self._template_combo.addItem(name, name)
        if dest.get("body_template_name"):
            idx = self._template_combo.findData(dest["body_template_name"])
            if idx >= 0:
                self._template_combo.setCurrentIndex(idx)
        layout.addWidget(self._template_combo)

        remove_btn = QPushButton("×")
        remove_btn.setFixedWidth(28)
        remove_btn.clicked.connect(self._request_remove)
        layout.addWidget(remove_btn)

    def _request_remove(self):
        parent = self.parent()
        while parent and not isinstance(parent, TabPostingConfigPanel):
            parent = parent.parent()
        if parent:
            parent._remove_destination_row(self)

    def get_target(self) -> Optional[dict]:
        targets = self._picker.get_targets()
        return targets[0] if targets else None

    def get_template(self) -> Optional[str]:
        return self._template_combo.currentData()

    @property
    def dest_id(self) -> Optional[int]:
        return self._dest_id


class TabPostingConfigPanel(QWidget):
    """Panel for configuring posting defaults for a tab."""

    def __init__(self, conn: sqlite3.Connection, tab_id: int, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._tab_id = tab_id
        self._dest_rows: list[_DestinationRow] = []
        self._build_ui()
        self._load()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setSpacing(8)

        outer.addWidget(QLabel(
            "Configure default posting destinations for all galleries in this tab. "
            "Galleries can add or override destinations individually in the composer."
        ))

        # Destinations list
        dest_group = QGroupBox("Default destinations")
        self._dest_layout = QVBoxLayout(dest_group)
        self._dest_layout.setSpacing(4)

        add_btn = QPushButton("+ Add destination")
        add_btn.clicked.connect(self._add_empty_row)
        self._dest_layout.addWidget(add_btn)
        outer.addWidget(dest_group)

        # Trigger settings
        trig_group = QGroupBox("Auto-posting")
        trig_layout = QHBoxLayout(trig_group)

        self._trigger_combo = QComboBox()
        self._trigger_combo.addItem("Manual only", "manual")
        self._trigger_combo.addItem("Auto when upload completes", "auto_on_upload")
        self._trigger_combo.addItem("Disabled", "none")
        trig_layout.addWidget(QLabel("Trigger:"))
        trig_layout.addWidget(self._trigger_combo, 1)

        self._enabled_check = QCheckBox("Enabled")
        self._enabled_check.setChecked(True)
        trig_layout.addWidget(self._enabled_check)
        outer.addWidget(trig_group)

    def _load(self):
        for dest in fp.list_tab_destinations(self._conn, self._tab_id):
            self._add_row(dest)
        settings = fp.get_tab_posting_settings_for_tab(self._conn, self._tab_id)
        if settings:
            idx = self._trigger_combo.findData(settings["trigger_mode"])
            if idx >= 0:
                self._trigger_combo.setCurrentIndex(idx)
            self._enabled_check.setChecked(bool(settings["enabled"]))

    def _add_row(self, dest: Optional[dict] = None):
        row = _DestinationRow(self._conn, dest, parent=self)
        self._dest_rows.append(row)
        # Insert before the "Add destination" button (last item in dest_layout)
        self._dest_layout.insertWidget(self._dest_layout.count() - 1, row)

    def _add_empty_row(self):
        self._add_row(None)

    def _remove_destination_row(self, row: _DestinationRow):
        if row in self._dest_rows:
            self._dest_rows.remove(row)
        self._dest_layout.removeWidget(row)
        row.deleteLater()

    def save(self) -> bool:
        for row in self._dest_rows:
            if row.get_target() is None:
                QMessageBox.warning(self, "Save", "Each destination needs a target selected.")
                return False
            if not row.get_template():
                QMessageBox.warning(self, "Save", "Each destination needs a template selected.")
                return False

        fp.clear_tab_destinations(self._conn, self._tab_id)
        for row in self._dest_rows:
            t = row.get_target()
            fp.add_tab_destination(
                self._conn,
                tab_id=self._tab_id,
                forum_fk=t["forum_fk"],
                target_id=t["target_id"],
                kind=t["kind"],
                body_template_name=row.get_template(),
            )

        fp.set_tab_posting_settings(
            self._conn,
            tab_id=self._tab_id,
            trigger_mode=self._trigger_combo.currentData() or "manual",
            enabled=self._enabled_check.isChecked(),
        )
        return True


class TabPostingConfigDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, tab_id: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tab Posting Defaults")
        self.resize(580, 420)
        self.panel = TabPostingConfigPanel(conn, tab_id, self)
        layout = QVBoxLayout(self)
        layout.addWidget(self.panel)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
        )
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

    def _accept(self):
        if self.panel.save():
            self.accept()
