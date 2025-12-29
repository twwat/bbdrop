#!/usr/bin/env python3
"""
Comprehensive test suite for logging.py
Testing AppLogger, file handlers, and logging configuration
"""

import pytest
import os
import logging
import tempfile
import configparser
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from src.utils.logging import (
    get_logger,
    AppLogger,
    _GzipTimedRotatingFileHandler,
    _GzipRotatingFileHandler
)


class TestGetLogger:
    """Test get_logger singleton function"""

    def test_returns_app_logger_instance(self):
        """Test get_logger returns AppLogger instance"""
        logger = get_logger()
        assert isinstance(logger, AppLogger)

    def test_singleton_behavior(self):
        """Test get_logger returns same instance"""
        logger1 = get_logger()
        logger2 = get_logger()
        assert logger1 is logger2


class TestAppLoggerInit:
    """Test AppLogger initialization"""

    @pytest.fixture
    def mock_paths(self, tmp_path):
        """Mock config and base paths"""
        config_path = tmp_path / "config.ini"
        base_path = tmp_path / "store"
        base_path.mkdir()

        # FIXED: Use correct patch target - __init__ doesn't use name mangling
        with patch('src.utils.logging.AppLogger.__init__') as mock_init:
            mock_init.return_value = None
            yield config_path, base_path

    def test_trace_level_registered(self):
        """Test TRACE level is registered with logging module"""
        assert logging.getLevelName(5) == "TRACE"

    def test_defaults_defined(self):
        """Test default settings are defined"""
        assert 'enabled' in AppLogger.DEFAULTS
        assert 'rotation' in AppLogger.DEFAULTS
        assert 'backup_count' in AppLogger.DEFAULTS
        assert 'compress' in AppLogger.DEFAULTS
        assert 'level_file' in AppLogger.DEFAULTS

    def test_level_map_complete(self):
        """Test all log levels are mapped"""
        assert AppLogger.LEVEL_MAP['TRACE'] == 5
        assert AppLogger.LEVEL_MAP['DEBUG'] == logging.DEBUG
        assert AppLogger.LEVEL_MAP['INFO'] == logging.INFO
        assert AppLogger.LEVEL_MAP['WARNING'] == logging.WARNING
        assert AppLogger.LEVEL_MAP['ERROR'] == logging.ERROR
        assert AppLogger.LEVEL_MAP['CRITICAL'] == logging.CRITICAL


class TestStripLeadingTime:
    """Test time stripping from messages"""

    @pytest.mark.parametrize("message,expected", [
        ("12:34:56 Test message", "Test message"),
        ("00:00:00 Start", "Start"),
        ("23:59:59 End", "End"),
        ("No timestamp here", "No timestamp here"),
        ("12:34 Incomplete", "12:34 Incomplete"),
        ("", ""),
    ])
    def test_strip_timestamp(self, message, expected):
        """Test timestamp stripping"""
        result = AppLogger._strip_leading_time(message)
        assert result == expected

    def test_strip_only_first_timestamp(self):
        """Test only first timestamp is removed"""
        message = "12:34:56 First 23:45:67 Second"
        result = AppLogger._strip_leading_time(message)
        assert result == "First 23:45:67 Second"


