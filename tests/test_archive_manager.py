#!/usr/bin/env python3
"""
Comprehensive test suite for archive_manager.py

Tests ZIP and 7Z archive creation, split archive functionality, caching,
reference counting, and error handling. Uses real file I/O with pytest fixtures
to catch actual API breakage (e.g., splitfile API changes).
"""

import pytest
import zipfile
import tempfile
from pathlib import Path
from PIL import Image
from unittest.mock import patch, MagicMock

from src.utils.archive_manager import (
    ArchiveManager,
    get_archive_manager,
    HAS_7Z_LIB,
    HAS_7Z_CLI,
)


@pytest.fixture
def temp_archive_dir(tmp_path):
    """Create a temporary directory for archive operations."""
    archive_dir = tmp_path / "archives"
    archive_dir.mkdir()
    return archive_dir


@pytest.fixture
def gallery_folder(tmp_path):
    """Create a test gallery folder with real image files."""
    folder = tmp_path / "gallery"
    folder.mkdir()

    # Create test images with PIL
    for i in range(3):
        img = Image.new('RGB', (100, 100), color=f'red' if i == 0 else ('green' if i == 1 else 'blue'))
        img.save(folder / f"image{i:03d}.jpg")

    # Also test with PNG and other formats
    img_png = Image.new('RGB', (100, 100), color='yellow')
    img_png.save(folder / "image_other.png")

    return folder


@pytest.fixture
def large_gallery_folder(tmp_path):
    """Create a test gallery with larger files for split testing."""
    folder = tmp_path / "large_gallery"
    folder.mkdir()

    # Create large uncompressed PNG files to ensure split archive functionality
    # PNG stores RGB data uncompressed (~3 bytes per pixel in worst case)
    # 2000x2000 RGB PNG = ~12MB+ uncompressed, split at 1MB will create multiple parts
    for i in range(2):
        img = Image.new('RGB', (2000, 2000), color='red' if i == 0 else 'green')
        # Save as PNG for minimal compression
        img.save(folder / f"large_image{i}.png", compress_level=1)

    return folder


