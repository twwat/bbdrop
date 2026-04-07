"""File manager clients for browsing and managing files on remote hosts."""

from src.network.file_manager.client import (
    FileManagerClient,
    FileInfo,
    FileListResult,
    FolderListResult,
    FileManagerCapabilities,
    BatchResult,
    OperationResult,
    RemoteJobStatus,
)
from src.network.file_manager.factory import create_file_manager_client

__all__ = [
    "FileManagerClient",
    "FileInfo",
    "FileListResult",
    "FolderListResult",
    "FileManagerCapabilities",
    "BatchResult",
    "OperationResult",
    "RemoteJobStatus",
    "create_file_manager_client",
]
