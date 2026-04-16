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

    def _api_post(self, endpoint: str, body: dict) -> dict:
        """POST to a K2S API endpoint with access_token injected automatically.

        Args:
            endpoint: API endpoint name (e.g. 'getFoldersList', 'getFilesList').
            body: Request body dict. 'access_token' is added automatically.

        Returns:
            Parsed JSON response dict.

        Raises:
            Exception: On HTTP errors or connection failures.
        """
        url = f"{self.api_base}/{endpoint}"
        payload = dict(body)
        payload['access_token'] = self.auth_token
        encoded = json.dumps(payload)

        curl = pycurl.Curl()
        response_buffer = BytesIO()

        try:
            curl.setopt(pycurl.URL, url)
            curl.setopt(pycurl.CAINFO, certifi.where())
            curl.setopt(pycurl.SSL_VERIFYPEER, 1)
            curl.setopt(pycurl.SSL_VERIFYHOST, 2)
            curl.setopt(pycurl.POST, 1)
            curl.setopt(pycurl.POSTFIELDS, encoded)
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

    def get_all_files(self) -> list[dict]:
        """Walk all folders recursively and return a flat list of all file dicts.

        Uses getFoldersList to enumerate folders and getFilesList to enumerate
        files within each folder. Starts from the root ('/') and recurses into
        every subfolder.

        Returns:
            Flat list of file dicts as returned by getFilesList, each containing
            at minimum: id, name, size, is_available, extended_info.
        """
        all_files: list[dict] = []
        self._walk_folder('/', all_files)
        return all_files

    def _walk_folder(self, folder_id: str, all_files: list[dict]) -> None:
        """Recursively collect files from folder_id and all its subfolders.

        Args:
            folder_id: Folder ID to walk ('/') for root.
            all_files: Accumulator list to append file dicts into.
        """
        # Enumerate subfolders
        try:
            resp = self._api_post('getFoldersList', {'parent': folder_id})
            subfolder_ids: list[str] = resp.get('foldersIds', [])
        except Exception as e:
            log(f"K2S getFoldersList failed for folder '{folder_id}': {e}", level="error", category="scanner")
            subfolder_ids = []

        # Enumerate files in this folder (skip root — root has no files directly)
        if folder_id != '/':
            try:
                fresp = self._api_post('getFilesList', {
                    'parent': folder_id,
                    'limit': 10000,
                    'extended_info': True,
                })
                files = fresp.get('files', [])
                all_files.extend(files)
            except Exception as e:
                log(f"K2S getFilesList failed for folder '{folder_id}': {e}", level="error", category="scanner")

        # Recurse into subfolders
        for subfolder_id in subfolder_ids:
            self._walk_folder(subfolder_id, all_files)

    def calc_storage_used(self, files: list[dict]) -> int:
        """Sum sizes of files where extended_info.storage_object == 'available'.

        Args:
            files: List of file dicts as returned by get_all_files().

        Returns:
            Total bytes used by available files.
        """
        total = 0
        for f in files:
            ext = f.get('extended_info', {}) or {}
            if ext.get('storage_object') == 'available':
                total += f.get('size', 0)
        return total

    def check_gallery_from_inventory(
        self,
        file_id_to_url: dict[str, str],
        inventory: dict[str, dict],
    ) -> dict[str, Any]:
        """Check gallery availability from a pre-fetched inventory dict.

        Avoids making any API calls — uses the inventory built by get_all_files().

        Args:
            file_id_to_url: Dict mapping file_id to its download URL.
            inventory: Dict mapping file_id to file dict (keyed by 'id').
                       Build from get_all_files() via {f['id']: f for f in files}.

        Returns:
            Same shape as check_gallery():
            {status, online, offline, errors, total, offline_urls}.
            status is one of: 'online', 'offline', 'partial', 'unknown'.
        """
        if not file_id_to_url:
            return {'status': 'unknown', 'online': 0, 'offline': 0, 'errors': 0, 'total': 0, 'offline_urls': []}

        online = offline = 0
        errors = 0  # kept for shape compat with check_gallery(); always 0 here
        offline_urls: list[str] = []

        for fid, url in file_id_to_url.items():
            file_info = inventory.get(fid)
            if file_info is None:
                # File not found in account — treat as offline
                offline += 1
                offline_urls.append(url)
            else:
                ext = file_info.get('extended_info', {}) or {}
                if ext.get('storage_object') == 'available':
                    online += 1
                else:
                    offline += 1
                    offline_urls.append(url)

        total = len(file_id_to_url)
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

    # ---------------------------------------------------------------------------
    # DEPRECATED — kept for rollback only. Do not use in new code.
    # ---------------------------------------------------------------------------

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

        .. deprecated::
            Use get_all_files() + check_gallery_from_inventory() instead.
            Kept for rollback compatibility.

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

        .. deprecated::
            Use get_all_files() + check_gallery_from_inventory() instead.
            Kept for rollback compatibility.

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
