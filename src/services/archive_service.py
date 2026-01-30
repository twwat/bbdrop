#!/usr/bin/env python3
"""
Archive extraction and cleanup service
Handles extracting archives and cleaning up temp directories
"""

import os
import shutil
import tarfile
import zipfile
from pathlib import Path
from typing import Optional

try:
    import py7zr
    HAS_7Z = True
except ImportError:
    HAS_7Z = False

try:
    import rarfile
    HAS_RAR = True
except ImportError:
    HAS_RAR = False

from src.utils.archive_utils import (
    is_valid_archive,
    validate_temp_extraction_path,
    find_folders_with_files,
    get_archive_type
)


class ArchiveService:
    """Service for extracting archives and managing temp directories"""

    def __init__(self, base_temp_dir: str | Path):
        """Initialize with base temporary directory

        Args:
            base_temp_dir: Base directory for temp extractions (e.g., ~/.bbdrop/temp)
        """
        self.base_temp_dir = Path(base_temp_dir)
        self.base_temp_dir.mkdir(parents=True, exist_ok=True)

    def _is_safe_tar_path(self, member_path: str) -> bool:
        """Check if tar member path is safe (no path traversal)

        Args:
            member_path: Path of tar member

        Returns:
            True if path is safe
        """
        # Reject absolute paths
        if os.path.isabs(member_path):
            return False

        # Reject paths with .. (parent directory traversal)
        path_parts = Path(member_path).parts
        if '..' in path_parts:
            return False

        return True

    def _extract_zip(self, archive_path: Path, temp_dir: Path) -> None:
        """Extract ZIP archive"""
        with zipfile.ZipFile(archive_path, 'r') as archive:
            archive.extractall(path=temp_dir)

    def _extract_rar(self, archive_path: Path, temp_dir: Path) -> None:
        """Extract RAR archive"""
        if not HAS_RAR:
            raise RuntimeError("rarfile library not available")

        with rarfile.RarFile(archive_path, 'r') as archive:
            archive.extractall(path=temp_dir)

    def _extract_7z(self, archive_path: Path, temp_dir: Path) -> None:
        """Extract 7-Zip archive"""
        if not HAS_7Z:
            raise RuntimeError("py7zr library not available")

        with py7zr.SevenZipFile(archive_path, 'r') as archive:
            archive.extractall(path=temp_dir)

    def _extract_tar(self, archive_path: Path, temp_dir: Path) -> None:
        """Extract TAR archive (handles .tar, .tar.gz, .tar.bz2)"""
        with tarfile.open(archive_path, 'r:*') as archive:
            # Security check: validate all member paths
            for member in archive.getmembers():
                if not self._is_safe_tar_path(member.name):
                    raise ValueError(f"Unsafe path in tar archive: {member.name}")

            archive.extractall(path=temp_dir)

    def extract_archive(self, archive_path: str | Path) -> Optional[Path]:
        """Extract archive to temp directory

        Args:
            archive_path: Path to archive file

        Returns:
            Path to extraction directory, or None if extraction failed
        """
        if not is_valid_archive(archive_path):
            return None

        # Get unique temp directory
        temp_dir = validate_temp_extraction_path(self.base_temp_dir, archive_path)

        try:
            # Create extraction directory
            temp_dir.mkdir(parents=True, exist_ok=True)

            # Extract based on archive type
            archive_path = Path(archive_path)
            archive_type = get_archive_type(archive_path)

            if archive_type == 'zip':
                self._extract_zip(archive_path, temp_dir)
            elif archive_type == 'rar':
                self._extract_rar(archive_path, temp_dir)
            elif archive_type == '7z':
                self._extract_7z(archive_path, temp_dir)
            elif archive_type == 'tar':
                self._extract_tar(archive_path, temp_dir)
            else:
                raise ValueError(f"Unsupported archive type: {archive_type}")

            return temp_dir

        except Exception:
            # Clean up on failure
            self.cleanup_temp_dir(temp_dir)
            return None

    def get_folders(self, temp_dir: Path) -> list[Path]:
        """Find folders with files in extracted directory

        Note: Queue manager handles image validation after folders are added

        Args:
            temp_dir: Extracted archive directory

        Returns:
            List of folder paths containing files
        """
        return find_folders_with_files(temp_dir)

    def cleanup_temp_dir(self, temp_dir: str | Path) -> bool:
        """Remove temp directory

        Args:
            temp_dir: Path to directory to remove

        Returns:
            True if successful
        """
        try:
            temp_path = Path(temp_dir)
            if temp_path.exists() and temp_path.is_dir():
                shutil.rmtree(temp_path)
            return True
        except Exception:
            return False
