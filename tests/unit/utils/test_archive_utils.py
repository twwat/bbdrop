#!/usr/bin/env python3
"""
Comprehensive test suite for archive_utils.py
Testing archive detection, validation, and path utilities
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from src.utils.archive_utils import (
    SUPPORTED_ARCHIVE_EXTENSIONS,
    is_archive_file,
    is_valid_archive,
    get_archive_name,
    get_archive_size,
    validate_temp_extraction_path,
    find_folders_with_files
)


class TestConstants:
    """Test module constants"""

    def test_supported_extensions(self):
        """Test supported archive extensions are defined"""
        assert '.zip' in SUPPORTED_ARCHIVE_EXTENSIONS
        assert '.cbz' in SUPPORTED_ARCHIVE_EXTENSIONS
        assert len(SUPPORTED_ARCHIVE_EXTENSIONS) >= 2


class TestIsArchiveFile:
    """Test archive file detection"""

    @pytest.mark.parametrize("filename,expected", [
        # Supported formats
        ("archive.zip", True),
        ("ARCHIVE.ZIP", True),
        ("comic.cbz", True),
        ("COMIC.CBZ", True),
        # Unsupported formats
        ("file.txt", False),
        ("image.jpg", False),
        ("document.pdf", False),
        ("archive.rar", False),
        ("archive.7z", False),
        ("archive.tar.gz", False),
        # Edge cases
        ("", False),
        (".zip", True),  # Hidden file
        ("archive", False),  # No extension
        ("archive.ZIP.backup", False),  # Wrong extension
    ])
    def test_extension_detection(self, filename, expected):
        """Test archive detection by extension"""
        assert is_archive_file(filename) == expected

    def test_path_object_input(self):
        """Test Path object input"""
        assert is_archive_file(Path("test.zip")) == True
        assert is_archive_file(Path("test.txt")) == False

    def test_none_input(self):
        """Test None input returns False"""
        assert is_archive_file(None) == False

    def test_empty_string(self):
        """Test empty string returns False"""
        assert is_archive_file("") == False

    def test_case_insensitive(self):
        """Test extension matching is case-insensitive"""
        assert is_archive_file("Archive.ZIP") == True
        assert is_archive_file("Comic.CbZ") == True

    def test_full_path(self):
        """Test with full path"""
        assert is_archive_file("/path/to/archive.zip") == True
        assert is_archive_file("C:\\Users\\test\\archive.cbz") == True


class TestIsValidArchive:
    """Test archive validation (existence + format)"""

    def test_valid_zip_file(self, tmp_path):
        """Test valid ZIP file returns True"""
        zip_file = tmp_path / "test.zip"
        zip_file.touch()
        assert is_valid_archive(zip_file) == True

    def test_valid_cbz_file(self, tmp_path):
        """Test valid CBZ file returns True"""
        cbz_file = tmp_path / "comic.cbz"
        cbz_file.touch()
        assert is_valid_archive(cbz_file) == True

    def test_nonexistent_file(self, tmp_path):
        """Test nonexistent file returns False"""
        zip_file = tmp_path / "nonexistent.zip"
        assert is_valid_archive(zip_file) == False

    def test_directory_not_valid(self, tmp_path):
        """Test directory returns False even with archive extension"""
        archive_dir = tmp_path / "archive.zip"
        archive_dir.mkdir()
        assert is_valid_archive(archive_dir) == False

    def test_wrong_extension(self, tmp_path):
        """Test file with wrong extension returns False"""
        txt_file = tmp_path / "file.txt"
        txt_file.touch()
        assert is_valid_archive(txt_file) == False

    def test_empty_path(self):
        """Test empty path returns False"""
        assert is_valid_archive("") == False

    def test_none_input(self):
        """Test None input returns False"""
        assert is_valid_archive(None) == False


class TestGetArchiveName:
    """Test archive name extraction"""

    @pytest.mark.parametrize("path,expected", [
        ("archive.zip", "archive"),
        ("my_comic.cbz", "my_comic"),
        ("/path/to/photos.zip", "photos"),
        ("C:\\Users\\test\\backup.zip", "backup"),
        ("file.with.dots.zip", "file.with.dots"),
        (".hidden.zip", ".hidden"),
    ])
    def test_name_extraction(self, path, expected):
        """Test extracting archive name without extension"""
        assert get_archive_name(path) == expected

    def test_path_object(self):
        """Test with Path object"""
        assert get_archive_name(Path("test.zip")) == "test"

    def test_empty_path(self):
        """Test empty path returns default"""
        assert get_archive_name("") == "archive"

    def test_none_input(self):
        """Test None input returns default"""
        assert get_archive_name(None) == "archive"

    def test_no_extension(self):
        """Test file with no extension"""
        assert get_archive_name("archive") == "archive"


class TestGetArchiveSize:
    """Test archive size retrieval"""

    def test_existing_file_size(self, tmp_path):
        """Test getting size of existing file"""
        zip_file = tmp_path / "test.zip"
        content = b"x" * 1024  # 1 KB
        zip_file.write_bytes(content)
        assert get_archive_size(zip_file) == 1024

    def test_empty_file(self, tmp_path):
        """Test empty file returns 0"""
        zip_file = tmp_path / "empty.zip"
        zip_file.touch()
        assert get_archive_size(zip_file) == 0

    def test_nonexistent_file(self, tmp_path):
        """Test nonexistent file returns 0"""
        zip_file = tmp_path / "nonexistent.zip"
        assert get_archive_size(zip_file) == 0

    def test_large_file(self, tmp_path):
        """Test large file size"""
        zip_file = tmp_path / "large.zip"
        content = b"x" * (10 * 1024 * 1024)  # 10 MB
        zip_file.write_bytes(content)
        assert get_archive_size(zip_file) == 10 * 1024 * 1024

    def test_directory_returns_zero(self, tmp_path):
        """Test directory path returns 0"""
        archive_dir = tmp_path / "dir.zip"
        archive_dir.mkdir()
        assert get_archive_size(archive_dir) == 0

    def test_path_object(self, tmp_path):
        """Test with Path object"""
        zip_file = tmp_path / "test.zip"
        zip_file.write_bytes(b"test")
        assert get_archive_size(zip_file) == 4


class TestValidateTempExtractionPath:
    """Test temp extraction path generation"""

    def test_basic_path_generation(self, tmp_path):
        """Test basic temp path generation"""
        archive = "photos.zip"
        result = validate_temp_extraction_path(tmp_path, archive)
        assert result == tmp_path / "extract_photos"
        assert not result.exists()

    def test_counter_on_conflict(self, tmp_path):
        """Test counter appended when path exists"""
        archive = "test.zip"
        base_dir = tmp_path / "extract_test"
        base_dir.mkdir()

        result = validate_temp_extraction_path(tmp_path, archive)
        assert result == tmp_path / "extract_test_1"

    def test_multiple_conflicts(self, tmp_path):
        """Test multiple conflicts increment counter"""
        archive = "test.zip"
        (tmp_path / "extract_test").mkdir()
        (tmp_path / "extract_test_1").mkdir()
        (tmp_path / "extract_test_2").mkdir()

        result = validate_temp_extraction_path(tmp_path, archive)
        assert result == tmp_path / "extract_test_3"

    def test_archive_name_extraction(self, tmp_path):
        """Test archive name is extracted properly"""
        archive = "/path/to/my_archive.cbz"
        result = validate_temp_extraction_path(tmp_path, archive)
        assert result == tmp_path / "extract_my_archive"

    def test_path_objects(self, tmp_path):
        """Test with Path objects for both parameters"""
        archive = Path("test.zip")
        result = validate_temp_extraction_path(tmp_path, archive)
        assert isinstance(result, Path)
        assert result == tmp_path / "extract_test"


class TestFindFoldersWithFiles:
    """Test finding folders containing files"""

    def test_single_folder_with_files(self, tmp_path):
        """Test finding single folder with files"""
        (tmp_path / "file1.txt").touch()
        (tmp_path / "file2.txt").touch()

        result = find_folders_with_files(tmp_path)
        assert len(result) == 1
        assert tmp_path in result

    def test_nested_folders_with_files(self, tmp_path):
        """Test finding nested folders with files"""
        # Create structure:
        # root/
        #   file1.txt
        #   sub1/
        #     file2.txt
        #   sub2/
        #     subsub/
        #       file3.txt

        (tmp_path / "file1.txt").touch()
        (tmp_path / "sub1").mkdir()
        (tmp_path / "sub1" / "file2.txt").touch()
        (tmp_path / "sub2").mkdir()
        (tmp_path / "sub2" / "subsub").mkdir()
        (tmp_path / "sub2" / "subsub" / "file3.txt").touch()

        result = find_folders_with_files(tmp_path)
        assert len(result) == 3
        assert tmp_path in result
        assert tmp_path / "sub1" in result
        assert tmp_path / "sub2" / "subsub" in result

    def test_empty_folders_excluded(self, tmp_path):
        """Test empty folders are not included"""
        (tmp_path / "with_files").mkdir()
        (tmp_path / "with_files" / "file.txt").touch()
        (tmp_path / "empty1").mkdir()
        (tmp_path / "empty2").mkdir()

        result = find_folders_with_files(tmp_path)
        assert len(result) == 1
        assert tmp_path / "with_files" in result

    def test_folders_with_only_subfolders(self, tmp_path):
        """Test folders with only subfolders (no files) are excluded"""
        (tmp_path / "parent").mkdir()
        (tmp_path / "parent" / "child").mkdir()
        (tmp_path / "parent" / "child" / "file.txt").touch()

        result = find_folders_with_files(tmp_path)
        # Only child should be included (has file)
        # Parent should be excluded (only has subfolder)
        assert tmp_path / "parent" / "child" in result
        assert len(result) == 1

    def test_empty_root(self, tmp_path):
        """Test empty root directory returns empty list"""
        result = find_folders_with_files(tmp_path)
        assert result == []

    def test_nonexistent_directory(self, tmp_path):
        """Test nonexistent directory returns empty list"""
        nonexistent = tmp_path / "nonexistent"
        result = find_folders_with_files(nonexistent)
        assert result == []

    def test_file_instead_of_directory(self, tmp_path):
        """Test passing a file path returns empty list"""
        file_path = tmp_path / "file.txt"
        file_path.touch()
        result = find_folders_with_files(file_path)
        assert result == []

    def test_mixed_content(self, tmp_path):
        """Test complex directory structure"""
        # Create:
        # root/file.txt
        # root/empty_dir/
        # root/dir_with_files/file1.txt
        # root/dir_with_files/subdir/file2.txt
        # root/dir_with_files/empty_subdir/

        (tmp_path / "file.txt").touch()
        (tmp_path / "empty_dir").mkdir()
        (tmp_path / "dir_with_files").mkdir()
        (tmp_path / "dir_with_files" / "file1.txt").touch()
        (tmp_path / "dir_with_files" / "subdir").mkdir()
        (tmp_path / "dir_with_files" / "subdir" / "file2.txt").touch()
        (tmp_path / "dir_with_files" / "empty_subdir").mkdir()

        result = find_folders_with_files(tmp_path)
        assert len(result) == 3
        assert tmp_path in result
        assert tmp_path / "dir_with_files" in result
        assert tmp_path / "dir_with_files" / "subdir" in result

    def test_hidden_files_counted(self, tmp_path):
        """Test hidden files are counted"""
        (tmp_path / ".hidden").touch()

        result = find_folders_with_files(tmp_path)
        assert len(result) == 1
        assert tmp_path in result
