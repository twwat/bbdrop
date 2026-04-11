"""Filespace file manager client — XFS web-panel scraping subclass.

Filespace runs XFileSharing Pro without the JSON API mod. Unlike
Filedot, Filespace does NOT use CSRF tokens — session cookies alone
authorize mutating operations. This client delegates all HTTP to the
running upload worker's FileHostClient so proxy, bandwidth counter,
session reuse, and reauth flow through the same pipeline as uploads.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from src.network.file_manager.client import FileManagerCapabilities
from src.network.file_manager.xfs_web_client import XFSWebFileManagerBase

FILESPACE_CAPABILITIES = FileManagerCapabilities(
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
    sortable_columns=["name", "size", "created"],
)


class FilespaceFileManagerClient(XFSWebFileManagerBase):
    """File manager for Filespace via web scraping."""

    BASE_URL = "https://filespace.com"
    LINK_PREFIX = "https://filespace.com/"
    USES_CSRF_TOKEN = False

    # File row: <TR align=center class="hi"> ... file_id value="\d+" ...
    # href="https://filespace.com/<code>">name</a> ... <TD align=right>size</TD>
    _FILE_ROW_RE = re.compile(
        r'<TR align=center class="hi">'
        r'.*?name="file_id"\s+value="(\d+)"'
        r'.*?href="https?://filespace\.com/([a-zA-Z0-9]+)"[^>]*>'
        r'\s*([^<]+?)\s*</a>'
        r'.*?<TD align=right>\s*([^<]+?)\s*</TD>',
        re.DOTALL | re.IGNORECASE,
    )
    # Folder row: <TR> ... <img alt="Folder"> ... href="?op=my_files&amp;fld_id=N">name</a>
    # (the italic "root folder" pseudo-row lacks the fld_id href, so it won't match.)
    # Allow optional HTML comments between <TR> and the first <TD>.
    _FOLDER_ROW_RE = re.compile(
        r'<TR>\s*(?:<!--.*?-->\s*)?<TD[^>]*>\s*<img[^>]*alt="Folder"[^>]*>\s*</TD>'
        r'\s*<TD[^>]*>\s*<a[^>]+href="\?op=my_files&amp;fld_id=(\d+)"[^>]*>'
        r'\s*(?:<b>)?\s*([^<]+?)\s*(?:</b>)?\s*</a>',
        re.DOTALL | re.IGNORECASE,
    )

    # ---- URL builders -----------------------------------------------------

    def _folder_url(self, folder_id: str, page: int = 1) -> str:
        fld = folder_id if folder_id and folder_id not in ("/", "") else "0"
        return f"{self.BASE_URL}/?op=my_files&fld_id={fld}&page={page}"

    def _file_edit_url(self, file_code: str) -> str:
        return f"{self.BASE_URL}/?op=file_edit&file_code={file_code}"

    def _fld_edit_url(self, fld_id: str) -> str:
        return f"{self.BASE_URL}/?op=fld_edit&fld_id={fld_id}"

    def _delete_file_url(self, file_code: str) -> str:
        return f"{self.BASE_URL}/?op=my_files&del_code={file_code}"

    def _delete_folder_url(self, fld_id: str) -> str:
        return f"{self.BASE_URL}/?op=my_files&fld_id=0&del_folder={fld_id}"

    # ---- Flag-toggle shape: one GET per file_id ---------------------------

    def _build_flag_requests(
        self,
        numeric_ids: List[str],
        flag_name: str,
        value: bool,
    ) -> List[Tuple[str, str, Optional[bytes]]]:
        # Filespace inline jah() AJAX uses set_public / set_premium_only
        # (file_premium_only → set_premium_only).
        suffix_map = {
            "file_public": "set_public",
            "file_premium_only": "set_premium_only",
        }
        suffix = suffix_map.get(flag_name)
        if suffix is None:
            return []
        lc = "true" if value else "false"
        return [
            (
                "GET",
                f"{self.BASE_URL}/?op=my_files&file_id={n}&{suffix}={lc}",
                None,
            )
            for n in numeric_ids
        ]

    # ---- Capabilities + account info --------------------------------------

    def get_capabilities(self) -> FileManagerCapabilities:
        return FILESPACE_CAPABILITIES

    def get_account_info(self) -> dict:
        # Filespace account-info scraping is not implemented yet — the
        # controller tolerates missing fields, so return an empty dict.
        return {}
