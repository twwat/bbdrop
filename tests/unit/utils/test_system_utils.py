"""
Comprehensive unit tests for src/utils/system_utils.py

Tests cover:
- Platform detection (Windows, Linux, macOS)
- System information retrieval
- Directory and file operations
- Disk space and resource checks
- Environment variable handling
- Command execution
- User and privilege checks
- CPU and threading utilities
"""

import os
import sys
import platform
import tempfile
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, PropertyMock
import pytest

# Import the module under test
from src.utils.system_utils import (
    get_platform_info,
    is_windows,
    is_linux,
    is_macos,
    get_home_directory,
    get_app_data_directory,
    get_temp_directory,
    get_executable_path,
    get_resource_path,
    get_available_disk_space,
    format_bytes,
    ensure_directory_exists,
    safe_remove_file,
    safe_remove_directory,
    get_environment_variable,
    set_environment_variable,
    execute_command,
    get_system_hostname,
    get_system_username,
    is_admin,
    get_cpu_count,
    get_optimal_thread_count,
)


class TestPlatformDetection:
    """Test platform detection functions."""

    @patch('platform.system')
    def test_is_windows_true(self, mock_system):
        """Test Windows detection returns True."""
        mock_system.return_value = 'Windows'
        assert is_windows() is True
        mock_system.assert_called_once()

    @patch('platform.system')
    def test_is_windows_false(self, mock_system):
        """Test Windows detection returns False on other platforms."""
        mock_system.return_value = 'Linux'
        assert is_windows() is False

    @patch('platform.system')
    def test_is_linux_true(self, mock_system):
        """Test Linux detection returns True."""
        mock_system.return_value = 'Linux'
        assert is_linux() is True

    @patch('platform.system')
    def test_is_linux_false(self, mock_system):
        """Test Linux detection returns False on other platforms."""
        mock_system.return_value = 'Darwin'
        assert is_linux() is False

    @patch('platform.system')
    def test_is_macos_true(self, mock_system):
        """Test macOS detection returns True."""
        mock_system.return_value = 'Darwin'
        assert is_macos() is True

    @patch('platform.system')
    def test_is_macos_false(self, mock_system):
        """Test macOS detection returns False on other platforms."""
        mock_system.return_value = 'Windows'
        assert is_macos() is False


class TestPlatformInfo:
    """Test platform information retrieval."""

    @patch('platform.python_version')
    @patch('platform.processor')
    @patch('platform.machine')
    @patch('platform.version')
    @patch('platform.release')
    @patch('platform.system')
    def test_get_platform_info_complete(
        self, mock_system, mock_release, mock_version,
        mock_machine, mock_processor, mock_python_version
    ):
        """Test get_platform_info returns all required fields."""
        mock_system.return_value = 'Linux'
        mock_release.return_value = '5.10.0'
        mock_version.return_value = '#1 SMP'
        mock_machine.return_value = 'x86_64'
        mock_processor.return_value = 'Intel'
        mock_python_version.return_value = '3.11.0'

        info = get_platform_info()

        assert info['system'] == 'Linux'
        assert info['release'] == '5.10.0'
        assert info['version'] == '#1 SMP'
        assert info['machine'] == 'x86_64'
        assert info['processor'] == 'Intel'
        assert info['python_version'] == '3.11.0'

    @patch('platform.python_version')
    @patch('platform.processor')
    @patch('platform.machine')
    @patch('platform.version')
    @patch('platform.release')
    @patch('platform.system')
    def test_get_platform_info_windows(
        self, mock_system, mock_release, mock_version,
        mock_machine, mock_processor, mock_python_version
    ):
        """Test platform info on Windows."""
        mock_system.return_value = 'Windows'
        mock_release.return_value = '10'
        mock_version.return_value = '10.0.19041'
        mock_machine.return_value = 'AMD64'
        mock_processor.return_value = 'AMD64 Family'
        mock_python_version.return_value = '3.10.0'

        info = get_platform_info()

        assert info['system'] == 'Windows'
        assert info['machine'] == 'AMD64'


