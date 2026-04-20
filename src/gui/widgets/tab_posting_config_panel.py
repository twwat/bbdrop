"""Tab Posting Config panel + dialog wrapper.

Spec: docs/superpowers/specs/2026-04-20-forum-posting-design.md §7.2.
"""

from __future__ import annotations

import sqlite3

from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QVBoxLayout, QWidget,
)

from src.storage import forum_posting as fp


class TabPostingConfigPanel(QWidget):
    """Embeddable panel. Use TabPostingConfigDialog for the modal wrapper.

    Two modes:
    - tab mode (pass tab_id): edits the tab's posting config row.
    - override mode (pass gallery_id): edits the per-gallery override row.
      Empty/(Inherit) fields fall back to the tab config.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        tab_id: int | None = None,
        parent=None,
        *,
        gallery_id: int | None = None,
    ):
        super().__init__(parent)
        if (tab_id is None) == (gallery_id is None):
            raise ValueError("Pass exactly one of tab_id or gallery_id")
        self._conn = conn
        self._tab_id = tab_id
        self._gallery_id = gallery_id
        self._override_mode = gallery_id is not None
        self._build_ui()
        self._populate_forums()
        self._load_existing()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        if self._override_mode:
            outer.addWidget(QLabel(
                "Override per-gallery posting settings. "
                "Empty / '(Inherit)' fields fall back to the tab's config.",
            ))
        else:
            outer.addWidget(QLabel(
                "Configure posting for this tab. "
                "Leave Enabled unchecked to disable.",
            ))
        form = QFormLayout()
        self.forum_combo = QComboBox()
        self.kind_combo = QComboBox()
        self.kind_combo.addItem("Reply to thread", "reply")
        self.kind_combo.addItem("Create new thread", "new_thread")
        self.kind_combo.currentIndexChanged.connect(
            self._update_kind_visibility,
        )
        self.target_id_input = QLineEdit()
        self.target_label = QLabel("Thread ID")
        self.body_template_input = QLineEdit()
        self.title_template_input = QLineEdit()
        self.trigger_combo = QComboBox()
        self.trigger_combo.addItem("Manual only", "manual")
        self.trigger_combo.addItem("Auto when upload completes", "auto_on_upload")
        self.update_mode_combo = QComboBox()
        for v, label in (
            ("whole", "Whole-body replace"),
            ("surgical", "Surgical link swap"),
            ("whole_then_surgical", "Whole, fall back to surgical"),
        ):
            self.update_mode_combo.addItem(label, v)
        self.manual_edit_combo = QComboBox()
        for v, label in (
            ("skip_alert", "Skip and alert"),
            ("overwrite", "Overwrite anyway"),
            ("surgical", "Surgical only"),
        ):
            self.manual_edit_combo.addItem(label, v)
        form.addRow("Forum", self.forum_combo)
        form.addRow("Kind", self.kind_combo)
        form.addRow(self.target_label, self.target_id_input)
        form.addRow("Body template", self.body_template_input)
        form.addRow("Title template (new threads only)", self.title_template_input)
        form.addRow("Trigger", self.trigger_combo)
        form.addRow("Update mode", self.update_mode_combo)
        form.addRow("On manual edits", self.manual_edit_combo)
        outer.addLayout(form)
        st_box = QGroupBox("Mark posts stale when:")
        st_layout = QHBoxLayout()
        self.st_upload = QCheckBox("Upload finishes")
        self.st_template = QCheckBox("Template edited")
        self.st_link_format = QCheckBox("Link format changed")
        self.st_manual = QCheckBox("Manual re-render")
        for w in (
            self.st_upload, self.st_template,
            self.st_link_format, self.st_manual,
        ):
            st_layout.addWidget(w)
        st_box.setLayout(st_layout)
        outer.addWidget(st_box)
        self.enabled_check = QCheckBox(
            "Enabled (posting active for this tab)",
        )
        outer.addWidget(self.enabled_check)
        outer.addStretch()
        if self._override_mode:
            # 'enabled' is intentionally not overrideable in v1 — too easy to
            # accidentally disable a whole tab from a single gallery.
            self.enabled_check.hide()
            for combo in (
                self.kind_combo, self.trigger_combo,
                self.update_mode_combo, self.manual_edit_combo,
            ):
                combo.insertItem(0, "(Inherit from tab)", None)
                combo.setCurrentIndex(0)
        self._update_kind_visibility()

    def _populate_forums(self):
        self.forum_combo.clear()
        if self._override_mode:
            self.forum_combo.addItem("(Inherit from tab)", None)
        for f in fp.list_forums(self._conn, enabled_only=False):
            self.forum_combo.addItem(f["name"], f["id"])

    def _update_kind_visibility(self):
        kind = self.kind_combo.currentData()
        # In override mode, kind may be None (inherit) — keep prior label text
        # rather than mislabeling. Default to Reply behaviour.
        if kind == "new_thread":
            self.target_label.setText("Forum (subforum) ID")
            self.title_template_input.setEnabled(True)
        else:
            self.target_label.setText("Thread ID")
            self.title_template_input.setEnabled(False)

    def _load_existing(self):
        if self._override_mode:
            self._load_existing_override()
            return
        cfg = fp.get_tab_posting_config(self._conn, self._tab_id)
        if not cfg:
            self.enabled_check.setChecked(False)
            return
        idx = self.forum_combo.findData(cfg["forum_fk"])
        if idx >= 0:
            self.forum_combo.setCurrentIndex(idx)
        kidx = self.kind_combo.findData(cfg["kind"])
        if kidx >= 0:
            self.kind_combo.setCurrentIndex(kidx)
        self.target_id_input.setText(cfg["target_id"] or "")
        self.body_template_input.setText(cfg["body_template_name"] or "")
        self.title_template_input.setText(cfg.get("title_template_name") or "")
        tidx = self.trigger_combo.findData(cfg["trigger_mode"])
        if tidx >= 0:
            self.trigger_combo.setCurrentIndex(tidx)
        uidx = self.update_mode_combo.findData(cfg["update_mode"])
        if uidx >= 0:
            self.update_mode_combo.setCurrentIndex(uidx)
        midx = self.manual_edit_combo.findData(cfg["manual_edit_handling"])
        if midx >= 0:
            self.manual_edit_combo.setCurrentIndex(midx)
        st = set(cfg.get("stale_triggers", []) or [])
        self.st_upload.setChecked("upload" in st)
        self.st_template.setChecked("template_edit" in st)
        self.st_link_format.setChecked("link_format" in st)
        self.st_manual.setChecked("manual_rerender" in st)
        self.enabled_check.setChecked(bool(cfg.get("enabled")))
        self._update_kind_visibility()

    def _load_existing_override(self):
        import json
        row = self._conn.execute(
            "SELECT * FROM gallery_posting_override WHERE gallery_fk=?",
            (self._gallery_id,),
        ).fetchone()
        if not row:
            return
        d = dict(row)
        if d.get("forum_fk") is not None:
            idx = self.forum_combo.findData(d["forum_fk"])
            if idx >= 0:
                self.forum_combo.setCurrentIndex(idx)
        if d.get("kind"):
            idx = self.kind_combo.findData(d["kind"])
            if idx >= 0:
                self.kind_combo.setCurrentIndex(idx)
        if d.get("target_id"):
            self.target_id_input.setText(d["target_id"])
        if d.get("body_template_name"):
            self.body_template_input.setText(d["body_template_name"])
        if d.get("title_template_name"):
            self.title_template_input.setText(d["title_template_name"])
        if d.get("trigger_mode"):
            idx = self.trigger_combo.findData(d["trigger_mode"])
            if idx >= 0:
                self.trigger_combo.setCurrentIndex(idx)
        if d.get("update_mode"):
            idx = self.update_mode_combo.findData(d["update_mode"])
            if idx >= 0:
                self.update_mode_combo.setCurrentIndex(idx)
        if d.get("manual_edit_handling"):
            idx = self.manual_edit_combo.findData(d["manual_edit_handling"])
            if idx >= 0:
                self.manual_edit_combo.setCurrentIndex(idx)
        if d.get("stale_triggers_json"):
            st = set(json.loads(d["stale_triggers_json"]))
            self.st_upload.setChecked("upload" in st)
            self.st_template.setChecked("template_edit" in st)
            self.st_link_format.setChecked("link_format" in st)
            self.st_manual.setChecked("manual_rerender" in st)
        self._update_kind_visibility()

    def save(self) -> bool:
        if self._override_mode:
            return self._save_override()
        forum_fk = self.forum_combo.currentData()
        if forum_fk is None:
            QMessageBox.warning(self, "Save", "Select a forum first.")
            return False
        if not self.target_id_input.text().strip():
            QMessageBox.warning(self, "Save", "Target ID is required.")
            return False
        if not self.body_template_input.text().strip():
            QMessageBox.warning(self, "Save", "Body template name is required.")
            return False
        triggers = []
        if self.st_upload.isChecked():
            triggers.append("upload")
        if self.st_template.isChecked():
            triggers.append("template_edit")
        if self.st_link_format.isChecked():
            triggers.append("link_format")
        if self.st_manual.isChecked():
            triggers.append("manual_rerender")
        fp.set_tab_posting_config(
            self._conn, tab_id=self._tab_id, forum_fk=forum_fk,
            kind=self.kind_combo.currentData(),
            target_id=self.target_id_input.text().strip(),
            body_template_name=self.body_template_input.text().strip(),
            title_template_name=(
                self.title_template_input.text().strip() or None
            ),
            trigger_mode=self.trigger_combo.currentData(),
            update_mode=self.update_mode_combo.currentData(),
            manual_edit_handling=self.manual_edit_combo.currentData(),
            stale_triggers=triggers,
            enabled=self.enabled_check.isChecked(),
        )
        return True

    def _save_override(self) -> bool:
        fields: dict = {}
        if self.forum_combo.currentData() is not None:
            fields["forum_fk"] = self.forum_combo.currentData()
        if self.kind_combo.currentData() is not None:
            fields["kind"] = self.kind_combo.currentData()
        target = self.target_id_input.text().strip()
        if target:
            fields["target_id"] = target
        body_tpl = self.body_template_input.text().strip()
        if body_tpl:
            fields["body_template_name"] = body_tpl
        title_tpl = self.title_template_input.text().strip()
        if title_tpl:
            fields["title_template_name"] = title_tpl
        if self.trigger_combo.currentData() is not None:
            fields["trigger_mode"] = self.trigger_combo.currentData()
        if self.update_mode_combo.currentData() is not None:
            fields["update_mode"] = self.update_mode_combo.currentData()
        if self.manual_edit_combo.currentData() is not None:
            fields["manual_edit_handling"] = self.manual_edit_combo.currentData()
        triggers: list = []
        if self.st_upload.isChecked():
            triggers.append("upload")
        if self.st_template.isChecked():
            triggers.append("template_edit")
        if self.st_link_format.isChecked():
            triggers.append("link_format")
        if self.st_manual.isChecked():
            triggers.append("manual_rerender")
        if triggers:
            fields["stale_triggers"] = triggers
        if not fields:
            fp.clear_gallery_override(self._conn, gallery_fk=self._gallery_id)
        else:
            fp.set_gallery_override(
                self._conn, gallery_fk=self._gallery_id, **fields,
            )
        return True


class TabPostingConfigDialog(QDialog):
    def __init__(self, conn, tab_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tab Posting Configuration")
        self.resize(560, 540)
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
