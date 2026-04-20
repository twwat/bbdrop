"""ForumClient ABC + result dataclasses + error enum.

Spec: docs/superpowers/specs/2026-04-20-forum-posting-design.md §3.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ForumErrorKind(str, Enum):
    OK = "ok"
    LOGIN_REQUIRED = "login_required"
    SECURITYTOKEN_STALE = "securitytoken_stale"
    FLOOD_BLOCK = "flood_block"
    POST_NOT_FOUND = "post_not_found"
    NETWORK = "network"
    UNPARSEABLE_RESPONSE = "unparseable_response"
    UNKNOWN = "unknown"


@dataclass
class AuthResult:
    success: bool
    username: Optional[str] = None
    error_kind: ForumErrorKind = ForumErrorKind.OK
    error_message: str = ""


@dataclass
class PostResult:
    success: bool
    post_id: Optional[str] = None
    thread_id: Optional[str] = None
    posted_url: Optional[str] = None
    error_kind: ForumErrorKind = ForumErrorKind.OK
    error_message: str = ""
    raw_response: str = ""


@dataclass
class EditResult:
    success: bool
    error_kind: ForumErrorKind = ForumErrorKind.OK
    error_message: str = ""
    raw_response: str = ""


@dataclass
class PostBody:
    success: bool
    post_id: str = ""
    thread_id: str = ""
    posted_url: str = ""
    body: str = ""
    error_kind: ForumErrorKind = ForumErrorKind.OK
    error_message: str = ""


@dataclass
class PostRef:
    post_id: str
    thread_id: Optional[str]
    forum_base_url: Optional[str]


@dataclass
class TargetRef:
    """A subforum or thread identified from a pasted URL.

    ``kind`` is one of ``"subforum"`` or ``"thread"``. ``name`` is a
    best-effort label extracted from the URL (e.g. slug or numeric id);
    callers that want the real forum/thread title should fetch it.
    """
    kind: str
    target_id: str
    name: str = ""
    forum_base_url: Optional[str] = None


# LinkMap is a dict of category -> list[{url, host_kind?, role?}]
LinkMap = dict


class ForumClient(ABC):
    software_id: str = ""
    base_url: str = ""

    def __init__(self, *, base_url: str, session_store=None):
        self.base_url = base_url.rstrip("/")
        self._sessions = session_store

    @abstractmethod
    def authenticate(self, username: str, password: str) -> AuthResult: ...
    @abstractmethod
    def is_logged_in(self) -> bool: ...
    @abstractmethod
    def logout(self) -> None: ...
    @abstractmethod
    def post_reply(self, thread_id: str, body: str) -> PostResult: ...
    @abstractmethod
    def create_thread(self, forum_id: str, title: str, body: str) -> PostResult: ...
    @abstractmethod
    def get_post(self, post_id: str) -> PostBody: ...
    @abstractmethod
    def edit_post(self, post_id: str, new_body: str) -> EditResult: ...
    @abstractmethod
    def parse_post_reference(self, text_or_url: str) -> Optional[PostRef]: ...
    @abstractmethod
    def parse_target_url(self, text_or_url: str) -> Optional[TargetRef]: ...
