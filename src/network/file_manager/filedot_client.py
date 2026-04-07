"""Filedot file manager client (web scraping).

Filedot runs XFileSharing Pro but has NOT enabled the API mod.
All operations go through the web panel with session cookie auth.

Currently supports:
- List files (scrape /?op=my_files)
- Delete files (POST /?op=my_files with del_code)

Other operations (rename, move, create folder) are not confirmed
available and are reported as unsupported via get_capabilities().
"""

from __future__ import annotations

import re
import pycurl
import certifi
from io import BytesIO
from typing import Dict, List, Optional

from src.network.file_manager.client import (
    BatchResult,
    FileInfo,
    FileListResult,
    FileManagerCapabilities,
    FileManagerClient,
    FolderListResult,
    OperationResult,
)
from src.utils.logger import log

FILEDOT_CAPABILITIES = FileManagerCapabilities(
    can_rename=False,
    can_move=False,
    can_delete=True,
    can_copy=False,
    can_change_access=False,
    can_create_folder=False,
    can_remote_upload=False,
    can_trash=False,
    can_get_download_link=True,
    has_batch_operations=False,
    max_items_per_page=50,
    sortable_columns=["name"],
)

# Regex patterns for scraping the my_files page
_FILE_ROW_RE = re.compile(
    r'<a[^>]*href="https?://filedot\.(?:to|xyz)/([a-z0-9]+)[^"]*"[^>]*>'
    r'\s*(.*?)\s*</a>'
    r'.*?<td[^>]*>\s*([\d.]+\s*[KMGT]?B)\s*</td>',
    re.DOTALL | re.IGNORECASE,
)

_PAGE_COUNT_RE = re.compile(
    r'>\s*(\d+)\s*</a>\s*(?:</div>|<a[^>]*>Next)',
    re.IGNORECASE,
)

# Size parsing
_SIZE_MULTIPLIERS = {
    "B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4,
}


def _parse_size(size_str: str) -> int:
    """Parse '2.4 GB' or '890 MB' to bytes."""
    size_str = size_str.strip().upper()
    for suffix, mult in sorted(_SIZE_MULTIPLIERS.items(), key=lambda x: -len(x[0])):
        if size_str.endswith(suffix):
            try:
                return int(float(size_str[:-len(suffix)].strip()) * mult)
            except ValueError:
                return 0
    return 0


