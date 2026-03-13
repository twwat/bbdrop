"""Thumbnail liveness checker using HEAD requests + ETag detection.

Checks a gallery's thumbnail URLs to determine if images are still online
on non-IMX image hosts. Uses the dead-image ETag catalog for detection
since hosts return HTTP 200 with placeholder images for removed content.
"""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List, Optional, Callable

from src.network.dead_image_etags import check_thumbnail_head, EARLY_EXIT_THRESHOLD
from src.utils.logger import log


class ThumbnailChecker:
    """Checks thumbnail URLs via HEAD requests with ETag-based dead-image detection.

    Supports:
    - Concurrent checking with configurable max_workers
    - Early-exit: if first N thumbnails are all offline, assume gallery is dead
    - Cancellation via threading.Event
    - Progress callbacks
    """

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers

    def check_gallery(
        self,
        thumb_urls: List[str],
        early_exit_threshold: int = EARLY_EXIT_THRESHOLD,
        cancel_event: Optional[threading.Event] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, Any]:
        """Check all thumbnail URLs for a single gallery.

        Args:
            thumb_urls: List of thumbnail URLs to check.
            early_exit_threshold: If the first N thumbs are all offline, skip rest.
            cancel_event: Optional event to signal cancellation.
            progress_callback: Optional callback(checked_count, total_count).

        Returns:
            Dict with keys: status, online, offline, errors, total, offline_urls
        """
        total = len(thumb_urls)
        if total == 0:
            return {'status': 'unknown', 'online': 0, 'offline': 0, 'errors': 0, 'total': 0, 'offline_urls': []}

        online = 0
        offline = 0
        errors = 0
        offline_urls: List[str] = []
        checked = 0
        lock = threading.Lock()
        early_exit_triggered = threading.Event()

        def _check_one(url: str) -> None:
            nonlocal online, offline, errors, checked

            if cancel_event and cancel_event.is_set():
                return
            if early_exit_triggered.is_set():
                return

            result = check_thumbnail_head(url)

            with lock:
                checked += 1
                if result['status'] == 'online':
                    online += 1
                elif result['status'] == 'offline':
                    offline += 1
                    offline_urls.append(url)
                else:
                    errors += 1

                if progress_callback:
                    progress_callback(checked, total)

        # Phase 1: Check first `early_exit_threshold` URLs for early-exit
        early_batch = thumb_urls[:early_exit_threshold]
        remaining = thumb_urls[early_exit_threshold:]

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(_check_one, url) for url in early_batch]
            for f in as_completed(futures):
                f.result()  # Propagate exceptions

        # Check if early-exit applies
        if checked > 0 and online == 0 and remaining:
            early_exit_triggered.set()
            log(f"Early-exit: first {checked} thumbnails all offline, skipping remaining {len(remaining)}",
                level="debug", category="scanner")
            offline += len(remaining)
            if progress_callback:
                progress_callback(total, total)
        elif remaining and not (cancel_event and cancel_event.is_set()):
            # Phase 2: Check remaining URLs
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = [executor.submit(_check_one, url) for url in remaining]
                for f in as_completed(futures):
                    f.result()

        # Determine overall status
        actual_total = online + offline + errors
        if actual_total == 0:
            status = 'unknown'
        elif offline == 0 and errors == 0:
            status = 'online'
        elif online == 0:
            status = 'offline'
        else:
            status = 'partial'

        return {
            'status': status,
            'online': online,
            'offline': offline,
            'errors': errors,
            'total': total,
            'offline_urls': offline_urls,
        }
