from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from requests.cookies import RequestsCookieJar

from src.network.forum.client import ForumErrorKind
from src.network.forum.session_store import SessionStore
from src.network.forum.vbulletin_client import VBulletinClient


def _jar(**cookies) -> RequestsCookieJar:
    j = RequestsCookieJar()
    for k, v in cookies.items():
        j.set(k, v)
    return j


FIX = Path(__file__).parents[3] / "fixtures"


def _fixture(name: str) -> str:
    return (FIX / name).read_text()


def _resp(status=200, text="", url="", headers=None, cookies=None):
    r = MagicMock()
    r.status_code = status
    r.text = text
    r.url = url
    r.headers = headers or {}
    r.cookies = cookies or {}
    return r


@pytest.fixture
def client():
    return VBulletinClient(
        base_url="https://vipergirls.to",
        session_store=SessionStore(),
    )


def test_authenticate_success_via_thank_you_text(client):
    with patch.object(client, "_session") as sess:
        sess.get.return_value = _resp(200, "<html>home</html>")
        sess.post.return_value = _resp(
            200, "<html>Thank you for logging in, testuser</html>",
        )
        sess.cookies = _jar()  # no userid cookie present
        result = client.authenticate("testuser", "secret")
    assert result.success
    assert result.error_kind == ForumErrorKind.OK


def test_authenticate_success_via_userid_cookie(client):
    with patch.object(client, "_session") as sess:
        sess.get.return_value = _resp(200, "<html>home</html>")
        sess.post.return_value = _resp(200, "<html>welcome page</html>")
        sess.cookies = _jar(bb_userid="42")
        result = client.authenticate("testuser", "secret")
    assert result.success


def test_authenticate_failure_when_no_signal(client):
    with patch.object(client, "_session") as sess:
        sess.get.return_value = _resp(200, "<html>home</html>")
        sess.post.return_value = _resp(200, "<html>Wrong password</html>")
        sess.cookies = _jar()
        result = client.authenticate("testuser", "wrong")
    assert not result.success
    assert result.error_kind == ForumErrorKind.LOGIN_REQUIRED
    assert "login_failed" in result.error_message


def test_authenticate_failure_when_userid_zero(client):
    with patch.object(client, "_session") as sess:
        sess.get.return_value = _resp(200, "<html>home</html>")
        sess.post.return_value = _resp(200, "<html>nothing</html>")
        sess.cookies = _jar(bb_userid="0")
        result = client.authenticate("testuser", "wrong")
    assert not result.success
    assert result.error_kind == ForumErrorKind.LOGIN_REQUIRED


def test_authenticate_network_error(client):
    import requests as rq
    with patch.object(client, "_session") as sess:
        sess.get.side_effect = rq.ConnectionError("boom")
        result = client.authenticate("u", "p")
    assert not result.success
    assert result.error_kind == ForumErrorKind.NETWORK


def test_post_reply_scrapes_token_then_posts(client):
    with patch.object(client, "_session") as sess:
        sess.get.return_value = _resp(200, _fixture("vb_newreply_form.html"))
        sess.post.return_value = _resp(
            200,
            '<html>Reply posted. '
            '<a href="showthread.php?p=999999#post999999">view</a></html>',
            url="https://vipergirls.to/showthread.php?p=999999",
        )
        result = client.post_reply("12345", "[b]hello[/b]")
    assert result.success
    assert result.post_id == "999999"
    assert result.thread_id == "12345"
    posted = sess.post.call_args.kwargs.get("data") or sess.post.call_args.args[1]
    assert posted["securitytoken"] == "1730000000-abcdefg"
    assert posted["message"] == "[b]hello[/b]"


