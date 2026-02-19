"""
Comprehensive test suite for src/processing/hooks_executor.py
Tests external program hook execution with subprocess mocking and error handling.
"""

import subprocess
import json
from unittest.mock import Mock, patch

from src.processing.hooks_executor import (
    HooksExecutor,
    get_hooks_executor,
    execute_gallery_hooks
)


class TestHooksExecutorInit:
    """Test HooksExecutor initialization"""

    def test_init(self):
        """Test HooksExecutor initialization"""
        executor = HooksExecutor()
        # Should not cache config on init
        assert not hasattr(executor, '_config')


class TestHooksExecutorConfigLoading:
    """Test configuration loading"""

    @patch('src.processing.hooks_executor.configparser.ConfigParser')
    @patch('src.processing.hooks_executor.get_config_path')
    @patch('src.processing.hooks_executor.os.path.exists')
    def test_load_config_file_exists(self, mock_exists, mock_get_path, mock_config_class):
        """Test loading config when file exists"""
        mock_exists.return_value = True
        mock_get_path.return_value = "/path/to/config.ini"

        mock_config = Mock()
        mock_config.getboolean.return_value = True
        mock_config.get.return_value = "test_command"
        mock_config_class.return_value = mock_config

        executor = HooksExecutor()
        config = executor._load_config()

        assert config['parallel_execution'] is True
        assert 'added' in config
        assert 'started' in config
        assert 'completed' in config

    @patch('src.processing.hooks_executor.configparser.ConfigParser')
    @patch('src.processing.hooks_executor.get_config_path')
    @patch('src.processing.hooks_executor.os.path.exists')
    def test_load_config_file_not_exists(self, mock_exists, mock_get_path, mock_config_class):
        """Test loading config when file doesn't exist"""
        mock_exists.return_value = False
        mock_get_path.return_value = "/path/to/config.ini"

        mock_config = Mock()
        mock_config.getboolean.side_effect = lambda section, key, fallback=None: fallback
        mock_config.get.side_effect = lambda section, key, fallback=None: fallback
        mock_config_class.return_value = mock_config

        executor = HooksExecutor()
        config = executor._load_config()

        # Should use fallback values
        assert config['parallel_execution'] is True
        assert config['added']['enabled'] is False
        assert config['started']['enabled'] is False
        assert config['completed']['enabled'] is False


class TestHooksExecutorVariableSubstitution:
    """Test variable substitution in commands"""

    def test_substitute_basic_variables(self):
        """Test substitution of basic variables"""
        executor = HooksExecutor()
        context = {
            'gallery_name': 'Test Gallery',
            'gallery_path': '/path/to/gallery',
            'image_count': 50,
            'gallery_id': 'gal123'
        }

        result = executor._substitute_variables(
            "process %N at %p with %C images (ID: %g)",
            context
        )

        assert result == "process Test Gallery at /path/to/gallery with 50 images (ID: gal123)"

    def test_substitute_custom_fields(self):
        """Test substitution of custom fields"""
        executor = HooksExecutor()
        context = {
            'custom1': 'value1',
            'custom2': 'value2',
            'custom3': 'value3',
            'custom4': 'value4'
        }

        result = executor._substitute_variables(
            "Fields: %c1 %c2 %c3 %c4",
            context
        )

        assert result == "Fields: value1 value2 value3 value4"

    def test_substitute_ext_fields(self):
        """Test substitution of ext fields"""
        executor = HooksExecutor()
        context = {
            'ext1': 'ext_val1',
            'ext2': 'ext_val2',
            'ext3': 'ext_val3',
            'ext4': 'ext_val4'
        }

        result = executor._substitute_variables(
            "Ext: %e1 %e2 %e3 %e4",
            context
        )

        assert result == "Ext: ext_val1 ext_val2 ext_val3 ext_val4"

    def test_substitute_escaped_percent(self):
        """Test escaping percent signs"""
        executor = HooksExecutor()
        context = {'gallery_name': 'Test'}

        # %% should become a literal %
        result = executor._substitute_variables(
            "Gallery %N has 100%% completion",
            context
        )

        assert result == "Gallery Test has 100% completion"

    def test_substitute_missing_values(self):
        """Test substitution with missing context values"""
        executor = HooksExecutor()
        context = {'gallery_name': 'Test'}

        result = executor._substitute_variables(
            "%N has %C images",
            context
        )

        assert result == "Test has 0 images"  # Missing values default to empty/0

    def test_substitute_artifact_paths(self):
        """Test substitution of artifact paths"""
        executor = HooksExecutor()
        context = {
            'json_path': '/path/to/gallery.json',
            'bbcode_path': '/path/to/gallery.bbcode',
            'zip_path': '/path/to/gallery.zip'
        }

        result = executor._substitute_variables(
            "Artifacts: JSON=%j BBCode=%b ZIP=%z",
            context
        )

        assert result == "Artifacts: JSON=/path/to/gallery.json BBCode=/path/to/gallery.bbcode ZIP=/path/to/gallery.zip"