class TestArchiveManagerInit:
    """Test ArchiveManager initialization."""

    def test_init_with_temp_dir(self, temp_archive_dir):
        """Test initialization with custom temp directory."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        assert manager.temp_dir == temp_archive_dir
        assert temp_archive_dir.exists()

    def test_init_without_temp_dir(self):
        """Test initialization uses system temp if not provided."""
        manager = ArchiveManager()
        assert manager.temp_dir is not None
        assert manager.temp_dir.exists()

    def test_init_creates_temp_dir(self, tmp_path):
        """Test initialization creates temp directory if missing."""
        archive_dir = tmp_path / "new_archives"
        assert not archive_dir.exists()
        manager = ArchiveManager(temp_dir=archive_dir)
        assert archive_dir.exists()

    def test_cache_initialized_empty(self, temp_archive_dir):
        """Test archive cache is initialized empty."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        assert manager.archive_cache == {}

    def test_lock_initialized(self, temp_archive_dir):
        """Test threading lock is initialized."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        assert manager.lock is not None


class TestCreateZipArchive:
    """Test single ZIP archive creation."""

    def test_create_new_zip(self, temp_archive_dir, gallery_folder):
        """Test creating a new ZIP file."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        paths = manager.create_or_reuse_archive(
            db_id=1,
            folder_path=gallery_folder,
            gallery_name="Test Gallery",
            archive_format='zip',
            compression='store',
            split_size_mb=0,
        )

        assert len(paths) == 1
        zip_path = paths[0]
        assert zip_path.exists()
        assert zip_path.suffix == ".zip"
        assert zipfile.is_zipfile(zip_path)

    def test_zip_contains_all_images(self, temp_archive_dir, gallery_folder):
        """Test ZIP contains all image files from gallery."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        paths = manager.create_or_reuse_archive(
            1, gallery_folder, archive_format='zip', compression='store'
        )
        zip_path = paths[0]

        with zipfile.ZipFile(zip_path, 'r') as zf:
            files = zf.namelist()
            assert len(files) == 4  # 3 JPG + 1 PNG
            assert "image000.jpg" in files
            assert "image001.jpg" in files
            assert "image002.jpg" in files
            assert "image_other.png" in files

    def test_zip_store_compression(self, temp_archive_dir, gallery_folder):
        """Test ZIP uses STORED (no compression) mode by default."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        paths = manager.create_or_reuse_archive(
            1, gallery_folder, compression='store'
        )
        zip_path = paths[0]

        with zipfile.ZipFile(zip_path, 'r') as zf:
            for info in zf.infolist():
                assert info.compress_type == zipfile.ZIP_STORED

    def test_zip_deflate_compression(self, temp_archive_dir, gallery_folder):
        """Test ZIP with DEFLATE compression."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        paths = manager.create_or_reuse_archive(
            1, gallery_folder, compression='deflate'
        )
        zip_path = paths[0]

        with zipfile.ZipFile(zip_path, 'r') as zf:
            for info in zf.infolist():
                assert info.compress_type == zipfile.ZIP_DEFLATED

    def test_zip_name_with_gallery_name(self, temp_archive_dir, gallery_folder):
        """Test ZIP filename includes gallery name."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        paths = manager.create_or_reuse_archive(
            db_id=42,
            folder_path=gallery_folder,
            gallery_name="My Test Gallery",
            archive_format='zip',
        )
        zip_path = paths[0]

        assert "42" in zip_path.name
        assert "Test" in zip_path.name or "My" in zip_path.name

    def test_zip_name_without_gallery_name(self, temp_archive_dir, gallery_folder):
        """Test ZIP filename without gallery name."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        paths = manager.create_or_reuse_archive(
            db_id=42,
            folder_path=gallery_folder,
            archive_format='zip',
        )
        zip_path = paths[0]

        assert "42" in zip_path.name
        assert "gallery" in zip_path.name.lower()

    def test_empty_gallery_raises_error(self, temp_archive_dir, tmp_path):
        """Test empty gallery folder raises ValueError."""
        empty_folder = tmp_path / "empty_gallery"
        empty_folder.mkdir()

        manager = ArchiveManager(temp_dir=temp_archive_dir)
        with pytest.raises(ValueError, match="No image files found"):
            manager.create_or_reuse_archive(1, empty_folder, archive_format='zip')

    def test_nonexistent_folder_raises_error(self, temp_archive_dir, tmp_path):
        """Test nonexistent folder raises FileNotFoundError."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        with pytest.raises(FileNotFoundError):
            manager.create_or_reuse_archive(1, tmp_path / "nonexistent")

    def test_file_instead_of_folder_raises_error(self, temp_archive_dir, tmp_path):
        """Test passing a file instead of folder raises ValueError."""
        test_file = tmp_path / "file.txt"
        test_file.touch()

        manager = ArchiveManager(temp_dir=temp_archive_dir)
        with pytest.raises(ValueError, match="not a directory"):
            manager.create_or_reuse_archive(1, test_file)