class TestDirectoryOperations:
    """Test directory and path operations."""

    def test_get_home_directory(self):
        """Test getting home directory."""
        home = get_home_directory()
        assert isinstance(home, Path)
        assert home.exists()
        assert home.is_dir()

    @patch('platform.system')
    @patch('os.getenv')
    def test_get_app_data_directory_windows(self, mock_getenv, mock_system):
        """Test app data directory on Windows."""
        mock_system.return_value = 'Windows'
        mock_getenv.return_value = '/tmp/appdata'

        with patch('pathlib.Path.mkdir') as mock_mkdir:
            app_dir = get_app_data_directory('testapp')
            assert 'testapp' in str(app_dir)
            mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

    @patch('platform.system')
    @patch('pathlib.Path.home')
    def test_get_app_data_directory_macos(self, mock_home, mock_system):
        """Test app data directory on macOS."""
        mock_system.return_value = 'Darwin'
        mock_home.return_value = Path('/Users/testuser')

        with patch('pathlib.Path.mkdir') as mock_mkdir:
            app_dir = get_app_data_directory('testapp')
            assert 'Library/Application Support/testapp' in str(app_dir)
            mock_mkdir.assert_called_once()

    @patch('platform.system')
    @patch('pathlib.Path.home')
    @patch('os.getenv')
    def test_get_app_data_directory_linux(self, mock_getenv, mock_home, mock_system):
        """Test app data directory on Linux."""
        mock_system.return_value = 'Linux'
        mock_home.return_value = Path('/home/testuser')
        mock_getenv.return_value = '/home/testuser/.config'

        with patch('pathlib.Path.mkdir') as mock_mkdir:
            app_dir = get_app_data_directory('testapp')
            assert '.config/testapp' in str(app_dir)
            mock_mkdir.assert_called_once()

    @patch('tempfile.gettempdir')
    def test_get_temp_directory(self, mock_gettempdir):
        """Test getting temporary directory."""
        mock_gettempdir.return_value = '/tmp'

        with patch('pathlib.Path.mkdir') as mock_mkdir:
            temp_dir = get_temp_directory('testapp')
            assert 'testapp' in str(temp_dir)
            mock_mkdir.assert_called_once()

    def test_ensure_directory_exists_new(self, tmp_path):
        """Test ensuring directory exists creates new directory."""
        test_dir = tmp_path / "new_directory" / "nested"
        result = ensure_directory_exists(test_dir)

        assert result == test_dir
        assert test_dir.exists()
        assert test_dir.is_dir()

    def test_ensure_directory_exists_existing(self, tmp_path):
        """Test ensuring directory exists with existing directory."""
        test_dir = tmp_path / "existing"
        test_dir.mkdir()

        result = ensure_directory_exists(test_dir)
        assert result == test_dir
        assert test_dir.exists()


class TestExecutablePaths:
    """Test executable and resource path functions."""

    def test_get_executable_path_script_mode(self):
        """Test getting executable path in script mode."""
        with patch.object(sys, 'frozen', False, create=True):
            with patch.object(sys, 'argv', ['/path/to/script.py']):
                path = get_executable_path()
                assert isinstance(path, Path)
                assert 'script.py' in str(path)

    def test_get_executable_path_frozen_mode(self):
        """Test getting executable path in frozen (compiled) mode."""
        with patch.object(sys, 'frozen', True, create=True):
            with patch.object(sys, 'executable', '/path/to/app.exe'):
                path = get_executable_path()
                assert isinstance(path, Path)
                assert 'app.exe' in str(path)

    def test_get_resource_path_script_mode(self):
        """Test getting resource path in script mode."""
        with patch.object(sys, 'frozen', False, create=True):
            path = get_resource_path('resources/config.json')
            assert isinstance(path, Path)
            assert 'resources/config.json' in str(path)

    def test_get_resource_path_frozen_mode(self):
        """Test getting resource path in frozen mode."""
        with patch.object(sys, 'frozen', True, create=True):
            with patch.object(sys, '_MEIPASS', '/tmp/app_bundle', create=True):
                path = get_resource_path('resources/data.txt')
                assert isinstance(path, Path)
                assert '/tmp/app_bundle' in str(path)


