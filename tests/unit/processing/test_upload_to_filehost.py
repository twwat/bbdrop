"""
Comprehensive test suite for src/processing/upload_to_filehost.py
Tests zip folder functionality, temporary zip creation, compression modes, and error handling.
"""

import pytest
import os
import zipfile
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from src.processing.upload_to_filehost import (
    zip_folder,
    create_temp_zip
)


class TestZipFolderBasic:
    """Test basic zip_folder functionality"""

    def test_zip_folder_creates_file(self, tmp_path):
        """Test that zip_folder creates a zip file"""
        # Create test folder with files
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        (test_folder / "file1.txt").write_text("content1")
        (test_folder / "file2.txt").write_text("content2")

        # Zip the folder
        result = zip_folder(str(test_folder))

        # Verify zip file was created
        assert os.path.exists(result)
        assert result.endswith('.zip')

    def test_zip_folder_returns_path(self, tmp_path):
        """Test that zip_folder returns the path to created zip"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        (test_folder / "file.txt").write_text("content")

        result = zip_folder(str(test_folder))

        assert isinstance(result, (str, type(None)))
        assert result is not None
        assert isinstance(result, str)

    def test_zip_folder_with_custom_output_path(self, tmp_path):
        """Test zip_folder with custom output path"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        (test_folder / "file.txt").write_text("content")

        output_path = str(tmp_path / "custom_output")
        result = zip_folder(str(test_folder), output_path=output_path)

        assert os.path.exists(result)
        assert "custom_output" in result
        assert result.endswith('.zip')

    def test_zip_folder_contains_files(self, tmp_path):
        """Test that zip file contains the original files"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        (test_folder / "file1.txt").write_text("content1")
        (test_folder / "file2.txt").write_text("content2")

        result = zip_folder(str(test_folder))

        # Verify contents
        with zipfile.ZipFile(result, 'r') as zipf:
            names = zipf.namelist()
            assert len(names) == 2
            assert any('file1.txt' in name for name in names)
            assert any('file2.txt' in name for name in names)

    def test_zip_folder_preserves_file_content(self, tmp_path):
        """Test that zip preserves file content"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        test_content = "This is test content"
        (test_folder / "test.txt").write_text(test_content)

        result = zip_folder(str(test_folder))

        # Extract and verify content
        with zipfile.ZipFile(result, 'r') as zipf:
            extracted_content = zipf.read('test_folder/test.txt').decode('utf-8')
            assert extracted_content == test_content

    def test_zip_folder_with_nested_directories(self, tmp_path):
        """Test zip_folder with nested folder structure"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        nested = test_folder / "nested" / "deep"
        nested.mkdir(parents=True)
        (nested / "deep_file.txt").write_text("deep content")
        (test_folder / "root_file.txt").write_text("root content")

        result = zip_folder(str(test_folder))

        with zipfile.ZipFile(result, 'r') as zipf:
            names = zipf.namelist()
            assert any('root_file.txt' in name for name in names)
            assert any('deep_file.txt' in name for name in names)
            assert len(names) == 2

    def test_zip_folder_empty_directory(self, tmp_path):
        """Test zipping an empty directory"""
        test_folder = tmp_path / "empty_folder"
        test_folder.mkdir()

        result = zip_folder(str(test_folder))

        assert os.path.exists(result)
        with zipfile.ZipFile(result, 'r') as zipf:
            assert len(zipf.namelist()) == 0

    def test_zip_folder_large_file(self, tmp_path):
        """Test zipping folder with large file"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        # Create 10MB file
        large_content = "x" * (10 * 1024 * 1024)
        (test_folder / "large.txt").write_text(large_content)

        result = zip_folder(str(test_folder))

        assert os.path.exists(result)
        with zipfile.ZipFile(result, 'r') as zipf:
            assert len(zipf.namelist()) == 1

    def test_zip_folder_special_characters_filename(self, tmp_path):
        """Test zipping files with special characters in names"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        (test_folder / "file with spaces.txt").write_text("content")
        (test_folder / "file-with-dashes.txt").write_text("content")

        result = zip_folder(str(test_folder))

        with zipfile.ZipFile(result, 'r') as zipf:
            names = zipf.namelist()
            assert any('spaces' in name for name in names)
            assert any('dashes' in name for name in names)


class TestZipFolderCompressionModes:
    """Test compression mode handling"""

    def test_zip_folder_store_compression(self, tmp_path):
        """Test zip_folder with store (no compression) mode"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        (test_folder / "file.txt").write_text("content" * 1000)

        result = zip_folder(str(test_folder), compression='store')

        with zipfile.ZipFile(result, 'r') as zipf:
            for info in zipf.infolist():
                assert info.compress_type == zipfile.ZIP_STORED

    def test_zip_folder_deflate_compression(self, tmp_path):
        """Test zip_folder with deflate compression"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        (test_folder / "file.txt").write_text("content" * 1000)

        result = zip_folder(str(test_folder), compression='deflate')

        with zipfile.ZipFile(result, 'r') as zipf:
            for info in zipf.infolist():
                assert info.compress_type == zipfile.ZIP_DEFLATED

    def test_zip_folder_deflate_reduces_size(self, tmp_path):
        """Test that deflate compression reduces file size"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        # Highly compressible content
        (test_folder / "file.txt").write_text("a" * 100000)

        result_store = zip_folder(str(test_folder), output_path=str(tmp_path / "store"), compression='store')
        result_deflate = zip_folder(str(test_folder), output_path=str(tmp_path / "deflate"), compression='deflate')

        size_store = os.path.getsize(result_store)
        size_deflate = os.path.getsize(result_deflate)

        # Deflate should be smaller for highly compressible content
        assert size_deflate < size_store

    def test_zip_folder_default_compression_is_store(self, tmp_path):
        """Test that default compression is store mode"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        (test_folder / "file.txt").write_text("content")

        result = zip_folder(str(test_folder))

        with zipfile.ZipFile(result, 'r') as zipf:
            for info in zipf.infolist():
                assert info.compress_type == zipfile.ZIP_STORED

    def test_zip_folder_invalid_compression_uses_deflate(self, tmp_path):
        """Test that invalid compression mode defaults to deflate"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        (test_folder / "file.txt").write_text("content")

        result = zip_folder(str(test_folder), compression='invalid_mode')

        with zipfile.ZipFile(result, 'r') as zipf:
            for info in zipf.infolist():
                assert info.compress_type == zipfile.ZIP_DEFLATED