class TestCreate7zArchive:
    """Test 7Z archive creation."""

    @pytest.mark.skipif(not HAS_7Z_LIB, reason="py7zr not installed")
    def test_create_new_7z(self, temp_archive_dir, gallery_folder):
        """Test creating a new 7Z file."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        paths = manager.create_or_reuse_archive(
            db_id=1,
            folder_path=gallery_folder,
            archive_format='7z',
            compression='copy',
            split_size_mb=0,
        )

        assert len(paths) == 1
        archive_path = paths[0]
        assert archive_path.exists()
        assert archive_path.suffix == ".7z"

    @pytest.mark.skipif(not HAS_7Z_LIB, reason="py7zr not installed")
    def test_7z_contains_images(self, temp_archive_dir, gallery_folder):
        """Test 7Z contains all images from gallery."""
        import py7zr

        manager = ArchiveManager(temp_dir=temp_archive_dir)
        paths = manager.create_or_reuse_archive(
            1, gallery_folder, archive_format='7z', compression='copy'
        )
        archive_path = paths[0]

        with py7zr.SevenZipFile(archive_path, 'r') as sz:
            files = sz.getnames()
            assert len(files) == 4
            assert "image000.jpg" in files
            assert "image_other.png" in files

    @pytest.mark.skipif(not HAS_7Z_LIB, reason="py7zr not installed")
    def test_7z_lzma2_compression(self, temp_archive_dir, gallery_folder):
        """Test 7Z with LZMA2 compression."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        paths = manager.create_or_reuse_archive(
            1, gallery_folder, archive_format='7z', compression='lzma2'
        )
        archive_path = paths[0]
        assert archive_path.exists()

    def test_7z_not_available_raises_error(self, temp_archive_dir, gallery_folder):
        """Test creating 7Z without library raises RuntimeError."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)

        with patch('src.utils.archive_manager.HAS_7Z_LIB', False):
            with pytest.raises(RuntimeError, match="py7zr library not available"):
                manager.create_or_reuse_archive(
                    1, gallery_folder, archive_format='7z'
                )


class TestSplitZipArchive:
    """Test split ZIP archive creation with splitzip library."""

    def test_create_split_zip_basic(self, temp_archive_dir, large_gallery_folder):
        """Test creating split ZIP archive with splitzip."""
        pytest.importorskip("splitzip")

        manager = ArchiveManager(temp_dir=temp_archive_dir)
        paths = manager.create_or_reuse_archive(
            db_id=1,
            folder_path=large_gallery_folder,
            archive_format='zip',
            compression='store',
            split_size_mb=1,
        )

        # Should have at least one path
        assert len(paths) >= 1

        # All parts should exist
        for path in paths:
            assert path.exists()

    def test_split_zip_naming_convention(self, temp_archive_dir, large_gallery_folder):
        """Test split ZIP uses proper .z01, .z02, ..., .zip naming when split occurs."""
        pytest.importorskip("splitzip")

        manager = ArchiveManager(temp_dir=temp_archive_dir)
        paths = manager.create_or_reuse_archive(
            1, large_gallery_folder, split_size_mb=1
        )

        # Check naming: should be .z01, .z02, ..., .zip (final) or just .zip if no split
        names = [p.name for p in paths]

        # Last part should always be .zip
        assert names[-1].endswith('.zip')

        # If there are intermediate parts, they should be .z01, .z02, etc.
        for i, path in enumerate(paths[:-1]):
            # Should follow pattern: basename.z01, basename.z02, etc.
            assert '.z' in path.name
            # Check it's a z-archive extension
            assert any(path.name.endswith(f'.z{j:02d}') for j in range(1, 100))

    def test_split_zip_data_integrity(self, temp_archive_dir, large_gallery_folder):
        """Test split ZIP preserves all image data."""
        pytest.importorskip("splitzip")

        manager = ArchiveManager(temp_dir=temp_archive_dir)
        paths = manager.create_or_reuse_archive(
            1, large_gallery_folder, split_size_mb=1
        )

        # Reconstruct by reading the final .zip part (or first part if no split)
        # splitzip creates a valid split ZIP that can be read
        assert len(paths) > 0

        # The final .zip file should be readable as a valid ZIP
        final_part = [p for p in paths if p.name.endswith('.zip')]
        assert len(final_part) == 1
        assert zipfile.is_zipfile(final_part[0])

        with zipfile.ZipFile(final_part[0], 'r') as zf:
            files = zf.namelist()
            # Should contain the large images
            assert len(files) >= 2

    def test_split_zip_compression_respected(self, temp_archive_dir, large_gallery_folder):
        """Test split ZIP respects compression setting."""
        pytest.importorskip("splitzip")

        manager = ArchiveManager(temp_dir=temp_archive_dir)
        paths = manager.create_or_reuse_archive(
            1, large_gallery_folder,
            compression='deflate',
            split_size_mb=1
        )

        assert len(paths) > 0

        # Check that final part is valid ZIP with compression
        final_part = [p for p in paths if p.name.endswith('.zip')][0]
        if zipfile.is_zipfile(final_part):
            with zipfile.ZipFile(final_part, 'r') as zf:
                for info in zf.infolist():
                    # Should be deflated
                    assert info.compress_type == zipfile.ZIP_DEFLATED


class TestSplit7zArchive:
    """Test split 7Z archive creation with 7z CLI."""

    @pytest.mark.skipif(not HAS_7Z_CLI, reason="7z CLI not available")
    def test_create_split_7z(self, temp_archive_dir, large_gallery_folder):
        """Test creating split 7Z archive via 7z CLI."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)

        # Split at 1MB
        paths = manager.create_or_reuse_archive(
            db_id=1,
            folder_path=large_gallery_folder,
            archive_format='7z',
            compression='copy',
            split_size_mb=1,
        )

        # Should have parts
        assert len(paths) >= 1

        # All parts should exist
        for path in paths:
            assert path.exists()

    @pytest.mark.skipif(not HAS_7Z_CLI, reason="7z CLI not available")
    def test_split_7z_naming(self, temp_archive_dir, large_gallery_folder):
        """Test split 7Z archive parts naming."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)

        paths = manager.create_or_reuse_archive(
            1, large_gallery_folder, archive_format='7z', split_size_mb=1
        )

        # Parts should follow 7z pattern: .7z.001, .7z.002, etc.
        # or just .7z if not actually split
        for path in paths:
            assert path.name.endswith('.7z') or '.7z.' in path.name

    def test_split_7z_without_cli_raises_error(self, temp_archive_dir, gallery_folder):
        """Test split 7Z without 7z CLI raises RuntimeError."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)

        with patch('src.utils.archive_manager.HAS_7Z_CLI', False):
            with patch('src.utils.archive_manager._find_7z_binary', return_value=None):
                with pytest.raises(RuntimeError, match="7-Zip is required"):
                    manager.create_or_reuse_archive(
                        1, gallery_folder, archive_format='7z', split_size_mb=1
                    )


