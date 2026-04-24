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
import threading
import time
from typing import Callable, Optional
from urllib.parse import urlparse

from PyQt6.QtCore import Qt, QObject, pyqtSignal

from src.network.forum.factory import create_forum_client
from src.network.forum.link_extractor import extract_link_map
from src.network.forum.session_store import SessionStore
from src.network.forum.update_planner import UpdateAction, plan_update
from src.processing.forum_posting_worker import (
    EditJob, FetchJob, ForumPostingWorker, PostJob,
)
from src.storage import forum_posting as fp
from src.utils.forum_signals import bbcode_regenerated_signal_hub
from src.utils.logger import log


class ForumController(QObject):
    forum_post_changed = pyqtSignal(int)   # forum_post_id

    def __init__(
        self,
        *,
        worker: Optional[ForumPostingWorker] = None,
        template_renderer: Optional[Callable] = None,
        credential_loader: Optional[Callable[[int], tuple[str, str]]] = None,
        db_connection_factory: Optional[Callable[[], sqlite3.Connection]] = None,
    ):
        super().__init__()
        self._sessions = SessionStore()
        self._template_renderer = template_renderer or self._default_render
        self._credential_loader = (
            credential_loader or self._default_credential_loader
        )
        self._db_connection_factory = db_connection_factory
        self._conn: Optional[sqlite3.Connection] = None
        log(
            f"ForumController.__init__ on thread {threading.current_thread().ident}: "
            f"db_connection_factory={db_connection_factory is not None}",
            level="debug", category="forum",
        )
        self._worker = worker or ForumPostingWorker(
            client_factory=self._make_client,
            cooldown_lookup=None,
            db_connection_factory=self._db_connection_factory,
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

    def handle_gallery_uploaded(self, gallery_id: int) -> list[int]:
        """Auto-post to all configured destinations when trigger=auto_on_upload."""
        conn = self._get_conn()
        settings = fp.get_tab_posting_settings_for_gallery(conn, gallery_id)
        if (not settings
                or settings.get("trigger_mode") != "auto_on_upload"
                or not settings.get("enabled")):
            return []
        destinations = fp.get_effective_destinations(conn, gallery_id)
        return self._enqueue_posts_for_destinations(gallery_id, destinations)

    def post_now(self, gallery_id: int, destinations: list[dict]) -> list[int]:
        """Post to an explicit list of destinations (used by the composer)."""
        return self._enqueue_posts_for_destinations(gallery_id, destinations)

    def quick_post(self, gallery_ids: list[int]) -> dict[int, list[int]]:
        """Post all configured destinations for each gallery without the composer."""
        conn = self._get_conn()
        results: dict[int, list[int]] = {}
        for gid in gallery_ids:
            dests = fp.get_effective_destinations(conn, gid)
            results[gid] = (
                self._enqueue_posts_for_destinations(gid, dests) if dests else []
            )
        return results

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
            for f in fp.list_forums(self._get_conn()):
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
                cfg = fp.get_effective_posting_config(self._get_conn(), gallery_id)
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
            self._get_conn(),
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

    def update_post(
        self, forum_post_id: int,
        override_mode: Optional[str] = None,
    ) -> dict:
        """Plan and (if applicable) enqueue an update for a single forum_post.

        Returns a dict ``{"action": <str>, "reason": <str>, "enqueued": bool}``.
        Does not block — when enqueued, results arrive via worker signals.
        Raises ValueError if the post/config is missing or in a bad state.
        """
        post = fp.get_forum_post(self._get_conn(), forum_post_id)
        if not post:
            raise ValueError(f"forum_post {forum_post_id} not found")
        if post["status"] not in ("stale", "posted", "failed"):
            raise ValueError(
                f"Cannot update post in status {post['status']}"
            )
        cfg = fp.get_effective_posting_config(self._get_conn(), post["gallery_fk"])
        if not cfg:
            raise ValueError("No effective posting config for gallery")

        update_mode = (
            override_mode
            or post.get("update_mode_at_post")
            or cfg["update_mode"]
        )
        manual_edit_handling = cfg["manual_edit_handling"]

        new_body, _new_title = self._template_renderer(
            post["gallery_fk"],
            cfg["body_template_name"],
            cfg.get("title_template_name"),
        )
        new_link_map = extract_link_map(new_body)

        client = (
            getattr(self, "_client_for_test", None)
            or self._make_client(post["forum_fk"])
        )
        live = client.get_post(post["posted_post_id"])
        if not live.success:
            reason = f"fetch failed: {live.error_message}"
            fp.update_forum_post(
                self._get_conn(), forum_post_id,
                status="stale",
                last_attempt_ts=int(time.time()),
                last_error=reason,
            )
            self.forum_post_changed.emit(forum_post_id)
            return {
                "action": UpdateAction.SKIP_AND_ALERT.value,
                "reason": reason,
                "enqueued": False,
            }

        live_body_hash = hashlib.sha256(
            live.body.encode("utf-8")
        ).hexdigest()

        old_link_map = {}
        if post.get("link_map_json"):
            try:
                old_link_map = json.loads(post["link_map_json"]) or {}
            except (TypeError, ValueError):
                old_link_map = {}

        plan = plan_update(
            update_mode=update_mode,
            manual_edit_handling=manual_edit_handling,
            stored_body_hash=post.get("body_hash") or "",
            live_body=live.body,
            live_body_hash=live_body_hash,
            old_link_map=old_link_map,
            new_body=new_body,
            new_link_map=new_link_map,
        )

        if plan.action == UpdateAction.NOOP:
            fp.update_forum_post(
                self._get_conn(), forum_post_id,
                status="posted",
                last_attempt_ts=int(time.time()),
                last_error=None,
            )
            self.forum_post_changed.emit(forum_post_id)
            return {
                "action": UpdateAction.NOOP.value,
                "reason": plan.reason,
                "enqueued": False,
            }

        if plan.action == UpdateAction.SKIP_AND_ALERT:
            fp.update_forum_post(
                self._get_conn(), forum_post_id,
                status="stale",
                last_attempt_ts=int(time.time()),
                last_error=f"skipped: {plan.reason}",
            )
            self.forum_post_changed.emit(forum_post_id)
            return {
                "action": UpdateAction.SKIP_AND_ALERT.value,
                "reason": plan.reason,
                "enqueued": False,
            }

        # WHOLE_BODY or SURGICAL — pre-update DB state so edit_completed
        # signal doesn't need to rebuild hash/link_map.
        new_body_hash = hashlib.sha256(
            plan.body_to_post.encode("utf-8")
        ).hexdigest()
        fp.update_forum_post(
            self._get_conn(), forum_post_id,
            status="updating",
            body_hash=new_body_hash,
            link_map_json=json.dumps(extract_link_map(plan.body_to_post)),
            update_mode_at_post=update_mode,
        )
        self.forum_post_changed.emit(forum_post_id)
        self._worker.enqueue(EditJob(
            forum_post_id=forum_post_id,
            forum_id=post["forum_fk"],
            post_id=post["posted_post_id"],
            new_body=plan.body_to_post,
            mode=plan.action.value,
        ))
        return {
            "action": plan.action.value,
            "reason": plan.reason,
            "enqueued": True,
        }

    def update_posts(
        self, forum_post_ids: list[int],
        override_mode: Optional[str] = None,
    ) -> list[dict]:
        """Batch entry point used by the Stale Posts dialog.

        Continues past per-post errors — each result dict reports its own
        outcome. A failure captures ``action="skip_and_alert"`` and the
        exception message as ``reason``.
        """
        results: list[dict] = []
        for pid in forum_post_ids:
            try:
                results.append(
                    self.update_post(pid, override_mode=override_mode)
                )
            except Exception as e:
                results.append({
                    "action": UpdateAction.SKIP_AND_ALERT.value,
                    "reason": str(e),
                    "enqueued": False,
                })
        return results

    def preview_render(self, gallery_id: int) -> tuple[str, str]:
        """Render (body, title) for the composer without enqueueing.

        Raises ValueError if no effective config exists for the gallery.
        """
        cfg = fp.get_effective_posting_config(self._get_conn(), gallery_id)
        if not cfg:
            raise ValueError("No effective posting config for gallery")
        return self._template_renderer(
            gallery_id,
            cfg["body_template_name"],
            cfg.get("title_template_name"),
        )

    # ----- internals -----

    def _get_conn(self) -> sqlite3.Connection:
        """Get a database connection from the factory. Called from GUI thread."""
        if not self._conn:
            if not self._db_connection_factory:
                raise RuntimeError("No database connection factory available")
            self._conn = self._db_connection_factory()
        return self._conn

    def _make_client(self, forum_id: int, worker_conn: Optional[sqlite3.Connection] = None):
        conn = worker_conn if worker_conn else self._get_conn()
        forum = fp.get_forum(conn, forum_id)
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
        forum = fp.get_forum(self._get_conn(), forum_id)
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
        after a successful upload. Checks both .uploaded/ and central store.
        For pre-existing galleries that were never uploaded by this app, the
        artifact won't exist — caller should inject a custom renderer that
        re-renders from DB state."""
        from src.utils.artifact_finder import find_gallery_bbcode
        row = self._get_conn().execute(
            "SELECT path, name, gallery_id FROM galleries WHERE id=?",
            (gallery_id,),
        ).fetchone()
        if not row:
            return ("", "")
        path = row["path"] if isinstance(row, sqlite3.Row) else row[0]
        name = (row["name"] if isinstance(row, sqlite3.Row) else row[1]) or os.path.basename(path)
        gid = (row["gallery_id"] if isinstance(row, sqlite3.Row) else row[2]) or ""

        body = find_gallery_bbcode(name, gid, path) or ""

        from src.utils.templates import extract_post_title
        title = extract_post_title(title_template, body_template, fallback_title=name)

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
            existing = self._get_conn().execute(
                "SELECT 1 FROM forum_targets "
                "WHERE forum_fk=? AND kind=? AND target_id=?",
                (forum_fk, target_kind, target_id),
            ).fetchone()
            if existing:
                return
            fp.upsert_target(
                self._get_conn(), forum_fk=forum_fk,
                name=f"{target_kind} {target_id}",
                kind=target_kind, target_id=target_id,
            )
        except Exception as e:
            log(
                f"forum: auto-remember target failed: {e}",
                level="warning", category="forum",
            )

    def _enqueue_posts_for_destinations(
        self, gallery_id: int, destinations: list[dict]
    ) -> list[int]:
        """Insert a forum_post row and enqueue a PostJob for each destination."""
        conn = self._get_conn()
        post_ids: list[int] = []
        for dest in destinations:
            try:
                body_template = dest.get("body_template_name") or ""
                body, title = self._template_renderer(gallery_id, body_template, None)
                body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
                link_map = extract_link_map(body)
                self._auto_remember_target(
                    forum_fk=dest["forum_fk"],
                    cfg_kind=dest["kind"],
                    target_id=str(dest["target_id"]),
                )
                post_id = fp.insert_forum_post(
                    conn,
                    gallery_fk=gallery_id,
                    forum_fk=dest["forum_fk"],
                    kind=dest["kind"],
                    target_id=dest["target_id"],
                    body_hash=body_hash,
                    link_map=link_map,
                )
                self._worker.enqueue(PostJob(
                    forum_post_id=post_id,
                    forum_id=dest["forum_fk"],
                    kind=dest["kind"],
                    target_id=dest["target_id"],
                    title=title,
                    body=body,
                ))
                post_ids.append(post_id)
            except Exception as exc:
                log(
                    f"forum: failed to enqueue post for gallery {gallery_id} "
                    f"dest {dest}: {exc}",
                    level="warning", category="forum",
                )
        return post_ids

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
            self._get_conn(),
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
            self._get_conn(), forum_post_id,
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
                self._get_conn(), forum_post_id,
                status="failed",
                last_attempt_ts=int(time.time()),
                last_error=err,
            )
            self.forum_post_changed.emit(forum_post_id)

    def _on_edit_completed(self, forum_post_id: int, success: bool, err: str):
        if success:
            fp.update_forum_post(
                self._get_conn(), forum_post_id,
                status="posted",
                last_attempt_ts=int(time.time()),
                last_error=None,
            )
        else:
            fp.update_forum_post(
                self._get_conn(), forum_post_id,
                status="failed",
                last_attempt_ts=int(time.time()),
                last_error=err,
            )
        self.forum_post_changed.emit(forum_post_id)

    def _on_onboard_payload(self, forum_post_id: int, payload: dict):
        fp.update_forum_post(
            self._get_conn(), forum_post_id,
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
                self._get_conn(), forum_post_id,
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
        cfg = fp.get_effective_posting_config(self._get_conn(), gallery_id)
        if not cfg:
            return
        # Stale-mark: existing posted rows whose config lists this cause
        triggers = cfg.get("stale_triggers", []) or []
        if cause in triggers:
            ids = fp.mark_posts_stale_for_gallery(self._get_conn(), gallery_id)
            for pid in ids:
                self.forum_post_changed.emit(pid)
        # Auto-post: only on upload cause + auto_on_upload tab config
        if cause == "upload":
            self.handle_gallery_uploaded(gallery_id)
