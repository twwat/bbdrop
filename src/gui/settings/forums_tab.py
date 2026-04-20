"""Forum Manager panel — embeddable widget used by both the standalone
ForumManagerDialog and the Settings dialog's Forums page.

Sections mirror other Settings tabs: a "Forums" group on the left with
the list of registered forums, and on the right two groups — "Forum
Details" (edit form + Test Login / Save) and "Targets" (per-forum
library of subforums / threads to post in). Targets are added by
pasting a forum URL; the per-software ``ForumClient.parse_target_url``
extracts ``(kind, target_id)`` and stores it under a friendly name.

Spec: docs/superpowers/specs/2026-04-20-forum-posting-design.md §7.1.
"""

from __future__ import annotations

import sqlite3
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from src.gui.dialogs.forum_credential_test_dialog import ForumCredentialTestDialog
from src.gui.widgets.info_button import InfoButton
from src.network.forum.factory import (
    create_forum_client, display_name_for, supported_software_ids,
)
from src.network.forum.session_store import SessionStore
from src.storage import forum_posting as fp
from src.utils.credentials import (
    decrypt_password, encrypt_password, get_credential,
    remove_credential, set_credential,
)


_FORUM_LIST_VISIBLE_ROWS = 11
_TARGET_LIST_VISIBLE_ROWS = 8


