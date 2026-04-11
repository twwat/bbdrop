"""Background worker for file manager API operations.

Runs on a QThread so API calls don't block the GUI. Operations are queued
and processed sequentially. Results are delivered via pyqtSignals.
"""

from __future__ import annotations

import queue
import traceback
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QThread, pyqtSignal

from src.network.file_manager.client import (
    BatchResult,
    FileInfo,
    FileListResult,
    FileManagerCapabilities,
    FileManagerClient,
    FolderListResult,
    OperationResult,
    RemoteJobStatus,
)
from src.network.file_manager.factory import create_file_manager_client
from src.utils.logger import log


class FileManagerWorker(QThread):
    """Background worker for file manager API calls.

    Submit operations via submit(). Results come back on signals.
    The worker creates/caches FileManagerClient instances per host.
    """

    # Result signals
    files_loaded = pyqtSignal(str, object)         # op_id, FileListResult
    folders_loaded = pyqtSignal(str, object)        # op_id, FolderListResult
    file_info_loaded = pyqtSignal(str, list)        # op_id, List[FileInfo]
    operation_complete = pyqtSignal(str, object)    # op_id, result (BatchResult/OperationResult)
    account_info_loaded = pyqtSignal(str, dict)     # op_id, account_info dict
    remote_jobs_loaded = pyqtSignal(str, list)      # op_id, List[RemoteJobStatus]
    error = pyqtSignal(str, str)                    # op_id, error_message
    loading = pyqtSignal(bool)                      # True when processing, False when idle

    def __init__(self, parent=None):
        super().__init__(parent)
        self._queue: queue.Queue[Optional[Dict[str, Any]]] = queue.Queue()
        self._clients: Dict[str, FileManagerClient] = {}
        self._running = True

    def run(self):
        while self._running:
            try:
                op = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if op is None:
                break

            self.loading.emit(True)
            try:
                self._process(op)
            except Exception as e:
                op_id = op.get("op_id", "unknown")
                log(f"File manager op failed: {e}\n{traceback.format_exc()}",
                    level="error", category="file_manager")
                self.error.emit(op_id, str(e))
            finally:
                self.loading.emit(False)

    def stop(self):
        self._running = False
        self._queue.put(None)

    def submit(self, operation: Dict[str, Any]):
        """Queue an operation for processing.

        Args:
            operation: Dict with keys:
                - op_id: str — unique ID for matching response to request
                - action: str — operation name (list_files, list_folders, etc.)
                - host_id: str — target host
                - auth_token: str (optional) — pre-decrypted token
                - ... action-specific params
        """
        self._queue.put(operation)

    def clear_queue(self):
        """Discard all pending operations."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def invalidate_client(self, host_id: str):
        """Remove cached client for a host (e.g. after credential change)."""
        self._clients.pop(host_id, None)

    # ------------------------------------------------------------------
    # Client management
    # ------------------------------------------------------------------

    def _get_client(self, host_id: str, auth_token: Optional[str] = None, *,
                    file_host_client: Optional[Any] = None) -> FileManagerClient:
        # Session-based hosts (filedot): never cache — always construct fresh
        # from the passed FileHostClient so the shared cookie jar stays current.
        if host_id == "filedot" and file_host_client is not None:
            return create_file_manager_client(host_id, file_host_client=file_host_client)
        if host_id not in self._clients or auth_token:
            self._clients[host_id] = create_file_manager_client(
                host_id, auth_token=auth_token
            )
        return self._clients[host_id]

    # ------------------------------------------------------------------
    # Operation dispatch
    # ------------------------------------------------------------------

    def _process(self, op: Dict[str, Any]):
        action = op["action"]
        op_id = op.get("op_id", "unknown")
        host_id = op["host_id"]
        auth_token = op.get("auth_token")
        file_host_client = op.get("file_host_client")
        file_host_worker = op.get("file_host_worker")
        client = self._get_client(host_id, auth_token, file_host_client=file_host_client)

        handler = getattr(self, f"_do_{action}", None)
        if handler is None:
            self.error.emit(op_id, f"Unknown action: {action}")
            return

        try:
            handler(client, op_id, op)
        finally:
            # After every session-based op, persist any cookie rotation back to
            # the worker so the upload session stays in sync.
            if file_host_worker is not None and file_host_client is not None:
                try:
                    file_host_worker._update_session_from_client(file_host_client)
                except Exception as e:
                    log(f"Failed to persist session state for {host_id}: {e}",
                        level="warning", category="file_manager")

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    def _do_list_files(self, client: FileManagerClient, op_id: str, op: dict):
        result = client.list_files(
            folder_id=op.get("folder_id", "/"),
            page=op.get("page", 1),
            per_page=op.get("per_page", 100),
            sort_by=op.get("sort_by", "name"),
            sort_dir=op.get("sort_dir", "asc"),
        )
        self.files_loaded.emit(op_id, result)

    def _do_list_folders(self, client: FileManagerClient, op_id: str, op: dict):
        result = client.list_folders(parent_id=op.get("parent_id", "/"))
        self.folders_loaded.emit(op_id, result)

    def _do_create_folder(self, client: FileManagerClient, op_id: str, op: dict):
        result = client.create_folder(
            name=op["name"],
            parent_id=op.get("parent_id", "/"),
            access=op.get("access", "public"),
        )
        self.operation_complete.emit(op_id, result)

    def _do_rename(self, client: FileManagerClient, op_id: str, op: dict):
        result = client.rename(item_id=op["item_id"], new_name=op["new_name"])
        self.operation_complete.emit(op_id, result)

    def _do_move(self, client: FileManagerClient, op_id: str, op: dict):
        result = client.move(
            item_ids=op["item_ids"],
            dest_folder_id=op["dest_folder_id"],
        )
        self.operation_complete.emit(op_id, result)

    def _do_delete(self, client: FileManagerClient, op_id: str, op: dict):
        result = client.delete(item_ids=op["item_ids"])
        self.operation_complete.emit(op_id, result)

    def _do_get_info(self, client: FileManagerClient, op_id: str, op: dict):
        result = client.get_info(item_ids=op["item_ids"])
        self.file_info_loaded.emit(op_id, result)

    def _do_change_access(self, client: FileManagerClient, op_id: str, op: dict):
        result = client.change_access(
            item_ids=op["item_ids"],
            access=op["access"],
        )
        self.operation_complete.emit(op_id, result)

    def _do_copy(self, client: FileManagerClient, op_id: str, op: dict):
        result = client.copy(
            item_ids=op["item_ids"],
            dest_folder_id=op["dest_folder_id"],
        )
        self.operation_complete.emit(op_id, result)

    def _do_get_download_link(self, client: FileManagerClient, op_id: str, op: dict):
        link = client.get_download_link(file_id=op["file_id"])
        self.operation_complete.emit(op_id, OperationResult(
            success=bool(link), message=link
        ))

    def _do_remote_upload_add(self, client: FileManagerClient, op_id: str, op: dict):
        result = client.remote_upload_add(
            urls=op["urls"],
            folder_id=op.get("folder_id", "/"),
        )
        self.operation_complete.emit(op_id, result)

    def _do_remote_upload_status(self, client: FileManagerClient, op_id: str, op: dict):
        result = client.remote_upload_status(job_ids=op.get("job_ids"))
        self.remote_jobs_loaded.emit(op_id, result)

    def _do_account_info(self, client: FileManagerClient, op_id: str, op: dict):
        result = client.get_account_info()
        self.account_info_loaded.emit(op_id, result)

    def _do_get_capabilities(self, client: FileManagerClient, op_id: str, op: dict):
        caps = client.get_capabilities()
        self.operation_complete.emit(op_id, OperationResult(
            success=True, data={"capabilities": caps}
        ))

    def _do_trash_list(self, client: FileManagerClient, op_id: str, op: dict):
        result = client.trash_list(
            page=op.get("page", 1),
            per_page=op.get("per_page", 100),
        )
        self.files_loaded.emit(op_id, result)

    def _do_trash_restore(self, client: FileManagerClient, op_id: str, op: dict):
        result = client.trash_restore(file_ids=op.get("file_ids"))
        self.operation_complete.emit(op_id, result)

    def _do_trash_empty(self, client: FileManagerClient, op_id: str, op: dict):
        result = client.trash_empty(file_ids=op.get("file_ids"))
        self.operation_complete.emit(op_id, result)

    def _do_set_file_public(self, client: FileManagerClient, op_id: str, op: dict):
        result = client.set_file_public(
            item_ids=op["item_ids"], value=op["value"],
        )
        self.operation_complete.emit(op_id, result)

    def _do_set_file_premium(self, client: FileManagerClient, op_id: str, op: dict):
        result = client.set_file_premium(
            item_ids=op["item_ids"], value=op["value"],
        )
        self.operation_complete.emit(op_id, result)

    def _do_read_file_properties(
        self, client: FileManagerClient, op_id: str, op: dict,
    ):
        scraped = client.read_file_properties(file_code=op["file_code"])
        # Stash the file_code so the controller knows which file this is for
        scraped_with_code = dict(scraped)
        scraped_with_code["_file_code"] = op["file_code"]
        self.operation_complete.emit(
            op_id,
            OperationResult(success=True, message="read", data=scraped_with_code),
        )

    def _do_update_file_properties(
        self, client: FileManagerClient, op_id: str, op: dict,
    ):
        result = client.update_file_properties(
            file_codes=op["file_codes"],
            fields=op["fields"],
            round_trip=op.get("round_trip", True),
        )
        self.operation_complete.emit(op_id, result)
