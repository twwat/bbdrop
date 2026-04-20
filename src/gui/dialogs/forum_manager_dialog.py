"""Forum Manager dialog: list, add, edit, remove forums + Test Login.

Spec: docs/superpowers/specs/2026-04-20-forum-posting-design.md §7.1.
"""

from __future__ import annotations

import sqlite3
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QHBoxLayout, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QSpinBox, QVBoxLayout,
)

from src.gui.dialogs.forum_credential_test_dialog import ForumCredentialTestDialog
from src.network.forum.factory import display_name_for, supported_software_ids
from src.storage import forum_posting as fp
from src.utils.credentials import (
    decrypt_password, encrypt_password, get_credential,
    remove_credential, set_credential,
)


class ForumManagerDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Forum Manager")
        self.resize(720, 480)
        self._conn = conn
        self._build_ui()
        self._reload_list()

    def _build_ui(self):
        outer = QHBoxLayout(self)
        # Left: list + add/remove
        left = QVBoxLayout()
        self.forum_list = QListWidget()
        self.forum_list.currentItemChanged.connect(self._on_select)
        left.addWidget(self.forum_list)
        btns = QHBoxLayout()
        add = QPushButton("Add")
        add.clicked.connect(self._on_add)
        rem = QPushButton("Remove")
        rem.clicked.connect(self._on_remove)
        btns.addWidget(add)
        btns.addWidget(rem)
        left.addLayout(btns)
        outer.addLayout(left, 1)
        # Right: edit form
        form = QFormLayout()
        self.name_input = QLineEdit()
        self.software_combo = QComboBox()
        for sid in supported_software_ids():
            self.software_combo.addItem(display_name_for(sid), sid)
        self.base_url_input = QLineEdit()
        self.username_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.cooldown_spin = QSpinBox()
        self.cooldown_spin.setRange(0, 3600)
        self.cooldown_spin.setValue(30)
        form.addRow("Name", self.name_input)
        form.addRow("Software", self.software_combo)
        form.addRow("Base URL", self.base_url_input)
        form.addRow("Username", self.username_input)
        form.addRow("Password", self.password_input)
        form.addRow("Cooldown (sec)", self.cooldown_spin)
        right = QVBoxLayout()
        right.addLayout(form)
        action_row = QHBoxLayout()
        test = QPushButton("Test Login")
        test.clicked.connect(self._on_test)
        save = QPushButton("Save")
        save.clicked.connect(self._on_save)
        action_row.addWidget(test)
        action_row.addStretch()
        action_row.addWidget(save)
        right.addLayout(action_row)
        right.addStretch()
        outer.addLayout(right, 2)

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
            return
        f = fp.get_forum(self._conn, fid)
        if not f:
            return
        self.name_input.setText(f["name"])
        idx = self.software_combo.findData(f["software_id"])
        if idx >= 0:
            self.software_combo.setCurrentIndex(idx)
        self.base_url_input.setText(f["base_url"])
        self.cooldown_spin.setValue(int(f["default_cooldown_s"]))
        # Best-effort credential load
        enc = get_credential(f"forum_{fid}_credentials")
        if enc:
            try:
                decrypted = decrypt_password(enc) or ""
            except Exception:
                decrypted = ""
            if ":" in decrypted:
                u, p = decrypted.split(":", 1)
                self.username_input.setText(u)
                self.password_input.setText(p)

    def _clear_form(self):
        self.name_input.clear()
        self.base_url_input.clear()
        self.username_input.clear()
        self.password_input.clear()
        self.cooldown_spin.setValue(30)

    def _on_add(self):
        self.forum_list.clearSelection()
        self._clear_form()
        self.name_input.setFocus()

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