class TestSettingsManagement:
    """Test settings load, save, and get"""

    @pytest.fixture
    def temp_config(self, tmp_path):
        """Create temporary config file"""
        config_path = tmp_path / "config.ini"
        base_path = tmp_path / "store"
        base_path.mkdir()

        # Create minimal config
        config = configparser.ConfigParser()
        config['LOGGING'] = {
            'enabled': 'true',
            'rotation': 'daily',
            'backup_count': '7'
        }
        with open(config_path, 'w') as f:
            config.write(f)

        return config_path, base_path

    def test_get_settings_normalizes_types(self):
        """Test get_settings normalizes boolean and int values"""
        with patch.object(AppLogger, '__init__', return_value=None):
            logger = AppLogger.__new__(AppLogger)
            logger._settings = {
                'enabled': 'true',
                'compress': 'false',
                'backup_count': '10',
                'max_bytes': '1048576'
            }

            settings = logger.get_settings()
            assert settings['enabled'] is True
            assert settings['compress'] is False
            assert settings['backup_count'] == 10
            assert settings['max_bytes'] == 1048576

    def test_update_settings_accepts_kwargs(self):
        """Test update_settings accepts keyword arguments"""
        with patch.object(AppLogger, '__init__', return_value=None):
            logger = AppLogger.__new__(AppLogger)
            logger._settings = dict(AppLogger.DEFAULTS)
            logger._save_settings = Mock()
            logger._apply_settings = Mock()

            logger.update_settings(enabled='false', backup_count='14')

            assert logger._settings['enabled'] == 'false'
            assert logger._settings['backup_count'] == '14'
            assert logger._save_settings.called
            assert logger._apply_settings.called

    def test_get_settings_normalizes_categories(self):
        """Test category settings are normalized to booleans"""
        with patch.object(AppLogger, '__init__', return_value=None):
            logger = AppLogger.__new__(AppLogger)
            logger._settings = {
                'cats_gui_uploads': 'true',
                'cats_file_auth': 'false',
            }

            settings = logger.get_settings()
            assert settings['cats_gui_uploads'] is True
            assert settings['cats_file_auth'] is False

    def test_get_settings_normalizes_modes(self):
        """Test upload success modes are normalized"""
        with patch.object(AppLogger, '__init__', return_value=None):
            logger = AppLogger.__new__(AppLogger)
            logger._settings = {
                'upload_success_mode_gui': 'gallery',
                'upload_success_mode_file': 'both'
            }

            settings = logger.get_settings()
            assert settings['upload_success_mode_gui'] == 'gallery'
            assert settings['upload_success_mode_file'] == 'both'

    def test_invalid_mode_defaults_to_gallery(self):
        """Test invalid mode defaults to 'gallery'"""
        with patch.object(AppLogger, '__init__', return_value=None):
            logger = AppLogger.__new__(AppLogger)
            logger._settings = {
                'upload_success_mode_gui': 'invalid'
            }

            settings = logger.get_settings()
            assert settings['upload_success_mode_gui'] == 'gallery'


class TestLogLevelFiltering:
    """Test log level and category filtering"""

    def test_should_emit_gui_respects_level(self):
        """Test should_emit_gui respects GUI log level"""
        with patch.object(AppLogger, '__init__', return_value=None):
            logger = AppLogger.__new__(AppLogger)
            logger._gui_level = logging.WARNING
            logger._settings = {}
            logger.get_settings = Mock(return_value={'cats_gui_general': True})

            # Below level - should not emit
            assert logger.should_emit_gui('general', logging.INFO) == False

            # At or above level - should emit
            assert logger.should_emit_gui('general', logging.WARNING) == True
            assert logger.should_emit_gui('general', logging.ERROR) == True

    def test_should_emit_gui_respects_category(self):
        """Test should_emit_gui respects category filters"""
        with patch.object(AppLogger, '__init__', return_value=None):
            logger = AppLogger.__new__(AppLogger)
            logger._gui_level = logging.INFO
            logger._settings = {}
            logger.get_settings = Mock(return_value={
                'cats_gui_uploads': True,
                'cats_gui_auth': False
            })

            assert logger.should_emit_gui('uploads', logging.INFO) == True
            assert logger.should_emit_gui('auth', logging.INFO) == False

    def test_should_emit_file_blocks_trace(self):
        """Test should_emit_file blocks TRACE level"""
        with patch.object(AppLogger, '__init__', return_value=None):
            logger = AppLogger.__new__(AppLogger)
            logger._file_level = logging.DEBUG
            logger._settings = {'enabled': 'true'}
            logger.get_settings = Mock(return_value={'cats_file_general': True})

            # TRACE should never be logged to file
            assert logger.should_emit_file('general', AppLogger.TRACE) == False

            # DEBUG and above should be logged
            assert logger.should_emit_file('general', logging.DEBUG) == True

    def test_should_emit_file_respects_enabled(self):
        """Test should_emit_file respects enabled flag"""
        with patch.object(AppLogger, '__init__', return_value=None):
            logger = AppLogger.__new__(AppLogger)
            logger._file_level = logging.INFO
            logger._settings = {'enabled': 'false'}
            logger.get_settings = Mock(return_value={'cats_file_general': True})

            assert logger.should_emit_file('general', logging.INFO) == False

    def test_should_emit_file_respects_category(self):
        """Test should_emit_file respects category filters"""
        with patch.object(AppLogger, '__init__', return_value=None):
            logger = AppLogger.__new__(AppLogger)
            logger._file_level = logging.INFO
            logger._settings = {'enabled': 'true'}
            logger.get_settings = Mock(return_value={
                'cats_file_network': True,
                'cats_file_ui': False
            })

            assert logger.should_emit_file('network', logging.INFO) == True
            assert logger.should_emit_file('ui', logging.INFO) == False


