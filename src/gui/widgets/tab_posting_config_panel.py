"""Tab Posting Config panel + dialog wrapper.

Supports two modes:
* Tab mode (``tab_id``): edits the row in ``tab_posting_config`` that
  says "posts generated from this BBDrop tab go to forum X, target Y".
* Override mode (``gallery_id``): edits the per-gallery override row.
  "(Inherit from tab)" picks keep the tab value; leaving a target empty
  means inherit.

The panel uses a Template dropdown sourced from ``load_templates()``
(the same list as the main window's quick-settings combo). Template
files may contain an optional ``#POSTTITLE:`` directive which becomes
the post title — no separate Title template field is needed.

Target selection goes through a library of ``forum_targets`` rows. A
``+`` button next to the Target combo prompts for a pasted URL, which
the forum client parses into ``(kind, target_id)`` before upserting
into the library. The CRUD UI for targets lives in Settings → Forums.

Spec: docs/superpowers/specs/2026-04-20-forum-posting-design.md §7.2.
"""

from __future__ import annotations

import sqlite3
from typing import Optional

from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMessageBox, QPushButton, QToolButton, QVBoxLayout, QWidget,
)

from src.gui.widgets.info_button import InfoButton
from src.network.forum.factory import create_forum_client
from src.network.forum.session_store import SessionStore
from src.storage import forum_posting as fp
from src.utils.templates import load_templates


# Sentinels used as combo itemData. ``None`` = "(Add new…)" action,
# ``_INHERIT`` = "(Inherit from tab)" in override mode. Real target rows
# carry a dict.
_ADD_NEW = "__add_new__"
_INHERIT = "__inherit__"


