"""Abstract base class and data models for file manager clients.

Each file host implements FileManagerClient to expose whatever subset of
file management operations its API supports. The capabilities dataclass
tells the UI which actions to enable/disable per host.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple

from src.core.constants import CHROME_UA  # noqa: F401 — re-exported for file manager clients


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class FileInfo:
    """Represents a file or folder on a remote host."""
    id: str
    name: str
    is_folder: bool
    size: int = 0                           # bytes, 0 for folders
    created: Optional[datetime] = None
    access: str = "public"                  # public / premium / private
    is_available: bool = True
    md5: Optional[str] = None
    download_count: Optional[int] = None    # RapidGator only
    content_type: Optional[str] = None
    parent_id: Optional[str] = None


@dataclass
class FileListResult:
    """Paginated list of files/folders in a directory."""
    files: List[FileInfo]
    total: int              # total items for pagination
    page: int
    per_page: int


@dataclass
class FolderListResult:
    """Folder listing with breadcrumb path."""
    folders: List[FileInfo]                         # is_folder=True items
    breadcrumb: List[Tuple[str, str]] = field(      # [(id, name), ...]
        default_factory=list
    )


@dataclass
class FileManagerCapabilities:
    """Declares what operations a host supports — drives UI enable/disable."""
    can_rename: bool = True
    can_move: bool = True
    can_delete: bool = True
    can_copy: bool = False
    can_change_access: bool = False
    can_create_folder: bool = True
    can_remote_upload: bool = False
    can_trash: bool = False
    can_get_download_link: bool = False
    has_batch_operations: bool = False
    max_items_per_page: int = 100
    sortable_columns: List[str] = field(
        default_factory=lambda: ["name", "created", "size"]
    )


@dataclass
class BatchResult:
    """Result of a batch operation (move, delete, etc.)."""
    succeeded: List[str]                            # IDs that succeeded
    failed: List[Tuple[str, str]] = field(          # [(id, error_msg), ...]
        default_factory=list
    )

    @property
    def all_succeeded(self) -> bool:
        return len(self.failed) == 0


@dataclass
class OperationResult:
    """Result of a single operation."""
    success: bool
    message: str = ""
    data: Optional[dict] = None


@dataclass
class RemoteJobStatus:
    """Status of a remote (URL-to-storage) upload job."""
    job_id: str
    status: str         # downloading / done / failed / canceled / waiting
    progress: int = 0   # 0-100
    file_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------

class FileManagerClient(ABC):
    """Abstract base for file host file management operations.

    Subclasses implement the abstract methods for their host's API.
    Optional methods raise NotImplementedError by default — the UI checks
    get_capabilities() before calling them.
    """

    @abstractmethod
    def list_files(
        self,
        folder_id: str = "/",
        page: int = 1,
        per_page: int = 100,
        sort_by: str = "name",
        sort_dir: str = "asc",
    ) -> FileListResult:
        """List files and folders in a directory."""

    @abstractmethod
    def list_folders(self, parent_id: str = "/") -> FolderListResult:
        """List folder tree from a parent."""

    @abstractmethod
    def create_folder(
        self, name: str, parent_id: str = "/", access: str = "public"
    ) -> OperationResult:
        """Create a new folder."""

    @abstractmethod
    def rename(self, item_id: str, new_name: str) -> OperationResult:
        """Rename a file or folder."""

    @abstractmethod
    def move(self, item_ids: List[str], dest_folder_id: str) -> BatchResult:
        """Move files/folders to a destination folder."""

    @abstractmethod
    def delete(self, item_ids: List[str]) -> BatchResult:
        """Delete files/folders."""

    @abstractmethod
    def get_info(self, item_ids: List[str]) -> List[FileInfo]:
        """Get detailed info for files/folders."""

    @abstractmethod
    def get_capabilities(self) -> FileManagerCapabilities:
        """Return what this host supports."""

    # -- Optional operations (override if supported) -----------------------

    def change_access(
        self, item_ids: List[str], access: str
    ) -> BatchResult:
        raise NotImplementedError

    def copy(self, item_ids: List[str], dest_folder_id: str) -> BatchResult:
        raise NotImplementedError

    def get_download_link(self, file_id: str) -> str:
        raise NotImplementedError

    def remote_upload_add(
        self, urls: List[str], folder_id: str = "/"
    ) -> OperationResult:
        raise NotImplementedError

    def remote_upload_status(
        self, job_ids: Optional[List[str]] = None
    ) -> List[RemoteJobStatus]:
        raise NotImplementedError

    def trash_list(
        self, page: int = 1, per_page: int = 100
    ) -> FileListResult:
        raise NotImplementedError

    def trash_restore(
        self, file_ids: Optional[List[str]] = None
    ) -> OperationResult:
        raise NotImplementedError

    def trash_empty(
        self, file_ids: Optional[List[str]] = None
    ) -> OperationResult:
        raise NotImplementedError

    def get_account_info(self) -> dict:
        """Return account info (storage, expiry, etc.). Host-specific shape."""
        raise NotImplementedError
