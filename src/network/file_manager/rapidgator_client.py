"""RapidGator file manager client.

Uses the RapidGator API v2 with token-based auth (24h TTL).
Richest API of all hosts — supports trash, copy, one-time links,
download counts, and access mode changes.
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
    RemoteJobStatus,
)
from src.utils.logger import log

API_BASE = "https://rapidgator.net/api/v2"

RAPIDGATOR_CAPABILITIES = FileManagerCapabilities(
    can_rename=True,
    can_move=True,
    can_delete=True,
    can_copy=True,
    can_change_access=True,
    can_create_folder=True,
    can_remote_upload=True,
    can_trash=True,
    can_get_download_link=True,
    has_batch_operations=True,
    max_items_per_page=500,
    sortable_columns=["name", "created", "size", "nb_downloads"],
)

# RG access modes
_ACCESS_MAP = {"public": 0, "premium": 1, "private": 2, "hotlink": 3}
_ACCESS_REVERSE = {v: k for k, v in _ACCESS_MAP.items()}


class RapidgatorFileManagerClient(FileManagerClient):
    """File manager for RapidGator via API v2."""

    def __init__(self, token: str, timeout: int = 30):
        self.token = token
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Low-level API call
    # ------------------------------------------------------------------

    def _api_call(self, endpoint: str, params: Optional[dict] = None) -> Dict[str, Any]:
        """GET request to RapidGator API v2.

        Args:
            endpoint: Path after /api/v2/ (e.g. 'folder/content').
            params: Query params (token is added automatically).

        Returns:
            Parsed JSON response.

        Raises:
            RuntimeError: On HTTP or API-level errors.
        """
        query = dict(params or {})
        query["token"] = self.token

        url = f"{API_BASE}/{endpoint}?{urlencode(query)}"

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

        if status < 200 or status >= 300:
            raise RuntimeError(f"RG API {endpoint} returned HTTP {status}")

        data = json.loads(raw)

        resp_status = data.get("status")
        if resp_status and int(resp_status) != 200:
            msg = data.get("response", {}).get("error", raw) if isinstance(data.get("response"), dict) else raw
            raise RuntimeError(f"RG API {endpoint} error {resp_status}: {msg}")

        return data

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_file(item: dict) -> FileInfo:
        """Convert an RG API file dict to FileInfo."""
        created = None
        ts = item.get("created")
        if ts:
            try:
                created = datetime.fromtimestamp(int(ts), tz=timezone.utc)
            except (ValueError, TypeError, OSError):
                pass

        mode = item.get("mode", 0)
        access = _ACCESS_REVERSE.get(int(mode), "public") if mode is not None else "public"

        return FileInfo(
            id=str(item.get("file_id", item.get("id", ""))),
            name=item.get("name", ""),
            is_folder=False,
            size=int(item.get("size", 0)),
            created=created,
            access=access,
            is_available=True,
            md5=item.get("hash"),
            download_count=item.get("nb_downloads"),
            parent_id=str(item.get("folder_id", "")) or None,
        )

    @staticmethod
    def _parse_folder(item: dict) -> FileInfo:
        """Convert an RG API folder dict to FileInfo."""
        created = None
        ts = item.get("created")
        if ts:
            try:
                created = datetime.fromtimestamp(int(ts), tz=timezone.utc)
            except (ValueError, TypeError, OSError):
                pass

        mode = item.get("mode", 0)
        access = _ACCESS_REVERSE.get(int(mode), "public") if mode is not None else "public"

        return FileInfo(
            id=str(item.get("folder_id", item.get("id", ""))),
            name=item.get("name", ""),
            is_folder=True,
            created=created,
            access=access,
            is_available=True,
            parent_id=str(item.get("parent_id", "")) or None,
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
            "sort_column": sort_by,
            "sort_direction": sort_dir,
        }
        if folder_id and folder_id != "/":
            params["folder_id"] = folder_id

        data = self._api_call("folder/content", params)
        resp = data.get("response", {})
        folder_data = resp.get("folder", {})

        files: list[FileInfo] = []

        # Parse subfolders
        for folder in folder_data.get("folders", []):
            files.append(self._parse_folder(folder))

        # Parse files
        for f in folder_data.get("files", []):
            files.append(self._parse_file(f))

        total = int(folder_data.get("nb_files", len(files)))

        return FileListResult(files=files, total=total, page=page, per_page=per_page)

    def list_folders(self, parent_id: str = "/") -> FolderListResult:
        params = {}
        if parent_id and parent_id != "/":
            params["folder_id"] = parent_id

        data = self._api_call("folder/info", params)
        resp = data.get("response", {})
        folder_data = resp.get("folder", {})

        folders = []
        for sub in folder_data.get("folders", []):
            folders.append(self._parse_folder(sub))

        # Build breadcrumb from parent chain
        breadcrumb = [("/", "/")]
        if parent_id != "/":
            breadcrumb.append((
                str(folder_data.get("folder_id", parent_id)),
                folder_data.get("name", parent_id),
            ))

        return FolderListResult(folders=folders, breadcrumb=breadcrumb)

    def create_folder(
        self, name: str, parent_id: str = "/", access: str = "public"
    ) -> OperationResult:
        params = {"name": name}
        if parent_id and parent_id != "/":
            params["folder_id"] = parent_id

        data = self._api_call("folder/create", params)
        resp = data.get("response", {})
        folder = resp.get("folder", {})
        return OperationResult(
            success=True,
            message="Folder created",
            data={"id": str(folder.get("folder_id", ""))},
        )

    def rename(self, item_id: str, new_name: str) -> OperationResult:
        # Try file rename first, fall back to folder rename
        try:
            self._api_call("file/rename", {"file_id": item_id, "name": new_name})
            return OperationResult(success=True, message="Renamed")
        except RuntimeError:
            self._api_call("folder/rename", {"folder_id": item_id, "name": new_name})
            return OperationResult(success=True, message="Renamed")

    def move(self, item_ids: List[str], dest_folder_id: str) -> BatchResult:
        # RG supports CSV file_id for batch move
        succeeded = []
        failed = []

        # Try as files first (most common)
        try:
            csv_ids = ",".join(item_ids)
            self._api_call("file/move", {
                "file_id": csv_ids,
                "folder_id_dest": dest_folder_id,
            })
            succeeded = list(item_ids)
        except RuntimeError:
            # Some might be folders — try individually
            for item_id in item_ids:
                try:
                    self._api_call("file/move", {
                        "file_id": item_id,
                        "folder_id_dest": dest_folder_id,
                    })
                    succeeded.append(item_id)
                except RuntimeError:
                    try:
                        self._api_call("folder/move", {
                            "folder_id": item_id,
                            "folder_id_dest": dest_folder_id,
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
                self._api_call("file/delete", {"file_id": item_id})
                succeeded.append(item_id)
            except RuntimeError:
                try:
                    self._api_call("folder/delete", {"folder_id": item_id})
                    succeeded.append(item_id)
                except RuntimeError as e:
                    failed.append((item_id, str(e)))

        return BatchResult(succeeded=succeeded, failed=failed)

    def get_info(self, item_ids: List[str]) -> List[FileInfo]:
        results = []
        for item_id in item_ids:
            try:
                data = self._api_call("file/info", {"file_id": item_id})
                resp = data.get("response", {})
                fi = resp.get("file", {})
                if fi:
                    results.append(self._parse_file(fi))
            except RuntimeError:
                try:
                    data = self._api_call("folder/info", {"folder_id": item_id})
                    resp = data.get("response", {})
                    folder = resp.get("folder", {})
                    if folder:
                        results.append(self._parse_folder(folder))
                except RuntimeError:
                    pass
        return results

    def get_capabilities(self) -> FileManagerCapabilities:
        return RAPIDGATOR_CAPABILITIES

    # ------------------------------------------------------------------
    # Optional operations
    # ------------------------------------------------------------------

    def change_access(self, item_ids: List[str], access: str) -> BatchResult:
        mode = _ACCESS_MAP.get(access, 0)
        succeeded = []
        failed = []

        for item_id in item_ids:
            try:
                self._api_call("file/change_mode", {"file_id": item_id, "mode": mode})
                succeeded.append(item_id)
            except RuntimeError:
                try:
                    self._api_call("folder/change_mode", {"folder_id": item_id, "mode": mode})
                    succeeded.append(item_id)
                except RuntimeError as e:
                    failed.append((item_id, str(e)))

        return BatchResult(succeeded=succeeded, failed=failed)

    def copy(self, item_ids: List[str], dest_folder_id: str) -> BatchResult:
        succeeded = []
        failed = []

        # File copy supports CSV
        try:
            csv_ids = ",".join(item_ids)
            self._api_call("file/copy", {
                "file_id": csv_ids,
                "folder_id_dest": dest_folder_id,
            })
            succeeded = list(item_ids)
        except RuntimeError:
            for item_id in item_ids:
                try:
                    self._api_call("file/copy", {
                        "file_id": item_id,
                        "folder_id_dest": dest_folder_id,
                    })
                    succeeded.append(item_id)
                except RuntimeError:
                    try:
                        self._api_call("folder/copy", {
                            "folder_id": item_id,
                            "folder_id_dest": dest_folder_id,
                        })
                        succeeded.append(item_id)
                    except RuntimeError as e:
                        failed.append((item_id, str(e)))

        return BatchResult(succeeded=succeeded, failed=failed)

    def get_download_link(self, file_id: str) -> str:
        data = self._api_call("file/download", {"file_id": file_id})
        resp = data.get("response", {})
        return resp.get("download_url", f"https://rapidgator.net/file/{file_id}")

    def remote_upload_add(
        self, urls: List[str], folder_id: str = "/"
    ) -> OperationResult:
        csv_urls = ",".join(urls)
        data = self._api_call("remote/create", {"url": csv_urls})
        resp = data.get("response", {})
        jobs = resp.get("jobs", [])
        job_ids = [str(j.get("job_id", "")) for j in jobs]
        return OperationResult(
            success=len(job_ids) > 0,
            message=f"{len(job_ids)} remote upload(s) started",
            data={"job_ids": job_ids},
        )

    def remote_upload_status(
        self, job_ids: Optional[List[str]] = None
    ) -> List[RemoteJobStatus]:
        params = {}
        if job_ids and len(job_ids) == 1:
            params["job_id"] = job_ids[0]

        data = self._api_call("remote/info", params)
        resp = data.get("response", {})

        _STATUS_MAP = {0: "downloading", 1: "done", 2: "failed", 3: "canceled", 4: "waiting"}

        jobs = resp.get("jobs", [])
        if not jobs and "job" in resp:
            jobs = [resp["job"]]

        results = []
        for job in jobs:
            state_code = int(job.get("state", 0))
            file_data = job.get("file", {})
            file_id = None
            if isinstance(file_data, dict) and file_data:
                file_id = str(file_data.get("file_id", "")) or None

            # Compute progress from dl_size/size if available
            size = int(job.get("size", 0) or 0)
            dl_size = int(job.get("dl_size", 0) or 0)
            progress = int((dl_size / size) * 100) if size > 0 else 0
            if state_code == 1:  # Done
                progress = 100

            results.append(RemoteJobStatus(
                job_id=str(job.get("job_id", "")),
                status=_STATUS_MAP.get(state_code, "unknown"),
                progress=progress,
                file_id=file_id,
            ))
        return results

    # ------------------------------------------------------------------
    # Trash operations (RapidGator-only)
    # ------------------------------------------------------------------

    def trash_list(
        self, page: int = 1, per_page: int = 100
    ) -> FileListResult:
        params: Dict[str, Any] = {
            "page": page,
            "per_page": per_page,
        }
        data = self._api_call("trashcan/content", params)
        resp = data.get("response", {})

        files = []
        for f in resp.get("files", []):
            fi = self._parse_file(f)
            fi.is_available = False  # Trash items are "unavailable"
            files.append(fi)

        total = len(files)
        return FileListResult(files=files, total=total, page=page, per_page=per_page)

    def trash_restore(
        self, file_ids: Optional[List[str]] = None
    ) -> OperationResult:
        params = {}
        if file_ids:
            params["file_id"] = ",".join(file_ids)

        self._api_call("trashcan/restore", params)
        msg = f"Restored {len(file_ids)} file(s)" if file_ids else "Restored all files"
        return OperationResult(success=True, message=msg)

    def trash_empty(
        self, file_ids: Optional[List[str]] = None
    ) -> OperationResult:
        params = {}
        if file_ids:
            params["file_id"] = ",".join(file_ids)

        self._api_call("trashcan/empty", params)
        msg = f"Permanently deleted {len(file_ids)} file(s)" if file_ids else "Emptied trash"
        return OperationResult(success=True, message=msg)

    def get_account_info(self) -> dict:
        data = self._api_call("user/info")
        resp = data.get("response", {})
        user = resp.get("user", {})
        storage = user.get("storage", {})
        return {
            "is_premium": user.get("is_premium", False),
            "storage_total": storage.get("total"),
            "storage_left": storage.get("left"),
            "email": user.get("email"),
        }
