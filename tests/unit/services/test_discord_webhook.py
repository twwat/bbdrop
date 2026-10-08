"""DiscordWebhookSender: URL validation, safe payloads, retries, no URL leaks."""

import threading
from unittest.mock import patch

import pytest
import requests

from src.services.discord_webhook import (
    DiscordWebhookSender, MAX_CONTENT, QUEUE_MAX, REQUEST_TIMEOUT,
)

URL = "https://discord.com/api/webhooks/123456789/SECRETTOKEN_abc-def"


class FakeResponse:
    def __init__(self, status_code=204, json_body=None, headers=None):
        self.status_code = status_code
        self._json = json_body
        self.headers = headers or {}

    def json(self):
        if self._json is None:
            raise ValueError("no json body")
        return self._json


class FakePost:
    """Stand-in for requests.post. Replays responses; the last one repeats."""

    def __init__(self, *responses):
        self.responses = list(responses) or [FakeResponse()]
        self.calls = []            # (url, json, timeout)
        self.threads = []
        self.entered = threading.Event()
        self.release = None        # set to an Event to block inside post()

    def __call__(self, url, json=None, timeout=None):
        self.calls.append((url, json, timeout))
        self.threads.append(threading.current_thread())
        self.entered.set()
        if self.release is not None:
            self.release.wait(5)
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(r, Exception):
            raise r
        return r


def make(*responses, url=URL):
    post = FakePost(*responses)
    sleeps = []
    sender = DiscordWebhookSender(post=post, sleep=sleeps.append)
    sender.set_url(url)
    return sender, post, sleeps


def drain(sender):
    sender._queue.join()


class TestIsValidUrl:
    @pytest.mark.parametrize("url", [
        "https://discord.com/api/webhooks/1/abc",
        "https://discordapp.com/api/webhooks/1/abc",
        "https://canary.discord.com/api/webhooks/1/abc",
        "https://ptb.discord.com/api/webhooks/1/abc",
        URL,
    ])
    def test_is_valid_url_accepts(self, url):
        assert DiscordWebhookSender.is_valid_url(url) is True

    @pytest.mark.parametrize("url", [
        "http://discord.com/api/webhooks/1/abc",
        "https://evil.com/api/webhooks/1/abc",
        "https://discord.com.evil.net/api/webhooks/1/abc",
        "https://evil.com/discord.com/api/webhooks/1/abc",
        "https://discord.com@evil.com/api/webhooks/1/abc",
        "https://discord.com/api/webhooks/abc/def",
        "https://discord.com/api/webhooks/1/",
        "https://discord.com/api/webhooks/1/abc?wait=true",
        "https://discord.com/api/webhooks/1/abc\n",
        "",
        None,
    ])
    def test_is_valid_url_rejects(self, url):
        assert DiscordWebhookSender.is_valid_url(url) is False


class TestSetUrl:
    def test_set_url_strips_whitespace(self):
        sender, post, _ = make(url="  " + URL + " \n")
        assert sender.has_url is True
        sender.send("hi")
        drain(sender)
        assert post.calls[0][0] == URL

    def test_set_url_rejects_invalid(self):
        with patch('src.services.discord_webhook.log') as log:
            sender, post, _ = make(url="https://evil.com/api/webhooks/1/abc")
        assert sender.has_url is False
        assert log.called

    def test_send_without_url_does_nothing(self):
        sender, post, _ = make(url="")
        sender.send("hi")
        assert post.calls == []
        assert sender._thread is None