class TestHooksExecutorExecution:
    """Test hook execution"""

    @patch('src.processing.hooks_executor.subprocess.run')
    def test_execute_hook_success(self, mock_run):
        """Test successful hook execution"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Success output"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        executor = HooksExecutor()
        config = {
            'test_hook': {
                'enabled': True,
                'command': 'echo "test"',
                'show_console': False
            }
        }
        context = {'gallery_name': 'Test'}

        success, json_data, _stdout = executor._execute_hook_with_config('test_hook', context, config)

        assert success is True
        mock_run.assert_called_once()

    @patch('src.processing.hooks_executor.subprocess.run')
    def test_execute_hook_failure(self, mock_run):
        """Test hook execution failure"""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error output"
        mock_run.return_value = mock_result

        executor = HooksExecutor()
        config = {
            'test_hook': {
                'enabled': True,
                'command': 'failing_command',
                'show_console': False
            }
        }
        context = {}

        success, json_data, _stdout = executor._execute_hook_with_config('test_hook', context, config)

        assert success is False
        assert json_data is None

    @patch('src.processing.hooks_executor.subprocess.run')
    def test_execute_hook_json_output(self, mock_run):
        """Test hook with JSON output"""
        json_output = {"download_url": "http://example.com/file", "file_id": "12345"}
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(json_output)
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        executor = HooksExecutor()
        config = {
            'test_hook': {
                'enabled': True,
                'command': 'json_producer',
                'show_console': False
            }
        }
        context = {}

        success, json_data, _stdout = executor._execute_hook_with_config('test_hook', context, config)

        assert success is True
        assert json_data == json_output

    @patch('src.processing.hooks_executor.subprocess.run')
    def test_execute_hook_timeout(self, mock_run):
        """Test hook execution timeout"""
        mock_run.side_effect = subprocess.TimeoutExpired('cmd', 300)

        executor = HooksExecutor()
        config = {
            'test_hook': {
                'enabled': True,
                'command': 'long_running_command',
                'show_console': False
            }
        }
        context = {}

        success, json_data, _stdout = executor._execute_hook_with_config('test_hook', context, config)

        assert success is False
        assert json_data is None

    @patch('src.processing.hooks_executor.subprocess.run')
    def test_execute_hook_disabled(self, mock_run):
        """Test disabled hook is skipped"""
        executor = HooksExecutor()
        config = {
            'test_hook': {
                'enabled': False,
                'command': 'should_not_run',
                'show_console': False
            }
        }
        context = {}

        success, json_data, _stdout = executor._execute_hook_with_config('test_hook', context, config)

        assert success is True
        assert json_data is None
        mock_run.assert_not_called()

    @patch('src.processing.hooks_executor.subprocess.run')
    def test_execute_hook_empty_command(self, mock_run):
        """Test hook with empty command"""
        executor = HooksExecutor()
        config = {
            'test_hook': {
                'enabled': True,
                'command': '',
                'show_console': False
            }
        }
        context = {}

        success, json_data, _stdout = executor._execute_hook_with_config('test_hook', context, config)

        assert success is True
        assert json_data is None
        mock_run.assert_not_called()


class TestHooksExecutorTempZip:
    """Test temporary ZIP creation for hooks"""

    @patch('src.processing.hooks_executor.subprocess.run')
    @patch('src.processing.hooks_executor.create_temp_zip')
    @patch('src.processing.hooks_executor.os.path.isdir')
    def test_execute_hook_creates_temp_zip(self, mock_isdir, mock_create_zip, mock_run):
        """Test hook creates temporary ZIP when needed"""
        mock_isdir.return_value = True
        mock_create_zip.return_value = '/tmp/temp_gallery.zip'

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        executor = HooksExecutor()
        config = {
            'test_hook': {
                'enabled': True,
                'command': 'process_zip %z',
                'show_console': False
            }
        }
        context = {
            'gallery_path': '/path/to/gallery',
            'zip_path': ''  # No existing ZIP
        }

        with patch.object(executor, '_remove_temp_file_with_retry'):
            success, json_data, _stdout = executor._execute_hook_with_config('test_hook', context, config)

        mock_create_zip.assert_called_once_with('/path/to/gallery')
        assert success is True

    @patch('src.processing.hooks_executor.subprocess.run')
    def test_execute_hook_uses_existing_zip(self, mock_run):
        """Test hook uses existing ZIP path"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        executor = HooksExecutor()
        config = {
            'test_hook': {
                'enabled': True,
                'command': 'process_zip %z',
                'show_console': False
            }
        }
        context = {
            'gallery_path': '/path/to/gallery',
            'zip_path': '/existing/gallery.zip'
        }

        success, json_data, _stdout = executor._execute_hook_with_config('test_hook', context, config)

        # Should use existing ZIP, not create new one
        assert success is True
        # Verify command was called with existing ZIP path
        call_args = mock_run.call_args[0][0]
        assert '/existing/gallery.zip' in ' '.join(call_args)


