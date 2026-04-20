"""In-memory session store for forum clients.

Cookies are not persisted to disk in v1 — re-login on app restart.

Spec: docs/superpowers/specs/2026-04-20-forum-posting-design.md §5.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ForumSession:
    cookies: dict[str, str]
    last_securitytoken: Optional[str]
    last_login_ts: float
    last_login_username: str


class SessionStore:
    def __init__(self):
        self._sessions: dict[int, ForumSession] = {}

    def get(self, forum_id: int) -> Optional[ForumSession]:
        return self._sessions.get(forum_id)

    def set(self, forum_id: int, session: ForumSession) -> None:
        self._sessions[forum_id] = session

    def clear(self, forum_id: int) -> None:
        self._sessions.pop(forum_id, None)
