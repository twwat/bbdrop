import time
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QCoreApplication

from src.network.forum.client import ForumErrorKind, PostBody, PostResult
from src.processing.forum_posting_worker import (
    FetchJob, ForumPostingWorker, PostJob,
)


@pytest.fixture
def app():
    a = QCoreApplication.instance() or QCoreApplication([])
    yield a


def _drain(app, max_ms=2000):
    deadline = time.monotonic() + max_ms / 1000
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)


def test_post_job_dispatch_calls_post_reply(app):
    client = MagicMock()
    client.post_reply.return_value = PostResult(
        True, post_id="1", thread_id="2", posted_url="u",
    )
    worker = ForumPostingWorker(
        client_factory=lambda fid: client, cooldown_lookup=lambda fid: 0,
    )
    completed = []
    worker.post_completed.connect(lambda *a: completed.append(a))
    worker.start()
    worker.enqueue(PostJob(
        forum_post_id=42, forum_id=1, kind="reply",
        target_id="2", title="", body="hi",
    ))
    _drain(app, 500)
    worker.stop()
    worker.wait(2000)
    assert client.post_reply.called
    assert completed and completed[0][1] is True


def test_cooldown_serializes_posts_to_same_forum(app):
    client = MagicMock()
    timestamps = []

    def record(*a, **kw):
        timestamps.append(time.monotonic())
        return PostResult(True, post_id="x", thread_id="t", posted_url="u")

    client.post_reply.side_effect = record
    worker = ForumPostingWorker(
        client_factory=lambda fid: client, cooldown_lookup=lambda fid: 0.2,
    )
    worker.start()
    worker.enqueue(PostJob(1, 1, "reply", "t", "", "a"))
    worker.enqueue(PostJob(2, 1, "reply", "t", "", "b"))
    _drain(app, 800)
    worker.stop()
    worker.wait(2000)
    assert len(timestamps) == 2
    assert timestamps[1] - timestamps[0] >= 0.18


def test_fetch_job_emits_onboard_completed(app):
    client = MagicMock()
    client.get_post.return_value = PostBody(
        True, post_id="555", thread_id="9", posted_url="u",
        body="hi https://imx.to/i/x",
    )
    worker = ForumPostingWorker(
        client_factory=lambda fid: client, cooldown_lookup=lambda fid: 0,
    )
    captured = []
    payloads = []
    worker.onboard_completed.connect(lambda *a: captured.append(a))
    worker.onboard_payload.connect(lambda *a: payloads.append(a))
    worker.start()
    worker.enqueue(FetchJob(forum_post_id=7, forum_id=1, post_id="555"))
    _drain(app, 500)
    worker.stop()
    worker.wait(2000)
    assert captured and captured[0][1] is True
    assert payloads and payloads[0][1]["body"] == "hi https://imx.to/i/x"
    assert payloads[0][1]["link_map"]["image_hosts"]


def test_post_failure_emits_with_false(app):
    client = MagicMock()
    client.post_reply.return_value = PostResult(
        False, error_kind=ForumErrorKind.NETWORK, error_message="boom",
    )
    worker = ForumPostingWorker(
        client_factory=lambda fid: client, cooldown_lookup=lambda fid: 0,
    )
    captured = []
    worker.post_completed.connect(lambda *a: captured.append(a))
    worker.start()
    worker.enqueue(PostJob(1, 1, "reply", "t", "", "x"))
    _drain(app, 500)
    worker.stop()
    worker.wait(2000)
    assert captured and captured[0][1] is False


def test_login_required_pauses_forum_and_emits_auth_failed(app):
    client = MagicMock()
    client.post_reply.return_value = PostResult(
        False, error_kind=ForumErrorKind.LOGIN_REQUIRED,
        error_message="nope",
    )
    worker = ForumPostingWorker(
        client_factory=lambda fid: client, cooldown_lookup=lambda fid: 0,
    )
    auth_evts = []
    worker.auth_failed.connect(lambda *a: auth_evts.append(a))
    worker.start()
    worker.enqueue(PostJob(1, 5, "reply", "t", "", "x"))
    worker.enqueue(PostJob(2, 5, "reply", "t", "", "y"))
    _drain(app, 500)
    worker.stop()
    worker.wait(2000)
    assert auth_evts and auth_evts[0][0] == 5
    # Second job should not have been processed (forum paused)
    assert client.post_reply.call_count == 1


def test_post_result_payload_carries_ids(app):
    client = MagicMock()
    client.post_reply.return_value = PostResult(
        True, post_id="999", thread_id="42",
        posted_url="https://x/showthread.php?p=999",
    )
    worker = ForumPostingWorker(
        client_factory=lambda fid: client, cooldown_lookup=lambda fid: 0,
    )
    payloads = []
    worker.post_result_payload.connect(lambda *a: payloads.append(a))
    worker.start()
    worker.enqueue(PostJob(99, 1, "reply", "42", "", "x"))
    _drain(app, 500)
    worker.stop()
    worker.wait(2000)
    assert payloads
    fpid, payload = payloads[0]
    assert fpid == 99
    assert payload["posted_post_id"] == "999"
    assert payload["posted_thread_id"] == "42"


def test_queue_changed_signal_emitted_on_enqueue(app):
    client = MagicMock()
    client.post_reply.return_value = PostResult(True, post_id="1")
    worker = ForumPostingWorker(
        client_factory=lambda fid: client, cooldown_lookup=lambda fid: 0,
    )
    events = []
    worker.queue_changed.connect(lambda *a: events.append(a))
    worker.start()
    worker.enqueue(PostJob(1, 7, "reply", "t", "", "x"))
    _drain(app, 300)
    worker.stop()
    worker.wait(2000)
    assert events and events[0][0] == 7