class TestZipFolderOutputPath:
    """Test output path handling"""

    def test_zip_folder_default_output_path(self, tmp_path):
        """Test that default output path uses folder name"""
        test_folder = tmp_path / "my_folder"
        test_folder.mkdir()
        (test_folder / "file.txt").write_text("content")

        result = zip_folder(str(test_folder))

        assert result.endswith('my_folder.zip')

    def test_zip_folder_output_path_without_zip_extension(self, tmp_path):
        """Test output path without .zip extension gets it added"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        (test_folder / "file.txt").write_text("content")

        output_path = str(tmp_path / "output")
        result = zip_folder(str(test_folder), output_path=output_path)

        assert result.endswith('.zip')
        assert 'output' in result

    def test_zip_folder_output_path_with_zip_extension(self, tmp_path):
        """Test output path with .zip extension doesn't double it"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        (test_folder / "file.txt").write_text("content")

        output_path = str(tmp_path / "output.zip")
        result = zip_folder(str(test_folder), output_path=output_path)

        # Should not be output.zip.zip
        assert result.count('.zip') == 1
        assert result.endswith('.zip')

    def test_zip_folder_creates_in_specified_directory(self, tmp_path):
        """Test that zip is created in the specified directory"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        (test_folder / "file.txt").write_text("content")

        output_dir = tmp_path / "output_dir"
        output_dir.mkdir()
        output_path = str(output_dir / "archive")

        result = zip_folder(str(test_folder), output_path=output_path)

        assert str(output_dir) in result
        assert os.path.exists(result)


class TestZipFolderErrors:
    """Test error handling"""

    def test_zip_folder_nonexistent_folder(self):
        """Test that zip_folder raises error for nonexistent folder"""
        with pytest.raises(FileNotFoundError) as exc_info:
            zip_folder("/nonexistent/path/to/folder")

        assert "Folder not found" in str(exc_info.value)

    def test_zip_folder_file_instead_of_directory(self, tmp_path):
        """Test that zip_folder raises error when given a file"""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        with pytest.raises(ValueError) as exc_info:
            zip_folder(str(test_file))

        assert "not a directory" in str(exc_info.value)

    def test_zip_folder_with_permission_error(self, tmp_path):
        """Test handling of permission errors during zipping"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        (test_folder / "file.txt").write_text("content")

        output_path = "/root/nonwritable/archive"

        with pytest.raises((FileNotFoundError, PermissionError)):
            zip_folder(str(test_folder), output_path=output_path)

    def test_zip_folder_path_as_pathlib_object(self, tmp_path):
        """Test that zip_folder works with pathlib.Path objects"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        (test_folder / "file.txt").write_text("content")

        result = zip_folder(test_folder)

        assert os.path.exists(result)
        assert result.endswith('.zip')


class TestCreateTempZip:
    """Test create_temp_zip functionality"""

    def test_create_temp_zip_creates_file(self, tmp_path):
        """Test that create_temp_zip creates a temporary zip file"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        (test_folder / "file.txt").write_text("content")

        result = create_temp_zip(str(test_folder))

        assert os.path.exists(result)
        assert result.endswith('.zip')

    def test_create_temp_zip_in_temp_directory(self, tmp_path):
        """Test that temp zip is created in system temp directory"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        (test_folder / "file.txt").write_text("content")

        result = create_temp_zip(str(test_folder))

        temp_dir = tempfile.gettempdir()
        assert temp_dir in result

    def test_create_temp_zip_uses_folder_name(self, tmp_path):
        """Test that temp zip uses the original folder name"""
        test_folder = tmp_path / "my_gallery"
        test_folder.mkdir()
        (test_folder / "file.txt").write_text("content")

        result = create_temp_zip(str(test_folder))

        assert "my_gallery" in result

    def test_create_temp_zip_uses_store_compression(self, tmp_path):
        """Test that temp zip uses store (no compression) mode"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        (test_folder / "file.txt").write_text("content")

        result = create_temp_zip(str(test_folder))

        with zipfile.ZipFile(result, 'r') as zipf:
            for info in zipf.infolist():
                assert info.compress_type == zipfile.ZIP_STORED

    def test_create_temp_zip_removes_existing_file(self, tmp_path):
        """Test that create_temp_zip removes existing temp file"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        (test_folder / "file.txt").write_text("content1")

        # Create first temp zip
        result1 = create_temp_zip(str(test_folder))
        file_stat1 = os.stat(result1)

        # Wait a bit to ensure different modification time
        time.sleep(0.1)

        # Create second temp zip - should replace first
        (test_folder / "file2.txt").write_text("content2")
        result2 = create_temp_zip(str(test_folder))
        file_stat2 = os.stat(result2)

        # Same file path but newer modification time
        assert result1 == result2
        assert file_stat2.st_mtime >= file_stat1.st_mtime

    @patch('os.remove')
    def test_create_temp_zip_handles_remove_error(self, mock_remove, tmp_path):
        """Test that create_temp_zip handles removal errors gracefully"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        (test_folder / "file.txt").write_text("content")

        # Make os.remove raise an exception
        mock_remove.side_effect = OSError("Cannot remove")

        result = create_temp_zip(str(test_folder))

        # Should still create a zip file with timestamp in name
        assert os.path.exists(result)
        assert result.endswith('.zip')
        # Should have timestamp in name when removal fails
        assert '_' in os.path.basename(result)

    def test_create_temp_zip_multiple_calls_same_folder(self, tmp_path):
        """Test multiple calls to create_temp_zip with same folder"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        (test_folder / "file.txt").write_text("content")

        result1 = create_temp_zip(str(test_folder))
        result2 = create_temp_zip(str(test_folder))

        # Both should exist and be valid zips
        assert os.path.exists(result1)
        assert os.path.exists(result2)

    def test_create_temp_zip_with_nested_structure(self, tmp_path):
        """Test create_temp_zip with nested folder structure"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        nested = test_folder / "nested" / "deep"
        nested.mkdir(parents=True)
        (nested / "file.txt").write_text("content")
        (test_folder / "root.txt").write_text("root")

        result = create_temp_zip(str(test_folder))

        with zipfile.ZipFile(result, 'r') as zipf:
            names = zipf.namelist()
            assert any('file.txt' in name for name in names)
            assert any('root.txt' in name for name in names)

    def test_create_temp_zip_with_pathlib_path(self, tmp_path):
        """Test create_temp_zip works with pathlib.Path objects"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        (test_folder / "file.txt").write_text("content")

        result = create_temp_zip(test_folder)

        assert os.path.exists(result)
        assert result.endswith('.zip')

    def test_create_temp_zip_returns_path(self, tmp_path):
        """Test that create_temp_zip returns the path"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        (test_folder / "file.txt").write_text("content")

        result = create_temp_zip(str(test_folder))

        assert isinstance(result, str)
        assert len(result) > 0


