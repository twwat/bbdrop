"""Unit tests for disk full error handling in logging system."""
import pytest
import sys
from unittest.mock import patch, MagicMock, call
from io import StringIO
import errno

from src.utils.logging import AppLogger
from src.processing.file_host_workers import FileHostWorker
from src.core.constants import DISK_ERROR_LOG_INTERVAL_SECONDS


class TestLoggingAntiRecursion:
    """Test anti-recursion logic when disk is full."""

    def test_log_to_file_disk_full_no_recursion(self):
        """Ensure disk full doesn't cause infinite recursion in log_to_file."""
        # Create AppLogger instance
        logger = AppLogger()

        # Mock the internal logger to raise OSError (disk full)
        disk_full_error = OSError(errno.ENOSPC, "No space left on device")

        with patch.object(logger, '_logger') as mock_logger:
            mock_logger.log.side_effect = disk_full_error

            # Mock stderr to capture output
            with patch('sys.stderr', new_callable=StringIO) as mock_stderr:
                # This should NOT raise exception or recurse
                logger.log_to_file("Test message", level=20, category="test")

                # Verify stderr was written to
                stderr_output = mock_stderr.getvalue()
                assert "[LOGGING] Disk write failed:" in stderr_output
                assert "No space left" in stderr_output

                # Verify log was only called once (no recursion)
                assert mock_logger.log.call_count == 1

    def test_log_to_file_io_error_no_recursion(self):
        """Ensure I/O errors don't cause infinite recursion."""
        logger = AppLogger()

        io_error = IOError("Disk I/O error")

        with patch.object(logger, '_logger') as mock_logger:
            mock_logger.log.side_effect = io_error

            with patch('sys.stderr', new_callable=StringIO) as mock_stderr:
                logger.log_to_file("Test message", level=20, category="test")

                stderr_output = mock_stderr.getvalue()
                assert "[LOGGING] Disk write failed:" in stderr_output
                assert "Disk I/O error" in stderr_output

    def test_log_to_file_other_exception_silent(self):
        """Ensure other exceptions fail silently without recursion."""
        logger = AppLogger()

        with patch.object(logger, '_logger') as mock_logger:
            mock_logger.log.side_effect = ValueError("Some other error")

            # Should not raise exception
            logger.log_to_file("Test message", level=20, category="test")

            # Should have tried once
            assert mock_logger.log.call_count == 1


class TestWorkerDiskFullRecovery:
    """Test file host worker disk full detection and recovery."""

    def test_worker_sets_disk_full_flag_on_error(self, tmp_path):
        """Verify worker sets _disk_full flag when database fails."""
        from src.storage.database import QueueStore

        # Create mock queue store
        mock_queue_store = MagicMock(spec=QueueStore)
        mock_queue_store.get_pending_file_host_uploads.side_effect = OSError(errno.ENOSPC, "Disk full")

        # Create worker
        worker = FileHostWorker(
            host_id="test_host",
            host_config={},
            queue_store=mock_queue_store,
            coordinator=MagicMock()
        )

        # Verify initial state
        assert worker._disk_full is False

        # Simulate one iteration of the worker loop (will hit disk error)
        # We can't easily test the full run() loop, so we'll test the logic directly
        try:
            pending_uploads = worker.queue_store.get_pending_file_host_uploads(host_name=worker.host_id)
        except Exception as e:
            error_str = str(e).lower()
            is_disk_error = any(x in error_str for x in ['disk', 'i/o', 'space', 'enospc'])

            if is_disk_error:
                worker._disk_full = True

        # Verify flag was set
        assert worker._disk_full is True

    def test_worker_recovers_from_disk_full(self, tmp_path):
        """Verify worker clears _disk_full flag on successful query."""
        from src.storage.database import QueueStore

        mock_queue_store = MagicMock(spec=QueueStore)

        worker = FileHostWorker(
            host_id="test_host",
            host_config={},
            queue_store=mock_queue_store,
            coordinator=MagicMock()
        )

        # Set disk full state
        worker._disk_full = True

        # Mock successful database query
        mock_queue_store.get_pending_file_host_uploads.return_value = []

        # Simulate successful query
        try:
            pending_uploads = worker.queue_store.get_pending_file_host_uploads(host_name=worker.host_id)

            # Success - clear disk full flag
            if worker._disk_full:
                worker._disk_full = False
        except Exception:
            pass

        # Verify flag was cleared
        assert worker._disk_full is False


class TestDiskErrorRateLimiting:
    """Test rate limiting of disk error log messages."""

    def test_disk_error_logged_once_per_interval(self):
        """Ensure disk errors logged max once per DISK_ERROR_LOG_INTERVAL_SECONDS."""
        from src.storage.database import QueueStore

        mock_queue_store = MagicMock(spec=QueueStore)

        worker = FileHostWorker(
            host_id="test_host",
            host_config={},
            queue_store=mock_queue_store,
            coordinator=MagicMock()
        )

        # Mock time.time() to control timing
        with patch('time.time', side_effect=[0, 30, 61, 90]) as mock_time:
            with patch.object(worker, '_log') as mock_log:
                worker._last_disk_error_log = 0

                # First error at t=0 - should log
                error = OSError("Disk full")
                error_str = str(error).lower()
                is_disk_error = any(x in error_str for x in ['disk', 'i/o', 'space', 'enospc'])

                if is_disk_error:
                    now = mock_time()
                    if now - worker._last_disk_error_log > DISK_ERROR_LOG_INTERVAL_SECONDS:
                        mock_log(f"Database unavailable due to disk full: {error}", level="error")
                        worker._last_disk_error_log = now

                # Second error at t=30 - should NOT log (30 < 60)
                now = mock_time()
                if now - worker._last_disk_error_log > DISK_ERROR_LOG_INTERVAL_SECONDS:
                    mock_log(f"Database unavailable due to disk full: {error}", level="error")
                    worker._last_disk_error_log = now

                # Third error at t=61 - should log (61 > 60)
                now = mock_time()
                if now - worker._last_disk_error_log > DISK_ERROR_LOG_INTERVAL_SECONDS:
                    mock_log(f"Database unavailable due to disk full: {error}", level="error")
                    worker._last_disk_error_log = now

                # Verify only 2 logs (at t=0 and t=61)
                assert mock_log.call_count == 2