def test_post_reply_retries_on_stale_token(client):
    with patch.object(client, "_session") as sess:
        sess.get.side_effect = [
            _resp(200, _fixture("vb_newreply_form.html")),
            _resp(200, _fixture("vb_newreply_form.html")),
        ]
        sess.post.side_effect = [
            _resp(200, "<html>Your security token is invalid.</html>"),
            _resp(
                200,
                '<a href="showthread.php?p=999999#post999999">view</a>',
                url="https://vipergirls.to/showthread.php?p=999999",
            ),
        ]
        result = client.post_reply("12345", "x")
    assert result.success
    assert sess.post.call_count == 2


def test_post_reply_relogins_on_redirect_to_login(client):
    with patch.object(client, "_session") as sess:
        sess.get.side_effect = [
            _resp(
                200, "<html>You are not logged in</html>",
                url="https://vipergirls.to/login.php?do=login",
            ),
            _resp(200, "<html>home</html>"),  # pre-flight GET inside re-login
            _resp(200, _fixture("vb_newreply_form.html")),
        ]
        sess.post.side_effect = [
            _resp(
                200, "<html>Thank you for logging in, testuser</html>",
            ),
            _resp(
                200, '<a href="showthread.php?p=1#post1">v</a>',
                url="https://vipergirls.to/showthread.php?p=1",
            ),
        ]
        sess.cookies = _jar()
        client._cached_creds = ("testuser", "secret")
        result = client.post_reply("12345", "x")
    assert result.success


def test_post_reply_login_required_when_no_creds(client):
    with patch.object(client, "_session") as sess:
        sess.get.return_value = _resp(
            200, "<html>You are not logged in</html>",
            url="https://vipergirls.to/login.php?do=login",
        )
        # No cached creds → relogin fails → returns get_resp which is login redirect
        result = client.post_reply("12345", "x")
    assert not result.success
    assert result.error_kind == ForumErrorKind.LOGIN_REQUIRED


def test_post_reply_unparseable_response(client):
    with patch.object(client, "_session") as sess:
        sess.get.return_value = _resp(200, _fixture("vb_newreply_form.html"))
        sess.post.return_value = _resp(200, "<html>weird</html>", url="")
        result = client.post_reply("12345", "x")
    assert not result.success
    assert result.error_kind == ForumErrorKind.UNPARSEABLE_RESPONSE


def test_create_thread_returns_post_and_thread_ids(client):
    with patch.object(client, "_session") as sess:
        sess.get.return_value = _resp(200, _fixture("vb_newthread_form.html"))
        sess.post.return_value = _resp(
            200,
            '<a href="showthread.php?t=2222&p=33333#post33333">v</a>',
            url="https://vipergirls.to/showthread.php?t=2222&p=33333",
        )
        result = client.create_thread("99", "title", "body")
    assert result.success
    assert result.post_id == "33333"
    assert result.thread_id == "2222"


def test_get_post_returns_raw_bbcode_via_editpost(client):
    with patch.object(client, "_session") as sess:
        sess.get.return_value = _resp(200, _fixture("vb_editpost_form.html"))
        result = client.get_post("555")
    assert result.success
    assert result.body == "old body content"
    assert result.post_id == "555"
    assert result.thread_id == "12345"


def test_get_post_no_permission(client):
    with patch.object(client, "_session") as sess:
        sess.get.return_value = _resp(
            200, "<html>You do not have permission to edit this post</html>",
        )
        result = client.get_post("555")
    assert not result.success
    assert result.error_kind == ForumErrorKind.POST_NOT_FOUND


def test_edit_post_succeeds(client):
    with patch.object(client, "_session") as sess:
        sess.get.return_value = _resp(200, _fixture("vb_editpost_form.html"))
        sess.post.return_value = _resp(200, "<html>OK</html>")
        result = client.edit_post("555", "new body")
    assert result.success


def test_edit_post_reports_failure(client):
    with patch.object(client, "_session") as sess:
        sess.get.return_value = _resp(200, _fixture("vb_editpost_form.html"))
        sess.post.return_value = _resp(
            200, "<html>The following errors occurred: bad</html>",
        )
        result = client.edit_post("555", "x")
    assert not result.success
    assert result.error_kind == ForumErrorKind.UNKNOWN


