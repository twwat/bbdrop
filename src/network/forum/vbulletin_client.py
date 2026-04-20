"""vBulletin 4.2.0 client implementation. Form-scrape pattern.

Compatible with 4.2.5 (vipergirls.to). Each posting operation:
GET form → scrape securitytoken → POST. Auto-rescrape on stale token,
transparent re-login on redirect to login.php.

Spec: docs/superpowers/specs/2026-04-20-forum-posting-design.md §4.
"""

from __future__ import annotations

import re
import time
from typing import Optional
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

from src.network.forum.client import (
    AuthResult, EditResult, ForumClient, ForumErrorKind,
    PostBody, PostRef, PostResult,
)
from src.network.forum.factory import register
from src.network.forum.session_store import ForumSession


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_STALE_TOKEN_MARKERS = ("your security token is invalid",)
_LOGIN_REDIRECT_MARKERS = ("you are not logged in", '<form action="login.php"')


@register("vbulletin_4_2_0")
class VBulletinClient(ForumClient):
    """vBulletin 4.2.0 / 4.2.5."""

    def __init__(self, *, base_url: str, session_store=None):
        super().__init__(base_url=base_url, session_store=session_store)
        self._session = requests.Session()
        self._session.headers["User-Agent"] = USER_AGENT
        self._username: Optional[str] = None
        self._cached_creds: Optional[tuple[str, str]] = None

    # ----- helpers -----

    def _mark_logged_in(self, username: str, cookies: dict[str, str]) -> None:
        self._username = username
        for k, v in cookies.items():
            self._session.cookies.set(k, v)

    def _is_login_redirect(self, resp) -> bool:
        if "login.php" in (getattr(resp, "url", "") or ""):
            return True
        text = (getattr(resp, "text", "") or "").lower()
        return any(m in text for m in _LOGIN_REDIRECT_MARKERS)

    def _is_stale_token(self, resp) -> bool:
        return any(
            m in (getattr(resp, "text", "") or "").lower()
            for m in _STALE_TOKEN_MARKERS
        )

    def _scrape_token(self, html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "html.parser")
        tok = soup.find("input", {"name": "securitytoken"})
        return tok["value"] if tok and tok.has_attr("value") else None

    def _try_relogin(self) -> bool:
        if not self._cached_creds:
            return False
        user, pw = self._cached_creds
        return self.authenticate(user, pw).success

    def _post_with_relogin(self, get_url: str, post_url: str, base_data: dict,
                           attempt_relogin: bool = True):
        """GET form → scrape token → POST. One automatic retry on stale-token;
        one automatic re-login on redirect-to-login."""
        get_resp = self._session.get(get_url, timeout=30, allow_redirects=True)
        if attempt_relogin and self._is_login_redirect(get_resp):
            if self._try_relogin():
                get_resp = self._session.get(
                    get_url, timeout=30, allow_redirects=True
                )
            else:
                return get_resp
        token = self._scrape_token(get_resp.text)
        if not token:
            return get_resp
        data = {**base_data, "securitytoken": token}
        post_resp = self._session.post(
            post_url, data=data, timeout=60, allow_redirects=True
        )
        if self._is_stale_token(post_resp):
            get_resp = self._session.get(
                get_url, timeout=30, allow_redirects=True
            )
            token = self._scrape_token(get_resp.text)
            if token:
                data["securitytoken"] = token
                post_resp = self._session.post(
                    post_url, data=data, timeout=60, allow_redirects=True
                )
        return post_resp

    # ----- ForumClient interface -----

    def authenticate(self, username: str, password: str) -> AuthResult:
        try:
            data = {
                "vb_login_username": username,
                "vb_login_password": password,
                "s": "",
                "securitytoken": "guest",
                "do": "login",
                "cookieuser": "1",
            }
            r = self._session.post(
                f"{self.base_url}/login.php?do=login",
                data=data, timeout=30, allow_redirects=True,
            )
        except requests.RequestException as e:
            return AuthResult(
                False, error_kind=ForumErrorKind.NETWORK,
                error_message=str(e),
            )
        bb_userid = (
            r.cookies.get("bb_userid")
            or self._session.cookies.get("bb_userid")
        )
        if not bb_userid or bb_userid == "0":
            return AuthResult(
                False, error_kind=ForumErrorKind.LOGIN_REQUIRED,
                error_message="login_failed",
            )
        self._username = username
        self._cached_creds = (username, password)
        if self._sessions is not None:
            self._sessions.set(0, ForumSession(
                cookies=dict(self._session.cookies),
                last_securitytoken=None,
                last_login_ts=time.time(),
                last_login_username=username,
            ))
        return AuthResult(True, username=username)

    def is_logged_in(self) -> bool:
        v = self._session.cookies.get("bb_userid")
        return bool(v and v != "0")

    def logout(self) -> None:
        self._session.cookies.clear()
        self._username = None

    def post_reply(self, thread_id: str, body: str) -> PostResult:
        get_url = f"{self.base_url}/newreply.php?do=newreply&t={thread_id}"
        post_url = f"{self.base_url}/newreply.php?do=postreply&t={thread_id}"
        try:
            r = self._post_with_relogin(get_url, post_url, base_data={
                "do": "postreply",
                "t": thread_id,
                "message": body,
                "submit": "Submit Reply",
            })
        except requests.RequestException as e:
            return PostResult(
                False, error_kind=ForumErrorKind.NETWORK,
                error_message=str(e),
            )
        if self._is_login_redirect(r):
            return PostResult(
                False, error_kind=ForumErrorKind.LOGIN_REQUIRED,
                raw_response=(r.text or "")[:4000],
            )
        post_id, _ = self._parse_post_id_from_response(r)
        if not post_id:
            return PostResult(
                False, error_kind=ForumErrorKind.UNPARSEABLE_RESPONSE,
                raw_response=(r.text or "")[:4000],
            )
        return PostResult(
            True, post_id=post_id, thread_id=thread_id,
            posted_url=f"{self.base_url}/showthread.php?p={post_id}#post{post_id}",
            raw_response=(r.text or "")[:4000],
        )

    def create_thread(self, forum_id: str, title: str, body: str) -> PostResult:
        get_url = f"{self.base_url}/newthread.php?do=newthread&f={forum_id}"
        post_url = f"{self.base_url}/newthread.php?do=postthread&f={forum_id}"
        try:
            r = self._post_with_relogin(get_url, post_url, base_data={
                "do": "postthread",
                "f": forum_id,
                "subject": title,
                "message": body,
                "submit": "Submit New Thread",
            })
        except requests.RequestException as e:
            return PostResult(
                False, error_kind=ForumErrorKind.NETWORK,
                error_message=str(e),
            )
        if self._is_login_redirect(r):
            return PostResult(
                False, error_kind=ForumErrorKind.LOGIN_REQUIRED,
                raw_response=(r.text or "")[:4000],
            )
        post_id, thread_id = self._parse_post_id_from_response(r)
        if not post_id:
            return PostResult(
                False, error_kind=ForumErrorKind.UNPARSEABLE_RESPONSE,
                raw_response=(r.text or "")[:4000],
            )
        return PostResult(
            True, post_id=post_id, thread_id=thread_id,
            posted_url=f"{self.base_url}/showthread.php?p={post_id}#post{post_id}",
            raw_response=(r.text or "")[:4000],
        )

    def get_post(self, post_id: str) -> PostBody:
        url = f"{self.base_url}/editpost.php?do=editpost&p={post_id}"
        try:
            r = self._session.get(url, timeout=30, allow_redirects=True)
        except requests.RequestException as e:
            return PostBody(
                False, error_kind=ForumErrorKind.NETWORK,
                error_message=str(e),
            )
        if self._is_login_redirect(r):
            if self._try_relogin():
                r = self._session.get(url, timeout=30, allow_redirects=True)
            else:
                return PostBody(
                    False, error_kind=ForumErrorKind.LOGIN_REQUIRED,
                )
        soup = BeautifulSoup(r.text, "html.parser")
        ta = soup.find("textarea", {"name": "message"})
        if not ta:
            if "do not have permission" in (r.text or "").lower():
                return PostBody(
                    False, error_kind=ForumErrorKind.POST_NOT_FOUND,
                    error_message="no_edit_permission",
                )
            return PostBody(
                False, error_kind=ForumErrorKind.UNPARSEABLE_RESPONSE,
            )
        body = ta.get_text()
        form = soup.find("form")
        thread_id = ""
        if form and form.has_attr("action"):
            qs = parse_qs(urlparse(form["action"]).query)
            thread_id = (qs.get("t", [""])[0]) or ""
        posted_url = (
            f"{self.base_url}/showthread.php?p={post_id}#post{post_id}"
        )
        return PostBody(
            True, post_id=post_id, thread_id=thread_id,
            posted_url=posted_url, body=body,
        )

    def edit_post(self, post_id: str, new_body: str) -> EditResult:
        get_url = f"{self.base_url}/editpost.php?do=editpost&p={post_id}"
        post_url = f"{self.base_url}/editpost.php?do=updatepost"
        try:
            r = self._post_with_relogin(get_url, post_url, base_data={
                "do": "updatepost",
                "postid": post_id,
                "message": new_body,
                "submit": "Save",
            })
        except requests.RequestException as e:
            return EditResult(
                False, error_kind=ForumErrorKind.NETWORK,
                error_message=str(e),
            )
        if self._is_login_redirect(r):
            return EditResult(
                False, error_kind=ForumErrorKind.LOGIN_REQUIRED,
            )
        text = (r.text or "").lower()
        if (
            "the following errors occurred" in text
            or "do not have permission" in text
        ):
            return EditResult(
                False, error_kind=ForumErrorKind.UNKNOWN,
                error_message="forum reported edit failure",
                raw_response=(r.text or "")[:4000],
            )
        return EditResult(True, raw_response=(r.text or "")[:4000])

    def parse_post_reference(self, text_or_url: str) -> Optional[PostRef]:
        s = (text_or_url or "").strip()
        if not s:
            return None
        if s.isdigit():
            return PostRef(post_id=s, thread_id=None, forum_base_url=None)
        try:
            u = urlparse(s)
            if not u.scheme or not u.netloc:
                return None
            qs = parse_qs(u.query)
            post_id = (qs.get("p", [""])[0]) or ""
            thread_id = (qs.get("t", [""])[0]) or None
            if not post_id and u.fragment.startswith("post"):
                post_id = u.fragment[4:]
            if not post_id:
                return None
            return PostRef(
                post_id=post_id, thread_id=thread_id,
                forum_base_url=f"{u.scheme}://{u.netloc}",
            )
        except Exception:
            return None

    def _parse_post_id_from_response(self, resp):
        """Extract (post_id, thread_id) from a vB success response. vB redirects
        to showthread.php?p=NEW#postNEW after post; sometimes also has &t=THREAD."""
        url = getattr(resp, "url", "") or ""
        qs = parse_qs(urlparse(url).query)
        post_id = (qs.get("p", [""])[0]) or None
        thread_id = (qs.get("t", [""])[0]) or None
        if post_id:
            return post_id, thread_id
        m = re.search(
            r"showthread\.php\?(?:t=(\d+)&)?p=(\d+)#post\d+",
            getattr(resp, "text", "") or "",
        )
        if m:
            return m.group(2), m.group(1)
        return None, None
