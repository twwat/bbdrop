#!/usr/bin/env python3
"""
Comprehensive test suite for logger.py
Testing unified logging interface and message routing
"""

import pytest
import logging
from unittest.mock import Mock, patch
from src.utils.logger import (
    timestamp,
    set_main_window,
    register_log_viewer,
    unregister_log_viewer,
    log,
    trace,
    debug,
    info,
    warning,
    error,
    critical,
    _detect_level_from_message,
    _detect_category_from_message,
    LEVEL_MAP,
    TRACE
)


@pytest.fixture(autouse=True)
def reset_logger_state():
    """Reset logger module globals before/after each test for xdist isolation."""
    from src.utils import logger

    # Save original state
    original_main = logger._main_window
    original_viewers = list(logger._log_viewers)  # Copy the list
    original_app = logger._app_logger

    # Reset to clean state
    logger._main_window = None
    logger._log_viewers.clear()  # Clear in-place, don't reassign
    logger._app_logger = None

    yield

    # Restore (for any tests that rely on persistent state)
    logger._main_window = original_main
    logger._log_viewers = original_viewers
    logger._app_logger = original_app


class TestTimestamp:
    """Test timestamp generation"""

    def test_timestamp_format(self):
        """Test timestamp returns HH:MM:SS format"""
        ts = timestamp()
        assert len(ts) == 8
        assert ts[2] == ":"
        assert ts[5] == ":"

    def test_timestamp_valid_components(self):
        """Test timestamp has valid time components"""
        ts = timestamp()
        h, m, s = ts.split(":")
        assert 0 <= int(h) <= 23
        assert 0 <= int(m) <= 59
        assert 0 <= int(s) <= 59


class TestLevelMap:
    """Test log level mappings"""

    def test_all_levels_defined(self):
        """Test all log levels are mapped"""
        assert 'trace' in LEVEL_MAP
        assert 'debug' in LEVEL_MAP
        assert 'info' in LEVEL_MAP
        assert 'warning' in LEVEL_MAP
        assert 'warn' in LEVEL_MAP  # Alias
        assert 'error' in LEVEL_MAP
        assert 'critical' in LEVEL_MAP

    def test_trace_level_value(self):
        """Test TRACE level is 5"""
        assert TRACE == 5
        assert LEVEL_MAP['trace'] == 5

    def test_warn_alias(self):
        """Test warn is alias for warning"""
        assert LEVEL_MAP['warn'] == LEVEL_MAP['warning']


class TestMainWindowManagement:
    """Test main window registration"""

    def test_set_main_window(self):
        """Test setting main window reference"""
        mock_window = Mock()
        set_main_window(mock_window)

        # Import the internal variable to verify
        from src.utils import logger
        assert logger._main_window is mock_window

    def test_set_main_window_replaces_existing(self):
        """Test setting main window replaces existing reference"""
        mock_window1 = Mock()
        mock_window2 = Mock()

        set_main_window(mock_window1)
        set_main_window(mock_window2)

        from src.utils import logger
        assert logger._main_window is mock_window2


class TestLogViewerManagement:
    """Test log viewer registration"""

    def test_register_log_viewer(self):
        """Test registering log viewer"""
        from src.utils import logger

        mock_viewer = Mock()
        register_log_viewer(mock_viewer)

        assert mock_viewer in logger._log_viewers

    def test_register_duplicate_viewer(self):
        """Test registering same viewer twice doesn't duplicate"""
        from src.utils import logger

        mock_viewer = Mock()
        register_log_viewer(mock_viewer)
        register_log_viewer(mock_viewer)

        assert logger._log_viewers.count(mock_viewer) == 1

    def test_unregister_log_viewer(self):
        """Test unregistering log viewer"""
        from src.utils import logger

        mock_viewer = Mock()
        register_log_viewer(mock_viewer)
        unregister_log_viewer(mock_viewer)

        assert mock_viewer not in logger._log_viewers

    def test_unregister_nonexistent_viewer(self):
        """Test unregistering viewer not in list doesn't error"""

        mock_viewer = Mock()
        unregister_log_viewer(mock_viewer)  # Should not raise


class TestDetectLevelFromMessage:
    """Test automatic log level detection"""

    @pytest.mark.parametrize("message,expected", [
        ("CRITICAL: System failure", "critical"),
        ("This is CRITICAL error", "critical"),
        ("ERROR: File not found", "error"),
        ("Error occurred", "error"),
        ("WARNING: Low memory", "warning"),
        ("WARN: Deprecated function", "warning"),
        ("Warning message", "warning"),
        ("DEBUG: Variable value", "debug"),
        ("Debug information", "debug"),
        ("TRACE: Verbose output", "trace"),
        ("INFO: Starting process", None),  # INFO not detected
        ("Regular message", None),
    ])
    def test_level_detection(self, message, expected):
        """Test level detection from message content"""
        result = _detect_level_from_message(message)
        assert result == expected

    def test_case_insensitive_detection(self):
        """Test detection is case-insensitive"""
        assert _detect_level_from_message("error: test") == "error"
        assert _detect_level_from_message("ERROR: test") == "error"
        assert _detect_level_from_message("Error: test") == "error"


