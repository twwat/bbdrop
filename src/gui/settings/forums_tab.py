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

import os
import re
import sqlite3
import threading
from typing import Optional
from urllib.parse import urlparse

from PyQt6.QtCore import QObject, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFormLayout, QGroupBox, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QSpinBox, QStyle,
    QStyledItemDelegate, QVBoxLayout, QWidget,
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


_FORUMS_MIN_ROWS = 2
_FORUMS_MAX_ROWS = 10
_TARGETS_MIN_ROWS = 3
_TARGETS_MAX_ROWS = 20

# Delegate reads each target's kind + numeric id via these custom roles.
_TARGET_KIND_ROLE = Qt.ItemDataRole.UserRole + 1
_TARGET_TID_ROLE = Qt.ItemDataRole.UserRole + 2

# Matches any http(s) URL inside pasted text, regardless of delimiters.
_URL_RE = re.compile(r"https?://\S+")


class _FaviconFetcher(QObject):
    """Fetches a forum's ``/favicon.ico`` in a background thread and emits
    ``favicon_ready(forum_id, path)`` when the file lands in the on-disk
    cache. Failures are swallowed — the icon just stays blank."""

    favicon_ready = pyqtSignal(int, str)

    def __init__(self):
        super().__init__()
        self._cache_dir = os.path.join(
            os.path.expanduser("~"), ".bbdrop", "favicons",
        )
        try:
            os.makedirs(self._cache_dir, exist_ok=True)
        except OSError:
            pass
        self._in_flight: set[int] = set()
        self._lock = threading.Lock()

    def cached_path(self, forum_id: int) -> Optional[str]:
        path = os.path.join(self._cache_dir, f"forum_{forum_id}.ico")
        return path if os.path.isfile(path) else None

    def fetch(self, forum_id: int, base_url: str) -> None:
        """Kick off a background download if not cached and not already
        in flight. No-op on empty URLs / thread-lock contention."""
        if not base_url:
            return
        if self.cached_path(forum_id):
            return
        with self._lock:
            if forum_id in self._in_flight:
                return
            self._in_flight.add(forum_id)
        threading.Thread(
            target=self._worker, args=(forum_id, base_url), daemon=True,
        ).start()

    def _worker(self, forum_id: int, base_url: str):
        try:
            import urllib.request
            parsed = urlparse(base_url)
            if not parsed.scheme or not parsed.netloc:
                return
            url = f"{parsed.scheme}://{parsed.netloc}/favicon.ico"
            req = urllib.request.Request(
                url, headers={"User-Agent": "BBDrop/favicon-fetcher"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = resp.read()
            if not data or len(data) < 20:
                return
            dest = os.path.join(
                self._cache_dir, f"forum_{forum_id}.ico",
            )
            tmp = dest + ".tmp"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, dest)
            self.favicon_ready.emit(forum_id, dest)
        except Exception:
            # Silent — favicon download is best-effort.
            pass
        finally:
            with self._lock:
                self._in_flight.discard(forum_id)


# Shared per-process fetcher — favicons are forum-identity data, not
# panel-scoped, so a single cache keeps the state tidy across reopens.
_favicon_fetcher: Optional[_FaviconFetcher] = None


def _get_favicon_fetcher() -> _FaviconFetcher:
    global _favicon_fetcher
    if _favicon_fetcher is None:
        _favicon_fetcher = _FaviconFetcher()
    return _favicon_fetcher


class _TargetKindDelegate(QStyledItemDelegate):
    """Paints a small colored pill at the row's right edge showing
    ``Subforum #304`` or ``Thread #12345``. Slimmer than the row so the
    row height doesn't grow; color alone tells kinds apart at a glance."""

    _PILL_BG = {
        "subforum": "#2f6aa1",   # blue
        "thread":   "#3d874a",   # green
    }
    _PILL_LABEL = {"subforum": "Subforum", "thread": "Thread"}
    _PAD_H = 6
    _GAP = 8
    _RADIUS = 3

    def paint(self, painter, option, index):
        self.initStyleOption(option, index)
        widget = option.widget
        style = widget.style() if widget else QApplication.style()

        # Let the style paint selection/hover background; suppress the
        # default text so we can draw the name + trailing pill ourselves.
        option.text = ""
        style.drawControl(
            QStyle.ControlElement.CE_ItemViewItem, option, painter, widget,
        )

        kind = index.data(_TARGET_KIND_ROLE) or ""
        tid = index.data(_TARGET_TID_ROLE)
        kind_label = self._PILL_LABEL.get(kind, "")
        pill_text = (
            f"{kind_label} #{tid}" if kind_label and tid else kind_label
        )

        painter.save()
        rect = option.rect.adjusted(6, 0, -6, 0)
        name_right = rect.right()

        if pill_text:
            pill_font = QFont(option.font)
            pt = pill_font.pointSizeF()
            if pt > 0:
                pill_font.setPointSizeF(pt * 0.85)
            painter.setFont(pill_font)
            fm = painter.fontMetrics()
            pill_w = fm.horizontalAdvance(pill_text) + 2 * self._PAD_H
            pill_h = fm.height()
            # Keep the pill shorter than the row so it can't push row
            # height up; clamp to row height just in case.
            pill_h = min(pill_h, rect.height() - 4)
            pill_y = rect.y() + (rect.height() - pill_h) // 2
            pill_rect = QRect(
                rect.right() - pill_w, pill_y, pill_w, pill_h,
            )

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self._PILL_BG.get(kind, "#666")))
            painter.drawRoundedRect(pill_rect, self._RADIUS, self._RADIUS)
            painter.setPen(QColor("white"))
            painter.drawText(
                pill_rect, Qt.AlignmentFlag.AlignCenter, pill_text,
            )
            name_right = pill_rect.left() - self._GAP

        painter.setFont(option.font)
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(option.palette.highlightedText().color())
        else:
            painter.setPen(option.palette.text().color())
        text_rect = QRect(
            rect.x(), rect.y(),
            max(0, name_right - rect.x()), rect.height(),
        )
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        fm = painter.fontMetrics()
        elided = fm.elidedText(text, Qt.TextElideMode.ElideRight, text_rect.width())
        painter.drawText(
            text_rect,
            int(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            ),
            elided,
        )
        painter.restore()