class TestHooksExecutorTempFileRemoval:
    """Test temporary file removal with retry"""

    @patch('src.processing.hooks_executor.os.path.exists')
    @patch('src.processing.hooks_executor.os.remove')
    def test_remove_temp_file_success(self, mock_remove, mock_exists):
        """Test successful temp file removal"""
        mock_exists.return_value = True

        executor = HooksExecutor()
        result = executor._remove_temp_file_with_retry('/tmp/test.zip')

        assert result is True
        mock_remove.assert_called_once_with('/tmp/test.zip')

    @patch('src.processing.hooks_executor.os.path.exists')
    def test_remove_temp_file_not_exists(self, mock_exists):
        """Test removing non-existent file"""
        mock_exists.return_value = False

        executor = HooksExecutor()
        result = executor._remove_temp_file_with_retry('/tmp/nonexistent.zip')

        assert result is True

    @patch('src.processing.hooks_executor.time.sleep')
    @patch('src.processing.hooks_executor.os.path.exists')
    @patch('src.processing.hooks_executor.os.remove')
    def test_remove_temp_file_permission_error_retry(self, mock_remove, mock_exists, mock_sleep):
        """Test file removal with permission error and retry"""
        mock_exists.return_value = True
        # First attempt fails, second succeeds
        mock_remove.side_effect = [PermissionError("File locked"), None]

        executor = HooksExecutor()
        result = executor._remove_temp_file_with_retry('/tmp/test.zip', max_retries=2)

        assert result is True
        assert mock_remove.call_count == 2
        mock_sleep.assert_called_once()

    @patch('src.processing.hooks_executor.time.sleep')
    @patch('src.processing.hooks_executor.os.path.exists')
    @patch('src.processing.hooks_executor.os.remove')
    def test_remove_temp_file_max_retries_exceeded(self, mock_remove, mock_exists, mock_sleep):
        """Test file removal fails after max retries"""
        mock_exists.return_value = True
        mock_remove.side_effect = PermissionError("File locked")

        executor = HooksExecutor()
        result = executor._remove_temp_file_with_retry('/tmp/test.zip', max_retries=3)

        assert result is False
        assert mock_remove.call_count == 3