class TestUploadSuccessFiltering:
    """Test upload success message filtering"""

    def test_should_log_upload_file_success(self):
        """Test file upload success filtering"""
        with patch.object(AppLogger, '__init__', return_value=None):
            logger = AppLogger.__new__(AppLogger)

            # Mode: file - should log
            logger._settings = {'upload_success_mode_gui': 'file'}
            assert logger.should_log_upload_file_success('gui') == True

            # Mode: both - should log
            logger._settings = {'upload_success_mode_gui': 'both'}
            assert logger.should_log_upload_file_success('gui') == True

            # Mode: gallery - should not log
            logger._settings = {'upload_success_mode_gui': 'gallery'}
            assert logger.should_log_upload_file_success('gui') == False

            # Mode: none - should not log
            logger._settings = {'upload_success_mode_gui': 'none'}
            assert logger.should_log_upload_file_success('gui') == False

    def test_should_log_upload_gallery_success(self):
        """Test gallery upload success filtering"""
        with patch.object(AppLogger, '__init__', return_value=None):
            logger = AppLogger.__new__(AppLogger)

            # Mode: gallery - should log
            logger._settings = {'upload_success_mode_file': 'gallery'}
            assert logger.should_log_upload_gallery_success('file') == True

            # Mode: both - should log
            logger._settings = {'upload_success_mode_file': 'both'}
            assert logger.should_log_upload_gallery_success('file') == True

            # Mode: file - should not log
            logger._settings = {'upload_success_mode_file': 'file'}
            assert logger.should_log_upload_gallery_success('file') == False

            # Mode: none - should not log
            logger._settings = {'upload_success_mode_file': 'none'}
            assert logger.should_log_upload_gallery_success('file') == False


class TestLogToFile:
    """Test file logging functionality"""

    def test_log_to_file_writes_message(self):
        """Test log_to_file writes to logger"""
        with patch.object(AppLogger, '__init__', return_value=None):
            logger = AppLogger.__new__(AppLogger)
            logger._settings = {'enabled': 'true'}
            logger._file_level = logging.INFO
            logger._logger = Mock()
            logger.should_emit_file = Mock(return_value=True)

            logger.log_to_file("Test message", logging.INFO, "general")

            logger._logger.log.assert_called_once()

    def test_log_to_file_strips_timestamp(self):
        """Test log_to_file strips HH:MM:SS timestamp"""
        with patch.object(AppLogger, '__init__', return_value=None):
            logger = AppLogger.__new__(AppLogger)
            logger._settings = {'enabled': 'true'}
            logger._file_level = logging.INFO
            logger._logger = Mock()
            logger.should_emit_file = Mock(return_value=True)

            logger.log_to_file("12:34:56 Test message", logging.INFO, "general")

            # Should log without timestamp
            call_args = logger._logger.log.call_args
            assert "12:34:56" not in call_args[0][1]

    def test_log_to_file_respects_disabled(self):
        """Test log_to_file respects enabled=false"""
        with patch.object(AppLogger, '__init__', return_value=None):
            logger = AppLogger.__new__(AppLogger)
            logger._settings = {'enabled': 'false'}
            logger._logger = Mock()

            logger.log_to_file("Test", logging.INFO)

            logger._logger.log.assert_not_called()

    def test_log_to_file_respects_level(self):
        """Test log_to_file respects file log level"""
        with patch.object(AppLogger, '__init__', return_value=None):
            logger = AppLogger.__new__(AppLogger)
            logger._settings = {'enabled': 'true'}
            logger._file_level = logging.WARNING
            logger._logger = Mock()
            logger.should_emit_file = Mock(return_value=False)

            logger.log_to_file("Test", logging.DEBUG)

            logger._logger.log.assert_not_called()


