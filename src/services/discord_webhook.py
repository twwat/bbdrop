"""Discord webhook delivery for BBDrop notifications.

Messages are queued and posted by one daemon thread so callers (which run on
the GUI thread) never block on the network. Only real Discord webhook URLs are
accepted, mentions are always suppressed, and the URL (which contains a secret
token) is never logged -- ``requests`` exceptions embed it, so only exception
type names are logged.
"""

import queue
import re
import threading
import time
from typing import Callable, Optional, Tuple

import requests

from src.utils.logger import log

MAX_CONTENT = 2000
QUEUE_MAX = 50
REQUEST_TIMEOUT = 10
MAX_RETRY_WAIT = 30.0
DEFAULT_RETRY_WAIT = 2.0

_URL_RE = re.compile(
    r'https://(?:(?:canary\.|ptb\.)?discord\.com|discordapp\.com)'
    r'/api/webhooks/\d+/[A-Za-z0-9_\-]+'
)


def _payload(message: str) -> dict:
    return {
        "content": message[:MAX_CONTENT],
        # An empty parse list stops @everyone, @here and user/role pings.
        "allowed_mentions": {"parse": []},
    }


def _retry_after(response) -> float:
    """Seconds Discord asks us to wait: JSON body, then header, then default."""
    try:
        value = float(response.json().get('retry_after'))
    except Exception:
        try:
            value = float(response.headers.get('Retry-After'))
        except Exception:
            value = DEFAULT_RETRY_WAIT
    return max(0.0, value)


class DiscordWebhookSender:
    """Non-blocking, URL-validated Discord webhook poster."""

    def __init__(self, post: Callable = requests.post,
                 sleep: Callable[[float], None] = time.sleep):
        self._post = post
        self._sleep = sleep
        self._url = ''
        self._queue: queue.Queue = queue.Queue(maxsize=QUEUE_MAX)
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._stop = threading.Event()

    # -- configuration -------------------------------------------------

    @staticmethod
    def is_valid_url(url) -> bool:
        return isinstance(url, str) and _URL_RE.fullmatch(url) is not None

    def set_url(self, url: Optional[str]) -> None:
        """Set the webhook URL. Empty or invalid means "do not send"."""
        url = (url or '').strip()
        if url and not self.is_valid_url(url):
            log("Discord webhook URL rejected: not a Discord webhook URL",
                level="warning", category="notifications")
            url = ''
        self._url = url

    @property
    def has_url(self) -> bool:
        return bool(self._url)

    # -- sending -------------------------------------------------------

    def send(self, message: str) -> None:
        """Queue a message; returns immediately."""
        if not self._url:
            return
        self._ensure_thread()
        try:
            self._queue.put_nowait(message)
        except queue.Full:
            log("Discord notification dropped: send queue is full",
                level="warning", category="notifications")

    def send_test(self, url: Optional[str] = None) -> Tuple[bool, str]:
        """Post a test message now. ``url=None`` tests the stored URL."""
        target = (self._url if url is None else url).strip()
        if not self.is_valid_url(target):
            return False, "That is not a Discord webhook URL"
        try:
            response = self._post(
                target,
                json=_payload("✅ BBDrop test message — Discord notifications are working."),
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as e:
            log(f"Discord test message failed ({type(e).__name__})",
                level="warning", category="notifications")
            return False, "Could not reach Discord"
        status = response.status_code
        if 200 <= status < 300:
            return True, ""
        if status in (401, 404):
            return False, "Discord does not recognise that webhook (it may have been deleted)"
        if status == 429:
            return False, "Discord is rate limiting this webhook - try again in a few seconds"
        return False, f"Discord rejected the message (HTTP {status})"

    def shutdown(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2)

    # -- worker --------------------------------------------------------

    def _ensure_thread(self) -> None:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._stop.clear()
                self._thread = threading.Thread(
                    target=self._run, name="DiscordWebhook", daemon=True)
                self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                message = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self._deliver(message)
            except Exception as e:  # never let one message kill the thread
                log(f"Discord notification failed ({type(e).__name__})",
                    level="warning", category="notifications")
            finally:
                self._queue.task_done()

    def _deliver(self, message: str) -> None:
        url = self._url
        if not url:
            return
        status, retry_after = self._post_once(url, message)
        if status == 429:
            self._sleep(min(retry_after, MAX_RETRY_WAIT))
            status, _ = self._post_once(url, message)
            if status == 429:
                log("Discord notification dropped: rate limited twice",
                    level="warning", category="notifications")
                return
        if status is not None and not 200 <= status < 300:
            log(f"Discord rejected a notification (HTTP {status})",
                level="warning", category="notifications")

    def _post_once(self, url: str, message: str) -> Tuple[Optional[int], float]:
        try:
            response = self._post(url, json=_payload(message),
                                  timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            log(f"Could not reach Discord ({type(e).__name__})",
                level="warning", category="notifications")
            return None, 0.0
        retry_after = _retry_after(response) if response.status_code == 429 else 0.0
        return response.status_code, retry_after
