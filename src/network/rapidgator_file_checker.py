"""RapidGator file availability checker using check_link API.

Accepts up to 25 comma-separated URLs per API call.
Uses token-based authentication (same token from FileHostClient login).
"""

import json
import pycurl
import certifi
from io import BytesIO
from typing import Dict, List, Optional, Any
from urllib.parse import quote

from src.utils.logger import log


class RapidgatorFileChecker:
    """Checks file availability on RapidGator via the check_link API."""

    API_BASE = 'https://rapidgator.net/api/v2'
    BATCH_SIZE = 25

    def __init__(self, auth_token: str, timeout: int = 30):
        self.auth_token = auth_token
        self.timeout = timeout

    def _api_call(self, urls: List[str]) -> Dict[str, Any]:
        """Call the check_link API with a batch of URLs.

        Args:
            urls: List of URLs to check (max BATCH_SIZE).

        Returns:
            Parsed JSON response from the API.

        Raises:
            Exception: On HTTP errors or connection failures.
        """
        url_csv = ','.join(urls)
        api_url = f"{self.API_BASE}/file/check_link?token={self.auth_token}&url={quote(url_csv)}"

        curl = pycurl.Curl()
        response_buffer = BytesIO()

        try:
            curl.setopt(pycurl.URL, api_url)
            curl.setopt(pycurl.CAINFO, certifi.where())
            curl.setopt(pycurl.SSL_VERIFYPEER, 1)
            curl.setopt(pycurl.SSL_VERIFYHOST, 2)
            curl.setopt(pycurl.WRITEDATA, response_buffer)
            curl.setopt(pycurl.TIMEOUT, self.timeout)
            curl.setopt(pycurl.FOLLOWLOCATION, True)

            curl.perform()
            status_code = curl.getinfo(pycurl.RESPONSE_CODE)

            if status_code != 200:
                raise Exception(f"API returned HTTP {status_code}")

            return json.loads(response_buffer.getvalue().decode('utf-8'))
        finally:
            curl.close()

    def check_urls(self, urls: List[str]) -> Dict[str, Optional[bool]]:
        """Check availability of multiple URLs, batching into groups of 25.

        Args:
            urls: List of RapidGator file URLs to check.

        Returns:
            Dict mapping each URL to True (available), False (unavailable),
            or None (error/unknown).
        """
        if not urls:
            return {}

        result: Dict[str, Optional[bool]] = {url: None for url in urls}

        for i in range(0, len(urls), self.BATCH_SIZE):
            batch = urls[i:i + self.BATCH_SIZE]
            try:
                response = self._api_call(batch)
                links = response.get('response', {}).get('links', [])
                for link_info in links:
                    link_url = link_info.get('url', '')
                    link_status = link_info.get('status', 0)
                    if link_url in result:
                        result[link_url] = (link_status == 1)
            except Exception as e:
                log(f"RapidGator check_link batch failed: {e}", level="error", category="scanner")

        return result

    def check_gallery(self, download_urls: List[str]) -> Dict[str, Any]:
        """Check availability of all files in a gallery.

        Args:
            download_urls: List of RapidGator download URLs for the gallery.

        Returns:
            Dict with keys: status, online, offline, errors, total, offline_urls
        """
        if not download_urls:
            return {'status': 'unknown', 'online': 0, 'offline': 0, 'errors': 0, 'total': 0, 'offline_urls': []}

        availability = self.check_urls(download_urls)

        online = offline = errors = 0
        offline_urls = []

        for url, is_available in availability.items():
            if is_available is True:
                online += 1
            elif is_available is False:
                offline += 1
                offline_urls.append(url)
            else:
                errors += 1

        total = len(download_urls)
        if total == 0:
            status = 'unknown'
        elif offline == 0 and errors == 0:
            status = 'online'
        elif online == 0 and errors == 0:
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