class TestDetectCategoryFromMessage:
    """Test automatic category detection from [tag] format"""

    @pytest.mark.parametrize("message,expected_category,expected_subtype", [
        ("[uploads] File uploaded", "uploads", None),
        ("[auth] Login successful", "auth", None),
        ("[network:http] Request sent", "network", "http"),
        ("[uploads:file] File uploaded", "uploads", "file"),
        ("12:34:56 [uploads] Message", "uploads", None),
        ("No category here", "general", None),
        ("[ui] Window opened", "ui", None),
    ])
    def test_category_detection(self, message, expected_category, expected_subtype):
        """Test category and subtype detection"""
        category, subtype, cleaned = _detect_category_from_message(message)
        assert category == expected_category
        assert subtype == expected_subtype

    def test_cleaned_message_removes_tag(self):
        """Test cleaned message has tag removed"""
        _, _, cleaned = _detect_category_from_message("[uploads] File uploaded")
        assert "[uploads]" not in cleaned
        assert "File uploaded" in cleaned

    def test_preserves_timestamp(self):
        """Test timestamp is preserved in cleaned message"""
        _, _, cleaned = _detect_category_from_message("12:34:56 [uploads] Message")
        assert "12:34:56" in cleaned
        assert "[uploads]" not in cleaned


class TestLogFunction:
    """Test main log() function"""

    @patch('src.utils.logger._get_app_logger')
    def test_log_basic_message(self, mock_get_logger):
        """Test logging basic message"""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_logger.should_emit_file.return_value = True

        log("Test message")

        # Should attempt file logging
        mock_logger.log_to_file.assert_called_once()

    @patch('src.utils.logger._get_app_logger')
    def test_log_with_level(self, mock_get_logger):
        """Test logging with explicit level"""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_logger.should_emit_file.return_value = True

        log("Test", level="error")

        # Verify ERROR level was used
        call_args = mock_logger.log_to_file.call_args
        assert call_args[0][1] == logging.ERROR

    @patch('src.utils.logger._get_app_logger')
    def test_log_with_category(self, mock_get_logger):
        """Test logging with explicit category"""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_logger.should_emit_file.return_value = True

        log("Test", category="auth")

        # Verify category was passed
        call_args = mock_logger.log_to_file.call_args
        assert call_args[0][2] == "auth"

    @patch('src.utils.logger._get_app_logger')
    def test_log_auto_detects_level(self, mock_get_logger):
        """Test log auto-detects level from message"""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_logger.should_emit_file.return_value = True

        log("ERROR: Something failed")

        # Should detect ERROR level
        call_args = mock_logger.log_to_file.call_args
        assert call_args[0][1] == logging.ERROR

    @patch('src.utils.logger._get_app_logger')
    def test_log_auto_detects_category(self, mock_get_logger):
        """Test log auto-detects category from [tag]"""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_logger.should_emit_file.return_value = True

        log("[network] Request sent")

        # Should detect network category
        call_args = mock_logger.log_to_file.call_args
        assert call_args[0][2] == "network"

    @patch('src.utils.logger._get_app_logger')
    def test_log_adds_timestamp(self, mock_get_logger):
        """Test log adds timestamp if missing"""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_logger.should_emit_file.return_value = True

        log("Test message")

        # Message should have timestamp added
        call_args = mock_logger.log_to_file.call_args
        message = call_args[0][0]
        # Should contain HH:MM:SS format
        assert message[2] == ":" and message[5] == ":"

    @patch('src.utils.logger._get_app_logger')
    def test_log_preserves_existing_timestamp(self, mock_get_logger):
        """Test log preserves existing timestamp"""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_logger.should_emit_file.return_value = True

        log("12:34:56 Test message")

        call_args = mock_logger.log_to_file.call_args
        message = call_args[0][0]
        assert "12:34:56" in message

    @patch('src.utils.logger._get_app_logger')
    def test_log_adds_level_prefix(self, mock_get_logger):
        """Test log adds level prefix to message"""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_logger.should_emit_file.return_value = True

        log("Test", level="error")

        call_args = mock_logger.log_to_file.call_args
        message = call_args[0][0]
        assert "ERROR:" in message

    @patch('src.utils.logger._get_app_logger')
    def test_log_doesnt_duplicate_level_prefix(self, mock_get_logger):
        """Test log doesn't add level prefix if already present"""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_logger.should_emit_file.return_value = True

        log("ERROR: Test message", level="error")

        call_args = mock_logger.log_to_file.call_args
        message = call_args[0][0]
        # Should only have one ERROR:
        assert message.count("ERROR:") == 1

    @patch('src.utils.logger._get_app_logger')
    def test_trace_level_not_logged_to_file(self, mock_get_logger):
        """Test TRACE level is never logged to file"""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_logger.should_emit_file.return_value = False

        log("Test", level="trace")

        # Should not call log_to_file for TRACE
        # (should_emit_file returns False for TRACE)
        assert mock_logger.should_emit_file.called


