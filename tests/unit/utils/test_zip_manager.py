"""Tests for archive_manager.py (and zip_manager.py backward compat wrapper)."""

import pytest
import zipfile
from pathlib import Path
from PIL import Image
from src.utils.archive_manager import ArchiveManager, get_archive_manager
from src.utils.zip_manager import ZIPManager, get_zip_manager


@pytest.fixture
def gallery_folder(tmp_path):
    """Create a test gallery folder with images."""
    folder = tmp_path / "gallery"
    folder.mkdir()
    for i in range(3):
        img = Image.new('RGB', (100, 100), color='red')
        img.save(folder / f"image{i}.jpg")
    return folder


@pytest.fixture
def manager(tmp_path):
    """Create an ArchiveManager with a temp directory."""
    return ArchiveManager(temp_dir=tmp_path)


# --- Initialization ---

class TestArchiveManagerInit:

    def test_init_with_temp_dir(self, tmp_path):
        m = ArchiveManager(temp_dir=tmp_path)
        assert m.temp_dir == tmp_path

    def test_init_without_temp_dir(self):
        m = ArchiveManager()
        assert m.temp_dir is not None
        assert m.temp_dir.exists()

    def test_init_creates_temp_dir(self, tmp_path):
        new_dir = tmp_path / "new_temp"
        ArchiveManager(temp_dir=new_dir)
        assert new_dir.exists()

    def test_cache_initialized_empty(self, manager):
        assert manager.archive_cache == {}

    def test_lock_initialized(self, manager):
        assert manager.lock is not None


# --- ZIP creation via new API ---

