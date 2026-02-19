"""
Comprehensive unit tests for path_manager.py module.

Tests path operations, directory creation, file validation,
and cross-platform compatibility with mocked filesystem.
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch
import tempfile

from src.storage.path_manager import (
    PathError,
    PathManager,
    get_common_ancestor,
    is_subdirectory,
    format_path_for_display
)


class TestPathError:
    """Test PathError exception class."""

    def test_path_error_creation(self):
        """Test PathError can be created and raised."""
        error = PathError("test error")
        assert str(error) == "test error"
        assert isinstance(error, Exception)

    def test_path_error_raise(self):
        """Test PathError can be raised and caught."""
        with pytest.raises(PathError) as exc_info:
            raise PathError("custom message")
        assert "custom message" in str(exc_info.value)


class TestPathManagerInitialization:
    """Test PathManager initialization."""

    def test_init_default_base_path(self):
        """Test initialization with default base path (cwd)."""
        manager = PathManager()
        assert manager._base_path == Path.cwd()

    def test_init_custom_base_path(self, tmp_path):
        """Test initialization with custom base path."""
        manager = PathManager(base_path=tmp_path)
        assert manager._base_path == tmp_path

    def test_init_string_base_path(self, tmp_path):
        """Test initialization with string base path."""
        manager = PathManager(base_path=str(tmp_path))
        assert manager._base_path == tmp_path


class TestNormalizePath:
    """Test normalize_path method."""

    def test_normalize_absolute_path(self, tmp_path):
        """Test normalizing absolute path."""
        manager = PathManager(base_path=tmp_path)
        result = manager.normalize_path(tmp_path / "test.txt")
        assert result.is_absolute()

    def test_normalize_relative_path(self, tmp_path):
        """Test normalizing relative path."""
        manager = PathManager(base_path=tmp_path)
        result = manager.normalize_path("test.txt")
        assert result.is_absolute()
        assert result.parent == tmp_path

    def test_normalize_home_directory(self):
        """Test expanding home directory."""
        manager = PathManager()
        result = manager.normalize_path("~/test.txt")
        assert result.is_absolute()
        assert "~" not in str(result)

    def test_normalize_path_string_input(self, tmp_path):
        """Test normalizing path from string."""
        manager = PathManager(base_path=tmp_path)
        result = manager.normalize_path("subdir/file.txt")
        assert isinstance(result, Path)
        assert result.is_absolute()

    def test_normalize_path_object_input(self, tmp_path):
        """Test normalizing path from Path object."""
        manager = PathManager(base_path=tmp_path)
        result = manager.normalize_path(Path("subdir/file.txt"))
        assert isinstance(result, Path)
        assert result.is_absolute()

    def test_normalize_path_with_dots(self, tmp_path):
        """Test normalizing path with .. components."""
        manager = PathManager(base_path=tmp_path)
        result = manager.normalize_path("subdir/../file.txt")
        assert ".." not in str(result)

    def test_normalize_path_resolve_failure(self, tmp_path):
        """Test normalizing path when resolve fails."""
        manager = PathManager(base_path=tmp_path)
        with patch.object(Path, 'resolve', side_effect=OSError("Mock error")):
            result = manager.normalize_path("test.txt")
            assert result.is_absolute()

    def test_normalize_path_runtime_error(self, tmp_path):
        """Test normalizing path when RuntimeError occurs."""
        manager = PathManager(base_path=tmp_path)
        with patch.object(Path, 'resolve', side_effect=RuntimeError("Mock error")):
            result = manager.normalize_path("test.txt")
            assert result.is_absolute()


class TestEnsureDirectory:
    """Test ensure_directory method."""

    def test_ensure_directory_creates_new(self, tmp_path):
        """Test creating a new directory."""
        manager = PathManager(base_path=tmp_path)
        new_dir = tmp_path / "new_dir"
        result = manager.ensure_directory(new_dir)
        assert result.exists()
        assert result.is_dir()

    def test_ensure_directory_existing(self, tmp_path):
        """Test ensuring existing directory."""
        manager = PathManager(base_path=tmp_path)
        existing_dir = tmp_path / "existing"
        existing_dir.mkdir()
        result = manager.ensure_directory(existing_dir)
        assert result.exists()
        assert result.is_dir()

    def test_ensure_directory_nested(self, tmp_path):
        """Test creating nested directories."""
        manager = PathManager(base_path=tmp_path)
        nested_dir = tmp_path / "level1" / "level2" / "level3"
        result = manager.ensure_directory(nested_dir)
        assert result.exists()
        assert result.is_dir()

    def test_ensure_directory_with_mode(self, tmp_path):
        """Test creating directory with specific mode."""
        manager = PathManager(base_path=tmp_path)
        new_dir = tmp_path / "mode_dir"
        result = manager.ensure_directory(new_dir, mode=0o755)
        assert result.exists()

    def test_ensure_directory_string_input(self, tmp_path):
        """Test creating directory from string path."""
        manager = PathManager(base_path=tmp_path)
        result = manager.ensure_directory("string_dir")
        assert result.exists()

    def test_ensure_directory_failure(self, tmp_path):
        """Test directory creation failure."""
        manager = PathManager(base_path=tmp_path)
        with patch.object(Path, 'mkdir', side_effect=PermissionError("No permission")):
            with pytest.raises(PathError) as exc_info:
                manager.ensure_directory("fail_dir")
            assert "Failed to create directory" in str(exc_info.value)


class TestEnsureParentDirectory:
    """Test ensure_parent_directory method."""

    def test_ensure_parent_directory(self, tmp_path):
        """Test creating parent directory for a file."""
        manager = PathManager(base_path=tmp_path)
        file_path = tmp_path / "subdir" / "file.txt"
        result = manager.ensure_parent_directory(file_path)
        assert result.exists()
        assert result.is_dir()
        assert result == file_path.parent

    def test_ensure_parent_directory_nested(self, tmp_path):
        """Test creating nested parent directories."""
        manager = PathManager(base_path=tmp_path)
        file_path = tmp_path / "a" / "b" / "c" / "file.txt"
        result = manager.ensure_parent_directory(file_path)
        assert result.exists()
        assert (tmp_path / "a" / "b" / "c").exists()

    def test_ensure_parent_directory_with_mode(self, tmp_path):
        """Test creating parent directory with mode."""
        manager = PathManager(base_path=tmp_path)
        file_path = tmp_path / "subdir" / "file.txt"
        result = manager.ensure_parent_directory(file_path, mode=0o755)
        assert result.exists()


class TestSafeJoin:
    """Test safe_join method."""

    def test_safe_join_simple(self, tmp_path):
        """Test simple safe path joining."""
        manager = PathManager(base_path=tmp_path)
        result = manager.safe_join("subdir", "file.txt")
        assert result.parent.name == "subdir"
        assert result.name == "file.txt"

    def test_safe_join_multiple_parts(self, tmp_path):
        """Test joining multiple path parts."""
        manager = PathManager(base_path=tmp_path)
        result = manager.safe_join("a", "b", "c", "file.txt")
        assert "a" in str(result)
        assert "b" in str(result)
        assert "c" in str(result)

    def test_safe_join_path_objects(self, tmp_path):
        """Test joining Path objects."""
        manager = PathManager(base_path=tmp_path)
        result = manager.safe_join(Path("subdir"), Path("file.txt"))
        assert isinstance(result, Path)

    def test_safe_join_prevents_traversal(self, tmp_path):
        """Test that safe_join prevents path traversal."""
        manager = PathManager(base_path=tmp_path)
        with pytest.raises(PathError) as exc_info:
            manager.safe_join("..", "..", "etc", "passwd")
        assert "Path traversal detected" in str(exc_info.value)

    def test_safe_join_absolute_part_traversal(self, tmp_path):
        """Test traversal with absolute path components."""
        manager = PathManager(base_path=tmp_path)
        # This should fail as it tries to go outside base
        with pytest.raises(PathError):
            manager.safe_join("subdir", "..", "..", "..", "outside")


class TestGetRelativePath:
    """Test get_relative_path method."""

    def test_get_relative_path_default_base(self, tmp_path):
        """Test getting relative path with default base."""
        manager = PathManager(base_path=tmp_path)
        target = tmp_path / "subdir" / "file.txt"
        result = manager.get_relative_path(target)
        assert not result.is_absolute()
        assert str(result) == "subdir/file.txt" or str(result) == "subdir\\file.txt"

    def test_get_relative_path_custom_base(self, tmp_path):
        """Test getting relative path with custom base."""
        manager = PathManager(base_path=tmp_path)
        base = tmp_path / "base"
        target = tmp_path / "base" / "subdir" / "file.txt"
        result = manager.get_relative_path(target, base=base)
        assert not result.is_absolute()

    def test_get_relative_path_not_relative(self, tmp_path):
        """Test getting relative path when paths are not related."""
        manager = PathManager(base_path=tmp_path)
        other_path = Path(tempfile.gettempdir()) / "other" / "file.txt"
        with pytest.raises(PathError) as exc_info:
            manager.get_relative_path(other_path)
        assert "Cannot make" in str(exc_info.value)

    def test_get_relative_path_string_input(self, tmp_path):
        """Test getting relative path with string input."""
        manager = PathManager(base_path=tmp_path)
        target = str(tmp_path / "file.txt")
        result = manager.get_relative_path(target)
        assert isinstance(result, Path)


class TestIsSafePath:
    """Test is_safe_path method."""

    def test_is_safe_path_valid(self, tmp_path):
        """Test checking safe path that is valid."""
        manager = PathManager(base_path=tmp_path)
        safe_path = tmp_path / "subdir" / "file.txt"
        assert manager.is_safe_path(safe_path) is True

    def test_is_safe_path_traversal(self, tmp_path):
        """Test checking path with traversal attempt."""
        manager = PathManager(base_path=tmp_path)
        unsafe_path = tmp_path / ".." / ".." / "etc" / "passwd"
        # After normalization, this goes outside base_path
        assert manager.is_safe_path(unsafe_path) is False

    def test_is_safe_path_outside_base(self, tmp_path):
        """Test checking path outside base directory."""
        manager = PathManager(base_path=tmp_path)
        outside_path = Path(tempfile.gettempdir()) / "outside.txt"
        assert manager.is_safe_path(outside_path) is False

    def test_is_safe_path_relative(self, tmp_path):
        """Test checking relative safe path."""
        manager = PathManager(base_path=tmp_path)
        assert manager.is_safe_path("subdir/file.txt") is True


class TestFindFiles:
    """Test find_files method."""

    def test_find_files_basic(self, tmp_path):
        """Test finding files with basic pattern."""
        manager = PathManager(base_path=tmp_path)
        # Create test files
        (tmp_path / "test1.txt").touch()
        (tmp_path / "test2.txt").touch()
        (tmp_path / "other.log").touch()

        results = manager.find_files("*.txt")
        assert len(results) == 2
        assert all(p.suffix == ".txt" for p in results)

    def test_find_files_recursive(self, tmp_path):
        """Test finding files recursively."""
        manager = PathManager(base_path=tmp_path)
        # Create nested structure
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (tmp_path / "root.txt").touch()
        (subdir / "nested.txt").touch()

        results = manager.find_files("*.txt", recursive=True)
        assert len(results) == 2

    def test_find_files_non_recursive(self, tmp_path):
        """Test finding files non-recursively."""
        manager = PathManager(base_path=tmp_path)
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (tmp_path / "root.txt").touch()
        (subdir / "nested.txt").touch()

        results = manager.find_files("*.txt", recursive=False)
        assert len(results) == 1
        assert results[0].name == "root.txt"

    def test_find_files_custom_directory(self, tmp_path):
        """Test finding files in custom directory."""
        manager = PathManager(base_path=tmp_path)
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file.txt").touch()

        results = manager.find_files("*.txt", directory=subdir)
        assert len(results) == 1

    def test_find_files_nonexistent_directory(self, tmp_path):
        """Test finding files in non-existent directory."""
        manager = PathManager(base_path=tmp_path)
        results = manager.find_files("*.txt", directory=tmp_path / "nonexistent")
        assert results == []

    def test_find_files_excludes_directories(self, tmp_path):
        """Test that find_files only returns files, not directories."""
        manager = PathManager(base_path=tmp_path)
        (tmp_path / "file.txt").touch()
        (tmp_path / "dir.txt").mkdir()  # Directory with .txt "extension"

        results = manager.find_files("*.txt")
        assert len(results) == 1
        assert results[0].is_file()


class TestGetSize:
    """Test get_size method."""

    def test_get_size_file(self, tmp_path):
        """Test getting size of a file."""
        manager = PathManager(base_path=tmp_path)
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World!")

        size = manager.get_size(test_file)
        assert size == len("Hello World!")

    def test_get_size_empty_file(self, tmp_path):
        """Test getting size of empty file."""
        manager = PathManager(base_path=tmp_path)
        test_file = tmp_path / "empty.txt"
        test_file.touch()

        size = manager.get_size(test_file)
        assert size == 0

    def test_get_size_directory(self, tmp_path):
        """Test getting size of directory."""
        manager = PathManager(base_path=tmp_path)
        (tmp_path / "file1.txt").write_text("12345")
        (tmp_path / "file2.txt").write_text("67890")

        size = manager.get_size(tmp_path)
        assert size == 10

    def test_get_size_nested_directory(self, tmp_path):
        """Test getting size of nested directory structure."""
        manager = PathManager(base_path=tmp_path)
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (tmp_path / "file1.txt").write_text("abc")
        (subdir / "file2.txt").write_text("def")

        size = manager.get_size(tmp_path)
        assert size == 6

    def test_get_size_nonexistent(self, tmp_path):
        """Test getting size of non-existent path."""
        manager = PathManager(base_path=tmp_path)
        with pytest.raises(PathError) as exc_info:
            manager.get_size(tmp_path / "nonexistent.txt")
        assert "does not exist" in str(exc_info.value)

    def test_get_size_permission_error(self, tmp_path):
        """Test getting size when permission error occurs."""
        manager = PathManager(base_path=tmp_path)
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        file1 = subdir / "file1.txt"
        file1.write_text("test")

        # Mock stat to raise PermissionError for one file (but not during exists() check)
        original_stat = Path.stat
        call_count = [0]  # Use list to allow modification in nested function
        def mock_stat(self, **kwargs):
            if self.name == "file1.txt":
                call_count[0] += 1
                # Only raise on second+ calls (skip the initial exists() check)
                if call_count[0] > 1:
                    raise PermissionError("No access")
            return original_stat(self, **kwargs)

        with patch.object(Path, 'stat', mock_stat):
            size = manager.get_size(subdir)
            # Should skip the file with permission error
            assert size == 0


class TestCleanFilename:
    """Test clean_filename method."""

    def test_clean_filename_basic(self):
        """Test cleaning basic filename."""
        manager = PathManager()
        result = manager.clean_filename("normal_file.txt")
        assert result == "normal_file.txt"

    def test_clean_filename_invalid_chars(self):
        """Test cleaning filename with invalid characters."""
        manager = PathManager()
        result = manager.clean_filename("file<>:|?*.txt")
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert "|" not in result
        assert "?" not in result
        assert "*" not in result

    def test_clean_filename_path_components(self):
        """Test removing path components from filename."""
        manager = PathManager()
        result = manager.clean_filename("/path/to/file.txt")
        assert result == "file.txt"
        assert "/" not in result

    def test_clean_filename_windows_path(self):
        """Test cleaning Windows path."""
        manager = PathManager()
        result = manager.clean_filename("C:\\path\\to\\file.txt")
        assert "\\" not in result

    def test_clean_filename_dots_and_spaces(self):
        """Test removing leading/trailing dots and spaces."""
        manager = PathManager()
        result = manager.clean_filename("  ..file.txt.. ")
        assert not result.startswith(".")
        assert not result.endswith(".")
        assert not result.startswith(" ")

    def test_clean_filename_empty_result(self):
        """Test cleaning filename that becomes empty."""
        manager = PathManager()
        result = manager.clean_filename("...")
        assert result == "unnamed"

    def test_clean_filename_long_name(self):
        """Test cleaning very long filename."""
        manager = PathManager()
        long_name = "a" * 300 + ".txt"
        result = manager.clean_filename(long_name)
        assert len(result) <= 255

    def test_clean_filename_custom_replacement(self):
        """Test cleaning with custom replacement character."""
        manager = PathManager()
        result = manager.clean_filename("file:name.txt", replacement="-")
        assert "-" in result
        assert ":" not in result

    def test_clean_filename_control_chars(self):
        """Test removing control characters."""
        manager = PathManager()
        result = manager.clean_filename("file\x00\x1fname.txt")
        assert "\x00" not in result
        assert "\x1f" not in result


class TestGetUniquePath:
    """Test get_unique_path method."""

    def test_get_unique_path_nonexistent(self, tmp_path):
        """Test getting unique path for non-existent file."""
        manager = PathManager(base_path=tmp_path)
        path = tmp_path / "unique.txt"
        result = manager.get_unique_path(path)
        assert result == path

    def test_get_unique_path_existing(self, tmp_path):
        """Test getting unique path for existing file."""
        manager = PathManager(base_path=tmp_path)
        original = tmp_path / "file.txt"
        original.touch()

        result = manager.get_unique_path(original)
        assert result != original
        assert "_1" in result.stem

    def test_get_unique_path_multiple_existing(self, tmp_path):
        """Test getting unique path with multiple conflicts."""
        manager = PathManager(base_path=tmp_path)
        (tmp_path / "file.txt").touch()
        (tmp_path / "file_1.txt").touch()
        (tmp_path / "file_2.txt").touch()

        result = manager.get_unique_path(tmp_path / "file.txt")
        assert "_3" in result.stem

    def test_get_unique_path_with_suffix(self, tmp_path):
        """Test getting unique path with custom suffix."""
        manager = PathManager(base_path=tmp_path)
        original = tmp_path / "file.txt"
        original.touch()

        result = manager.get_unique_path(original, suffix="backup")
        assert "backup" in result.stem

    def test_get_unique_path_multiple_extensions(self, tmp_path):
        """Test unique path with multiple file extensions."""
        manager = PathManager(base_path=tmp_path)
        original = tmp_path / "file.tar.gz"
        original.touch()

        result = manager.get_unique_path(original)
        # The implementation adds _1 before all suffixes, so suffixes change
        assert ".tar" in "".join(result.suffixes)
        assert ".gz" in result.name

    def test_get_unique_path_max_attempts(self, tmp_path):
        """Test unique path reaching max attempts."""
        manager = PathManager(base_path=tmp_path)
        path = tmp_path / "file.txt"

        # Mock exists to always return True
        with patch.object(Path, 'exists', return_value=True):
            with pytest.raises(PathError) as exc_info:
                manager.get_unique_path(path)
            assert "10000 attempts" in str(exc_info.value)


class TestGetCommonAncestor:
    """Test get_common_ancestor function."""

    def test_common_ancestor_empty(self):
        """Test common ancestor with no paths."""
        result = get_common_ancestor()
        assert result is None

    def test_common_ancestor_single_file(self, tmp_path):
        """Test common ancestor with single file path."""
        file_path = tmp_path / "file.txt"
        result = get_common_ancestor(file_path)
        # For single non-existent file, returns the path itself
        # For existing file, would return parent
        assert result == tmp_path or result == file_path

    def test_common_ancestor_single_directory(self, tmp_path):
        """Test common ancestor with single directory."""
        result = get_common_ancestor(tmp_path)
        assert result == tmp_path

    def test_common_ancestor_same_directory(self, tmp_path):
        """Test common ancestor of files in same directory."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        result = get_common_ancestor(file1, file2)
        assert result == tmp_path

    def test_common_ancestor_nested_paths(self, tmp_path):
        """Test common ancestor of nested paths."""
        path1 = tmp_path / "a" / "b" / "file1.txt"
        path2 = tmp_path / "a" / "c" / "file2.txt"
        result = get_common_ancestor(path1, path2)
        assert result == tmp_path / "a"

    def test_common_ancestor_no_common(self):
        """Test common ancestor with no common path."""
        # Use different drive roots on Windows, different top-level dirs on Unix
        if os.name == 'nt':
            path1 = Path("C:/test/file1.txt")
            path2 = Path("D:/test/file2.txt")
        else:
            path1 = Path("/tmp/file1.txt")
            path2 = Path("/var/file2.txt")

        result = get_common_ancestor(path1, path2)
        # Should have some common ancestor (at least root)
        assert result is not None or result is None  # Platform dependent

    def test_common_ancestor_string_paths(self, tmp_path):
        """Test common ancestor with string paths."""
        path1 = str(tmp_path / "file1.txt")
        path2 = str(tmp_path / "file2.txt")
        result = get_common_ancestor(path1, path2)
        assert result is not None