class TestDiskSpaceOperations:
    """Test disk space and file size utilities."""

    @patch('shutil.disk_usage')
    def test_get_available_disk_space(self, mock_disk_usage):
        """Test getting available disk space."""
        mock_usage = MagicMock()
        mock_usage.free = 1024 * 1024 * 1024  # 1 GB
        mock_disk_usage.return_value = mock_usage

        space = get_available_disk_space(Path('/tmp'))
        assert space == 1024 * 1024 * 1024
        mock_disk_usage.assert_called_once()

    def test_format_bytes_small(self):
        """Test formatting small byte values."""
        assert format_bytes(0) == "0.00 B"
        assert format_bytes(512) == "512.00 B"
        assert format_bytes(1023) == "1023.00 B"

    def test_format_bytes_kilobytes(self):
        """Test formatting kilobytes."""
        assert format_bytes(1024) == "1.00 KB"
        assert format_bytes(1536) == "1.50 KB"

    def test_format_bytes_megabytes(self):
        """Test formatting megabytes."""
        assert format_bytes(1024 * 1024) == "1.00 MB"
        assert format_bytes(1024 * 1024 * 2.5) == "2.50 MB"

    def test_format_bytes_gigabytes(self):
        """Test formatting gigabytes."""
        assert format_bytes(1024 * 1024 * 1024) == "1.00 GB"
        assert format_bytes(1024 * 1024 * 1024 * 5) == "5.00 GB"

    def test_format_bytes_terabytes(self):
        """Test formatting terabytes."""
        assert format_bytes(1024 * 1024 * 1024 * 1024) == "1.00 TB"

    def test_format_bytes_precision(self):
        """Test format_bytes with different precision."""
        value = 1536  # 1.5 KB
        assert "KB" in format_bytes(value, precision=0)
        assert "1.5 KB" == format_bytes(value, precision=1)
        assert "1.500 KB" == format_bytes(value, precision=3)

    def test_format_bytes_negative(self):
        """Test formatting negative byte values."""
        assert format_bytes(-1024) == "-1.00 KB"


class TestFileOperations:
    """Test file and directory manipulation."""

    def test_safe_remove_file_existing(self, tmp_path):
        """Test safely removing an existing file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        result = safe_remove_file(test_file)
        assert result is True
        assert not test_file.exists()

    def test_safe_remove_file_nonexistent(self, tmp_path):
        """Test safely removing a non-existent file."""
        test_file = tmp_path / "nonexistent.txt"
        result = safe_remove_file(test_file)
        assert result is True

    def test_safe_remove_file_permission_error(self, tmp_path):
        """Test safe_remove_file handles permission errors."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        with patch('pathlib.Path.unlink', side_effect=PermissionError()):
            result = safe_remove_file(test_file)
            assert result is False

    def test_safe_remove_directory_empty(self, tmp_path):
        """Test removing empty directory."""
        test_dir = tmp_path / "empty_dir"
        test_dir.mkdir()

        result = safe_remove_directory(test_dir, recursive=False)
        assert result is True
        assert not test_dir.exists()

    def test_safe_remove_directory_recursive(self, tmp_path):
        """Test removing directory recursively with contents."""
        test_dir = tmp_path / "dir_with_files"
        test_dir.mkdir()
        (test_dir / "file1.txt").write_text("content")
        (test_dir / "subdir").mkdir()
        (test_dir / "subdir" / "file2.txt").write_text("content")

        result = safe_remove_directory(test_dir, recursive=True)
        assert result is True
        assert not test_dir.exists()

    def test_safe_remove_directory_nonexistent(self, tmp_path):
        """Test removing non-existent directory."""
        test_dir = tmp_path / "nonexistent"
        result = safe_remove_directory(test_dir)
        assert result is True

    def test_safe_remove_directory_error_handling(self, tmp_path):
        """Test safe_remove_directory handles errors."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()
        (test_dir / "file.txt").write_text("content")

        # Try to remove non-recursively with contents
        with patch('pathlib.Path.rmdir', side_effect=OSError()):
            result = safe_remove_directory(test_dir, recursive=False)
            assert result is False


class TestEnvironmentVariables:
    """Test environment variable handling."""

    def test_get_environment_variable_existing(self):
        """Test getting existing environment variable."""
        os.environ['TEST_VAR'] = 'test_value'
        value = get_environment_variable('TEST_VAR')
        assert value == 'test_value'
        del os.environ['TEST_VAR']

    def test_get_environment_variable_default(self):
        """Test getting non-existent variable with default."""
        value = get_environment_variable('NONEXISTENT_VAR', 'default_value')
        assert value == 'default_value'

    def test_get_environment_variable_none(self):
        """Test getting non-existent variable returns None."""
        value = get_environment_variable('NONEXISTENT_VAR')
        assert value is None

    def test_set_environment_variable(self):
        """Test setting environment variable."""
        set_environment_variable('TEST_SET_VAR', 'new_value')
        assert os.environ['TEST_SET_VAR'] == 'new_value'
        del os.environ['TEST_SET_VAR']


class TestCommandExecution:
    """Test command execution utilities."""

    @patch('subprocess.run')
    def test_execute_command_success(self, mock_run):
        """Test successful command execution."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "output"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        code, stdout, stderr = execute_command(['echo', 'hello'])

        assert code == 0
        assert stdout == "output"
        assert stderr == ""
        mock_run.assert_called_once()

    @patch('subprocess.run')
    def test_execute_command_failure(self, mock_run):
        """Test failed command execution."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error message"
        mock_run.return_value = mock_result

        code, stdout, stderr = execute_command(['false'])

        assert code == 1
        assert stderr == "error message"

    @patch('subprocess.run')
    def test_execute_command_timeout(self, mock_run):
        """Test command execution with timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired('cmd', 5)

        code, stdout, stderr = execute_command(['sleep', '10'], timeout=5)

        assert code == -1
        assert "timed out" in stderr
        assert "5 seconds" in stderr

    @patch('subprocess.run')
    def test_execute_command_exception(self, mock_run):
        """Test command execution with exception."""
        mock_run.side_effect = Exception("Command not found")

        code, stdout, stderr = execute_command(['nonexistent_command'])

        assert code == -1
        assert "Command not found" in stderr


