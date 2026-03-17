"""K2S file availability checker using getFilesInfo API.

Works for Keep2Share, FileBoom, and TezFiles (same API, different domains).
Supports batch checking up to 10,000 file IDs per call.
"""

import json
import pycurl
import certifi
from io import BytesIO
from typing import Dict, List, Optional, Any

from src.utils.logger import log


class K2SFileChecker:
    """Checks file availability on K2S-family hosts via getFilesInfo API."""

    def __init__(self, api_base: str, auth_token: str, batch_size: int = 10000, timeout: int = 30):
        self.api_base = api_base.rstrip('/')
        self.auth_token = auth_token
        self.batch_size = batch_size
        self.timeout = timeout

    def _api_call(self, file_ids: List[str]) -> Dict[str, Any]:
        """Call getFilesInfo API endpoint with a batch of file IDs.

        Args:
            file_ids: List of file IDs to check (max batch_size per call).

        Returns:
            Parsed JSON response dict with 'files' list.

        Raises:
            Exception: On HTTP errors or connection failures.
        """
        url = f"{self.api_base}/getFilesInfo"
        body = json.dumps({"ids": file_ids, "access_token": self.auth_token})

        curl = pycurl.Curl()
        response_buffer = BytesIO()

        try:
            curl.setopt(pycurl.URL, url)
            curl.setopt(pycurl.CAINFO, certifi.where())
            curl.setopt(pycurl.SSL_VERIFYPEER, 1)
            curl.setopt(pycurl.SSL_VERIFYHOST, 2)
            curl.setopt(pycurl.POST, 1)
            curl.setopt(pycurl.POSTFIELDS, body)
            curl.setopt(pycurl.HTTPHEADER, ["Content-Type: application/json"])
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

    def check_files(self, file_ids: List[str]) -> Dict[str, Optional[bool]]:
        """Check availability of files by their IDs.

        Splits into batches of batch_size and calls the API for each batch.
        Files that fail to check (API error, missing from response) get None.

        Args:
            file_ids: List of K2S file IDs to check.

        Returns:
            Dict mapping file_id to True (available), False (unavailable), or None (error).
        """
        if not file_ids:
            return {}

        result: Dict[str, Optional[bool]] = {fid: None for fid in file_ids}

        for i in range(0, len(file_ids), self.batch_size):
            batch = file_ids[i:i + self.batch_size]
            try:
                response = self._api_call(batch)
                files_list = response.get('files', [])
                for file_info in files_list:
                    fid = file_info.get('id')
                    if fid and fid in result:
                        result[fid] = file_info.get('is_available', False)
            except Exception as e:
                log(f"K2S getFilesInfo batch failed: {e}", level="error", category="scanner")

        return result

    def check_gallery(self, file_id_to_url: Dict[str, str]) -> Dict[str, Any]:
        """Check availability of all files in a gallery.

        Args:
            file_id_to_url: Dict mapping file_id to its download URL.

        Returns:
            Dict with keys: status, online, offline, errors, total, offline_urls.
            status is one of: 'online', 'offline', 'partial', 'unknown'.
        """
        if not file_id_to_url:
            return {'status': 'unknown', 'online': 0, 'offline': 0, 'errors': 0, 'total': 0, 'offline_urls': []}

        file_ids = list(file_id_to_url.keys())
        availability = self.check_files(file_ids)

        online = offline = errors = 0
        offline_urls: List[str] = []

        for fid, is_available in availability.items():
            if is_available is True:
                online += 1
            elif is_available is False:
                offline += 1
                if fid in file_id_to_url:
                    offline_urls.append(file_id_to_url[fid])
            else:
                errors += 1

        total = len(file_ids)
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