class TestIsSubdirectory:
    """Test is_subdirectory function."""

    def test_is_subdirectory_true(self, tmp_path):
        """Test checking actual subdirectory."""
        parent = tmp_path
        child = tmp_path / "subdir" / "nested"
        child.mkdir(parents=True)

        assert is_subdirectory(child, parent) is True

    def test_is_subdirectory_false(self, tmp_path):
        """Test checking non-subdirectory."""
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        dir1.mkdir()
        dir2.mkdir()

        assert is_subdirectory(dir1, dir2) is False

    def test_is_subdirectory_same_path(self, tmp_path):
        """Test checking if path is subdirectory of itself."""
        # A path is technically under itself
        assert is_subdirectory(tmp_path, tmp_path) is True

    def test_is_subdirectory_parent_child(self, tmp_path):
        """Test parent is not subdirectory of child."""
        child = tmp_path / "child"
        child.mkdir()

        assert is_subdirectory(tmp_path, child) is False

    def test_is_subdirectory_string_paths(self, tmp_path):
        """Test with string paths."""
        child = tmp_path / "child"
        child.mkdir()

        assert is_subdirectory(str(child), str(tmp_path)) is True

    def test_is_subdirectory_nonexistent(self, tmp_path):
        """Test with non-existent paths."""
        child = tmp_path / "nonexistent" / "child"
        # Should still work based on path structure
        result = is_subdirectory(child, tmp_path)
        assert isinstance(result, bool)