class FiledotFileManagerClient(FileManagerClient):
    """File manager for Filedot via web scraping."""

    def __init__(self, session_cookie: str, sess_id: str = "", timeout: int = 30):
        """
        Args:
            session_cookie: Session cookie value from login.
            sess_id: CSRF-like session ID scraped from the upload page.
            timeout: Request timeout in seconds.
        """
        self.session_cookie = session_cookie
        self.sess_id = sess_id
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Low-level web request
    # ------------------------------------------------------------------

    def _web_get(self, url: str) -> str:
        """GET request with session cookie."""
        curl = pycurl.Curl()
        buf = BytesIO()
        header_buf = BytesIO()

        try:
            curl.setopt(pycurl.URL, url)
            curl.setopt(pycurl.CAINFO, certifi.where())
            curl.setopt(pycurl.SSL_VERIFYPEER, 1)
            curl.setopt(pycurl.SSL_VERIFYHOST, 2)
            curl.setopt(pycurl.WRITEDATA, buf)
            curl.setopt(pycurl.HEADERFUNCTION, header_buf.write)
            curl.setopt(pycurl.TIMEOUT, self.timeout)
            curl.setopt(pycurl.FOLLOWLOCATION, True)
            curl.setopt(pycurl.COOKIE, self.session_cookie)
            curl.setopt(pycurl.USERAGENT,
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )

            curl.perform()
            status = curl.getinfo(pycurl.RESPONSE_CODE)
        finally:
            curl.close()

        if status != 200:
            raise RuntimeError(f"Filedot web request returned HTTP {status}")

        return buf.getvalue().decode("utf-8", errors="replace")

    def _web_post(self, url: str, fields: dict) -> str:
        """POST form data with session cookie."""
        curl = pycurl.Curl()
        buf = BytesIO()

        # Build multipart form
        form_data = []
        for key, value in fields.items():
            form_data.append((key, (pycurl.FORM_CONTENTS, str(value))))

        try:
            curl.setopt(pycurl.URL, url)
            curl.setopt(pycurl.CAINFO, certifi.where())
            curl.setopt(pycurl.SSL_VERIFYPEER, 1)
            curl.setopt(pycurl.SSL_VERIFYHOST, 2)
            curl.setopt(pycurl.WRITEDATA, buf)
            curl.setopt(pycurl.TIMEOUT, self.timeout)
            curl.setopt(pycurl.FOLLOWLOCATION, True)
            curl.setopt(pycurl.COOKIE, self.session_cookie)
            curl.setopt(pycurl.HTTPPOST, form_data)
            curl.setopt(pycurl.USERAGENT,
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )

            curl.perform()
            status = curl.getinfo(pycurl.RESPONSE_CODE)
        finally:
            curl.close()

        if status not in (200, 302):
            raise RuntimeError(f"Filedot web POST returned HTTP {status}")

        return buf.getvalue().decode("utf-8", errors="replace")

    # ------------------------------------------------------------------
    # Abstract method implementations
    # ------------------------------------------------------------------

    def list_files(
        self,
        folder_id: str = "/",
        page: int = 1,
        per_page: int = 50,
        sort_by: str = "name",
        sort_dir: str = "asc",
    ) -> FileListResult:
        url = f"https://filedot.to/?op=my_files&page={page}"

        html = self._web_get(url)

        files = []
        for match in _FILE_ROW_RE.finditer(html):
            file_code = match.group(1)
            name = re.sub(r'<[^>]+>', '', match.group(2)).strip()
            size_str = match.group(3)

            files.append(FileInfo(
                id=file_code,
                name=name or file_code,
                is_folder=False,
                size=_parse_size(size_str),
                is_available=True,
            ))

        # Try to find total pages
        total_pages = 1
        page_matches = _PAGE_COUNT_RE.findall(html)
        if page_matches:
            try:
                total_pages = max(int(p) for p in page_matches)
            except ValueError:
                pass

        # Estimate total (we don't know exact count from HTML)
        total = max(len(files), total_pages * per_page) if total_pages > 1 else len(files)

        return FileListResult(files=files, total=total, page=page, per_page=per_page)

    def list_folders(self, parent_id: str = "/") -> FolderListResult:
        # Filedot web panel doesn't expose folder navigation
        return FolderListResult(folders=[], breadcrumb=[("/", "/")])

    def create_folder(
        self, name: str, parent_id: str = "/", access: str = "public"
    ) -> OperationResult:
        raise NotImplementedError("Filedot does not support folder creation")

    def rename(self, item_id: str, new_name: str) -> OperationResult:
        raise NotImplementedError("Filedot does not support rename")

    def move(self, item_ids: List[str], dest_folder_id: str) -> BatchResult:
        raise NotImplementedError("Filedot does not support move")

    def delete(self, item_ids: List[str]) -> BatchResult:
        succeeded = []
        failed = []

        for item_id in item_ids:
            try:
                fields = {"op": "my_files", "del_code": item_id}
                if self.sess_id:
                    fields["sess_id"] = self.sess_id
                self._web_post("https://filedot.to/?op=my_files", fields)
                succeeded.append(item_id)
            except Exception as e:
                failed.append((item_id, str(e)))

        return BatchResult(succeeded=succeeded, failed=failed)

    def get_info(self, item_ids: List[str]) -> List[FileInfo]:
        # No file info endpoint — return minimal info from ID
        return [
            FileInfo(id=fid, name=fid, is_folder=False)
            for fid in item_ids
        ]

    def get_capabilities(self) -> FileManagerCapabilities:
        return FILEDOT_CAPABILITIES

    # ------------------------------------------------------------------
    # Optional operations
    # ------------------------------------------------------------------

    def get_download_link(self, file_id: str) -> str:
        return f"https://filedot.to/{file_id}"

    def get_account_info(self) -> dict:
        try:
            html = self._web_get("https://filedot.to/account/")
            # Parse storage from HTML
            storage_match = re.search(
                r'Used space:?\s*</td>\s*<td>\s*<(?:b|strong)>\s*([\d.]+)\s+of\s+([\d.]+)\s+GB',
                html, re.IGNORECASE,
            )
            if storage_match:
                used_gb = float(storage_match.group(1))
                total_gb = float(storage_match.group(2))
                return {
                    "storage_used": int(used_gb * 1024**3),
                    "storage_left": int((total_gb - used_gb) * 1024**3),
                }
        except Exception as e:
            log(f"Filedot account info failed: {e}",
                level="warning", category="file_manager")

        return {}