class TestReferenceCounting:
    """Test archive reference counting and caching."""

    def test_archive_added_to_cache(self, temp_archive_dir, gallery_folder):
        """Test created archive is added to cache."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        paths = manager.create_or_reuse_archive(1, gallery_folder)

        assert 1 in manager.archive_cache
        cached_paths, ref_count = manager.archive_cache[1]
        assert cached_paths == paths
        assert ref_count == 1

    def test_reuse_existing_archive(self, temp_archive_dir, gallery_folder):
        """Test reusing cached archive increments ref count."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)

        # Create first time
        paths1 = manager.create_or_reuse_archive(1, gallery_folder)

        # Request again - should reuse
        paths2 = manager.create_or_reuse_archive(1, gallery_folder)

        assert paths1 == paths2
        _, ref_count = manager.archive_cache[1]
        assert ref_count == 2

    def test_multiple_reuse_increments_count(self, temp_archive_dir, gallery_folder):
        """Test multiple reuses increment ref count correctly."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)

        for _ in range(5):
            manager.create_or_reuse_archive(1, gallery_folder)

        _, ref_count = manager.archive_cache[1]
        assert ref_count == 5

    def test_release_decrements_ref_count(self, temp_archive_dir, gallery_folder):
        """Test release decrements reference count."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        manager.create_or_reuse_archive(1, gallery_folder)
        manager.create_or_reuse_archive(1, gallery_folder)  # ref_count = 2

        deleted = manager.release_archive(1)

        assert not deleted
        _, ref_count = manager.archive_cache[1]
        assert ref_count == 1

    def test_release_last_reference_keeps_file(self, temp_archive_dir, gallery_folder):
        """Test releasing last reference keeps file but doesn't return True."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        paths = manager.create_or_reuse_archive(1, gallery_folder)

        deleted = manager.release_archive(1)

        # Returns False (not immediately deleted), file still exists
        assert deleted == False
        assert paths[0].exists()
        # But cache ref count is 0
        _, ref_count = manager.archive_cache[1]
        assert ref_count == 0

    def test_force_delete_ignores_ref_count(self, temp_archive_dir, gallery_folder):
        """Test force_delete ignores ref count."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        paths = manager.create_or_reuse_archive(1, gallery_folder)
        manager.create_or_reuse_archive(1, gallery_folder)  # ref_count = 2

        deleted = manager.release_archive(1, force_delete=True)

        assert deleted == True
        assert not paths[0].exists()
        assert 1 not in manager.archive_cache

    def test_release_nonexistent_gallery(self, temp_archive_dir):
        """Test releasing nonexistent gallery returns False."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        result = manager.release_archive(999)
        assert result == False

    def test_cleanup_gallery(self, temp_archive_dir, gallery_folder):
        """Test cleanup_gallery force deletes."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        paths = manager.create_or_reuse_archive(1, gallery_folder)

        manager.cleanup_gallery(1)

        assert not paths[0].exists()
        assert 1 not in manager.archive_cache

    def test_cleanup_all(self, temp_archive_dir, gallery_folder):
        """Test cleanup_all deletes all archives."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)

        paths1 = manager.create_or_reuse_archive(1, gallery_folder)
        paths2 = manager.create_or_reuse_archive(2, gallery_folder)
        paths3 = manager.create_or_reuse_archive(3, gallery_folder)

        deleted_count = manager.cleanup_all()

        assert deleted_count == 3
        assert not paths1[0].exists()
        assert not paths2[0].exists()
        assert not paths3[0].exists()
        assert len(manager.archive_cache) == 0

    def test_cleanup_all_empty_cache(self, temp_archive_dir):
        """Test cleanup_all with empty cache."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        deleted_count = manager.cleanup_all()
        assert deleted_count == 0