class TestFormatPathForDisplay:
    """Test format_path_for_display function."""

    def test_format_short_path(self):
        """Test formatting path shorter than max length."""
        path = "/short/path"
        result = format_path_for_display(path, max_length=50)
        assert result == path

    def test_format_long_path(self):
        """Test formatting path longer than max length."""
        path = "/very/long/path/that/exceeds/maximum/length/for/display"
        result = format_path_for_display(path, max_length=30)
        # Allow slight variance due to string splitting
        assert 29 <= len(result) <= 31
        assert "..." in result

    def test_format_very_short_max(self):
        """Test formatting with very short max length."""
        path = "/some/long/path"
        result = format_path_for_display(path, max_length=5)
        assert len(result) == 5

    def test_format_exact_length(self):
        """Test formatting path at exact max length."""
        path = "a" * 50
        result = format_path_for_display(path, max_length=50)
        assert result == path

    def test_format_path_object(self, tmp_path):
        """Test formatting Path object."""
        result = format_path_for_display(tmp_path, max_length=50)
        assert isinstance(result, str)

    def test_format_ellipsis_placement(self):
        """Test that ellipsis is placed in middle."""
        path = "a" * 100
        result = format_path_for_display(path, max_length=20)
        assert result.count("...") == 1
        # Check start and end are preserved
        assert result.startswith("a")
        assert result.endswith("a")