class ForumsPanel(QWidget):
    """Forum management UI.

    Layout: three QGroupBoxes (Forums list, Forum Details, Targets).
    Saves each forum immediately on Save-button click — does not
    participate in the Settings dialog's dirty/apply buffering.
    """

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._build_ui()
        self._reload_list()
        self._update_enabled_state()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        root.addWidget(self._build_forums_group(), 1)

        right = QVBoxLayout()
        right.setSpacing(10)
        right.addWidget(self._build_details_group())
        right.addWidget(self._build_targets_group())
        right.addStretch()
        root.addLayout(right, 2)

    def _build_forums_group(self) -> QGroupBox:
        box = QGroupBox("Forums")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        self.forum_list = QListWidget()
        self.forum_list.currentItemChanged.connect(self._on_select)
        # Cap visible height to ~11 rows so the list doesn't stretch to
        # the window. Actual row height depends on the font; sample one.
        row_h = self.forum_list.fontMetrics().height() + 6
        self.forum_list.setFixedHeight(
            row_h * _FORUM_LIST_VISIBLE_ROWS + 2 * self.forum_list.frameWidth()
        )
        layout.addWidget(self.forum_list)

        btn_row = QHBoxLayout()
        add = QPushButton("Add")
        add.clicked.connect(self._on_add)
        rem = QPushButton("Remove")
        rem.clicked.connect(self._on_remove)
        btn_row.addWidget(add)
        btn_row.addWidget(rem)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        return box

    def _build_details_group(self) -> QGroupBox:
        box = QGroupBox("Forum Details")
        outer = QVBoxLayout(box)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.name_input = QLineEdit()

        self.software_combo = QComboBox()
        for sid in supported_software_ids():
            self.software_combo.addItem(display_name_for(sid), sid)

        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText("https://example.com")

        self.username_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.cooldown_spin = QSpinBox()
        self.cooldown_spin.setRange(0, 3600)
        self.cooldown_spin.setSuffix(" s")
        self.cooldown_spin.setValue(30)

        form.addRow("Name", self.name_input)
        form.addRow(
            self._label_with_info(
                "Software",
                "The forum engine this site runs on. Determines how "
                "BBDrop logs in, posts, and parses URLs. Currently "
                "supported: vBulletin&nbsp;4.2.0.",
            ),
            self.software_combo,
        )
        form.addRow(
            self._label_with_info(
                "Base URL",
                "Root URL of the forum, without trailing slash or path. "
                "Example: <code>https://vipergirls.to</code>. All login "
                "and post requests are built relative to this URL.",
            ),
            self.base_url_input,
        )
        form.addRow("Username", self.username_input)
        form.addRow("Password", self.password_input)
        form.addRow(
            self._label_with_info(
                "Cooldown",
                "Minimum delay between posts to this forum, to respect "
                "the site's flood-control rules. BBDrop enforces this "
                "across all tabs posting to the same forum.",
            ),
            self.cooldown_spin,
        )
        outer.addLayout(form)

        action_row = QHBoxLayout()
        test_btn = QPushButton("Test Login")
        test_btn.clicked.connect(self._on_test)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._on_save)
        action_row.addWidget(test_btn)
        action_row.addStretch()
        action_row.addWidget(save_btn)
        outer.addLayout(action_row)

        self._details_group = box
        return box

    def _build_targets_group(self) -> QGroupBox:
        box = QGroupBox("Targets")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        hint_row = QHBoxLayout()
        hint_row.addWidget(QLabel(
            "Subforums and threads you post in. Paste a link to add."
        ))
        hint_row.addWidget(InfoButton(
            "<b>Targets library</b><br>"
            "Each forum keeps a named list of subforums and threads you "
            "post in, so you don't have to re-enter numeric IDs. Paste a "
            "forum or thread URL and BBDrop extracts the kind and id "
            "automatically. These targets appear in the <i>Tab posting "
            "config</i> and <i>Per-gallery override</i> pickers."
        ))
        hint_row.addStretch()
        layout.addLayout(hint_row)

        self.target_list = QListWidget()
        row_h = self.target_list.fontMetrics().height() + 6
        self.target_list.setFixedHeight(
            row_h * _TARGET_LIST_VISIBLE_ROWS + 2 * self.target_list.frameWidth()
        )
        layout.addWidget(self.target_list)

        paste_row = QHBoxLayout()
        self.target_url_input = QLineEdit()
        self.target_url_input.setPlaceholderText(
            "Paste a forum or thread URL..."
        )
        self.target_url_input.returnPressed.connect(self._on_add_target_from_url)
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._on_add_target_from_url)
        paste_row.addWidget(self.target_url_input, 1)
        paste_row.addWidget(add_btn)
        layout.addLayout(paste_row)

        bottom_row = QHBoxLayout()
        rename_btn = QPushButton("Rename…")
        rename_btn.clicked.connect(self._on_rename_target)
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._on_remove_target)
        bottom_row.addStretch()
        bottom_row.addWidget(rename_btn)
        bottom_row.addWidget(remove_btn)
        layout.addLayout(bottom_row)

        self._targets_group = box
        return box

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
    # Forums list
    # ------------------------------------------------------------------

    def _reload_list(self):
        self.forum_list.clear()
        for f in fp.list_forums(self._conn):
            item = QListWidgetItem(f["name"])
            item.setData(Qt.ItemDataRole.UserRole, f["id"])
            self.forum_list.addItem(item)

    def _selected_id(self) -> Optional[int]:
        item = self.forum_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_select(self):
        fid = self._selected_id()
        if fid is None:
            self._clear_form()
            self._reload_targets()
            self._update_enabled_state()
            return
        f = fp.get_forum(self._conn, fid)
        if not f:
            # Forum row disappeared (e.g. deleted by another panel or a
            # test harness). Don't leave stale form data on screen.
            self._clear_form()
            self._reload_targets()
            self._update_enabled_state()
            return
        self.name_input.setText(f["name"])
        idx = self.software_combo.findData(f["software_id"])
        if idx >= 0:
            self.software_combo.setCurrentIndex(idx)
        self.base_url_input.setText(f["base_url"])
        self.cooldown_spin.setValue(int(f["default_cooldown_s"]))
        # Best-effort credential load.
        enc = get_credential(f"forum_{fid}_credentials")
        self.username_input.clear()
        self.password_input.clear()
        if enc:
            try:
                decrypted = decrypt_password(enc) or ""
            except Exception:
                decrypted = ""
            if ":" in decrypted:
                u, p = decrypted.split(":", 1)
                self.username_input.setText(u)
                self.password_input.setText(p)
        self._reload_targets()
        self._update_enabled_state()

    def _clear_form(self):
        self.name_input.clear()
        self.base_url_input.clear()
        self.username_input.clear()
        self.password_input.clear()
        self.cooldown_spin.setValue(30)

    def _update_enabled_state(self):
        has_forum = self._selected_id() is not None
        # Targets group only makes sense once a forum exists so its
        # base_url / software_id can parse pasted URLs.
        self._targets_group.setEnabled(has_forum)

    def _on_add(self):
        self.forum_list.clearSelection()
        self._clear_form()
        self.name_input.setFocus()
        self._reload_targets()
        self._update_enabled_state()

    def _on_remove(self):
        fid = self._selected_id()
        if fid is None:
            return
        if QMessageBox.question(
            self, "Remove forum",
            "Remove this forum and all its posting configs?",
        ) != QMessageBox.StandardButton.Yes:
            return
        fp.delete_forum(self._conn, fid)
        try:
            remove_credential(f"forum_{fid}_credentials")
        except Exception:
            pass
        self._reload_list()
        self._clear_form()
        self._reload_targets()
        self._update_enabled_state()

    def _on_save(self):
        fid = self._save_forum(
            name=self.name_input.text().strip(),
            software_id=self.software_combo.currentData(),
            base_url=self.base_url_input.text().strip(),
            default_cooldown_s=self.cooldown_spin.value(),
            username=self.username_input.text(),
            password=self.password_input.text(),
        )
        if fid is not None:
            self._reload_list()
            for i in range(self.forum_list.count()):
                if self.forum_list.item(i).data(Qt.ItemDataRole.UserRole) == fid:
                    self.forum_list.setCurrentRow(i)
                    break

    def _save_forum(
        self, *, name, software_id, base_url, default_cooldown_s,
        username, password,
    ) -> Optional[int]:
        if not name or not base_url:
            QMessageBox.warning(
                self, "Missing fields",
                "Name and Base URL are required.",
            )
            return None
        fid = self._selected_id()
        if fid is None:
            fid = fp.insert_forum(
                self._conn, name=name, software_id=software_id,
                base_url=base_url,
                default_cooldown_s=default_cooldown_s,
            )
        else:
            fp.update_forum(
                self._conn, fid, name=name, software_id=software_id,
                base_url=base_url,
                default_cooldown_s=default_cooldown_s,
            )
        if username and password:
            enc = encrypt_password(f"{username}:{password}")
            set_credential(f"forum_{fid}_credentials", enc)
        return fid

    def _on_test(self):
        if not self.username_input.text() or not self.password_input.text():
            QMessageBox.warning(
                self, "Test login",
                "Enter username and password first.",
            )
            return
        base_url = self.base_url_input.text().strip()
        if not base_url:
            QMessageBox.warning(self, "Test login", "Enter Base URL first.")
            return
        dlg = ForumCredentialTestDialog(
            forum_name=self.name_input.text().strip() or "Forum",
            software_id=self.software_combo.currentData(),
            base_url=base_url,
            username=self.username_input.text(),
            password=self.password_input.text(),
            parent=self,
        )
        dlg.exec()

    # ------------------------------------------------------------------
    # Targets
    # ------------------------------------------------------------------

    def _reload_targets(self):
        self.target_list.clear()
        fid = self._selected_id()
        if fid is None:
            return
        for t in fp.list_targets(self._conn, fid):
            label = f"{t['name']} ({t['kind']} #{t['target_id']})"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, t["id"])
            self.target_list.addItem(item)

    def _selected_target_id(self) -> Optional[int]:
        item = self.target_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_add_target_from_url(self):
        fid = self._selected_id()
        if fid is None:
            QMessageBox.warning(
                self, "Add target",
                "Save the forum first, then add targets for it.",
            )
            return
        url = self.target_url_input.text().strip()
        if not url:
            return
        forum = fp.get_forum(self._conn, fid)
        if not forum:
            return
        try:
            client = create_forum_client(
                forum["software_id"], base_url=forum["base_url"],
                session_store=SessionStore(),
            )
        except Exception as e:
            QMessageBox.warning(self, "Add target", f"Forum client error: {e}")
            return
        ref = client.parse_target_url(url)
        if ref is None:
            QMessageBox.warning(
                self, "Add target",
                "Couldn't recognise that URL. Paste a subforum link "
                "(e.g. /forumdisplay.php?f=…) or a thread link "
                "(e.g. /showthread.php?t=…).",
            )
            return
        # Let the user confirm / edit the name before saving.
        name, ok = QInputDialog.getText(
            self, "Name this target",
            f"Name for this {ref.kind} (#{ref.target_id}):",
            QLineEdit.EchoMode.Normal, ref.name or f"{ref.kind} {ref.target_id}",
        )
        if not ok:
            return
        name = (name or "").strip() or ref.name or f"{ref.kind} {ref.target_id}"
        fp.upsert_target(
            self._conn, forum_fk=fid, name=name,
            kind=ref.kind, target_id=ref.target_id,
        )
        self.target_url_input.clear()
        self._reload_targets()

    def _on_remove_target(self):
        tid = self._selected_target_id()
        if tid is None:
            return
        fp.delete_target(self._conn, tid)
        self._reload_targets()

    def _on_rename_target(self):
        tid = self._selected_target_id()
        if tid is None:
            return
        row = fp.get_target(self._conn, tid)
        if not row:
            return
        name, ok = QInputDialog.getText(
            self, "Rename target",
            f"New name for this {row['kind']} (#{row['target_id']}):",
            QLineEdit.EchoMode.Normal, row["name"],
        )
        if not ok:
            return
        name = (name or "").strip()
        if not name:
            return
        fp.update_target(self._conn, tid, name=name)
        self._reload_targets()