class TestSystemInformation:
    """Test system information retrieval."""

    @patch('platform.node')
    def test_get_system_hostname(self, mock_node):
        """Test getting system hostname."""
        mock_node.return_value = 'test-hostname'
        hostname = get_system_hostname()
        assert hostname == 'test-hostname'
        mock_node.assert_called_once()

    @patch('platform.system')
    @patch('os.getenv')
    def test_get_system_username_windows(self, mock_getenv, mock_system):
        """Test getting username on Windows."""
        mock_system.return_value = 'Windows'
        mock_getenv.return_value = 'WindowsUser'

        username = get_system_username()
        assert username == 'WindowsUser'
        mock_getenv.assert_called_with('USERNAME', 'unknown')

    @patch('platform.system')
    @patch('os.getenv')
    def test_get_system_username_unix(self, mock_getenv, mock_system):
        """Test getting username on Unix systems."""
        mock_system.return_value = 'Linux'
        mock_getenv.return_value = 'linuxuser'

        username = get_system_username()
        assert username == 'linuxuser'
        mock_getenv.assert_called_with('USER', 'unknown')

    @patch('platform.system')
    @patch('os.getenv')
    def test_get_system_username_fallback(self, mock_getenv, mock_system):
        """Test username fallback to 'unknown'."""
        mock_system.return_value = 'Linux'

        def getenv_side_effect(key, default=None):
            return default

        mock_getenv.side_effect = getenv_side_effect

        username = get_system_username()
        assert username == 'unknown'


class TestPrivilegeChecks:
    """Test administrator/root privilege checks."""

    @patch('platform.system')
    @patch('builtins.__import__')
    def test_is_admin_windows_admin(self, mock_import, mock_system):
        """Test admin check on Windows as administrator."""
        mock_system.return_value = 'Windows'

        # Mock ctypes import
        mock_ctypes = MagicMock()
        mock_ctypes.windll.shell32.IsUserAnAdmin.return_value = 1

        def import_side_effect(name, *args, **kwargs):
            if name == 'ctypes':
                return mock_ctypes
            return __import__(name, *args, **kwargs)

        mock_import.side_effect = import_side_effect
        assert is_admin() is True

    @patch('platform.system')
    @patch('builtins.__import__')
    def test_is_admin_windows_not_admin(self, mock_import, mock_system):
        """Test admin check on Windows as regular user."""
        mock_system.return_value = 'Windows'

        # Mock ctypes import
        mock_ctypes = MagicMock()
        mock_ctypes.windll.shell32.IsUserAnAdmin.return_value = 0

        def import_side_effect(name, *args, **kwargs):
            if name == 'ctypes':
                return mock_ctypes
            return __import__(name, *args, **kwargs)

        mock_import.side_effect = import_side_effect
        assert is_admin() is False

    @patch('platform.system')
    @patch('os.geteuid')
    def test_is_admin_unix_root(self, mock_geteuid, mock_system):
        """Test admin check on Unix as root."""
        mock_system.return_value = 'Linux'
        mock_geteuid.return_value = 0

        assert is_admin() is True

    @patch('platform.system')
    @patch('os.geteuid')
    def test_is_admin_unix_user(self, mock_geteuid, mock_system):
        """Test admin check on Unix as regular user."""
        mock_system.return_value = 'Linux'
        mock_geteuid.return_value = 1000

        assert is_admin() is False

    @patch('platform.system')
    def test_is_admin_exception_handling(self, mock_system):
        """Test is_admin handles exceptions gracefully."""
        mock_system.side_effect = Exception("Error")

        result = is_admin()
        assert result is False