class ForumsPanel(QWidget):
    """Forum management UI.

    Layout: three QGroupBoxes (Forums list, Forum Details, Targets).
    Saves each forum immediately on Save-button click — does not
    participate in the Settings dialog's dirty/apply buffering.
    """

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._creating_new = False
        self._favicons = _get_favicon_fetcher()
        self._favicons.favicon_ready.connect(
            self._on_favicon_ready, Qt.ConnectionType.QueuedConnection,
        )
        self._build_ui()
        self._reload_list()
        self._restore_last_selection()
        self._update_enabled_state()

    def _main_window(self):
        """Walk up to the main window so we can read/write the
        session-only ``_last_forum_id`` attribute."""
        p = self.parent()
        while p is not None:
            if hasattr(p, '_forum_db_conn'):
                return p
            parent_fn = getattr(p, 'parent', None)
            p = parent_fn() if callable(parent_fn) else None
        return None

    def _restore_last_selection(self):
        mw = self._main_window()
        last_id = getattr(mw, '_last_forum_id', None) if mw else None
        if last_id is not None:
            for i in range(self.forum_list.count()):
                item = self.forum_list.item(i)
                if item.data(Qt.ItemDataRole.UserRole) == last_id:
                    self.forum_list.setCurrentRow(i)
                    return
        # No remembered pick — default to the first row so Details and
        # Targets are visible immediately. Otherwise the first click on
        # the only forum pops both groups in and the layout jumps.
        if self.forum_list.count() > 0:
            self.forum_list.setCurrentRow(0)

    def _remember_current_selection(self, fid):
        mw = self._main_window()
        if mw is not None:
            mw._last_forum_id = fid

    @staticmethod
    def _fit_list_to_content(
        lw: QListWidget, min_rows: int, max_rows: int,
    ) -> None:
        """Size ``lw`` so it shows exactly ``count`` rows when small and
        caps at ``max_rows`` when long (scrollbar kicks in past that).
        A ``min_rows`` floor keeps buttons from overlapping when a list
        is empty or near-empty."""
        row_h = lw.sizeHintForRow(0) if lw.count() > 0 else 0
        if row_h <= 0:
            row_h = lw.fontMetrics().height() + 6
        frame = 2 * lw.frameWidth()
        rows = max(min_rows, min(lw.count(), max_rows))
        lw.setFixedHeight(row_h * rows + frame + 2)

    def _on_favicon_ready(self, forum_id: int, path: str):
        """Delegate-level repaint isn't enough — set the item icon so
        the list's own style renders it."""
        if not os.path.isfile(path):
            return
        icon = QIcon(path)
        for i in range(self.forum_list.count()):
            item = self.forum_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == forum_id:
                item.setIcon(icon)
                break

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # Left column: Forums list on top, Forum Details under it.
        left = QVBoxLayout()
        left.setSpacing(10)
        left.addWidget(self._build_forums_group())
        left.addWidget(self._build_details_group())
        left.addStretch()
        root.addLayout(left, 3)

        # Right column: Targets runs full height (it's the tallest
        # content and benefits from room to grow).
        right = QVBoxLayout()
        right.setSpacing(10)
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
        # Height is fit-to-content (2..10 rows); applied after each reload
        # so the groupbox never shows empty space below a short list or
        # squeezes the buttons on top of a long one.
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
        self.target_list.setItemDelegate(_TargetKindDelegate(self.target_list))
        # Height fit-to-content (3..20 rows); applied on reload.
        layout.addWidget(self.target_list)

        paste_row = QHBoxLayout()
        self.target_url_input = QLineEdit()
        self.target_url_input.setPlaceholderText(
            "Paste one URL, or several at once (any separator) to add in bulk."
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
            cached = self._favicons.cached_path(f["id"])
            if cached:
                item.setIcon(QIcon(cached))
            else:
                self._favicons.fetch(f["id"], f["base_url"])
            self.forum_list.addItem(item)
        self._fit_list_to_content(
            self.forum_list, _FORUMS_MIN_ROWS, _FORUMS_MAX_ROWS,
        )

    def _selected_id(self) -> Optional[int]:
        item = self.forum_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_select(self):
        fid = self._selected_id()
        self._remember_current_selection(fid)
        if fid is None:
            self._clear_form()
            self._reload_targets()
            self._update_enabled_state()
            return
        # Picking an existing forum cancels any in-progress "new" flow.
        self._creating_new = False
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
        if self.software_combo.count() > 0:
            self.software_combo.setCurrentIndex(0)

    def _update_enabled_state(self):
        has_forum = self._selected_id() is not None
        # Hide the edit form until the user either picks an existing forum
        # or hits "Add" — editing nothing is confusing.
        show_form = has_forum or self._creating_new
        self._details_group.setVisible(show_form)
        self._targets_group.setVisible(has_forum)

    def _on_add(self):
        self._creating_new = True
        # setCurrentRow(-1) actually clears currentItem (unlike
        # clearSelection, which leaves currentItem stale and suppresses
        # currentItemChanged on a follow-up click to the same forum).
        self.forum_list.setCurrentRow(-1)
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
        self._creating_new = False
        self._reload_list()
        # If any forums remain, auto-select the first so Details/Targets
        # stay visible — keeps the panel from collapsing and re-expanding
        # on the next click.
        if self.forum_list.count() > 0:
            self.forum_list.setCurrentRow(0)
        else:
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
            self._creating_new = False
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
        if fid is not None:
            for t in fp.list_targets(self._conn, fid):
                # Pill delegate renders "Subforum #id" / "Thread #id" at
                # the right edge; display text is just the friendly name.
                item = QListWidgetItem(t["name"])
                item.setData(Qt.ItemDataRole.UserRole, t["id"])
                item.setData(_TARGET_KIND_ROLE, t["kind"])
                item.setData(_TARGET_TID_ROLE, t["target_id"])
                self.target_list.addItem(item)
        self._fit_list_to_content(
            self.target_list, _TARGETS_MIN_ROWS, _TARGETS_MAX_ROWS,
        )

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
        raw = self.target_url_input.text().strip()
        if not raw:
            return
        # Extract every http(s) URL from the pasted text regardless of
        # delimiters (whitespace, commas, quotes, etc.). Trim any trailing
        # punctuation the regex greedily caught.
        urls = [u.rstrip(",.;'\"") for u in _URL_RE.findall(raw)]
        if not urls:
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

        if len(urls) == 1:
            # Single URL — keep the confirm-name-before-save flow.
            if not self._add_single_target(fid, client, urls[0]):
                return
        else:
            # Bulk — auto-name each, show a summary at the end.
            added, skipped = self._add_bulk_targets(fid, client, urls)
            msg = f"Added {added} target(s)."
            if skipped:
                preview = "\n".join(skipped[:10])
                extra = (
                    f"\n… and {len(skipped) - 10} more"
                    if len(skipped) > 10 else ""
                )
                msg += (
                    f"\nSkipped {len(skipped)} unrecognised URL(s):\n"
                    f"{preview}{extra}"
                )
            QMessageBox.information(self, "Add targets", msg)

        self.target_url_input.clear()
        self._reload_targets()

    def _add_single_target(self, fid: int, client, url: str) -> bool:
        ref = client.parse_target_url(url)
        if ref is None:
            QMessageBox.warning(
                self, "Add target",
                "Couldn't recognise that URL. Paste a subforum link "
                "(e.g. /forumdisplay.php?f=…) or a thread link "
                "(e.g. /showthread.php?t=…).",
            )
            return False
        name, ok = QInputDialog.getText(
            self, "Name this target",
            f"Name for this {ref.kind} (#{ref.target_id}):",
            QLineEdit.EchoMode.Normal,
            ref.name or f"{ref.kind} {ref.target_id}",
        )
        if not ok:
            return False
        name = (name or "").strip() or ref.name or f"{ref.kind} {ref.target_id}"
        fp.upsert_target(
            self._conn, forum_fk=fid, name=name,
            kind=ref.kind, target_id=ref.target_id,
        )
        return True

    def _add_bulk_targets(
        self, fid: int, client, urls: list[str],
    ) -> tuple[int, list[str]]:
        added = 0
        skipped: list[str] = []
        for url in urls:
            ref = client.parse_target_url(url)
            if ref is None:
                skipped.append(url)
                continue
            name = (ref.name or f"{ref.kind} {ref.target_id}").strip()
            fp.upsert_target(
                self._conn, forum_fk=fid, name=name,
                kind=ref.kind, target_id=ref.target_id,
            )
            added += 1
        return added, skipped

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