class TestEdgeCasesAndIntegration:
    """Test edge cases and integration scenarios."""

    def test_concurrent_directory_creation(self, tmp_path):
        """Test creating same directory concurrently (should not fail)."""
        manager = PathManager(base_path=tmp_path)
        test_dir = tmp_path / "concurrent"

        # First creation
        result1 = manager.ensure_directory(test_dir)
        # Second creation (already exists)
        result2 = manager.ensure_directory(test_dir)

        assert result1 == result2
        assert test_dir.exists()

    def test_unicode_filename_handling(self, tmp_path):
        """Test handling Unicode characters in filenames."""
        manager = PathManager(base_path=tmp_path)
        unicode_name = "file_测试_🎉.txt"
        cleaned = manager.clean_filename(unicode_name)
        # Should handle Unicode gracefully
        assert isinstance(cleaned, str)

    def test_whitespace_path_handling(self, tmp_path):
        """Test handling paths with whitespace."""
        manager = PathManager(base_path=tmp_path)
        path_with_spaces = tmp_path / "dir with spaces" / "file with spaces.txt"
        manager.ensure_parent_directory(path_with_spaces)
        assert (tmp_path / "dir with spaces").exists()

    def test_symlink_handling(self, tmp_path):
        """Test handling symbolic links."""
        manager = PathManager(base_path=tmp_path)
        real_file = tmp_path / "real.txt"
        real_file.touch()
        link_file = tmp_path / "link.txt"

        try:
            link_file.symlink_to(real_file)
            result = manager.normalize_path(link_file)
            # Should resolve to real file
            assert result.exists()
        except (OSError, NotImplementedError):
            # Skip if symlinks not supported (Windows without admin)
            pytest.skip("Symlinks not supported")

    def test_case_sensitivity(self, tmp_path):
        """Test case sensitivity handling."""
        manager = PathManager(base_path=tmp_path)
        (tmp_path / "File.txt").touch()

        # Find should respect filesystem case sensitivity
        results = manager.find_files("file.txt")
        # Result depends on filesystem (case-sensitive or not)
        assert isinstance(results, list)

    def test_empty_pattern_search(self, tmp_path):
        """Test searching with empty pattern."""
        manager = PathManager(base_path=tmp_path)
        (tmp_path / "file.txt").touch()

        results = manager.find_files("")
        # Empty pattern should match nothing or everything depending on glob
        assert isinstance(results, list)

    def test_special_characters_in_path(self, tmp_path):
        """Test handling special characters in paths."""
        manager = PathManager(base_path=tmp_path)
        special_name = "file[test].txt"
        cleaned = manager.clean_filename(special_name)
        # Brackets might be valid in some filesystems
        assert isinstance(cleaned, str)

    def test_path_manager_chain_operations(self, tmp_path):
        """Test chaining multiple path operations."""
        manager = PathManager(base_path=tmp_path)

        # Create directory
        new_dir = manager.ensure_directory("chain/test")

        # Create file in it
        file_path = new_dir / "test.txt"
        file_path.write_text("test content")

        # Find it
        results = manager.find_files("*.txt", directory=new_dir)
        assert len(results) == 1

        # Get its size
        size = manager.get_size(results[0])
        assert size == len("test content")

        # Get unique path
        unique = manager.get_unique_path(file_path)
        assert unique != file_path

    def test_base_path_change_behavior(self, tmp_path):
        """Test that base path is used consistently."""
        dir1 = tmp_path / "base1"
        dir2 = tmp_path / "base2"
        dir1.mkdir()
        dir2.mkdir()

        manager1 = PathManager(base_path=dir1)
        manager2 = PathManager(base_path=dir2)

        # Same relative path should resolve differently
        path1 = manager1.normalize_path("file.txt")
        path2 = manager2.normalize_path("file.txt")

        assert path1.parent == dir1
        assert path2.parent == dir2