class TabPostingConfigPanel(QWidget):
    """Embeddable panel used by both the tab-level config dialog and
    the per-gallery override dialog."""

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
        self._populate_templates()
        self._reload_targets_for_selected_forum()
        self._load_existing()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setSpacing(8)
        if self._override_mode:
            outer.addWidget(QLabel(
                "Override per-gallery posting settings. "
                "'(Inherit from tab)' picks fall back to the tab's config.",
            ))
        else:
            outer.addWidget(QLabel(
                "Configure posting for this tab. "
                "Leave Enabled unchecked to disable.",
            ))

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # Forum
        self.forum_combo = QComboBox()
        self.forum_combo.currentIndexChanged.connect(
            self._on_forum_changed,
        )
        form.addRow("Forum", self.forum_combo)

        # Target (combo + "+" button for paste-URL)
        self.target_combo = QComboBox()
        self.target_combo.currentIndexChanged.connect(
            self._on_target_changed,
        )
        self._target_add_btn = QToolButton()
        self._target_add_btn.setText("+")
        self._target_add_btn.setToolTip(
            "Add a subforum or thread from a URL"
        )
        self._target_add_btn.clicked.connect(self._on_add_target)
        target_row = QWidget()
        trl = QHBoxLayout(target_row)
        trl.setContentsMargins(0, 0, 0, 0)
        trl.setSpacing(4)
        trl.addWidget(self.target_combo, 1)
        trl.addWidget(self._target_add_btn)
        form.addRow(
            self._label_with_info(
                "Target",
                "Subforum or thread to post to. The picker is sourced "
                "from the forum's target library (Settings → Forums). "
                "Click <b>+</b> to add a new one by pasting its URL.",
            ),
            target_row,
        )

        # Template (single dropdown)
        self.template_combo = QComboBox()
        form.addRow(
            self._label_with_info(
                "Template",
                "BBCode template used to render the post body. Templates "
                "live in your central store's <code>templates/</code> "
                "folder. If the template's first line is "
                "<code>#POSTTITLE: …</code>, that line becomes the post "
                "title when creating a new thread — no separate title "
                "template is needed.",
            ),
            self.template_combo,
        )

        # Trigger
        self.trigger_combo = QComboBox()
        self.trigger_combo.addItem("Manual only", "manual")
        self.trigger_combo.addItem("Auto when upload completes", "auto_on_upload")
        form.addRow(
            self._label_with_info(
                "Trigger",
                "When BBDrop should post automatically. "
                "<b>Manual only</b>: nothing happens until you click "
                "Post manually. "
                "<b>Auto when upload completes</b>: every gallery under "
                "this tab is queued for posting as soon as its upload "
                "finishes.",
            ),
            self.trigger_combo,
        )

        # Update mode
        self.update_mode_combo = QComboBox()
        for v, label in (
            ("whole", "Whole-body replace"),
            ("surgical", "Surgical link swap"),
            ("whole_then_surgical", "Whole, fall back to surgical"),
        ):
            self.update_mode_combo.addItem(label, v)
        form.addRow(
            self._label_with_info(
                "Update mode",
                "How BBDrop edits an existing post when it's marked "
                "stale.<br>"
                "<b>Whole-body replace</b>: re-renders the entire body "
                "from the template. Safest when you haven't edited the "
                "post on the site.<br>"
                "<b>Surgical link swap</b>: finds and replaces just the "
                "changed links, leaving the surrounding text untouched. "
                "Use when you've manually edited the post on the forum.<br>"
                "<b>Whole, fall back to surgical</b>: try whole-body "
                "replace; if BBDrop detects manual edits it can't "
                "preserve, downgrade to surgical.",
            ),
            self.update_mode_combo,
        )

        # Manual edit handling
        self.manual_edit_combo = QComboBox()
        for v, label in (
            ("skip_alert", "Skip and alert"),
            ("overwrite", "Overwrite anyway"),
            ("surgical", "Surgical only"),
        ):
            self.manual_edit_combo.addItem(label, v)
        form.addRow(
            self._label_with_info(
                "On manual edits",
                "What to do when BBDrop detects the post was edited on "
                "the site since its last sync.<br>"
                "<b>Skip and alert</b>: don't update; show a warning.<br>"
                "<b>Overwrite anyway</b>: force the new body in, "
                "discarding your edits.<br>"
                "<b>Surgical only</b>: only swap the changed links, "
                "leaving your text in place.",
            ),
            self.manual_edit_combo,
        )

        outer.addLayout(form)

        # Stale triggers
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
        st_layout.addWidget(InfoButton(
            "<b>Stale triggers</b><br>"
            "Events that flip existing posts to <i>stale</i>, which "
            "queues them for re-posting according to the update mode. "
            "Check only the changes that should propagate to the forum."
        ))
        st_box.setLayout(st_layout)
        outer.addWidget(st_box)

        # Enabled
        enabled_row = QHBoxLayout()
        self.enabled_check = QCheckBox(
            "Enabled (posting active for this tab)",
        )
        enabled_row.addWidget(self.enabled_check)
        enabled_row.addWidget(InfoButton(
            "<b>Enabled</b><br>"
            "Master switch. Unchecking stops BBDrop from queuing any "
            "new posts for this tab — existing posts are untouched."
        ))
        enabled_row.addStretch()
        outer.addLayout(enabled_row)
        outer.addStretch()

        if self._override_mode:
            # 'enabled' is intentionally not overrideable in v1 — too
            # easy to accidentally disable a whole tab from a single
            # gallery.
            self.enabled_check.hide()
            for combo in (
                self.trigger_combo, self.update_mode_combo,
                self.manual_edit_combo,
            ):
                combo.insertItem(0, "(Inherit from tab)", None)
                combo.setCurrentIndex(0)

    @staticmethod
    def _label_with_info(text: str, html: str) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(QLabel(text))
        lay.addWidget(InfoButton(html))
        lay.addStretch()
        return w

    # ------------------------------------------------------------------
    # Populate combos
    # ------------------------------------------------------------------

    def _populate_forums(self):
        self.forum_combo.blockSignals(True)
        self.forum_combo.clear()
        if self._override_mode:
            self.forum_combo.addItem("(Inherit from tab)", _INHERIT)
        for f in fp.list_forums(self._conn, enabled_only=False):
            self.forum_combo.addItem(f["name"], f["id"])
        self.forum_combo.blockSignals(False)

    def _populate_templates(self):
        self.template_combo.blockSignals(True)
        self.template_combo.clear()
        if self._override_mode:
            self.template_combo.addItem("(Inherit from tab)", _INHERIT)
        for name in load_templates().keys():
            self.template_combo.addItem(name, name)
        self.template_combo.blockSignals(False)

    def _current_forum_fk(self) -> Optional[int]:
        data = self.forum_combo.currentData()
        return data if isinstance(data, int) else None

    def _populate_target_combo_from_forum(
        self, *, forum_fk: int,
        preserve_target_id: str | None = None,
        preserve_kind: str | None = None,
    ):
        """Fill the target combo from ``forum_fk``'s target library
        without touching the forum combo. Used when override mode
        inherits the forum but pins a target."""
        self.target_combo.blockSignals(True)
        self.target_combo.clear()
        if self._override_mode:
            self.target_combo.addItem("(Inherit from tab)", _INHERIT)
        selected_index = 0 if self._override_mode else -1
        rows = fp.list_targets(self._conn, forum_fk)
        for t in rows:
            label = f"{t['name']} ({t['kind']} #{t['target_id']})"
            data = {
                "kind": t["kind"], "target_id": t["target_id"],
                "pk": t["id"], "name": t["name"],
            }
            self.target_combo.addItem(label, data)
            if (preserve_target_id is not None
                    and str(t["target_id"]) == str(preserve_target_id)
                    and (preserve_kind is None or t["kind"] == preserve_kind)):
                selected_index = self.target_combo.count() - 1
        self.target_combo.addItem("+ Add new target from URL…", _ADD_NEW)
        if (preserve_target_id and selected_index <= 0
                and not self._override_mode):
            # Orphan entry so we don't silently switch targets.
            kind = preserve_kind or "thread"
            label = f"(unknown) {kind} #{preserve_target_id}"
            data = {
                "kind": kind, "target_id": str(preserve_target_id),
                "pk": None, "name": label,
            }
            idx = self.target_combo.count() - 1
            self.target_combo.insertItem(idx, label, data)
            selected_index = idx
        if selected_index >= 0:
            self.target_combo.setCurrentIndex(selected_index)
        self.target_combo.blockSignals(False)

    def _reload_targets_for_selected_forum(self, preserve_target_id: str | None = None,
                                            preserve_kind: str | None = None):
        """Rebuild the target combo for the currently-selected forum.

        If ``preserve_target_id`` is provided, we try to reselect it
        after rebuilding (used on initial load so the combo lands on
        the existing config's target)."""
        self.target_combo.blockSignals(True)
        self.target_combo.clear()
        if self._override_mode:
            self.target_combo.addItem("(Inherit from tab)", _INHERIT)
        fid = self._current_forum_fk()
        selected_index = 0 if self._override_mode else -1
        if fid is not None:
            rows = fp.list_targets(self._conn, fid)
            for t in rows:
                label = f"{t['name']} ({t['kind']} #{t['target_id']})"
                data = {
                    "kind": t["kind"], "target_id": t["target_id"],
                    "pk": t["id"], "name": t["name"],
                }
                self.target_combo.addItem(label, data)
                if (preserve_target_id is not None
                        and str(t["target_id"]) == str(preserve_target_id)
                        and (preserve_kind is None or t["kind"] == preserve_kind)):
                    selected_index = self.target_combo.count() - 1
        # Always offer the "Add new…" action at the end.
        self.target_combo.addItem("+ Add new target from URL…", _ADD_NEW)

        # If we couldn't find the preserve_target_id but it was
        # supplied, synthesize an orphan entry so existing configs
        # don't silently switch target on load.
        if (preserve_target_id and selected_index < 0
                and fid is not None):
            kind = preserve_kind or "thread"
            label = f"(unknown) {kind} #{preserve_target_id}"
            data = {
                "kind": kind, "target_id": str(preserve_target_id),
                "pk": None, "name": label,
            }
            # Insert before the Add-new sentinel.
            idx = self.target_combo.count() - 1
            self.target_combo.insertItem(idx, label, data)
            selected_index = idx

        if selected_index >= 0:
            self.target_combo.setCurrentIndex(selected_index)
        self.target_combo.blockSignals(False)

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def _on_forum_changed(self):
        self._reload_targets_for_selected_forum()

    def _on_target_changed(self):
        if self.target_combo.currentData() == _ADD_NEW:
            # Defer so the dropdown closes first; otherwise Qt may
            # reopen it when we pop the input dialog.
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, self._on_add_target)

    def _on_add_target(self):
        fid = self._current_forum_fk()
        if fid is None:
            QMessageBox.warning(
                self, "Add target",
                "Select a forum first (or save it in Forums settings).",
            )
            self._restore_target_to_valid()
            return
        forum = fp.get_forum(self._conn, fid)
        if not forum:
            self._restore_target_to_valid()
            return
        url, ok = QInputDialog.getText(
            self, "Add target",
            "Paste a subforum or thread URL:",
            QLineEdit.EchoMode.Normal, "",
        )
        if not ok or not (url or "").strip():
            self._restore_target_to_valid()
            return
        try:
            client = create_forum_client(
                forum["software_id"], base_url=forum["base_url"],
                session_store=SessionStore(),
            )
            ref = client.parse_target_url(url.strip())
        except Exception as e:
            QMessageBox.warning(self, "Add target", f"Error: {e}")
            self._restore_target_to_valid()
            return
        if ref is None:
            QMessageBox.warning(
                self, "Add target",
                "Couldn't recognise that URL. Paste a subforum link "
                "(e.g. /forumdisplay.php?f=…) or a thread link "
                "(e.g. /showthread.php?t=…).",
            )
            self._restore_target_to_valid()
            return
        name, ok = QInputDialog.getText(
            self, "Name this target",
            f"Name for this {ref.kind} (#{ref.target_id}):",
            QLineEdit.EchoMode.Normal,
            ref.name or f"{ref.kind} {ref.target_id}",
        )
        if not ok:
            self._restore_target_to_valid()
            return
        name = (name or "").strip() or ref.name or f"{ref.kind} {ref.target_id}"
        fp.upsert_target(
            self._conn, forum_fk=fid, name=name,
            kind=ref.kind, target_id=ref.target_id,
        )
        self._reload_targets_for_selected_forum(
            preserve_target_id=ref.target_id, preserve_kind=ref.kind,
        )

    def _restore_target_to_valid(self):
        """Move the target combo off the '+ Add new…' sentinel back to
        whatever concrete (or inherit) entry came before it."""
        count = self.target_combo.count()
        # Find the first non-sentinel entry.
        for i in range(count):
            data = self.target_combo.itemData(i)
            if data != _ADD_NEW:
                self.target_combo.blockSignals(True)
                self.target_combo.setCurrentIndex(i)
                self.target_combo.blockSignals(False)
                return

    # ------------------------------------------------------------------
    # Load existing config
    # ------------------------------------------------------------------

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
        # After forum selection, populate targets and reselect the saved
        # target id (map cfg.kind reply/new_thread → target.kind thread/subforum).
        target_kind = "subforum" if cfg["kind"] == "new_thread" else "thread"
        self._reload_targets_for_selected_forum(
            preserve_target_id=str(cfg["target_id"]),
            preserve_kind=target_kind,
        )
        # Template
        tpl_name = cfg["body_template_name"] or ""
        if tpl_name:
            tidx = self.template_combo.findData(tpl_name)
            if tidx < 0:
                # Template removed since last save — show it anyway so
                # the user notices; they can pick another.
                self.template_combo.addItem(f"{tpl_name} (missing)", tpl_name)
                tidx = self.template_combo.count() - 1
            self.template_combo.setCurrentIndex(tidx)
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
        if d.get("target_id"):
            kind = d.get("kind")
            target_kind = (
                "subforum" if kind == "new_thread" else "thread"
            ) if kind else None
            # If the override didn't also override forum_fk, the forum
            # combo is still on "(Inherit)" and targets won't populate.
            # Reload targets using the tab's forum_fk so the saved
            # target_id can still be found and highlighted — the combo
            # selection remains "(Inherit)" at the forum level, but the
            # target combo now contains concrete entries to match.
            if d.get("forum_fk") is None:
                tab_row = self._conn.execute(
                    "SELECT t.forum_fk FROM galleries g "
                    "JOIN tab_posting_config t ON t.tab_id = g.tab_id "
                    "WHERE g.id=?",
                    (self._gallery_id,),
                ).fetchone()
                if tab_row and tab_row[0]:
                    # Pull targets directly from DB so the forum combo
                    # stays on "(Inherit)" while the list is populated.
                    self._populate_target_combo_from_forum(
                        forum_fk=tab_row[0],
                        preserve_target_id=str(d["target_id"]),
                        preserve_kind=target_kind,
                    )
                    return
            self._reload_targets_for_selected_forum(
                preserve_target_id=str(d["target_id"]),
                preserve_kind=target_kind,
            )
        if d.get("body_template_name"):
            idx = self.template_combo.findData(d["body_template_name"])
            if idx < 0:
                self.template_combo.addItem(
                    f"{d['body_template_name']} (missing)",
                    d["body_template_name"],
                )
                idx = self.template_combo.count() - 1
            self.template_combo.setCurrentIndex(idx)
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

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _selected_target(self) -> Optional[dict]:
        """Return {'kind', 'target_id'} for the current target selection,
        or None for "(Inherit)" / "+ Add new…"."""
        data = self.target_combo.currentData()
        if data in (None, _INHERIT, _ADD_NEW):
            return None
        if isinstance(data, dict):
            return {"kind": data["kind"], "target_id": data["target_id"]}
        return None

    def save(self) -> bool:
        if self._override_mode:
            return self._save_override()
        forum_fk = self.forum_combo.currentData()
        if not isinstance(forum_fk, int):
            QMessageBox.warning(self, "Save", "Select a forum first.")
            return False
        target = self._selected_target()
        if not target:
            QMessageBox.warning(
                self, "Save",
                "Select a target (subforum or thread). Use + to add a "
                "new one.",
            )
            return False
        tpl = self.template_combo.currentData()
        if not isinstance(tpl, str) or not tpl:
            QMessageBox.warning(self, "Save", "Select a template.")
            return False
        kind = "new_thread" if target["kind"] == "subforum" else "reply"
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
            kind=kind, target_id=str(target["target_id"]),
            body_template_name=tpl,
            # Single-template model: the body template may carry a
            # #POSTTITLE: directive; the renderer resolves it when the
            # title_template_name field is left unset.
            title_template_name=None,
            trigger_mode=self.trigger_combo.currentData(),
            update_mode=self.update_mode_combo.currentData(),
            manual_edit_handling=self.manual_edit_combo.currentData(),
            stale_triggers=triggers,
            enabled=self.enabled_check.isChecked(),
        )
        return True

    def _save_override(self) -> bool:
        fields: dict = {}
        forum_data = self.forum_combo.currentData()
        if isinstance(forum_data, int):
            fields["forum_fk"] = forum_data
        target = self._selected_target()
        if target:
            fields["kind"] = (
                "new_thread" if target["kind"] == "subforum" else "reply"
            )
            fields["target_id"] = str(target["target_id"])
        tpl_data = self.template_combo.currentData()
        if isinstance(tpl_data, str) and tpl_data and tpl_data != _INHERIT:
            fields["body_template_name"] = tpl_data
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
        self.resize(560, 560)
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