class TestZipFolderIntegration:
    """Integration tests for zip_folder"""

    def test_zip_folder_multiple_file_types(self, tmp_path):
        """Test zipping folder with multiple file types"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        (test_folder / "document.txt").write_text("text")
        (test_folder / "image.jpg").write_bytes(b"fake_jpg_data")
        (test_folder / "script.py").write_text("print('hello')")

        result = zip_folder(str(test_folder))

        with zipfile.ZipFile(result, 'r') as zipf:
            names = zipf.namelist()
            assert len(names) == 3

    def test_zip_folder_created_zip_is_valid(self, tmp_path):
        """Test that created zip is valid and extractable"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        (test_folder / "file1.txt").write_text("content1")
        (test_folder / "file2.txt").write_text("content2")

        result = zip_folder(str(test_folder))

        # Try to extract and verify
        extract_path = tmp_path / "extracted"
        extract_path.mkdir()

        with zipfile.ZipFile(result, 'r') as zipf:
            zipf.extractall(extract_path)

        # Verify extracted files exist
        extracted_files = list(extract_path.rglob('*.txt'))
        assert len(extracted_files) == 2

    def test_zip_and_unzip_preserves_data(self, tmp_path):
        """Test that zip and unzip preserves data integrity"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()

        test_data = {
            "file1.txt": "This is content for file 1",
            "file2.txt": "This is content for file 2",
            "nested_file.txt": "Nested content"
        }

        for filename, content in test_data.items():
            if "/" in filename:
                nested_dir = test_folder / os.path.dirname(filename)
                nested_dir.mkdir(parents=True, exist_ok=True)
            (test_folder / filename).write_text(content)

        result = zip_folder(str(test_folder))

        # Extract and verify
        extract_path = tmp_path / "extracted"
        extract_path.mkdir()

        with zipfile.ZipFile(result, 'r') as zipf:
            zipf.extractall(extract_path)

        # Verify content integrity
        extracted_file = extract_path / "test_folder" / "file1.txt"
        assert extracted_file.read_text() == test_data["file1.txt"]

    def test_zip_folder_relative_path(self, tmp_path):
        """Test zip_folder with relative path"""
        # Change to temp directory
        original_cwd = os.getcwd()
        try:
            os.chdir(str(tmp_path))

            test_folder = Path("test_folder")
            test_folder.mkdir()
            (test_folder / "file.txt").write_text("content")

            result = zip_folder(str(test_folder))

            assert os.path.exists(result)
            assert result.endswith('.zip')
        finally:
            os.chdir(original_cwd)


class TestCreateTempZipIntegration:
    """Integration tests for create_temp_zip"""

    def test_create_temp_zip_and_extract(self, tmp_path):
        """Test creating and extracting temp zip"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        (test_folder / "file1.txt").write_text("content1")
        (test_folder / "file2.txt").write_text("content2")

        result = create_temp_zip(str(test_folder))

        # Extract and verify
        extract_path = tmp_path / "extracted"
        extract_path.mkdir()

        with zipfile.ZipFile(result, 'r') as zipf:
            zipf.extractall(extract_path)

        # Verify files exist
        extracted_files = list(extract_path.rglob('*.txt'))
        assert len(extracted_files) == 2

    def test_create_temp_zip_performance(self, tmp_path):
        """Test that temp zip creation is reasonably fast"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()

        # Create multiple files
        for i in range(10):
            (test_folder / f"file_{i}.txt").write_text(f"content_{i}" * 100)

        start_time = time.time()
        result = create_temp_zip(str(test_folder))
        elapsed = time.time() - start_time

        assert os.path.exists(result)
        # Should complete in reasonable time (< 5 seconds for test files)
        assert elapsed < 5.0

    def test_cleanup_temp_zip(self, tmp_path):
        """Test that temp zip can be cleaned up"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        (test_folder / "file.txt").write_text("content")

        result = create_temp_zip(str(test_folder))

        assert os.path.exists(result)

        # Verify we can delete it
        os.remove(result)
        assert not os.path.exists(result)


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_zip_folder_unicode_filenames(self, tmp_path):
        """Test zipping with unicode filenames"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        (test_folder / "файл_😀.txt").write_text("unicode content")

        result = zip_folder(str(test_folder))

        with zipfile.ZipFile(result, 'r') as zipf:
            names = zipf.namelist()
            assert len(names) >= 1

    def test_zip_folder_symlinks(self, tmp_path):
        """Test handling of symlinks (if supported)"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        real_file = test_folder / "real_file.txt"
        real_file.write_text("content")

        # Try to create symlink (might not work on Windows)
        try:
            symlink_file = test_folder / "link_file.txt"
            symlink_file.symlink_to(real_file)
            result = zip_folder(str(test_folder))
            assert os.path.exists(result)
        except (OSError, NotImplementedError):
            # Skip if symlinks not supported
            pytest.skip("Symlinks not supported on this system")

    def test_zip_folder_hidden_files(self, tmp_path):
        """Test handling of hidden files"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        (test_folder / ".hidden").write_text("hidden content")
        (test_folder / "normal.txt").write_text("normal content")

        result = zip_folder(str(test_folder))

        with zipfile.ZipFile(result, 'r') as zipf:
            names = zipf.namelist()
            # Should include hidden file
            assert len(names) == 2

    def test_zip_folder_many_files(self, tmp_path):
        """Test zipping folder with many files"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()

        # Create 100 files
        for i in range(100):
            (test_folder / f"file_{i:03d}.txt").write_text(f"content_{i}")

        result = zip_folder(str(test_folder))

        with zipfile.ZipFile(result, 'r') as zipf:
            assert len(zipf.namelist()) == 100

    def test_zip_folder_deeply_nested(self, tmp_path):
        """Test zipping deeply nested directories"""
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()

        # Create deeply nested structure
        deep_path = test_folder
        for i in range(10):
            deep_path = deep_path / f"level_{i}"
            deep_path.mkdir(parents=True, exist_ok=True)

        (deep_path / "deep_file.txt").write_text("deep content")

        result = zip_folder(str(test_folder))

        with zipfile.ZipFile(result, 'r') as zipf:
            names = zipf.namelist()
            assert len(names) == 1
            assert "deep_file.txt" in names[0]
