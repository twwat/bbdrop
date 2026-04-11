"""Filedot file manager client (web scraping).

Filedot runs XFileSharing Pro but has NOT enabled the API mod.
All operations go through the web panel using the session already
maintained by the upload worker's FileHostClient — this client
delegates all HTTP to that shared client so proxy, bandwidth
counter, session reuse, and reauth all happen through the same
pipeline as uploads.

Currently supports:
- List files and folders (scrape /files/?fld_id=N)
- Navigate into folders (via fld_id query param)
- Delete files (GET /files?del_code=...&token=...)

Move, copy, rename, and folder creation use the same web panel but
aren't implemented yet — the action panel form parameters are known
(to_folder_move / to_folder_copy / create_folder_submit) and can be
added as a follow-up.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode

from src.network.file_host_client import FileHostClient
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
    list_files_includes_folders=True,
    max_items_per_page=50,
    sortable_columns=["name"],
)

# File row: <tr class="filerow"> ... checkbox value="numeric" ... <a href=".../file_code">name</a> ... <td class="tdinfo">size</td>
_FILE_ROW_RE = re.compile(
    r'<tr class="filerow">'
    r'.*?name="file_id"\s+value="(\d+)"'
    r'.*?<td class="filename">\s*<a[^>]+href="https?://filedot\.(?:to|xyz)/([a-zA-Z0-9]+)"[^>]*>'
    r'\s*(.*?)\s*</a>'
    r'.*?<td class="tdinfo">\s*([^<]+?)\s*</td>',
    re.DOTALL,
)

# Folder row: <tr class="folderrow"> ... <a href=".../files?fld_id=N">name</a>
_FOLDER_ROW_RE = re.compile(
    r'<tr class="folderrow">'
    r'.*?href="https?://filedot\.(?:to|xyz)/files\?fld_id=(\d+)"[^>]*>'
    r'\s*(.*?)\s*</a>',
    re.DOTALL,
)

# CSRF token from any action link (delete/move use the same page token).
# The page encodes & as &amp; in attribute values, so don't anchor on [?&].
_TOKEN_RE = re.compile(r'token=([a-f0-9]{16,})', re.IGNORECASE)

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
    """File manager for Filedot via web scraping.

    All HTTP is delegated to an injected FileHostClient so proxy,
    bandwidth tracking, session reuse, and reauth go through the same
    pipeline the upload worker already uses.
    """

    def __init__(self, file_host_client: FileHostClient, timeout: int = 30):
        """
        Args:
            file_host_client: The upload worker's FileHostClient for
                this host. All HTTP requests go through it, inheriting
                proxy, bandwidth counter, session cookies, and reauth.
            timeout: Per-request timeout in seconds.
        """
        self._http = file_host_client
        self.timeout = timeout
        # CSRF token scraped from the most recent list_files call.
        # Used by delete() since delete URLs require ?token=<hex>.
        self._action_token: str = ""

    # ------------------------------------------------------------------
    # Low-level web request — thin wrappers around FileHostClient.request
    # ------------------------------------------------------------------

    def _web_get(self, url: str) -> str:
        """GET request through the shared FileHostClient."""
        _status, _headers, body = self._http.request(
            "GET", url, timeout=self.timeout
        )
        return body.decode("utf-8", errors="replace")

    def _web_post(self, url: str, fields: Dict[str, str]) -> str:
        """POST form-urlencoded fields through the shared FileHostClient.

        Used by future move/copy/create_folder implementations; delete
        currently uses GET and goes through _web_get.
        """
        body = urlencode(fields).encode("utf-8")
        _status, _headers, resp = self._http.request(
            "POST",
            url,
            body=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=self.timeout,
        )
        return resp.decode("utf-8", errors="replace")

    # ------------------------------------------------------------------
    # URL helpers
    # ------------------------------------------------------------------

    def _folder_url(self, folder_id: str, page: int = 1) -> str:
        """Build the file-listing URL for a given folder.

        Filedot's file manager lives at /files/. Root uses fld_id=0 per
        the action-panel select dropdown; subfolders use fld_id=<numeric>.
        """
        fld = folder_id if folder_id and folder_id not in ("/", "") else "0"
        return f"https://filedot.to/files/?fld_id={fld}&page={page}"

    # ------------------------------------------------------------------
    # Scraping
    # ------------------------------------------------------------------

    def _scrape_page(self, folder_id: str, page: int) -> tuple[list, list]:
        """Fetch a folder page and return (folders, files) as FileInfo lists.

        Side effects:
        - Caches the CSRF token from the first action link found, which
          delete() needs.
        """
        html = self._web_get(self._folder_url(folder_id, page))

        # Cache CSRF token for this session — any action link has it
        token_match = _TOKEN_RE.search(html)
        if token_match:
            self._action_token = token_match.group(1)

        folders = []
        for match in _FOLDER_ROW_RE.finditer(html):
            fld_id = match.group(1)
            raw_name = match.group(2)
            name = re.sub(r'<[^>]+>', '', raw_name).strip()
            folders.append(FileInfo(
                id=fld_id,
                name=name or fld_id,
                is_folder=True,
                parent_id=folder_id if folder_id not in ("/", "") else None,
            ))

        files = []
        for match in _FILE_ROW_RE.finditer(html):
            file_code = match.group(2)
            raw_name = match.group(3)
            name = re.sub(r'<[^>]+>', '', raw_name).strip()
            size_str = match.group(4)
            files.append(FileInfo(
                id=file_code,
                name=name or file_code,
                is_folder=False,
                size=_parse_size(size_str),
                is_available=True,
                parent_id=folder_id if folder_id not in ("/", "") else None,
            ))

        log(f"Filedot scraped folder_id={folder_id!r} page={page}: "
            f"{len(folders)} folders, {len(files)} files "
            f"(token_cached={bool(self._action_token)})",
            level="debug", category="file_manager")

        return folders, files

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
        folders, files = self._scrape_page(folder_id, page)

        # Return folders first, then files — the controller's file list
        # widget treats is_folder entries as navigable rows.
        items = folders + files
        return FileListResult(
            files=items,
            total=len(items),
            page=page,
            per_page=per_page,
        )

    def list_folders(self, parent_id: str = "/") -> FolderListResult:
        """Return immediate child folders of parent_id for the tree widget."""
        folders, _files = self._scrape_page(parent_id, page=1)
        return FolderListResult(
            folders=folders, breadcrumb=[(parent_id, parent_id)]
        )

    def create_folder(
        self, name: str, parent_id: str = "/", access: str = "public"
    ) -> OperationResult:
        raise NotImplementedError("Filedot does not support folder creation")

    def rename(self, item_id: str, new_name: str) -> OperationResult:
        raise NotImplementedError("Filedot does not support rename")

    def move(self, item_ids: List[str], dest_folder_id: str) -> BatchResult:
        raise NotImplementedError("Filedot does not support move")

    def delete(self, item_ids: List[str]) -> BatchResult:
        """Delete files via the web panel.

        Filedot deletes are GETs to /files?del_code=<code>&token=<tok>.
        The token is scraped from the most recent list_files call — if
        we don't have one, prime it by hitting the root page.
        """
        succeeded: list = []
        failed: list = []

        if not self._action_token:
            try:
                self._scrape_page("/", 1)
            except Exception as e:
                return BatchResult(
                    succeeded=[],
                    failed=[(i, f"failed to load action token: {e}") for i in item_ids],
                )

        for item_id in item_ids:
            try:
                url = (
                    f"https://filedot.to/files?del_code={item_id}"
                    f"&token={self._action_token}"
                )
                self._web_get(url)
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