class TestHooksExecutorParallelExecution:
    """Test parallel and sequential hook execution"""

    @patch('src.processing.hooks_executor.subprocess.run')
    def test_execute_hooks_parallel(self, mock_run):
        """Test parallel execution of multiple hooks"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        executor = HooksExecutor()

        with patch.object(executor, '_load_config') as mock_load_config:
            mock_load_config.return_value = {
                'parallel_execution': True,
                'added': {
                    'enabled': True,
                    'command': 'hook1',
                    'show_console': False,
                    'key_mapping': {}
                },
                'started': {
                    'enabled': True,
                    'command': 'hook2',
                    'show_console': False,
                    'key_mapping': {}
                }
            }

            context = {'gallery_name': 'Test'}
            executor.execute_hooks(['added', 'started'], context)

        # Both hooks should be executed
        assert mock_run.call_count == 2

    @patch('src.processing.hooks_executor.subprocess.run')
    def test_execute_hooks_sequential(self, mock_run):
        """Test sequential execution of multiple hooks"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        executor = HooksExecutor()

        with patch.object(executor, '_load_config') as mock_load_config:
            mock_load_config.return_value = {
                'parallel_execution': False,
                'added': {
                    'enabled': True,
                    'command': 'hook1',
                    'show_console': False,
                    'key_mapping': {}
                },
                'started': {
                    'enabled': True,
                    'command': 'hook2',
                    'show_console': False,
                    'key_mapping': {}
                }
            }

            context = {'gallery_name': 'Test'}
            executor.execute_hooks(['added', 'started'], context)

        # Both hooks should be executed sequentially
        assert mock_run.call_count == 2

    @patch('src.processing.hooks_executor.subprocess.run')
    def test_execute_hooks_no_enabled(self, mock_run):
        """Test execution when no hooks are enabled"""
        executor = HooksExecutor()

        with patch.object(executor, '_load_config') as mock_load_config:
            mock_load_config.return_value = {
                'parallel_execution': True,
                'added': {
                    'enabled': False,
                    'command': 'hook1',
                    'show_console': False,
                    'key_mapping': {}
                }
            }

            context = {'gallery_name': 'Test'}
            results = executor.execute_hooks(['added'], context)

        # No hooks should be executed
        mock_run.assert_not_called()
        assert results == {}


class TestHooksExecutorKeyMapping:
    """Test JSON key mapping to ext fields"""

    @patch('src.processing.hooks_executor.subprocess.run')
    def test_execute_hooks_extracts_ext_fields(self, mock_run):
        """Test extraction of ext fields from JSON"""
        json_output = {
            "download_url": "http://example.com/file",
            "file_id": "12345",
            "extra_field": "value"
        }

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(json_output)
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        executor = HooksExecutor()

        with patch.object(executor, '_load_config') as mock_load_config:
            mock_load_config.return_value = {
                'parallel_execution': False,
                'completed': {
                    'enabled': True,
                    'command': 'upload_hook',
                    'show_console': False,
                    'key_mapping': {
                        'ext1': 'download_url',
                        'ext2': 'file_id',
                        'ext3': '',
                        'ext4': 'extra_field'
                    }
                }
            }

            context = {'gallery_name': 'Test'}
            results = executor.execute_hooks(['completed'], context)

        # Should extract mapped fields
        assert results['ext1'] == "http://example.com/file"
        assert results['ext2'] == "12345"
        assert results['ext4'] == "value"
        assert 'ext3' not in results  # Empty mapping should be skipped

    @patch('src.processing.hooks_executor.subprocess.run')
    def test_execute_hooks_missing_json_keys(self, mock_run):
        """Test handling of missing JSON keys"""
        json_output = {"file_id": "12345"}

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(json_output)
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        executor = HooksExecutor()

        with patch.object(executor, '_load_config') as mock_load_config:
            mock_load_config.return_value = {
                'parallel_execution': False,
                'completed': {
                    'enabled': True,
                    'command': 'upload_hook',
                    'show_console': False,
                    'key_mapping': {
                        'ext1': 'download_url',  # Missing in JSON
                        'ext2': 'file_id'  # Present in JSON
                    }
                }
            }

            context = {'gallery_name': 'Test'}
            results = executor.execute_hooks(['completed'], context)

        # Should only extract present keys
        assert 'ext1' not in results
        assert results['ext2'] == "12345"


