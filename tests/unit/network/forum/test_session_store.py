import time

from src.network.forum.session_store import SessionStore, ForumSession


def test_set_and_get():
    s = SessionStore()
    s.set(1, ForumSession(
        cookies={"bb_userid": "42"},
        last_securitytoken=None,
        last_login_ts=time.time(),
        last_login_username="u",
    ))
    got = s.get(1)
    assert got is not None
    assert got.cookies["bb_userid"] == "42"


def test_get_missing_returns_none():
    s = SessionStore()
    assert s.get(99) is None


def test_clear():
    s = SessionStore()
    s.set(1, ForumSession({}, None, 0.0, "u"))
    s.clear(1)
    assert s.get(1) is None


def test_clear_missing_is_noop():
    s = SessionStore()
    s.clear(1)
    assert s.get(1) is None


def test_overwrite_replaces():
    s = SessionStore()
    s.set(1, ForumSession({"a": "1"}, None, 0.0, "alice"))
    s.set(1, ForumSession({"b": "2"}, "tok", 1.0, "bob"))
    got = s.get(1)
    assert got.cookies == {"b": "2"}
    assert got.last_securitytoken == "tok"
    assert got.last_login_username == "bob"


def test_separate_forums_isolated():
    s = SessionStore()
    s.set(1, ForumSession({"x": "1"}, None, 0.0, "u1"))
    s.set(2, ForumSession({"x": "2"}, None, 0.0, "u2"))
    assert s.get(1).cookies["x"] == "1"
    assert s.get(2).cookies["x"] == "2"