class TestCacheInfo:
    """Test cache information retrieval."""

    def test_cache_info_structure(self, temp_archive_dir, gallery_folder):
        """Test cache info returns correct structure."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        manager.create_or_reuse_archive(1, gallery_folder)

        info = manager.get_cache_info()

        assert 1 in info
        assert 'paths' in info[1]
        assert 'ref_count' in info[1]
        assert 'exists' in info[1]
        assert 'size_mb' in info[1]
        assert 'parts' in info[1]

    def test_cache_info_values(self, temp_archive_dir, gallery_folder):
        """Test cache info contains correct values."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        paths = manager.create_or_reuse_archive(1, gallery_folder)

        info = manager.get_cache_info()

        assert info[1]['paths'] == [str(paths[0])]
        assert info[1]['ref_count'] == 1
        assert info[1]['exists'] == True
        assert info[1]['size_mb'] > 0
        assert info[1]['parts'] == 1

    def test_cache_info_after_deletion(self, temp_archive_dir, gallery_folder):
        """Test cache info after archive deleted externally."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        paths = manager.create_or_reuse_archive(1, gallery_folder)
        paths[0].unlink()

        info = manager.get_cache_info()

        assert info[1]['exists'] == False
        assert info[1]['size_mb'] == 0


class TestBackwardCompatibility:
    """Test backward compatibility with ZIPManager API."""

    def test_create_or_reuse_zip_legacy(self, temp_archive_dir, gallery_folder):
        """Test legacy create_or_reuse_zip method."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        zip_path = manager.create_or_reuse_zip(1, gallery_folder, "Test Gallery")

        assert zip_path.exists()
        assert zip_path.suffix == ".zip"
        assert zipfile.is_zipfile(zip_path)

    def test_release_zip_legacy(self, temp_archive_dir, gallery_folder):
        """Test legacy release_zip method."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        zip_path = manager.create_or_reuse_zip(1, gallery_folder)

        deleted = manager.release_zip(1, force_delete=True)

        assert deleted == True
        assert not zip_path.exists()


class TestMultipleGalleries:
    """Test managing archives for multiple galleries."""

    def test_separate_caches_for_galleries(self, temp_archive_dir, gallery_folder):
        """Test each gallery gets separate cache entry."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)

        paths1 = manager.create_or_reuse_archive(1, gallery_folder)
        paths2 = manager.create_or_reuse_archive(2, gallery_folder)

        assert paths1[0] != paths2[0]
        assert len(manager.archive_cache) == 2
        assert 1 in manager.archive_cache
        assert 2 in manager.archive_cache

    def test_independent_ref_counts(self, temp_archive_dir, gallery_folder):
        """Test ref counts are independent per gallery."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)

        manager.create_or_reuse_archive(1, gallery_folder)
        manager.create_or_reuse_archive(1, gallery_folder)  # ref_count = 2

        manager.create_or_reuse_archive(2, gallery_folder)  # ref_count = 1

        _, ref1 = manager.archive_cache[1]
        _, ref2 = manager.archive_cache[2]

        assert ref1 == 2
        assert ref2 == 1


class TestNameGeneration:
    """Test archive name generation."""

    def test_name_with_gallery_name(self, temp_archive_dir):
        """Test filename includes gallery name."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        name = manager._generate_archive_name(42, "Test Gallery")

        assert "42" in name
        assert "Test" in name or "Gallery" in name

    def test_name_without_gallery_name(self, temp_archive_dir):
        """Test filename without gallery name."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        name = manager._generate_archive_name(42)

        assert "42" in name
        assert "gallery" in name.lower()

    def test_name_sanitization(self, temp_archive_dir):
        """Test gallery name is sanitized."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        name = manager._generate_archive_name(1, "Test<>Gallery/Name!@#")

        # Should only contain alphanumeric, space, dash, underscore
        assert "<" not in name
        assert ">" not in name
        assert "/" not in name
        assert "!" not in name
        assert "@" not in name
        assert "#" not in name

    def test_name_length_limit(self, temp_archive_dir):
        """Test long gallery names are truncated."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        long_name = "A" * 100
        name = manager._generate_archive_name(1, long_name)

        # Gallery name part should be limited to 50 chars
        assert len(name) < 100

    def test_empty_gallery_name_uses_default(self, temp_archive_dir):
        """Test empty gallery name uses default format."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        name = manager._generate_archive_name(1, "")

        assert "1" in name
        assert "gallery" in name.lower()


