"""vBulletin 4.2.0 forum client (stub — filled in P1 Task 3).

Spec: docs/superpowers/specs/2026-04-20-forum-posting-design.md §4.
"""

from __future__ import annotations

from src.network.forum.client import ForumClient
from src.network.forum.factory import register


@register("vbulletin_4_2_0")
class VBulletinClient(ForumClient):
    def authenticate(self, *a, **kw):
        raise NotImplementedError

    def is_logged_in(self):
        raise NotImplementedError

    def logout(self):
        raise NotImplementedError

    def post_reply(self, *a, **kw):
        raise NotImplementedError

    def create_thread(self, *a, **kw):
        raise NotImplementedError

    def get_post(self, *a, **kw):
        raise NotImplementedError

    def edit_post(self, *a, **kw):
        raise NotImplementedError

    def parse_post_reference(self, *a, **kw):
        raise NotImplementedError
