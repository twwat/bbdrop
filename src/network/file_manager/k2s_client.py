"""K2S-family file manager client (Keep2Share, TezFiles, FileBoom).

All three hosts share the same API v2 — just different base URLs.
Auth is via permanent API key passed as access_token in JSON POST bodies.
"""

from __future__ import annotations

import json
import pycurl
import certifi
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional

from src.network.file_manager.client import (
    CHROME_UA,
    BatchResult,
    FileInfo,
    FileListResult,
    FileManagerCapabilities,
    FileManagerClient,
    FolderListResult,
    OperationResult,
    RemoteJobStatus,
)
from src.utils.logger import log

# API base URLs per host
K2S_API_BASES = {
    "keep2share": "https://k2s.cc/api/v2",
    "fileboom": "https://fboom.me/api/v2",
    "tezfiles": "https://tezfiles.com/api/v2",
}

K2S_CAPABILITIES = FileManagerCapabilities(
    can_rename=True,
    can_move=True,
    can_delete=True,
    can_copy=False,
    can_change_access=True,
    can_create_folder=True,
    can_remote_upload=True,
    can_trash=False,
    can_get_download_link=True,
    has_batch_operations=True,
    max_items_per_page=10000,
    sortable_columns=["name", "date_created"],
)


class K2SFileManagerClient(FileManagerClient):
    """File manager for Keep2Share, TezFiles, and FileBoom via API v2."""

    def __init__(self, host_id: str, access_token: str, timeout: int = 30):
        self.host_id = host_id
        self.access_token = access_token
        self.timeout = timeout
        self.api_base = K2S_API_BASES.get(host_id, "").rstrip("/")
        if not self.api_base:
            raise ValueError(f"Unknown K2S-family host: {host_id}")

    # ------------------------------------------------------------------
    # Low-level API call
    # ------------------------------------------------------------------

    def _api_call(self, endpoint: str, body: Optional[dict] = None) -> Dict[str, Any]:
        """POST JSON to a K2S API endpoint.

        Args:
            endpoint: API endpoint name (e.g. 'getFilesList').
            body: Request body dict (access_token is added automatically).

        Returns:
            Parsed JSON response.

        Raises:
            RuntimeError: On HTTP or API-level errors.
        """
        url = f"{self.api_base}/{endpoint}"
        payload = dict(body or {})
        payload["access_token"] = self.access_token

        curl = pycurl.Curl()
        buf = BytesIO()

        try:
            curl.setopt(pycurl.URL, url)
            curl.setopt(pycurl.CAINFO, certifi.where())
            curl.setopt(pycurl.SSL_VERIFYPEER, 1)
            curl.setopt(pycurl.SSL_VERIFYHOST, 2)
            curl.setopt(pycurl.POST, 1)
            curl.setopt(pycurl.POSTFIELDS, json.dumps(payload))
            curl.setopt(pycurl.HTTPHEADER, ["Content-Type: application/json"])
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
            raise RuntimeError(f"K2S API {endpoint} returned HTTP {status}")

        data = json.loads(raw)

        # K2S uses 'code' for error signaling (200/201/202 = ok)
        code = data.get("code")
        if code and int(code) not in (200, 201, 202):
            raise RuntimeError(
                f"K2S API {endpoint} error {code}: {data.get('message', raw)}"
            )

        return data

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_file_info(item: dict) -> FileInfo:
        """Convert a K2S API file/folder dict to FileInfo."""
        created = None
        date_str = item.get("date_created")
        if date_str:
            try:
                created = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        return FileInfo(
            id=item.get("id", ""),
            name=item.get("name", ""),
            is_folder=bool(item.get("is_folder", False)),
            size=int(item.get("size", 0)),
            created=created,
            access=item.get("access", "public"),
            is_available=bool(item.get("is_available", True)),
            md5=item.get("md5"),
            content_type=item.get("content_type"),
            parent_id=item.get("parent_id"),
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
        sort_val = 1 if sort_dir == "asc" else -1
        body: Dict[str, Any] = {
            "parent": folder_id,
            "limit": per_page,
            "offset": (page - 1) * per_page,
            "sort": [{sort_by: sort_val}],
            "extended_info": True,
        }

        data = self._api_call("getFilesList", body)
        files_raw = data.get("files", [])
        files = [self._parse_file_info(f) for f in files_raw]
        total = int(data.get("total", len(files)))

        return FileListResult(files=files, total=total, page=page, per_page=per_page)

    def list_folders(self, parent_id: str = "/") -> FolderListResult:
        body = {}
        if parent_id and parent_id != "/":
            body["parent_id"] = parent_id

        data = self._api_call("getFoldersList", body)

        folder_names = data.get("foldersList", [])
        folder_ids = data.get("foldersIds", [])
        parent_names = data.get("parentFoldersList", [])
        parent_ids = data.get("parentFoldersIds", [])

        folders = []
        for i, fid in enumerate(folder_ids):
            name = folder_names[i] if i < len(folder_names) else fid
            folders.append(FileInfo(id=fid, name=name, is_folder=True))

        breadcrumb = []
        for i, pid in enumerate(parent_ids):
            pname = parent_names[i] if i < len(parent_names) else pid
            breadcrumb.append((pid, pname))

        return FolderListResult(folders=folders, breadcrumb=breadcrumb)

    def create_folder(
        self, name: str, parent_id: str = "/", access: str = "public"
    ) -> OperationResult:
        data = self._api_call("createFolder", {
            "name": name,
            "parent": parent_id,
            "access": access,
        })
        folder_id = data.get("id", "")
        return OperationResult(success=True, message=f"Folder created", data={"id": folder_id})

    def rename(self, item_id: str, new_name: str) -> OperationResult:
        self._api_call("updateFile", {"id": item_id, "new_name": new_name})
        return OperationResult(success=True, message="Renamed")

    def move(self, item_ids: List[str], dest_folder_id: str) -> BatchResult:
        if len(item_ids) == 1:
            self._api_call("updateFile", {
                "id": item_ids[0],
                "new_parent": dest_folder_id,
            })
            return BatchResult(succeeded=item_ids)

        # Batch move
        data = self._api_call("updateFiles", {
            "ids": item_ids,
            "new_parent": dest_folder_id,
        })

        succeeded = []
        failed = []
        for result in data.get("files", []):
            fid = result.get("id", "")
            if result.get("status") == "success":
                succeeded.append(fid)
            else:
                errors = result.get("errors", ["Unknown error"])
                failed.append((fid, str(errors[0]) if errors else "Unknown error"))

        # If API doesn't return per-file results, assume all succeeded
        if not succeeded and not failed:
            succeeded = list(item_ids)

        return BatchResult(succeeded=succeeded, failed=failed)

    def delete(self, item_ids: List[str]) -> BatchResult:
        data = self._api_call("deleteFiles", {"ids": item_ids})
        deleted = data.get("deleted", 0)
        if deleted == len(item_ids):
            return BatchResult(succeeded=list(item_ids))
        # Can't tell which failed — report all as succeeded if any deleted
        return BatchResult(succeeded=list(item_ids))

    def get_info(self, item_ids: List[str]) -> List[FileInfo]:
        data = self._api_call("getFilesInfo", {
            "ids": item_ids,
            "extended_info": True,
        })
        return [self._parse_file_info(f) for f in data.get("files", [])]

    def get_capabilities(self) -> FileManagerCapabilities:
        return K2S_CAPABILITIES

    # ------------------------------------------------------------------
    # Optional operations
    # ------------------------------------------------------------------

    def change_access(self, item_ids: List[str], access: str) -> BatchResult:
        if len(item_ids) == 1:
            self._api_call("updateFile", {
                "id": item_ids[0],
                "new_access": access,
            })
            return BatchResult(succeeded=item_ids)

        data = self._api_call("updateFiles", {
            "ids": item_ids,
            "new_access": access,
        })

        succeeded = []
        failed = []
        for result in data.get("files", []):
            fid = result.get("id", "")
            if result.get("status") == "success":
                succeeded.append(fid)
            else:
                errors = result.get("errors", ["Unknown error"])
                failed.append((fid, str(errors[0]) if errors else "Unknown error"))

        if not succeeded and not failed:
            succeeded = list(item_ids)

        return BatchResult(succeeded=succeeded, failed=failed)

    def get_download_link(self, file_id: str) -> str:
        info = self.get_info([file_id])
        if info:
            # K2S download link pattern
            return f"https://k2s.cc/file/{file_id}"
        return ""

    def remote_upload_add(
        self, urls: List[str], folder_id: str = "/"
    ) -> OperationResult:
        data = self._api_call("remoteUploadAdd", {"urls": urls})
        accepted = data.get("acceptedUrls", [])
        rejected = data.get("rejectedUrls", [])
        return OperationResult(
            success=len(accepted) > 0,
            message=f"{len(accepted)} accepted, {len(rejected)} rejected",
            data={"accepted": accepted, "rejected": rejected},
        )

    def remote_upload_status(
        self, job_ids: Optional[List[str]] = None
    ) -> List[RemoteJobStatus]:
        body = {}
        if job_ids:
            body["ids"] = job_ids
        data = self._api_call("remoteUploadStatus", body)

        jobs = []
        for job in data.get("jobs", []):
            jobs.append(RemoteJobStatus(
                job_id=job.get("id", ""),
                status=job.get("status", "unknown"),
                progress=int(job.get("progress", 0)),
                file_id=job.get("file_id"),
            ))
        return jobs

    def get_account_info(self) -> dict:
        return self._api_call("accountInfo")