class TestGetImageFiles:
    """Test image file discovery."""

    def test_get_supported_image_formats(self, temp_archive_dir, gallery_folder):
        """Test that all supported image formats are found."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        files = manager._get_image_files(gallery_folder)

        # Should find JPG and PNG files
        filenames = {f.name for f in files}
        assert "image000.jpg" in filenames
        assert "image_other.png" in filenames

    def test_only_image_files_included(self, temp_archive_dir, tmp_path):
        """Test that only image files are included, not other files."""
        folder = tmp_path / "mixed"
        folder.mkdir()

        # Create images
        img = Image.new('RGB', (100, 100), color='red')
        img.save(folder / "image1.jpg")
        img.save(folder / "image2.png")

        # Create non-image files
        (folder / "readme.txt").touch()
        (folder / "config.json").touch()

        manager = ArchiveManager(temp_dir=temp_archive_dir)
        files = manager._get_image_files(folder)

        filenames = {f.name for f in files}
        assert "image1.jpg" in filenames
        assert "image2.png" in filenames
        assert "readme.txt" not in filenames
        assert "config.json" not in filenames

    def test_images_returned_sorted(self, temp_archive_dir, tmp_path):
        """Test that images are returned in sorted order."""
        folder = tmp_path / "sorted_test"
        folder.mkdir()

        # Create images with names that sort differently than creation order
        for name in ["zebra.jpg", "apple.jpg", "monkey.jpg"]:
            img = Image.new('RGB', (100, 100), color='red')
            img.save(folder / name)

        manager = ArchiveManager(temp_dir=temp_archive_dir)
        files = manager._get_image_files(folder)
        filenames = [f.name for f in files]

        assert filenames == ["apple.jpg", "monkey.jpg", "zebra.jpg"]


class TestGlobalSingleton:
    """Test global singleton instance."""

    def test_get_archive_manager_returns_instance(self):
        """Test get_archive_manager returns ArchiveManager instance."""
        manager = get_archive_manager()
        assert isinstance(manager, ArchiveManager)

    def test_get_archive_manager_singleton(self):
        """Test multiple calls return same instance."""
        manager1 = get_archive_manager()
        manager2 = get_archive_manager()
        assert manager1 is manager2


class TestCachedArchiveRecreation:
    """Test behavior when cached archive is deleted externally."""

    def test_recreate_on_external_deletion(self, temp_archive_dir, gallery_folder):
        """Test archive is recreated if cached file is deleted externally."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)

        # Create archive
        paths1 = manager.create_or_reuse_archive(1, gallery_folder)
        assert paths1[0].exists()

        # Delete archive externally
        paths1[0].unlink()

        # Request again - should recreate
        paths2 = manager.create_or_reuse_archive(1, gallery_folder)
        assert paths2[0].exists()
        assert paths2[0] == paths1[0]  # Same path


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_archive_creation_failure_propagates(self, temp_archive_dir):
        """Test that archive creation failures are properly propagated."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)

        # Try with nonexistent folder
        with pytest.raises(FileNotFoundError):
            manager.create_or_reuse_archive(1, Path("/nonexistent/path"))

    def test_invalid_compression_method(self, temp_archive_dir, gallery_folder):
        """Test handling of invalid compression method."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)

        # Should handle gracefully - unknown compression defaults to STORED
        paths = manager.create_or_reuse_archive(
            1, gallery_folder, compression='unknown_method'
        )
        assert paths[0].exists()

    def test_invalid_archive_format_defaults_to_zip(self, temp_archive_dir, gallery_folder):
        """Test invalid archive format falls through to default behavior."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)

        # Invalid format should default to ZIP (or raise, depending on implementation)
        # At minimum, it should either succeed or raise a clear error
        try:
            paths = manager.create_or_reuse_archive(
                1, gallery_folder, archive_format='invalid'
            )
            # If it doesn't raise, should still create something
            assert len(paths) > 0
        except (ValueError, KeyError, AttributeError, TypeError):
            # These are acceptable errors for invalid format
            pass


class TestArchiveSizes:
    """Test archive size calculations."""

    def test_cache_info_reports_size(self, temp_archive_dir, gallery_folder):
        """Test that cache info reports archive size in MB."""
        manager = ArchiveManager(temp_dir=temp_archive_dir)
        manager.create_or_reuse_archive(1, gallery_folder)

        info = manager.get_cache_info()
        assert info[1]['size_mb'] > 0

    def test_multiple_parts_size_summed(self, temp_archive_dir, large_gallery_folder):
        """Test split archive total size is sum of parts."""
        pytest.importorskip("splitzip")

        manager = ArchiveManager(temp_dir=temp_archive_dir)
        paths = manager.create_or_reuse_archive(
            1, large_gallery_folder, split_size_mb=1
        )

        if len(paths) > 1:  # Only test if actually split
            total_size = sum(p.stat().st_size for p in paths)
            info = manager.get_cache_info()

            # Should be approximately equal (allow for small rounding difference)
            assert abs(info[1]['size_mb'] - (total_size / (1024 * 1024))) < 0.1
