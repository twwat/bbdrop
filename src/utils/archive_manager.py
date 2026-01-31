"""
Archive manager for file host uploads.

Generalized archive creation supporting multiple formats (ZIP, 7Z),
configurable compression, and split archive support.

Replaces the ZIP-only ZIPManager with format-agnostic archive creation.
"""

import os
import shutil
import subprocess
import tempfile
import threading
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.utils.logger import log

try:
    import py7zr
    HAS_7Z_LIB = True
except ImportError:
    HAS_7Z_LIB = False


_custom_7z_path: Optional[str] = None


def _find_7z_binary() -> Optional[str]:
    """Find the 7z binary on the system."""
    # Check user-configured custom path first
    if _custom_7z_path and os.path.isfile(_custom_7z_path):
        return _custom_7z_path
    # Check saved QSettings path
    try:
        from PyQt6.QtCore import QSettings
        settings = QSettings("BBDropUploader", "BBDropGUI")
        saved = settings.value("Archive/7z_path", "")
        if saved and os.path.isfile(saved):
            return saved
    except Exception:
        pass
    # Check common names on PATH
    for name in ('7z', '7za', '7zz'):
        path = shutil.which(name)
        if path:
            return path
    # Windows: check common install locations
    for prog_dir in (os.environ.get('ProgramFiles', ''), os.environ.get('ProgramFiles(x86)', '')):
        if prog_dir:
            candidate = os.path.join(prog_dir, '7-Zip', '7z.exe')
            if os.path.isfile(candidate):
                return candidate
    return None


HAS_7Z_CLI = _find_7z_binary() is not None


# Compression method mappings
ZIP_COMPRESSION_MAP = {
    'store': zipfile.ZIP_STORED,
    'deflate': zipfile.ZIP_DEFLATED,
    'lzma': zipfile.ZIP_LZMA,
    'bzip2': zipfile.ZIP_BZIP2,
}

SEVENZ_COMPRESSION_MAP = {
    'copy': 'COPY',
    'lzma2': 'LZMA2',
    'lzma': 'LZMA',
    'deflate': 'DEFLATE',
    'bzip2': 'BZIP2',
}


