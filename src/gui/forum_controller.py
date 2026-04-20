"""Forum posting controller. Lives on the GUI thread.

Wires:
- gallery_uploaded → auto-post when tab is configured for auto_on_upload
- bbcode_regenerated_signal_hub → stale-mark matching forum_posts (and
  forward upload-cause to the auto-post path)
- worker signals → DB updates + per-row GUI refresh signals

Spec: docs/superpowers/specs/2026-04-20-forum-posting-design.md §7.3 / §7.6.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from typing import Callable, Optional
from urllib.parse import urlparse

from PyQt6.QtCore import Qt, QObject, pyqtSignal

from src.network.forum.factory import create_forum_client
from src.network.forum.link_extractor import extract_link_map
from src.network.forum.session_store import SessionStore
from src.processing.forum_posting_worker import (
    FetchJob, ForumPostingWorker, PostJob,
)
from src.storage import forum_posting as fp
from src.utils.forum_signals import bbcode_regenerated_signal_hub
from src.utils.logger import log


class ForumController(QObject):
    forum_post_changed = pyqtSignal(int)   # forum_post_id

    def __init__(
        self,
        *,
        conn: sqlite3.Connection,
        worker: Optional[ForumPostingWorker] = None,
        template_renderer: Optional[Callable] = None,
        credential_loader: Optional[Callable[[int], tuple[str, str]]] = None,
    ):
        super().__init__()
        self._conn = conn
        self._sessions = SessionStore()
        self._template_renderer = template_renderer or self._default_render
        self._credential_loader = (
            credential_loader or self._default_credential_loader
        )
        self._worker = worker or ForumPostingWorker(
            client_factory=self._make_client,
            cooldown_lookup=self._lookup_cooldown,
        )
        self._worker.post_result_payload.connect(
            self._on_post_result_payload, Qt.ConnectionType.QueuedConnection,
        )
        self._worker.post_completed.connect(
            self._on_post_completed, Qt.ConnectionType.QueuedConnection,
        )
        self._worker.edit_completed.connect(
            self._on_edit_completed, Qt.ConnectionType.QueuedConnection,
        )
        self._worker.onboard_payload.connect(
            self._on_onboard_payload, Qt.ConnectionType.QueuedConnection,
        )
        self._worker.onboard_completed.connect(
            self._on_onboard_completed, Qt.ConnectionType.QueuedConnection,
        )
        self._worker.auth_failed.connect(
            self._on_auth_failed, Qt.ConnectionType.QueuedConnection,
        )
        bbcode_regenerated_signal_hub.bbcode_regenerated.connect(
            self._on_bbcode_regenerated, Qt.ConnectionType.QueuedConnection,
        )

    def start(self) -> None:
        if not self._worker.isRunning():
            self._worker.start()

    def stop(self) -> None:
        self._worker.stop()
        self._worker.wait(5000)

    # ----- public entry points -----

    def handle_gallery_uploaded(self, gallery_id: int) -> Optional[int]:
        cfg = fp.get_effective_posting_config(self._conn, gallery_id)
        if (
            not cfg
            or not cfg.get("enabled")
            or cfg.get("trigger_mode") != "auto_on_upload"
        ):
            return None
        # Skip if a non-failed post already exists for this gallery — re-uploads
        # of already-posted galleries should update via stale flow, not duplicate.
        existing = [
            p for p in fp.list_forum_posts_for_gallery(self._conn, gallery_id)
            if p["status"] in ("queued", "posted", "stale")
        ]
        if existing:
            return None
        return self._enqueue_post(gallery_id, cfg)

    def post_now(
        self, gallery_id: int, override_cfg: Optional[dict] = None,
    ) -> int:
        cfg = override_cfg or fp.get_effective_posting_config(
            self._conn, gallery_id,
        )
        if not cfg:
            raise ValueError("No effective posting config for gallery")
        return self._enqueue_post(gallery_id, cfg)

    def onboard_post(
        self, gallery_id: int, text_or_url: str,
        forum_hint: Optional[int] = None,
    ) -> int:
        """Onboard an existing forum post for an already-created gallery.

        Returns the new forum_posts row id. Raises ValueError if the input
        can't be resolved to a (forum, post_id) pair.
        """
        s = (text_or_url or "").strip()
        if not s:
            raise ValueError("Empty input")

        forum_id: Optional[int] = None
        if s.startswith("http://") or s.startswith("https://"):
            host = urlparse(s).netloc.lower()
            for f in fp.list_forums(self._conn):
                if urlparse(f["base_url"]).netloc.lower() == host:
                    forum_id = f["id"]
                    break
            if forum_id is None:
                raise ValueError(
                    f"No registered forum matches host '{host}'. "
                    "Add this forum in Forum Manager first."
                )
        else:
            if forum_hint is not None:
                forum_id = forum_hint
            else:
                cfg = fp.get_effective_posting_config(self._conn, gallery_id)
                if not cfg:
                    raise ValueError(
                        "No tab posting config for this gallery. "
                        "Configure tab posting first or paste a full URL."
                    )
                forum_id = cfg["forum_fk"]

        client = self._make_client(forum_id)
        ref = client.parse_post_reference(s)
        if ref is None or not ref.post_id:
            raise ValueError("Could not extract a post ID from input")

        self._auto_remember_target(
            forum_fk=forum_id, cfg_kind="reply",
            target_id=str(ref.thread_id or "0"),
        )
        post_row_id = fp.insert_forum_post(
            self._conn,
            gallery_fk=gallery_id, forum_fk=forum_id,
            kind="reply", target_id=(ref.thread_id or "0"),
            body_hash="", link_map={}, source="onboarded",
        )
        self._worker.enqueue(FetchJob(
            forum_post_id=post_row_id,
            forum_id=forum_id,
            post_id=ref.post_id,
        ))
        return post_row_id

    def preview_render(self, gallery_id: int) -> tuple[str, str]:
        """Render (body, title) for the composer without enqueueing.

        Raises ValueError if no effective config exists for the gallery.
        """
        cfg = fp.get_effective_posting_config(self._conn, gallery_id)
        if not cfg:
            raise ValueError("No effective posting config for gallery")
        return self._template_renderer(
            gallery_id,
            cfg["body_template_name"],
            cfg.get("title_template_name"),
        )

    # ----- internals -----

    def _make_client(self, forum_id: int):
        forum = fp.get_forum(self._conn, forum_id)
        if not forum:
            raise RuntimeError(f"Forum {forum_id} missing")
        client = create_forum_client(
            forum["software_id"],
            base_url=forum["base_url"],
            session_store=self._sessions,
        )
        try:
            user, pw = self._credential_loader(forum_id)
            if user and pw:
                client.authenticate(user, pw)
        except Exception as e:
            log(
                f"forum {forum_id} auth on client-create failed: {e}",
                level="warning", category="forum",
            )
        return client

    def _lookup_cooldown(self, forum_id: int) -> float:
        forum = fp.get_forum(self._conn, forum_id)
        return float(forum["default_cooldown_s"]) if forum else 30.0

    def _default_credential_loader(self, forum_id: int) -> tuple[str, str]:
        from src.utils.credentials import decrypt_password, get_credential
        enc = get_credential(f"forum_{forum_id}_credentials")
        if not enc:
            return ("", "")
        try:
            decrypted = decrypt_password(enc) or ""
        except Exception:
            return ("", "")
        if ":" in decrypted:
            user, pw = decrypted.split(":", 1)
            return (user, pw)
        return ("", "")

    def _default_render(
        self,
        gallery_id: int,
        body_template: str,
        title_template: Optional[str],
    ) -> tuple[str, str]:
        """Default renderer reads the BBCode artifact written by upload_workers
        after a successful upload. For pre-existing galleries that were never
        uploaded by this app, the artifact won't exist — caller should inject
        a custom renderer that re-renders from DB state."""
        from src.storage.gallery_management import build_gallery_filenames
        row = self._conn.execute(
            "SELECT path, name, gallery_id FROM galleries WHERE id=?",
            (gallery_id,),
        ).fetchone()
        if not row:
            return ("", "")
        path = row["path"] if isinstance(row, sqlite3.Row) else row[0]
        name = (row["name"] if isinstance(row, sqlite3.Row) else row[1]) or os.path.basename(path)
        gid = (row["gallery_id"] if isinstance(row, sqlite3.Row) else row[2]) or ""
        _, _, bbcode_filename = build_gallery_filenames(name, gid)
        base = path if os.path.isdir(path) else os.path.dirname(path)
        bbcode_path = os.path.join(base, ".uploaded", bbcode_filename)
        body = ""
        if os.path.isfile(bbcode_path):
            try:
                with open(bbcode_path, encoding="utf-8") as f:
                    body = f.read()
            except OSError as e:
                log(
                    f"forum: failed to read bbcode artifact {bbcode_path}: {e}",
                    level="warning", category="forum",
                )
        title = ""
        try:
            from src.utils.templates import load_post_titles
            titles = load_post_titles() or {}
            # Prefer an explicit title_template; otherwise fall back to
            # the body template's #POSTTITLE: directive so the single
            # "Template" dropdown in the tab config is sufficient.
            lookup_key = title_template or body_template
            if lookup_key:
                title = titles.get(lookup_key, "") or ""
        except Exception:
            pass
        return body, title

    def _auto_remember_target(
        self, *, forum_fk: int, cfg_kind: str, target_id: str,
    ) -> None:
        """Best-effort: upsert this (forum, target) into the forum_targets
        library so future pickers have it without re-typing the id.

        Silent on failure — the post path must not break because of a
        target-cache write. ``cfg_kind`` is the tab_posting_config kind
        ("reply" / "new_thread"), mapped to the target-library kind
        ("thread" / "subforum")."""
        if not target_id or target_id == "0":
            return
        target_kind = "subforum" if cfg_kind == "new_thread" else "thread"
        try:
            existing = self._conn.execute(
                "SELECT 1 FROM forum_targets "
                "WHERE forum_fk=? AND kind=? AND target_id=?",
                (forum_fk, target_kind, target_id),
            ).fetchone()
            if existing:
                return
            fp.upsert_target(
                self._conn, forum_fk=forum_fk,
                name=f"{target_kind} {target_id}",
                kind=target_kind, target_id=target_id,
            )
        except Exception as e:
            log(
                f"forum: auto-remember target failed: {e}",
                level="warning", category="forum",
            )

    def _enqueue_post(self, gallery_id: int, cfg: dict) -> int:
        # Composer can short-circuit rendering by passing _body_override /
        # _title_override on the cfg dict — these are the user's edited text.
        body_override = cfg.get("_body_override")
        title_override = cfg.get("_title_override")
        if body_override is not None:
            body = body_override
            if title_override is not None:
                title = title_override
            else:
                _, title = self._template_renderer(
                    gallery_id,
                    cfg["body_template_name"],
                    cfg.get("title_template_name"),
                )
        else:
            body, title = self._template_renderer(
                gallery_id,
                cfg["body_template_name"],
                cfg.get("title_template_name"),
            )
        body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        link_map = extract_link_map(body)
        self._auto_remember_target(
            forum_fk=cfg["forum_fk"], cfg_kind=cfg["kind"],
            target_id=str(cfg["target_id"]),
        )
        post_row_id = fp.insert_forum_post(
            self._conn,
            gallery_fk=gallery_id, forum_fk=cfg["forum_fk"],
            kind=cfg["kind"], target_id=cfg["target_id"],
            body_hash=body_hash, link_map=link_map,
            update_mode_at_post=cfg["update_mode"],
        )
        self._worker.enqueue(PostJob(
            forum_post_id=post_row_id,
            forum_id=cfg["forum_fk"],
            kind=cfg["kind"],
            target_id=cfg["target_id"],
            title=title,
            body=body,
        ))
        return post_row_id

    # ----- signal handlers -----

    def _on_post_result_payload(self, forum_post_id: int, payload: dict):
        fp.update_forum_post(
            self._conn, forum_post_id,
            posted_post_id=payload.get("posted_post_id"),
            posted_thread_id=payload.get("posted_thread_id"),
            posted_url=payload.get("posted_url"),
            posted_ts=int(time.time()),
            status="posted",
            last_attempt_ts=int(time.time()),
            last_error=None,
        )
        self.forum_post_changed.emit(forum_post_id)

    def _on_post_completed(self, forum_post_id: int, success: bool, err: str):
        if not success:
            fp.update_forum_post(
                self._conn, forum_post_id,
                status="failed",
                last_attempt_ts=int(time.time()),
                last_error=err,
            )
            self.forum_post_changed.emit(forum_post_id)

    def _on_edit_completed(self, forum_post_id: int, success: bool, err: str):
        if success:
            fp.update_forum_post(
                self._conn, forum_post_id,
                status="posted",
                last_attempt_ts=int(time.time()),
                last_error=None,
            )
        else:
            fp.update_forum_post(
                self._conn, forum_post_id,
                status="failed",
                last_attempt_ts=int(time.time()),
                last_error=err,
            )
        self.forum_post_changed.emit(forum_post_id)

    def _on_onboard_payload(self, forum_post_id: int, payload: dict):
        fp.update_forum_post(
            self._conn, forum_post_id,
            body_hash=payload["body_hash"],
            link_map_json=json.dumps(payload["link_map"]),
            posted_post_id=payload.get("posted_post_id"),
            posted_thread_id=payload.get("posted_thread_id"),
            posted_url=payload.get("posted_url"),
            posted_ts=int(time.time()),
            status="posted",
            last_attempt_ts=int(time.time()),
            last_error=None,
        )
        self.forum_post_changed.emit(forum_post_id)

    def _on_onboard_completed(
        self, forum_post_id: int, success: bool, err: str,
    ):
        if not success:
            fp.update_forum_post(
                self._conn, forum_post_id,
                status="failed",
                last_attempt_ts=int(time.time()),
                last_error=err,
            )
            self.forum_post_changed.emit(forum_post_id)

    def _on_auth_failed(self, forum_id: int, msg: str):
        log(
            f"forum {forum_id} auth failed: {msg}",
            level="warning", category="forum",
        )

    def _on_bbcode_regenerated(self, gallery_id: int, cause: str):
        cfg = fp.get_effective_posting_config(self._conn, gallery_id)
        if not cfg:
            return
        # Stale-mark: existing posted rows whose config lists this cause
        triggers = cfg.get("stale_triggers", []) or []
        if cause in triggers:
            ids = fp.mark_posts_stale_for_gallery(self._conn, gallery_id)
            for pid in ids:
                self.forum_post_changed.emit(pid)
        # Auto-post: only on upload cause + auto_on_upload tab config
        if cause == "upload":
            self.handle_gallery_uploaded(gallery_id)