class TestGlobalFunctions:
    """Test module-level global functions"""

    def test_get_hooks_executor_singleton(self):
        """Test singleton pattern for hooks executor"""
        executor1 = get_hooks_executor()
        executor2 = get_hooks_executor()

        assert executor1 is executor2

    @patch('src.processing.hooks_executor.get_hooks_executor')
    def test_execute_gallery_hooks_convenience(self, mock_get_executor):
        """Test convenience function for executing gallery hooks"""
        mock_executor = Mock()
        mock_executor.execute_hooks.return_value = {'ext1': 'value1'}
        mock_get_executor.return_value = mock_executor

        results = execute_gallery_hooks(
            event_type='completed',
            gallery_path='/path/to/gallery',
            gallery_name='Test Gallery',
            image_count=50,
            gallery_id='gal123'
        )

        mock_executor.execute_hooks.assert_called_once()
        assert results == {'ext1': 'value1'}

    @patch('src.processing.hooks_executor.get_hooks_executor')
    def test_execute_gallery_hooks_default_name(self, mock_get_executor):
        """Test convenience function uses folder name if gallery_name not provided"""
        mock_executor = Mock()
        mock_executor.execute_hooks.return_value = {}
        mock_get_executor.return_value = mock_executor

        execute_gallery_hooks(
            event_type='added',
            gallery_path='/path/to/my_gallery'
        )

        # Should use folder name as gallery_name
        call_args = mock_executor.execute_hooks.call_args[0]
        context = call_args[1]
        assert context['gallery_name'] == 'my_gallery'


class TestHooksExecutorCommandParsing:
    """Test command parsing for different platforms"""

    @patch('src.processing.hooks_executor.subprocess.run')
    @patch('src.processing.hooks_executor.sys.platform', 'win32')
    def test_execute_hook_windows_command_parsing(self, mock_run):
        """Test Windows command parsing with quotes"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        executor = HooksExecutor()
        config = {
            'test_hook': {
                'enabled': True,
                'command': 'program.exe "argument with spaces"',
                'show_console': False
            }
        }
        context = {}

        success, json_data, _stdout = executor._execute_hook_with_config('test_hook', context, config)

        assert success is True
        # Verify subprocess.run was called with proper argument list
        call_args = mock_run.call_args[0][0]
        assert isinstance(call_args, list)

    @patch('src.processing.hooks_executor.subprocess.run')
    @patch('src.processing.hooks_executor.sys.platform', 'linux')
    def test_execute_hook_unix_command_parsing(self, mock_run):
        """Test Unix command parsing with shlex"""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        executor = HooksExecutor()
        config = {
            'test_hook': {
                'enabled': True,
                'command': 'program "argument with spaces"',
                'show_console': False
            }
        }
        context = {}

        success, json_data, _stdout = executor._execute_hook_with_config('test_hook', context, config)

        assert success is True
        call_args = mock_run.call_args[0][0]
        assert isinstance(call_args, list)
