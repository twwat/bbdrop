"""XFS (XFileSharing) file manager client.

Base implementation for hosts running XFileSharing Pro with the API mod
enabled. Currently used by Katfile. Filespace extends this with web
fallback for operations the API doesn't cover.

All endpoints are GET requests with ?key=API_KEY query parameter.
Response shape: {"status": 200, "result": ..., "msg": "...", "server_time": "..."}
"""

from __future__ import annotations

import json
import pycurl
import certifi
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from src.network.file_manager.client import (
    CHROME_UA,
    BatchResult,
    FileInfo,
    FileListResult,
    FileManagerCapabilities,
    FileManagerClient,
    FolderListResult,
    OperationResult,
)
from src.utils.logger import log

# API base URLs per host
XFS_API_BASES = {
    "katfile": "https://katfile.cloud/api",
}

KATFILE_CAPABILITIES = FileManagerCapabilities(
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


class XFSFileManagerClient(FileManagerClient):
    """File manager for XFS-based hosts (Katfile, etc.)."""

    def __init__(self, host_id: str, api_key: str, timeout: int = 30):
        self.host_id = host_id
        self.api_key = api_key
        self.timeout = timeout
        self.api_base = XFS_API_BASES.get(host_id, "").rstrip("/")
        if not self.api_base:
            raise ValueError(f"Unknown XFS host: {host_id}")

        # Link prefix for download URLs
        self._link_prefixes = {
            "katfile": "https://katfile.cloud/",
        }

    # ------------------------------------------------------------------
    # Low-level API call
    # ------------------------------------------------------------------

    def _api_call(self, endpoint: str, params: Optional[dict] = None) -> Dict[str, Any]:
        """GET request to XFS API.

        Args:
            endpoint: Path after /api/ (e.g. 'file/list').
            params: Query params (key is added automatically).

        Returns:
            Parsed JSON response.

        Raises:
            RuntimeError: On HTTP or API-level errors.
        """
        query = dict(params or {})
        query["key"] = self.api_key

        url = f"{self.api_base}/{endpoint}?{urlencode(query)}"

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

            curl.perform()
            status = curl.getinfo(pycurl.RESPONSE_CODE)
        finally:
            curl.close()

        raw = buf.getvalue().decode("utf-8")

        if status != 200:
            raise RuntimeError(f"XFS API {endpoint} returned HTTP {status}")

        data = json.loads(raw)

        api_status = data.get("status")
        if api_status and int(api_status) != 200:
            raise RuntimeError(
                f"XFS API {endpoint} error {api_status}: {data.get('msg', raw)}"
            )

        return data

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_file(self, item: dict) -> FileInfo:
        """Convert an XFS API file dict to FileInfo."""
        created = None
        date_str = item.get("created")
        if date_str:
            try:
                created = datetime.fromisoformat(date_str)
            except (ValueError, AttributeError):
                pass

        file_code = item.get("file_code", item.get("filecode", ""))
        link_prefix = self._link_prefixes.get(self.host_id, "")

        return FileInfo(
            id=file_code,
            name=item.get("file_title", item.get("title", file_code)),
            is_folder=False,
            size=int(item.get("file_size", item.get("size", 0))),
            created=created,
            access="public" if item.get("file_public", item.get("public", 1)) else "private",
            is_available=True,
            md5=item.get("file_md5"),
            content_type=item.get("file_content_type"),
            metadata=dict(item),
        )

    @staticmethod
    def _parse_folder(item: dict) -> FileInfo:
        """Convert an XFS API folder dict to FileInfo."""
        return FileInfo(
            id=str(item.get("fld_id", "")),
            name=item.get("name", ""),
            is_folder=True,
            parent_id=str(item.get("parent_id", "")) or None,
            metadata=dict(item),
        )

    # ------------------------------------------------------------------
    # Abstract method implementations
    # ------------------------------------------------------------------

    def list_files(
        self,
        folder_id: str = "/",
        page: int = 1,
        per_page: int = 100,
        sort_by: str = "name",
        sort_dir: str = "asc",
    ) -> FileListResult:
        params: Dict[str, Any] = {
            "page": page,
            "per_page": per_page,
        }
        if folder_id and folder_id not in ("/", "0"):
            params["fld_id"] = folder_id

        data = self._api_call("file/list", params)
        result = data.get("result", {})

        files_raw = result.get("files", []) if isinstance(result, dict) else result
        if isinstance(files_raw, list):
            files = [self._parse_file(f) for f in files_raw]
        else:
            files = []

        total = int(result.get("results_total", len(files))) if isinstance(result, dict) else len(files)

        return FileListResult(files=files, total=total, page=page, per_page=per_page)

    def list_folders(self, parent_id: str = "/") -> FolderListResult:
        params = {}
        if parent_id and parent_id not in ("/", "0"):
            params["fld_id"] = parent_id

        data = self._api_call("folder/list", params)
        result = data.get("result", {})

        folders_raw = result.get("folders", []) if isinstance(result, dict) else result
        folders = []
        if isinstance(folders_raw, list):
            folders = [self._parse_folder(f) for f in folders_raw]

        breadcrumb = [("/", "/")]
        if parent_id not in ("/", "0"):
            breadcrumb.append((parent_id, parent_id))

        return FolderListResult(folders=folders, breadcrumb=breadcrumb)

    def create_folder(
        self, name: str, parent_id: str = "/", access: str = "public"
    ) -> OperationResult:
        params = {"name": name}
        if parent_id and parent_id not in ("/", "0"):
            params["parent_id"] = parent_id

        data = self._api_call("folder/create", params)
        result = data.get("result", {})
        fld_id = result.get("fld_id", "") if isinstance(result, dict) else ""
        return OperationResult(
            success=True,
            message="Folder created",
            data={"id": str(fld_id)},
        )

    def rename(self, item_id: str, new_name: str) -> OperationResult:
        # Try file edit first, then folder edit
        try:
            self._api_call("file/edit", {
                "file_code": item_id,
                "file_title": new_name,
            })
            return OperationResult(success=True, message="Renamed")
        except RuntimeError:
            self._api_call("folder/edit", {
                "fld_id": item_id,
                "name": new_name,
            })
            return OperationResult(success=True, message="Renamed")

    def move(self, item_ids: List[str], dest_folder_id: str) -> BatchResult:
        succeeded = []
        failed = []

        for item_id in item_ids:
            try:
                self._api_call("file/move", {
                    "file_code": item_id,
                    "to_folder": dest_folder_id,
                })
                succeeded.append(item_id)
            except RuntimeError as e:
                failed.append((item_id, str(e)))

        return BatchResult(succeeded=succeeded, failed=failed)

    def delete(self, item_ids: List[str]) -> BatchResult:
        succeeded = []
        failed = []

        for item_id in item_ids:
            try:
                self._api_call("file/delete", {"file_code": item_id})
                succeeded.append(item_id)
            except RuntimeError:
                try:
                    self._api_call("folder/delete", {"fld_id": item_id})
                    succeeded.append(item_id)
                except RuntimeError as e:
                    failed.append((item_id, str(e)))

        return BatchResult(succeeded=succeeded, failed=failed)

    def get_info(self, item_ids: List[str]) -> List[FileInfo]:
        results = []
        for item_id in item_ids:
            try:
                data = self._api_call("file/info", {"file_code": item_id})
                result = data.get("result", {})
                if isinstance(result, dict):
                    results.append(self._parse_file(result))
                elif isinstance(result, list) and result:
                    results.append(self._parse_file(result[0]))
            except RuntimeError:
                pass
        return results

    def get_capabilities(self) -> FileManagerCapabilities:
        return KATFILE_CAPABILITIES

    # ------------------------------------------------------------------
    # Optional operations
    # ------------------------------------------------------------------

    def copy(self, item_ids: List[str], dest_folder_id: str) -> BatchResult:
        succeeded = []
        failed = []

        for item_id in item_ids:
            try:
                self._api_call("file/clone", {
                    "file_code": item_id,
                    "fld_id": dest_folder_id,
                })
                succeeded.append(item_id)
            except RuntimeError as e:
                failed.append((item_id, str(e)))

        return BatchResult(succeeded=succeeded, failed=failed)

    def get_download_link(self, file_id: str) -> str:
        try:
            data = self._api_call("file/direct_link", {"file_code": file_id})
            result = data.get("result", "")
            if isinstance(result, str) and result:
                return result
        except RuntimeError:
            pass
        # Fallback to constructed URL
        prefix = self._link_prefixes.get(self.host_id, "")
        return f"{prefix}{file_id}" if prefix else file_id

    def get_account_info(self) -> dict:
        data = self._api_call("account/info")
        result = data.get("result", {})
        return {
            "storage_left": result.get("storage_left"),
            "storage_used": result.get("storage_used"),
            "premium_expire": result.get("premium_expire"),
            "email": result.get("email"),
        }