def test_parse_post_reference_bare_id(client):
    ref = client.parse_post_reference("999999")
    assert ref.post_id == "999999"
    assert ref.forum_base_url is None
    assert ref.thread_id is None


def test_parse_post_reference_full_url(client):
    ref = client.parse_post_reference(
        "https://vipergirls.to/showthread.php?p=999999",
    )
    assert ref.post_id == "999999"
    assert ref.forum_base_url == "https://vipergirls.to"


def test_parse_post_reference_thread_with_anchor(client):
    ref = client.parse_post_reference(
        "https://vipergirls.to/showthread.php?t=12345&p=999999#post999999",
    )
    assert ref.post_id == "999999"
    assert ref.thread_id == "12345"
    assert ref.forum_base_url == "https://vipergirls.to"


def test_parse_post_reference_anchor_only(client):
    ref = client.parse_post_reference(
        "https://vipergirls.to/showthread.php?t=12345#post777",
    )
    assert ref.post_id == "777"
    assert ref.thread_id == "12345"


def test_parse_post_reference_invalid(client):
    assert client.parse_post_reference("not a url or id") is None


def test_parse_post_reference_empty(client):
    assert client.parse_post_reference("") is None
    assert client.parse_post_reference("   ") is None


def test_is_logged_in_true_when_authenticated_flag_set(client):
    client._authenticated = True
    assert client.is_logged_in()


def test_is_logged_in_true_when_userid_cookie_present(client):
    client._session.cookies.set("bb_userid", "42")
    assert client.is_logged_in()


def test_is_logged_in_false_when_zero(client):
    client._session.cookies.set("bb_userid", "0")
    assert not client.is_logged_in()


def test_logout_clears_session(client):
    client._session.cookies.set("bb_userid", "42")
    client._username = "u"
    client._authenticated = True
    client.logout()
    assert not client.is_logged_in()
    assert client._username is None
    assert client._authenticated is False


# ---------------------------------------------------------------------------
# parse_target_url
# ---------------------------------------------------------------------------

def test_parse_target_url_classic_forumdisplay(client):
    r = client.parse_target_url("https://vipergirls.to/forumdisplay.php?f=12")
    assert r.kind == "subforum" and r.target_id == "12"
    assert r.forum_base_url == "https://vipergirls.to"


def test_parse_target_url_classic_showthread(client):
    r = client.parse_target_url("https://vipergirls.to/showthread.php?t=9001")
    assert r.kind == "thread" and r.target_id == "9001"


def test_parse_target_url_showthread_with_post_fragment(client):
    r = client.parse_target_url(
        "https://vipergirls.to/showthread.php?t=9001&p=12345#post12345",
    )
    assert r.kind == "thread" and r.target_id == "9001"


def test_parse_target_url_post_only_returns_none(client):
    # Post URL without t= can't reliably give a thread id without fetching.
    assert client.parse_target_url(
        "https://vipergirls.to/showthread.php?p=12345#post12345",
    ) is None


def test_parse_target_url_friendly_forums(client):
    r = client.parse_target_url(
        "https://vipergirls.to/forums/12-Celebrity-Photos",
    )
    assert r.kind == "subforum" and r.target_id == "12"
    assert r.name == "Celebrity Photos"


def test_parse_target_url_friendly_threads(client):
    r = client.parse_target_url(
        "https://vipergirls.to/threads/9001-Daily-Dump-Thread",
    )
    assert r.kind == "thread" and r.target_id == "9001"
    assert r.name == "Daily Dump Thread"


def test_parse_target_url_friendly_without_slug(client):
    r = client.parse_target_url("https://vipergirls.to/threads/9001")
    assert r.kind == "thread" and r.target_id == "9001"
    assert r.name == "thread 9001"


def test_parse_target_url_rejects_empty_and_non_url(client):
    assert client.parse_target_url("") is None
    assert client.parse_target_url("   ") is None
    assert client.parse_target_url("not a url") is None
    assert client.parse_target_url("12345") is None