class TestConvenienceFunctions:
    """Test convenience logging functions"""

    @patch('src.utils.logger.log')
    def test_trace_function(self, mock_log):
        """Test trace() convenience function"""
        trace("Test message")
        mock_log.assert_called_once_with("Test message", level="trace", category=None)

    @patch('src.utils.logger.log')
    def test_debug_function(self, mock_log):
        """Test debug() convenience function"""
        debug("Test message", category="network")
        mock_log.assert_called_once_with("Test message", level="debug", category="network")

    @patch('src.utils.logger.log')
    def test_info_function(self, mock_log):
        """Test info() convenience function"""
        info("Test message")
        mock_log.assert_called_once_with("Test message", level="info", category=None)

    @patch('src.utils.logger.log')
    def test_warning_function(self, mock_log):
        """Test warning() convenience function"""
        warning("Test message")
        mock_log.assert_called_once_with("Test message", level="warning", category=None)

    @patch('src.utils.logger.log')
    def test_error_function(self, mock_log):
        """Test error() convenience function"""
        error("Test message")
        mock_log.assert_called_once_with("Test message", level="error", category=None)

    @patch('src.utils.logger.log')
    def test_critical_function(self, mock_log):
        """Test critical() convenience function"""
        critical("Test message")
        mock_log.assert_called_once_with("Test message", level="critical", category=None)


class TestGUIIntegration:
    """Test GUI log routing"""

    @patch('src.utils.logger._get_app_logger')
    def test_log_routes_to_gui(self, mock_get_logger):
        """Test log routes to GUI when main window is set"""
        from src.utils import logger

        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_logger.should_emit_file.return_value = False
        mock_logger.should_emit_gui.return_value = True

        mock_window = Mock()
        mock_window.add_log_message = Mock()
        logger._main_window = mock_window

        log("Test message")

        # Should call add_log_message on main window
        mock_window.add_log_message.assert_called_once()

    @patch('src.utils.logger._get_app_logger')
    def test_log_routes_to_viewers(self, mock_get_logger):
        """Test log routes to registered viewers"""
        from src.utils import logger

        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_logger.should_emit_file.return_value = False

        mock_viewer = Mock()
        mock_viewer.append_message = Mock()
        logger._log_viewers = [mock_viewer]

        log("Test message", level="info", category="general")

        # Should call append_message on viewer
        mock_viewer.append_message.assert_called_once()


class TestDebugMode:
    """Test debug mode behavior"""

    @patch('src.utils.logger._debug_mode', True)
    @patch('sys.stdout')
    def test_debug_mode_prints_all(self, mock_stdout):
        """Test debug mode prints all messages to console"""

        with patch('src.utils.logger._get_app_logger') as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger
            mock_logger.should_emit_file.return_value = False

            with patch('builtins.print') as mock_print:
                log("Test message", level="debug")

                # Should print in debug mode
                assert mock_print.called


class TestCriticalErrorHandling:
    """Test critical error always prints to console"""

    @patch('sys.stderr')
    @patch('src.utils.logger._get_app_logger')
    def test_error_always_prints(self, mock_get_logger, mock_stderr):
        """Test ERROR level always prints to console"""
        from src.utils import logger

        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_logger.should_emit_file.return_value = True

        logger._main_window = Mock()  # Even with GUI

        with patch('builtins.print') as mock_print:
            log("Critical error", level="error")

            # Should print to stderr
            assert mock_print.called

    @patch('sys.stderr')
    @patch('src.utils.logger._get_app_logger')
    def test_critical_always_prints(self, mock_get_logger, mock_stderr):
        """Test CRITICAL level always prints to console"""
        from src.utils import logger

        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_logger.should_emit_file.return_value = True

        logger._main_window = Mock()

        with patch('builtins.print') as mock_print:
            log("Critical failure", level="critical")

            assert mock_print.called


class TestCategorySubtype:
    """Test category:subtype parsing"""

    @patch('src.utils.logger._get_app_logger')
    def test_category_subtype_parsing(self, mock_get_logger):
        """Test category:subtype format is parsed"""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_logger.should_emit_file.return_value = True

        log("Test", category="uploads:file")

        # Category should be "uploads"
        call_args = mock_logger.log_to_file.call_args
        assert call_args[0][2] == "uploads"

    @patch('src.utils.logger._get_app_logger')
    def test_upload_file_success_filtering(self, mock_get_logger):
        """Test upload file success filtering"""
        from src.utils import logger

        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        mock_logger.should_emit_file.return_value = False
        mock_logger.should_emit_gui.return_value = True
        mock_logger.should_log_upload_file_success.return_value = False

        mock_window = Mock()
        logger._main_window = mock_window

        log("File uploaded", category="uploads:file")

        # Should check upload success mode
        mock_logger.should_log_upload_file_success.assert_called_once_with("gui")