class TestCPUThreading:
    """Test CPU and threading utilities."""

    @patch('os.cpu_count')
    def test_get_cpu_count_normal(self, mock_cpu_count):
        """Test getting CPU count."""
        mock_cpu_count.return_value = 8
        count = get_cpu_count()
        assert count == 8

    @patch('os.cpu_count')
    def test_get_cpu_count_none_fallback(self, mock_cpu_count):
        """Test CPU count fallback when None."""
        mock_cpu_count.return_value = None
        count = get_cpu_count()
        assert count == 1

    @patch('os.cpu_count')
    def test_get_optimal_thread_count_no_max(self, mock_cpu_count):
        """Test optimal thread count without maximum."""
        mock_cpu_count.return_value = 8
        count = get_optimal_thread_count()
        assert count == 7  # CPU count - 1

    @patch('os.cpu_count')
    def test_get_optimal_thread_count_with_max(self, mock_cpu_count):
        """Test optimal thread count with maximum limit."""
        mock_cpu_count.return_value = 8
        count = get_optimal_thread_count(max_threads=4)
        assert count == 4

    @patch('os.cpu_count')
    def test_get_optimal_thread_count_single_cpu(self, mock_cpu_count):
        """Test optimal thread count on single CPU system."""
        mock_cpu_count.return_value = 1
        count = get_optimal_thread_count()
        assert count == 1  # Never go below 1

    @patch('os.cpu_count')
    def test_get_optimal_thread_count_high_max(self, mock_cpu_count):
        """Test optimal thread count with high max doesn't exceed CPU-1."""
        mock_cpu_count.return_value = 4
        count = get_optimal_thread_count(max_threads=100)
        assert count == 3  # CPU count - 1, not the max


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_format_bytes_zero(self):
        """Test formatting zero bytes."""
        assert format_bytes(0) == "0.00 B"

    def test_format_bytes_very_large(self):
        """Test formatting very large byte values."""
        petabytes = 1024 ** 5
        result = format_bytes(petabytes * 2)
        assert "PB" in result

    def test_ensure_directory_exists_path_string(self, tmp_path):
        """Test ensure_directory_exists with string path."""
        test_path = str(tmp_path / "string_path")
        result = ensure_directory_exists(test_path)
        assert isinstance(result, Path)
        assert result.exists()

    @patch('platform.system')
    @patch('pathlib.Path.home')
    def test_app_data_directory_unknown_os(self, mock_home, mock_system):
        """Test app data directory on unknown OS defaults to Linux-like."""
        mock_system.return_value = 'UnknownOS'
        mock_home.return_value = Path('/home/user')

        with patch('pathlib.Path.mkdir'):
            with patch('os.getenv', return_value='/home/user/.config'):
                app_dir = get_app_data_directory('test')
                # Unknown OS defaults to Linux behavior
                assert 'test' in str(app_dir)


class TestIntegration:
    """Integration tests combining multiple functions."""

    def test_cross_platform_paths_consistency(self, tmp_path):
        """Test path operations work consistently across platforms."""
        # Create a directory
        test_dir = tmp_path / "integration_test"
        ensure_directory_exists(test_dir)

        # Create a file
        test_file = test_dir / "test.txt"
        test_file.write_text("content")

        # Remove file
        assert safe_remove_file(test_file)
        assert not test_file.exists()

        # Remove directory
        assert safe_remove_directory(test_dir)
        assert not test_dir.exists()

    @patch('subprocess.run')
    @patch('os.cpu_count')
    def test_system_resource_check(self, mock_cpu_count, mock_run):
        """Test combining CPU count with command execution."""
        mock_cpu_count.return_value = 4
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "success"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        cpu_count = get_cpu_count()
        assert cpu_count == 4

        thread_count = get_optimal_thread_count(max_threads=2)
        assert thread_count == 2

        code, stdout, stderr = execute_command(['test'])
        assert code == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--cov=src.utils.system_utils', '--cov-report=term-missing'])