class TestSend:
    def test_send_delivers_on_background_thread(self):
        sender, post, _ = make()
        sender.send("hello")
        drain(sender)
        assert len(post.calls) == 1
        assert post.threads[0] is not threading.current_thread()
        assert post.threads[0].daemon is True

    def test_payload_has_content_timeout_and_no_mentions(self):
        sender, post, _ = make()
        sender.send("@everyone ping")
        drain(sender)
        url, body, timeout = post.calls[0]
        assert url == URL
        assert body == {"content": "@everyone ping",
                        "allowed_mentions": {"parse": []}}
        assert timeout == REQUEST_TIMEOUT

    def test_payload_truncates_long_messages(self):
        sender, post, _ = make()
        sender.send("x" * 5000)
        drain(sender)
        assert len(post.calls[0][1]["content"]) == MAX_CONTENT

    def test_429_waits_retry_after_then_retries_once(self):
        sender, post, sleeps = make(
            FakeResponse(429, {"retry_after": 1.5}), FakeResponse(204))
        sender.send("hi")
        drain(sender)
        assert len(post.calls) == 2
        assert sleeps == [1.5]

    def test_429_wait_is_capped(self):
        sender, post, sleeps = make(
            FakeResponse(429, {"retry_after": 999}), FakeResponse(204))
        sender.send("hi")
        drain(sender)
        assert sleeps == [30.0]

    def test_429_falls_back_to_retry_after_header(self):
        sender, post, sleeps = make(
            FakeResponse(429, None, {"Retry-After": "3"}), FakeResponse(204))
        sender.send("hi")
        drain(sender)
        assert sleeps == [3.0]

    def test_second_429_drops_message_with_warning(self):
        with patch('src.services.discord_webhook.log') as log:
            sender, post, _ = make(FakeResponse(429, {"retry_after": 0.1}))
            sender.send("hi")
            drain(sender)
        assert len(post.calls) == 2
        assert log.called

    def test_http_error_is_dropped_and_next_message_still_sent(self):
        sender, post, _ = make(FakeResponse(500), FakeResponse(204))
        sender.send("one")
        sender.send("two")
        drain(sender)
        assert len(post.calls) == 2

    def test_network_exception_does_not_kill_the_thread(self):
        sender, post, _ = make(
            requests.ConnectionError("boom"), FakeResponse(204))
        sender.send("one")
        sender.send("two")
        drain(sender)
        assert len(post.calls) == 2

    def test_url_token_never_logged(self):
        err = requests.ConnectionError(f"Max retries exceeded with url: {URL}")
        with patch('src.services.discord_webhook.log') as log:
            sender, post, _ = make(err, FakeResponse(500), FakeResponse(429))
            sender.send("one")
            sender.send("two")
            drain(sender)
        assert "SECRETTOKEN" not in str(log.call_args_list)

    def test_queue_is_capped_and_overflow_dropped(self):
        sender, post, _ = make()
        post.release = threading.Event()
        sender.send("m0")
        assert post.entered.wait(2)           # worker took m0 and is blocked
        for i in range(1, QUEUE_MAX + 1):
            sender.send(f"m{i}")              # fills the queue exactly
        with patch('src.services.discord_webhook.log') as log:
            sender.send("overflow")
        assert log.called
        post.release.set()
        drain(sender)
        sent = [c[1]["content"] for c in post.calls]
        assert len(sent) == QUEUE_MAX + 1
        assert "overflow" not in sent

    def test_shutdown_stops_the_thread(self):
        sender, post, _ = make()
        sender.send("hi")
        drain(sender)
        sender.shutdown()
        assert not sender._thread.is_alive()


class TestSendTest:
    def test_send_test_success(self):
        sender, post, _ = make()
        assert sender.send_test() == (True, "")
        assert post.calls[0][0] == URL
        assert post.calls[0][1]["allowed_mentions"] == {"parse": []}

    def test_send_test_uses_given_url_not_stored(self):
        sender, post, _ = make(url="")
        other = "https://discord.com/api/webhooks/9/zzz"
        assert sender.send_test(other) == (True, "")
        assert post.calls[0][0] == other

    def test_send_test_rejects_invalid_url_without_posting(self):
        sender, post, _ = make(url="")
        ok, reason = sender.send_test("https://evil.com/x")
        assert ok is False and "Discord webhook" in reason
        assert post.calls == []

    def test_send_test_unknown_webhook(self):
        sender, _, _ = make(FakeResponse(404))
        ok, reason = sender.send_test()
        assert ok is False and "recognise" in reason

    def test_send_test_rate_limited(self):
        sender, _, _ = make(FakeResponse(429))
        ok, reason = sender.send_test()
        assert ok is False and "rate" in reason.lower()

    def test_send_test_other_http_error(self):
        sender, _, _ = make(FakeResponse(500))
        assert sender.send_test() == (False, "Discord rejected the message (HTTP 500)")

    def test_send_test_failure_does_not_log_token(self):
        err = requests.ConnectionError(f"url: {URL}")
        with patch('src.services.discord_webhook.log') as log:
            sender, _, _ = make(err)
            ok, reason = sender.send_test()
        assert (ok, reason) == (False, "Could not reach Discord")
        assert "SECRETTOKEN" not in str(log.call_args_list)
        assert "SECRETTOKEN" not in reason
