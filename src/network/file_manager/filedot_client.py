"""Filedot file manager client — XFS web-panel scraping subclass.

Filedot runs XFileSharing Pro but has NOT enabled the API mod, so all
operations use the web panel. Filedot uses session-scoped CSRF tokens
that rotate on some error paths. Token handling and shared scraping
live in XFSWebFileManagerBase; this class only provides URLs, regexes,
and the Filedot-specific flag-toggle POST shape.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple
from urllib.parse import urlencode

from src.network.file_manager.client import (
    FileManagerCapabilities,
)
from src.network.file_manager.xfs_web_client import XFSWebFileManagerBase
from src.utils.logger import log

FILEDOT_CAPABILITIES = FileManagerCapabilities(
    can_rename=True,
    can_move=True,
    can_delete=True,
    can_copy=True,
    can_change_access=False,
    can_edit_properties=True,
    can_set_file_flags=True,
    can_create_folder=True,
    can_remote_upload=False,
    can_trash=False,
    can_get_download_link=True,
    has_batch_operations=False,
    list_files_includes_folders=True,
    max_items_per_page=500,
    sortable_columns=["name"],
)


class FiledotFileManagerClient(XFSWebFileManagerBase):
    """File manager for Filedot via web scraping."""

    BASE_URL = "https://filedot.to"
    LINK_PREFIX = "https://filedot.to/"
    USES_CSRF_TOKEN = True

    _FILE_ROW_RE = re.compile(
        r'<tr class="filerow">'
        r'.*?name="file_id"\s+value="(\d+)"'
        r'.*?<td class="filename">\s*<a[^>]+href="https?://filedot\.(?:to|xyz)/([a-zA-Z0-9]+)"[^>]*>'
        r'\s*(.*?)\s*</a>'
        r'.*?<td class="tdinfo">\s*([^<]+?)\s*</td>',
        re.DOTALL,
    )
    _FOLDER_ROW_RE = re.compile(
        r'<tr class="folderrow">'
        r'.*?href="https?://filedot\.(?:to|xyz)/files\?fld_id=(\d+)"[^>]*>'
        r'\s*(.*?)\s*</a>',
        re.DOTALL,
    )
    _TOKEN_RE = re.compile(r'token=([a-f0-9]{16,})', re.IGNORECASE)
    _HIDDEN_TOKEN_INPUT_RE = re.compile(
        r'<input[^>]*\bname="token"[^>]*\bvalue="([a-f0-9]{16,})"',
        re.IGNORECASE,
    )
    _STALE_TOKEN_MARKERS = (
        "Anti-CSRF check failed",
        "session expired",
        "token invalid",
        "invalid token",
    )

    # ---- URL builders -----------------------------------------------------

    def _folder_url(self, folder_id: str, page: int = 1) -> str:
        fld = folder_id if folder_id and folder_id not in ("/", "") else "0"
        return f"{self.BASE_URL}/files/?fld_id={fld}&page={page}"

    def _file_edit_url(self, file_code: str) -> str:
        return f"{self.BASE_URL}/file_edit?file_code={file_code}"

    def _fld_edit_url(self, fld_id: str) -> str:
        return f"{self.BASE_URL}/fld_edit?fld_id={fld_id}"

    def _delete_file_url(self, file_code: str) -> str:
        return (
            f"{self.BASE_URL}/files?del_code={file_code}"
            f"&token={self._action_token}"
        )

    def _delete_folder_url(self, fld_id: str) -> str:
        return (
            f"{self.BASE_URL}/files?fld_id=0"
            f"&del_folder={fld_id}"
            f"&token={self._action_token}"
        )

    # ---- Flag-toggle shape: single batched POST ---------------------------

    def _build_flag_requests(
        self,
        numeric_ids: List[str],
        flag_name: str,
        value: bool,
    ) -> List[Tuple[str, str, Optional[bytes]]]:
        fields: list = [
            ("op", "my_files"),
            ("set_flag", flag_name),
            ("value", "1" if value else "0"),
            ("token", self._action_token),
        ]
        for num in numeric_ids:
            fields.append(("file_id", num))
        body = urlencode(fields).encode("utf-8")
        return [("POST", f"{self.BASE_URL}/?", body)]

    # ---- Capabilities + account info --------------------------------------

    def get_capabilities(self) -> FileManagerCapabilities:
        return FILEDOT_CAPABILITIES

    def get_account_info(self) -> dict:
        try:
            html = self._web_get(f"{self.BASE_URL}/account/")
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