class ArchiveManager:
    """Manages temporary archive files with reference counting for reuse across hosts.

    Supports ZIP and 7Z formats with configurable compression and optional
    split archive creation via splitzip and 7z CLI.
    """

    def __init__(self, temp_dir: Optional[Path] = None):
        """Initialize archive manager.

        Args:
            temp_dir: Directory for temporary archives. If None, uses system temp.
        """
        self.temp_dir = temp_dir or Path(tempfile.gettempdir())
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # Cache: {gallery_id: (archive_paths, ref_count)}
        self.archive_cache: Dict[int, Tuple[List[Path], int]] = {}
        self.lock = threading.Lock()

    def create_or_reuse_archive(
        self,
        db_id: int,
        folder_path: Path,
        gallery_name: Optional[str] = None,
        archive_format: str = 'zip',
        compression: str = 'store',
        split_size_mb: int = 0,
    ) -> List[Path]:
        """Create a new archive or return existing cached archive paths.

        Args:
            db_id: Unique database ID
            folder_path: Path to gallery folder
            gallery_name: Optional gallery name for archive filename
            archive_format: 'zip' or '7z'
            compression: Compression method (format-dependent)
            split_size_mb: Split size in MB (0 = no split)

        Returns:
            List of archive file paths (1 for non-split, N for split)

        Raises:
            Exception: If archive creation fails
        """
        with self.lock:
            if db_id in self.archive_cache:
                paths, ref_count = self.archive_cache[db_id]
                if paths and all(p.exists() for p in paths):
                    self.archive_cache[db_id] = (paths, ref_count + 1)
                    log(
                        f"Reusing existing archive for gallery {db_id} (refs: {ref_count + 1})",
                        level="debug", category="file_hosts"
                    )
                    return paths
                else:
                    log(
                        f"Cached archive no longer exists for gallery {db_id}, recreating...",
                        level="warning", category="file_hosts"
                    )
                    del self.archive_cache[db_id]

            # Create new archive
            base_name = self._generate_archive_name(db_id, gallery_name)
            log(f"Creating {archive_format.upper()} archive for gallery {db_id}: {base_name}",
                level="info", category="file_hosts")

            try:
                if split_size_mb > 0:
                    paths = self._create_split_archive(
                        folder_path, base_name, archive_format, compression, split_size_mb
                    )
                elif archive_format == '7z':
                    paths = [self._create_7z(folder_path, base_name, compression)]
                else:
                    paths = [self._create_zip(folder_path, base_name, compression)]

                self.archive_cache[db_id] = (paths, 1)

                total_size = sum(p.stat().st_size for p in paths)
                size_mb = total_size / (1024 * 1024)
                log(
                    f"Created archive: {len(paths)} part(s), {size_mb:.2f} MiB total",
                    level="info", category="file_hosts"
                )
                return paths

            except Exception as e:
                log(f"Failed to create archive for gallery {db_id}: {e}",
                    level="error", category="file_hosts")
                raise

    def release_archive(self, db_id: int, force_delete: bool = False) -> bool:
        """Release a reference to an archive. Deletes when ref_count reaches 0.

        Args:
            db_id: Database ID
            force_delete: If True, delete immediately regardless of ref count

        Returns:
            True if archive was deleted, False otherwise
        """
        with self.lock:
            if db_id not in self.archive_cache:
                log(f"Attempted to release non-existent archive for gallery {db_id}",
                    level="warning", category="file_hosts")
                return False

            paths, ref_count = self.archive_cache[db_id]

            if force_delete:
                deleted = False
                for p in paths:
                    try:
                        if p.exists():
                            p.unlink()
                            deleted = True
                    except (OSError, PermissionError) as e:
                        log(f"Failed to delete {p}: {e}", level="error", category="file_hosts")
                del self.archive_cache[db_id]
                return deleted
            elif ref_count <= 1:
                self.archive_cache[db_id] = (paths, 0)
                log(f"Released archive reference for gallery {db_id} (refs: 0, kept for retry)",
                    level="debug", category="file_hosts")
                return False
            else:
                self.archive_cache[db_id] = (paths, ref_count - 1)
                log(f"Released archive reference for gallery {db_id} (refs: {ref_count - 1})",
                    level="debug", category="file_hosts")
                return False

    def cleanup_gallery(self, gallery_id: int) -> None:
        """Force cleanup of archive for a gallery."""
        self.release_archive(gallery_id, force_delete=True)

    def cleanup_all(self) -> int:
        """Clean up all cached archives. Use when shutting down.

        Returns:
            Number of archives deleted
        """
        with self.lock:
            gallery_ids = list(self.archive_cache.keys())

        deleted_count = 0
        for gallery_id in gallery_ids:
            if self.release_archive(gallery_id, force_delete=True):
                deleted_count += 1
        return deleted_count

    def get_cache_info(self) -> Dict[int, Dict]:
        """Get information about cached archives."""
        with self.lock:
            info = {}
            for gallery_id, (paths, ref_count) in self.archive_cache.items():
                total_size = sum(
                    p.stat().st_size for p in paths if p.exists()
                )
                info[gallery_id] = {
                    'paths': [str(p) for p in paths],
                    'ref_count': ref_count,
                    'exists': all(p.exists() for p in paths),
                    'size_mb': total_size / (1024 * 1024),
                    'parts': len(paths),
                }
            return info

    # --- Backward compatibility with ZIPManager API ---

    def create_or_reuse_zip(
        self,
        db_id: int,
        folder_path: Path,
        gallery_name: Optional[str] = None,
    ) -> Path:
        """Legacy API: Create or reuse a ZIP archive (single file).

        Returns:
            Path to the ZIP file (first/only part)
        """
        paths = self.create_or_reuse_archive(
            db_id, folder_path, gallery_name,
            archive_format='zip', compression='store', split_size_mb=0,
        )
        return paths[0]

    def release_zip(self, db_id: int, force_delete: bool = False) -> bool:
        """Legacy API: Release a ZIP reference."""
        return self.release_archive(db_id, force_delete=force_delete)

    # --- Private creation methods ---

    def _generate_archive_name(self, gallery_id: int, gallery_name: Optional[str] = None) -> str:
        """Generate base archive name (without extension)."""
        if gallery_name:
            safe_name = "".join(
                c for c in gallery_name if c.isalnum() or c in (' ', '-', '_')
            ).strip()[:50]
            if safe_name:
                return f"bbdrop_{gallery_id}_{safe_name}"
        return f"bbdrop_gallery_{gallery_id}"

    def _create_zip(self, folder_path: Path, base_name: str, compression: str) -> Path:
        """Create a single ZIP archive."""
        zip_path = self.temp_dir / f"{base_name}.zip"
        compression_type = ZIP_COMPRESSION_MAP.get(compression, zipfile.ZIP_STORED)

        image_files = self._get_image_files(folder_path)
        if not image_files:
            raise ValueError(f"No image files found in: {folder_path}")

        with zipfile.ZipFile(zip_path, 'w', compression_type) as zf:
            for image_file in image_files:
                zf.write(image_file, arcname=image_file.name)

        if not zip_path.exists():
            raise RuntimeError(f"ZIP file was not created: {zip_path}")

        return zip_path

    def _create_7z(self, folder_path: Path, base_name: str, compression: str) -> Path:
        """Create a single 7Z archive using py7zr."""
        if not HAS_7Z_LIB:  # noqa: guard import availability
            raise RuntimeError("py7zr library not available. Install with: pip install py7zr")

        archive_path = self.temp_dir / f"{base_name}.7z"
        compression_name = SEVENZ_COMPRESSION_MAP.get(compression, 'COPY')

        image_files = self._get_image_files(folder_path)
        if not image_files:
            raise ValueError(f"No image files found in: {folder_path}")

        filter_map = {
            'LZMA2': py7zr.FILTER_LZMA2,
            'LZMA': py7zr.FILTER_LZMA,
            'DEFLATE': py7zr.FILTER_DEFLATE,
            'BZIP2': py7zr.FILTER_BZIP2,
            'COPY': py7zr.FILTER_COPY,
        }
        filters = [{'id': filter_map.get(compression_name, py7zr.FILTER_COPY)}]

        with py7zr.SevenZipFile(archive_path, 'w', filters=filters) as sz:
            for image_file in image_files:
                sz.write(image_file, arcname=image_file.name)

        if not archive_path.exists():
            raise RuntimeError(f"7Z file was not created: {archive_path}")

        return archive_path

    def _create_split_archive(
        self,
        folder_path: Path,
        base_name: str,
        archive_format: str,
        compression: str,
        split_size_mb: int,
    ) -> List[Path]:
        """Create a split archive.

        ZIP: uses splitzip (pure Python, proper split ZIP spec).
        7z: uses 7z CLI (requires 7-Zip installed).
        """
        image_files = self._get_image_files(folder_path)
        if not image_files:
            raise ValueError(f"No image files found in: {folder_path}")

        split_size_bytes = split_size_mb * 1024 * 1024

        if archive_format == 'zip':
            return self._create_split_zip(image_files, base_name, compression, split_size_bytes)
        else:
            return self._create_split_7z(image_files, base_name, compression, split_size_mb)

    def _create_split_zip(
        self, image_files: List[Path], base_name: str,
        compression: str, split_size_bytes: int
    ) -> List[Path]:
        """Create a split ZIP using splitzip (proper split ZIP spec)."""
        from splitzip import SplitZipWriter, STORED, DEFLATED

        compression_map = {
            'store': STORED,
            'deflate': DEFLATED,
        }
        comp = compression_map.get(compression, STORED)

        archive_path = self.temp_dir / f"{base_name}.zip"
        with SplitZipWriter(str(archive_path), split_size=split_size_bytes, compression=comp) as zf:
            for image_file in image_files:
                zf.write(str(image_file), arcname=image_file.name)

        # splitzip creates: .z01, .z02, ..., .zip (final volume)
        # Collect all parts in order
        parts = sorted(self.temp_dir.glob(f"{base_name}.z[0-9]*"))
        zip_final = self.temp_dir / f"{base_name}.zip"
        if zip_final.exists():
            parts.append(zip_final)

        if not parts:
            raise RuntimeError(f"No archive files found for {base_name}")
        return parts

    def _create_split_7z(
        self, image_files: List[Path], base_name: str,
        compression: str, split_size_mb: int
    ) -> List[Path]:
        """Create a split 7z archive using the 7z CLI."""
        sz_bin = _find_7z_binary()
        if not sz_bin:
            raise RuntimeError(
                "7-Zip is required for split 7z archives but was not found.\n"
                "Install from: https://www.7-zip.org/download.html"
            )

        archive_path = self.temp_dir / f"{base_name}.7z"

        compression_map = {
            'store': '0', 'copy': '0',
            'deflate': '5', 'lzma': '9', 'lzma2': '9', 'bzip2': '7',
        }
        mx_level = compression_map.get(compression, '0')

        cmd = [
            sz_bin, 'a',
            '-t7z',
            f'-mx{mx_level}',
            f'-v{split_size_mb}m',
            str(archive_path),
        ]
        for image_file in image_files:
            cmd.append(str(image_file))

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"7z failed (exit {result.returncode}): {result.stderr or result.stdout}"
            )

        parts = sorted(self.temp_dir.glob(f"{base_name}.7z.*"))
        if not parts:
            if archive_path.exists():
                return [archive_path]
            raise RuntimeError(f"No archive files found for {base_name}")
        return parts

    def _get_image_files(self, folder_path: Path) -> List[Path]:
        """Get sorted list of image files in a folder."""
        if not folder_path.exists():
            raise FileNotFoundError(f"Folder does not exist: {folder_path}")
        if not folder_path.is_dir():
            raise ValueError(f"Path is not a directory: {folder_path}")

        image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')
        return sorted(
            f for f in folder_path.iterdir()
            if f.is_file() and f.suffix.lower() in image_extensions
        )


# Global singleton instance
_archive_manager: Optional[ArchiveManager] = None
_archive_manager_lock = threading.Lock()


def get_archive_manager() -> ArchiveManager:
    """Get or create the global ArchiveManager instance."""
    global _archive_manager
    if _archive_manager is None:
        with _archive_manager_lock:
            if _archive_manager is None:
                _archive_manager = ArchiveManager()
    return _archive_manager