class TestCreateOrReuseArchive:

    def test_create_zip(self, manager, gallery_folder):
        paths = manager.create_or_reuse_archive(1, gallery_folder)
        assert len(paths) == 1
        assert paths[0].exists()
        assert paths[0].suffix == ".zip"
        assert zipfile.is_zipfile(paths[0])

    def test_added_to_cache(self, manager, gallery_folder):
        paths = manager.create_or_reuse_archive(1, gallery_folder)
        assert 1 in manager.archive_cache
        cached_paths, ref_count = manager.archive_cache[1]
        assert cached_paths[0] == paths[0]
        assert ref_count == 1

    def test_reuse_increments_ref(self, manager, gallery_folder):
        paths1 = manager.create_or_reuse_archive(1, gallery_folder)
        paths2 = manager.create_or_reuse_archive(1, gallery_folder)
        assert paths1[0] == paths2[0]
        _, ref_count = manager.archive_cache[1]
        assert ref_count == 2

    def test_zip_contains_images(self, manager, gallery_folder):
        paths = manager.create_or_reuse_archive(1, gallery_folder)
        with zipfile.ZipFile(paths[0], 'r') as zf:
            names = zf.namelist()
            assert len(names) == 3
            assert "image0.jpg" in names

    def test_store_compression_default(self, manager, gallery_folder):
        paths = manager.create_or_reuse_archive(1, gallery_folder)
        with zipfile.ZipFile(paths[0], 'r') as zf:
            for info in zf.infolist():
                assert info.compress_type == zipfile.ZIP_STORED

    def test_deflate_compression(self, manager, gallery_folder):
        paths = manager.create_or_reuse_archive(1, gallery_folder, compression='deflate')
        with zipfile.ZipFile(paths[0], 'r') as zf:
            for info in zf.infolist():
                assert info.compress_type == zipfile.ZIP_DEFLATED

    def test_empty_folder_raises(self, manager, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(ValueError, match="No image files found"):
            manager.create_or_reuse_archive(1, empty)

    def test_nonexistent_folder_raises(self, manager, tmp_path):
        with pytest.raises(FileNotFoundError):
            manager.create_or_reuse_archive(1, tmp_path / "nope")

    def test_file_instead_of_folder_raises(self, manager, tmp_path):
        f = tmp_path / "file.txt"
        f.touch()
        with pytest.raises(ValueError, match="not a directory"):
            manager.create_or_reuse_archive(1, f)

    def test_recreates_if_deleted_externally(self, manager, gallery_folder):
        paths = manager.create_or_reuse_archive(1, gallery_folder)
        paths[0].unlink()
        paths2 = manager.create_or_reuse_archive(1, gallery_folder)
        assert paths2[0].exists()

    def test_multiple_galleries(self, manager, gallery_folder):
        p1 = manager.create_or_reuse_archive(1, gallery_folder)
        p2 = manager.create_or_reuse_archive(2, gallery_folder)
        assert p1[0] != p2[0]
        assert len(manager.archive_cache) == 2


# --- Release ---

class TestReleaseArchive:

    def test_decrement_ref_count(self, manager, gallery_folder):
        manager.create_or_reuse_archive(1, gallery_folder)
        manager.create_or_reuse_archive(1, gallery_folder)  # ref=2
        deleted = manager.release_archive(1)
        assert not deleted
        _, ref_count = manager.archive_cache[1]
        assert ref_count == 1

    def test_release_last_ref_keeps_for_retry(self, manager, gallery_folder):
        paths = manager.create_or_reuse_archive(1, gallery_folder)
        deleted = manager.release_archive(1)
        assert not deleted
        assert paths[0].exists()
        assert 1 in manager.archive_cache
        _, ref_count = manager.archive_cache[1]
        assert ref_count == 0

    def test_force_delete(self, manager, gallery_folder):
        paths = manager.create_or_reuse_archive(1, gallery_folder)
        manager.create_or_reuse_archive(1, gallery_folder)  # ref=2
        deleted = manager.release_archive(1, force_delete=True)
        assert deleted
        assert not paths[0].exists()
        assert 1 not in manager.archive_cache

    def test_release_nonexistent(self, manager):
        assert manager.release_archive(999) is False

    def test_release_already_deleted_file(self, manager, gallery_folder):
        paths = manager.create_or_reuse_archive(1, gallery_folder)
        paths[0].unlink()
        deleted = manager.release_archive(1)
        assert not deleted
        assert 1 in manager.archive_cache
        _, ref_count = manager.archive_cache[1]
        assert ref_count == 0


# --- Cleanup ---

class TestCleanup:

    def test_cleanup_gallery(self, manager, gallery_folder):
        paths = manager.create_or_reuse_archive(1, gallery_folder)
        manager.cleanup_gallery(1)
        assert not paths[0].exists()
        assert 1 not in manager.archive_cache

    def test_cleanup_all(self, manager, gallery_folder):
        p1 = manager.create_or_reuse_archive(1, gallery_folder)
        p2 = manager.create_or_reuse_archive(2, gallery_folder)
        count = manager.cleanup_all()
        assert count == 2
        assert not p1[0].exists()
        assert not p2[0].exists()
        assert len(manager.archive_cache) == 0

    def test_cleanup_all_empty(self, manager):
        assert manager.cleanup_all() == 0


# --- Cache info ---

class TestCacheInfo:

    def test_structure(self, manager, gallery_folder):
        manager.create_or_reuse_archive(1, gallery_folder)
        info = manager.get_cache_info()
        assert 1 in info
        assert 'paths' in info[1]
        assert 'ref_count' in info[1]
        assert 'exists' in info[1]
        assert 'size_mb' in info[1]
        assert 'parts' in info[1]

    def test_values(self, manager, gallery_folder):
        paths = manager.create_or_reuse_archive(1, gallery_folder)
        info = manager.get_cache_info()
        assert info[1]['paths'][0] == str(paths[0])
        assert info[1]['ref_count'] == 1
        assert info[1]['exists'] is True
        assert info[1]['size_mb'] > 0
        assert info[1]['parts'] == 1

    def test_after_external_deletion(self, manager, gallery_folder):
        paths = manager.create_or_reuse_archive(1, gallery_folder)
        paths[0].unlink()
        info = manager.get_cache_info()
        assert info[1]['exists'] is False
        assert info[1]['size_mb'] == 0


# --- Archive name generation ---

class TestGenerateArchiveName:

    def test_with_gallery_name(self, manager):
        name = manager._generate_archive_name(42, "Test Gallery")
        assert "42" in name
        assert "Test" in name

    def test_without_gallery_name(self, manager):
        assert manager._generate_archive_name(42) == "bbdrop_gallery_42"

    def test_sanitization(self, manager):
        name = manager._generate_archive_name(1, "Test<>Gallery/Name")
        assert "<" not in name
        assert ">" not in name
        assert "/" not in name

    def test_length_limit(self, manager):
        name = manager._generate_archive_name(1, "A" * 100)
        assert len(name) < 100

    def test_empty_name_uses_default(self, manager):
        assert manager._generate_archive_name(1, "") == "bbdrop_gallery_1"


# --- Split ZIP ---

class TestSplitZipArchive:

    @pytest.fixture
    def large_gallery(self, tmp_path):
        """Create a gallery with enough data to force splitting."""
        folder = tmp_path / "large_gallery"
        folder.mkdir()
        # Create images large enough to exceed a tiny split size
        for i in range(5):
            img = Image.new('RGB', (500, 500), color='blue')
            img.save(folder / f"big{i}.jpg")
        return folder

    def test_split_zip_returns_multiple_parts(self, tmp_path, large_gallery):
        m = ArchiveManager(temp_dir=tmp_path)
        # Use a very small split size to force splitting
        paths = m.create_or_reuse_archive(
            1, large_gallery, archive_format='zip', split_size_mb=1
        )
        # Should have at least the final .zip part
        assert len(paths) >= 1
        assert all(p.exists() for p in paths)

    def test_split_zip_cached(self, tmp_path, large_gallery):
        m = ArchiveManager(temp_dir=tmp_path)
        paths1 = m.create_or_reuse_archive(
            1, large_gallery, archive_format='zip', split_size_mb=1
        )
        paths2 = m.create_or_reuse_archive(
            1, large_gallery, archive_format='zip', split_size_mb=1
        )
        assert paths1 == paths2
        _, ref_count = m.archive_cache[1]
        assert ref_count == 2

    def test_split_zip_cleanup(self, tmp_path, large_gallery):
        m = ArchiveManager(temp_dir=tmp_path)
        paths = m.create_or_reuse_archive(
            1, large_gallery, archive_format='zip', split_size_mb=1
        )
        m.cleanup_gallery(1)
        assert all(not p.exists() for p in paths)
        assert 1 not in m.archive_cache

    def test_split_zip_cache_info_parts(self, tmp_path, large_gallery):
        m = ArchiveManager(temp_dir=tmp_path)
        paths = m.create_or_reuse_archive(
            1, large_gallery, archive_format='zip', split_size_mb=1
        )
        info = m.get_cache_info()
        assert info[1]['parts'] == len(paths)

    def test_split_zip_empty_folder_raises(self, manager, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(ValueError, match="No image files found"):
            manager.create_or_reuse_archive(
                1, empty, archive_format='zip', split_size_mb=1
            )


# --- 7z archive ---

class TestSevenZipArchive:

    def test_create_7z(self, manager, gallery_folder):
        pytest.importorskip("py7zr")
        paths = manager.create_or_reuse_archive(
            1, gallery_folder, archive_format='7z', compression='lzma2'
        )
        assert len(paths) == 1
        assert paths[0].exists()
        assert paths[0].suffix == ".7z"

    def test_7z_cached(self, manager, gallery_folder):
        pytest.importorskip("py7zr")
        paths1 = manager.create_or_reuse_archive(
            1, gallery_folder, archive_format='7z'
        )
        paths2 = manager.create_or_reuse_archive(
            1, gallery_folder, archive_format='7z'
        )
        assert paths1[0] == paths2[0]
        _, ref_count = manager.archive_cache[1]
        assert ref_count == 2

    def test_7z_contains_images(self, manager, gallery_folder):
        py7zr = pytest.importorskip("py7zr")
        paths = manager.create_or_reuse_archive(
            1, gallery_folder, archive_format='7z'
        )
        with py7zr.SevenZipFile(paths[0], 'r') as sz:
            names = sz.getnames()
            assert len(names) == 3
            assert "image0.jpg" in names

    def test_7z_not_available_raises(self, manager, gallery_folder, monkeypatch):
        import src.utils.archive_manager as am
        monkeypatch.setattr(am, 'HAS_7Z_LIB', False)
        with pytest.raises(RuntimeError, match="py7zr"):
            manager.create_or_reuse_archive(
                1, gallery_folder, archive_format='7z'
            )


# --- Image file filtering ---

class TestGetImageFiles:

    def test_filters_image_extensions(self, manager, tmp_path):
        folder = tmp_path / "mixed"
        folder.mkdir()
        Image.new('RGB', (10, 10)).save(folder / "a.jpg")
        Image.new('RGB', (10, 10)).save(folder / "b.png")
        Image.new('RGB', (10, 10)).save(folder / "c.gif")
        (folder / "readme.txt").touch()
        (folder / "data.csv").touch()
        result = manager._get_image_files(folder)
        names = [p.name for p in result]
        assert "a.jpg" in names
        assert "b.png" in names
        assert "c.gif" in names
        assert "readme.txt" not in names
        assert "data.csv" not in names

    def test_all_supported_extensions(self, manager, tmp_path):
        folder = tmp_path / "allext"
        folder.mkdir()
        for ext in ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'):
            Image.new('RGB', (10, 10)).save(folder / f"img{ext}")
        result = manager._get_image_files(folder)
        assert len(result) == 6

    def test_sorted_output(self, manager, tmp_path):
        folder = tmp_path / "sorted"
        folder.mkdir()
        for name in ("c.jpg", "a.jpg", "b.jpg"):
            Image.new('RGB', (10, 10)).save(folder / name)
        result = manager._get_image_files(folder)
        assert [p.name for p in result] == ["a.jpg", "b.jpg", "c.jpg"]

    def test_case_insensitive_extensions(self, manager, tmp_path):
        folder = tmp_path / "case"
        folder.mkdir()
        Image.new('RGB', (10, 10)).save(folder / "photo.JPG")
        Image.new('RGB', (10, 10)).save(folder / "pic.Png")
        result = manager._get_image_files(folder)
        assert len(result) == 2

    def test_empty_folder(self, manager, tmp_path):
        folder = tmp_path / "empty"
        folder.mkdir()
        assert manager._get_image_files(folder) == []

    def test_nonexistent_raises(self, manager, tmp_path):
        with pytest.raises(FileNotFoundError):
            manager._get_image_files(tmp_path / "nope")

    def test_file_raises(self, manager, tmp_path):
        f = tmp_path / "file.txt"
        f.touch()
        with pytest.raises(ValueError):
            manager._get_image_files(f)


# --- Additional compression modes ---

class TestCompressionModes:

    def test_lzma_compression(self, manager, gallery_folder):
        paths = manager.create_or_reuse_archive(
            1, gallery_folder, compression='lzma'
        )
        with zipfile.ZipFile(paths[0], 'r') as zf:
            for info in zf.infolist():
                assert info.compress_type == zipfile.ZIP_LZMA

    def test_bzip2_compression(self, manager, gallery_folder):
        paths = manager.create_or_reuse_archive(
            1, gallery_folder, compression='bzip2'
        )
        with zipfile.ZipFile(paths[0], 'r') as zf:
            for info in zf.infolist():
                assert info.compress_type == zipfile.ZIP_BZIP2

    def test_unknown_compression_falls_back_to_stored(self, manager, gallery_folder):
        paths = manager.create_or_reuse_archive(
            1, gallery_folder, compression='bogus'
        )
        with zipfile.ZipFile(paths[0], 'r') as zf:
            for info in zf.infolist():
                assert info.compress_type == zipfile.ZIP_STORED


# --- Split 7z (CLI) ---

class TestSplit7zArchive:

    def test_split_7z_no_binary_raises(self, manager, gallery_folder, monkeypatch):
        import src.utils.archive_manager as am
        monkeypatch.setattr(am, '_find_7z_binary', lambda: None)
        with pytest.raises(RuntimeError, match="7-Zip is required"):
            manager.create_or_reuse_archive(
                1, gallery_folder, archive_format='7z', split_size_mb=1
            )


# --- Global singleton ---

class TestGetArchiveManager:

    def test_returns_archive_manager(self):
        m = get_archive_manager()
        assert isinstance(m, ArchiveManager)

    def test_singleton(self):
        assert get_archive_manager() is get_archive_manager()

    def test_has_temp_dir(self):
        m = get_archive_manager()
        assert m.temp_dir is not None
        assert m.temp_dir.exists()


# --- Backward compat (ZIPManager / get_zip_manager) ---

class TestBackwardCompat:

    def test_zip_manager_is_archive_manager(self):
        assert issubclass(ZIPManager, ArchiveManager)

    def test_create_or_reuse_zip(self, tmp_path, gallery_folder):
        m = ZIPManager(temp_dir=tmp_path)
        path = m.create_or_reuse_zip(1, gallery_folder)
        assert isinstance(path, Path)
        assert path.exists()
        assert zipfile.is_zipfile(path)

    def test_release_zip(self, tmp_path, gallery_folder):
        m = ZIPManager(temp_dir=tmp_path)
        m.create_or_reuse_zip(1, gallery_folder)
        assert m.release_zip(1) is False

    def test_get_zip_manager_returns_archive_manager(self):
        m = get_zip_manager()
        assert isinstance(m, ArchiveManager)

    def test_get_zip_manager_singleton(self):
        assert get_zip_manager() is get_zip_manager()