class TestReadCurrentLog:
    """Test log file reading"""

    def test_read_full_log(self, tmp_path):
        """Test reading entire log file"""
        log_file = tmp_path / "test.log"
        content = "Line 1\nLine 2\nLine 3\n"
        log_file.write_text(content)

        with patch.object(AppLogger, '__init__', return_value=None):
            logger = AppLogger.__new__(AppLogger)
            logger.get_current_log_path = Mock(return_value=str(log_file))

            result = logger.read_current_log()
            assert result == content

    def test_read_tail_bytes(self, tmp_path):
        """Test reading last N bytes of log"""
        log_file = tmp_path / "test.log"
        content = "x" * 1000
        log_file.write_text(content)

        with patch.object(AppLogger, '__init__', return_value=None):
            logger = AppLogger.__new__(AppLogger)
            logger.get_current_log_path = Mock(return_value=str(log_file))

            result = logger.read_current_log(tail_bytes=100)
            assert len(result) <= 100

    def test_read_nonexistent_log(self, tmp_path):
        """Test reading nonexistent log returns empty string"""
        with patch.object(AppLogger, '__init__', return_value=None):
            logger = AppLogger.__new__(AppLogger)
            logger.get_current_log_path = Mock(return_value=str(tmp_path / "nonexistent.log"))

            result = logger.read_current_log()
            assert result == ""

    def test_read_handles_unicode(self, tmp_path):
        """Test reading log with unicode content"""
        log_file = tmp_path / "test.log"
        content = "Test 日本語 中文 🎉\n"
        log_file.write_text(content, encoding='utf-8')

        with patch.object(AppLogger, '__init__', return_value=None):
            logger = AppLogger.__new__(AppLogger)
            logger.get_current_log_path = Mock(return_value=str(log_file))

            result = logger.read_current_log()
            assert "日本語" in result
            assert "中文" in result


class TestGetLogsDir:
    """Test logs directory management"""

    def test_get_logs_dir_creates_directory(self, tmp_path):
        """Test get_logs_dir creates logs directory if missing"""
        base_path = tmp_path / "store"

        with patch.object(AppLogger, '__init__', return_value=None):
            logger = AppLogger.__new__(AppLogger)
            logger._get_central_base = Mock(return_value=str(base_path))

            logs_dir = logger.get_logs_dir()

            assert os.path.exists(logs_dir)
            assert logs_dir.endswith("logs")

    def test_get_current_log_path(self, tmp_path):
        """Test get_current_log_path returns correct path"""
        base_path = tmp_path / "store"
        base_path.mkdir()

        with patch.object(AppLogger, '__init__', return_value=None):
            logger = AppLogger.__new__(AppLogger)
            logger._get_central_base = Mock(return_value=str(base_path))
            logger._settings = {'filename': 'test.log'}

            log_path = logger.get_current_log_path()

            assert log_path.endswith("test.log")
            assert "logs" in log_path


class TestGzipHandlers:
    """Test gzip compression handlers"""

    def test_gzip_timed_handler_initialization(self, tmp_path):
        """Test GzipTimedRotatingFileHandler initializes"""
        log_file = tmp_path / "test.log"
        handler = _GzipTimedRotatingFileHandler(
            filename=str(log_file),
            when='midnight',
            backupCount=7,
            encoding='utf-8',
            compress=True
        )
        assert handler.compress == True
        handler.close()

    def test_gzip_rotating_handler_initialization(self, tmp_path):
        """Test GzipRotatingFileHandler initializes"""
        log_file = tmp_path / "test.log"
        handler = _GzipRotatingFileHandler(
            filename=str(log_file),
            maxBytes=1024*1024,
            backupCount=5,
            encoding='utf-8',
            compress=True
        )
        assert handler.compress == True
        handler.close()
