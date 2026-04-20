"""Forum posting worker: single QThread, per-forum cooldown queue.

Spec: docs/superpowers/specs/2026-04-20-forum-posting-design.md §6 / §8.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Event, Lock
from typing import Callable, Optional

from PyQt6.QtCore import QThread, pyqtSignal

from src.network.forum.client import ForumClient, ForumErrorKind
from src.utils.logger import log


@dataclass
class PostJob:
    forum_post_id: int
    forum_id: int
    kind: str               # 'reply' | 'new_thread'
    target_id: str
    title: str
    body: str


@dataclass
class EditJob:
    forum_post_id: int
    forum_id: int
    post_id: str
    new_body: str
    mode: str               # 'whole' | 'surgical' (informational)


@dataclass
class FetchJob:
    forum_post_id: int
    forum_id: int
    post_id: str


class ForumPostingWorker(QThread):
    post_started = pyqtSignal(int)
    post_completed = pyqtSignal(int, bool, str)
    post_result_payload = pyqtSignal(int, dict)
    edit_completed = pyqtSignal(int, bool, str)
    onboard_completed = pyqtSignal(int, bool, str)
    onboard_payload = pyqtSignal(int, dict)
    auth_failed = pyqtSignal(int, str)
    queue_changed = pyqtSignal(int, int)

    def __init__(
        self,
        client_factory: Callable[[int], ForumClient],
        cooldown_lookup: Callable[[int], float],
    ):
        super().__init__()
        self._client_factory = client_factory
        self._cooldown_lookup = cooldown_lookup
        self._clients: dict[int, ForumClient] = {}
        self._queues: dict[int, deque] = defaultdict(deque)
        self._next_allowed: dict[int, float] = defaultdict(lambda: 0.0)
        self._paused_forums: set[int] = set()
        self._lock = Lock()
        self._wake = Event()
        self._stop = False

    def enqueue(self, job) -> None:
        with self._lock:
            self._queues[job.forum_id].append(job)
            depth = len(self._queues[job.forum_id])
        self.queue_changed.emit(job.forum_id, depth)
        self._wake.set()

    def stop(self) -> None:
        self._stop = True
        self._wake.set()

    def resume_forum(self, forum_id: int) -> None:
        self._paused_forums.discard(forum_id)
        self._wake.set()

    def _client_for(self, forum_id: int) -> ForumClient:
        c = self._clients.get(forum_id)
        if c is None:
            c = self._client_factory(forum_id)
            self._clients[forum_id] = c
        return c

    def _pick_next_job(self):
        """Returns (job, sleep_for_seconds). job=None means nothing ready."""
        with self._lock:
            now = time.monotonic()
            soonest = float("inf")
            for fid, q in self._queues.items():
                if not q or fid in self._paused_forums:
                    continue
                ready_at = self._next_allowed[fid]
                if now >= ready_at:
                    return q.popleft(), 0.0
                soonest = min(soonest, ready_at)
        if soonest == float("inf"):
            return None, 1.0
        return None, max(0.0, soonest - now)

    def run(self) -> None:
        while not self._stop:
            job, sleep_for = self._pick_next_job()
            if job is None:
                self._wake.wait(timeout=min(sleep_for, 5.0))
                self._wake.clear()
                continue
            try:
                self._dispatch(job)
            except Exception as e:
                log(
                    f"forum worker dispatch error: {e}",
                    level="error", category="forum",
                )
            finally:
                self._next_allowed[job.forum_id] = (
                    time.monotonic() + self._cooldown_lookup(job.forum_id)
                )

    def _dispatch(self, job) -> None:
        if isinstance(job, PostJob):
            self._do_post(job)
        elif isinstance(job, EditJob):
            self._do_edit(job)
        elif isinstance(job, FetchJob):
            self._do_fetch(job)

    def _do_post(self, job: PostJob) -> None:
        self.post_started.emit(job.forum_post_id)
        client = self._client_for(job.forum_id)
        if job.kind == "reply":
            r = client.post_reply(job.target_id, job.body)
        else:
            r = client.create_thread(job.target_id, job.title, job.body)
        if r.success:
            self.post_result_payload.emit(job.forum_post_id, {
                "posted_post_id": r.post_id,
                "posted_thread_id": r.thread_id,
                "posted_url": r.posted_url,
            })
            self.post_completed.emit(job.forum_post_id, True, "")
        else:
            self._handle_failure(job.forum_id, r.error_kind, r.error_message)
            self.post_completed.emit(
                job.forum_post_id, False,
                f"{r.error_kind}:{r.error_message}",
            )

    def _do_edit(self, job: EditJob) -> None:
        client = self._client_for(job.forum_id)
        r = client.edit_post(job.post_id, job.new_body)
        if r.success:
            self.edit_completed.emit(job.forum_post_id, True, "")
        else:
            self._handle_failure(job.forum_id, r.error_kind, r.error_message)
            self.edit_completed.emit(
                job.forum_post_id, False,
                f"{r.error_kind}:{r.error_message}",
            )

    def _do_fetch(self, job: FetchJob) -> None:
        import hashlib

        from src.network.forum.link_extractor import extract_link_map

        client = self._client_for(job.forum_id)
        r = client.get_post(job.post_id)
        if not r.success:
            self._handle_failure(job.forum_id, r.error_kind, r.error_message)
            self.onboard_completed.emit(
                job.forum_post_id, False,
                f"{r.error_kind}:{r.error_message}",
            )
            return
        body_hash = hashlib.sha256(r.body.encode("utf-8")).hexdigest()
        link_map = extract_link_map(r.body)
        self.onboard_payload.emit(job.forum_post_id, {
            "body": r.body,
            "body_hash": body_hash,
            "link_map": link_map,
            "posted_post_id": r.post_id,
            "posted_thread_id": r.thread_id,
            "posted_url": r.posted_url,
        })
        self.onboard_completed.emit(job.forum_post_id, True, "")

    def _handle_failure(
        self, forum_id: int, kind: ForumErrorKind, msg: str,
    ) -> None:
        if kind == ForumErrorKind.LOGIN_REQUIRED:
            self._paused_forums.add(forum_id)
            self.auth_failed.emit(forum_id, msg or "login_required")
        elif kind == ForumErrorKind.FLOOD_BLOCK:
            self._next_allowed[forum_id] = (
                time.monotonic() + 4 * self._cooldown_lookup(forum_id)
            )
