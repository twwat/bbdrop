"""Factory + registry for forum clients.

Use `@register("software_id")` on a `ForumClient` subclass to make it
constructible by `create_forum_client()`.

Spec: docs/superpowers/specs/2026-04-20-forum-posting-design.md §3.
"""

from __future__ import annotations

from typing import Optional

from src.network.forum.client import ForumClient
from src.network.forum.session_store import SessionStore


_REGISTRY: dict[str, type[ForumClient]] = {}


def register(software_id: str):
    def deco(cls: type[ForumClient]):
        cls.software_id = software_id
        _REGISTRY[software_id] = cls
        return cls
    return deco


def create_forum_client(
    software_id: str, *, base_url: str,
    session_store: Optional[SessionStore] = None,
) -> ForumClient:
    if software_id not in _REGISTRY:
        raise ValueError(f"Unknown forum software_id: {software_id}")
    return _REGISTRY[software_id](base_url=base_url, session_store=session_store)


def supported_software_ids() -> list[str]:
    # Force import of bundled clients so they self-register.
    from src.network.forum import vbulletin_client  # noqa: F401
    return sorted(_REGISTRY.keys())
