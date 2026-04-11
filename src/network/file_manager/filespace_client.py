"""Filespace file manager client.

Extends the XFS base client. Uses the XFS REST API (with API key) for
list/rename/move/create/clone operations, but falls back to the web
panel (with session cookie) for delete — the XFS API doesn't expose a
delete endpoint on Filespace.

Requires two credentials:
- API key for REST endpoints
- Session cookie (xfss) for web panel delete (reused from upload session)
"""

from __future__ import annotations

import pycurl
import certifi
from io import BytesIO
from typing import Dict, List, Optional

from src.network.file_manager.client import (
    CHROME_UA,
    BatchResult,
    FileManagerCapabilities,
)
from src.network.file_manager.xfs_client import XFSFileManagerClient, XFS_API_BASES
from src.utils.logger import log

# Register Filespace in XFS API bases
XFS_API_BASES["filespace"] = "https://filespace.com/api"

FILESPACE_CAPABILITIES = FileManagerCapabilities(
    can_rename=True,
    can_move=True,
    can_delete=True,
    can_copy=True,
    can_change_access=False,
    can_create_folder=True,
    can_remote_upload=False,
    can_trash=False,
    can_get_download_link=True,
    has_batch_operations=False,
    max_items_per_page=100,
    sortable_columns=["name", "created"],
)


class FilespaceFileManagerClient(XFSFileManagerClient):
    """File manager for Filespace — XFS API + web panel fallback."""

    def __init__(
        self,
        api_key: str,
        session_cookie: Optional[str] = None,
        timeout: int = 30,
    ):
        # Add link prefix for Filespace
        super().__init__(host_id="filespace", api_key=api_key, timeout=timeout)
        self._link_prefixes["filespace"] = "https://filespace.com/"
        self._session_cookie = session_cookie

    def get_capabilities(self) -> FileManagerCapabilities:
        return FILESPACE_CAPABILITIES

    def delete(self, item_ids: List[str]) -> BatchResult:
        """Delete files via web panel (GET with session cookie).

        The XFS API on Filespace doesn't have a delete endpoint, so we
        use the web panel: GET /?op=my_files&del_code={file_code}
        """
        if not self._session_cookie:
            # Fall back to API attempt (may work on newer XFS versions)
            return super().delete(item_ids)

        succeeded = []
        failed = []

        for item_id in item_ids:
            try:
                self._web_delete(item_id)
                succeeded.append(item_id)
            except Exception as e:
                # Try folder delete via API
                try:
                    self._api_call("folder/delete", {"fld_id": item_id})
                    succeeded.append(item_id)
                except RuntimeError as e2:
                    failed.append((item_id, str(e)))

        return BatchResult(succeeded=succeeded, failed=failed)

    def _web_delete(self, file_code: str):
        """Delete a file via web panel GET request with session cookie."""
        url = f"https://filespace.com/?op=my_files&del_code={file_code}"

        curl = pycurl.Curl()
        buf = BytesIO()

        try:
            curl.setopt(pycurl.URL, url)
            curl.setopt(pycurl.CAINFO, certifi.where())
            curl.setopt(pycurl.SSL_VERIFYPEER, 1)
            curl.setopt(pycurl.SSL_VERIFYHOST, 2)
            curl.setopt(pycurl.USERAGENT, CHROME_UA)
            curl.setopt(pycurl.WRITEDATA, buf)
            curl.setopt(pycurl.TIMEOUT, self.timeout)
            curl.setopt(pycurl.FOLLOWLOCATION, True)
            curl.setopt(pycurl.COOKIE, f"xfss={self._session_cookie}")

            curl.perform()
            status = curl.getinfo(pycurl.RESPONSE_CODE)
        finally:
            curl.close()

        if status not in (200, 302):
            raise RuntimeError(f"Filespace web delete returned HTTP {status}")

    def get_account_info(self) -> dict:
        info = super().get_account_info()
        # Filespace may not return all fields — provide fallback
        return {
            "storage_left": info.get("storage_left"),
            "storage_used": info.get("storage_used"),
            "premium_expire": info.get("premium_expire"),
        }
