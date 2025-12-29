"""
Comprehensive test suite for src/processing/archive_worker.py
Tests archive extraction worker with threading and signal mocking.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call
from PyQt6.QtCore import QObject

from src.processing.archive_worker import (
    ArchiveExtractionSignals,
    ArchiveExtractionWorker
)


class TestArchiveExtractionSignalsInit:
    """Test ArchiveExtractionSignals initialization"""

    def test_signals_init(self):
        """Test signal object initialization"""
        signals = ArchiveExtractionSignals()

        assert signals is not None
        assert isinstance(signals, QObject)

    def test_finished_signal_exists(self):
        """Test finished signal exists"""
        signals = ArchiveExtractionSignals()

        assert hasattr(signals, 'finished')
        # Verify it's a pyqtSignal by checking it can connect
        assert callable(signals.finished.connect)

    def test_error_signal_exists(self):
        """Test error signal exists"""
        signals = ArchiveExtractionSignals()

        assert hasattr(signals, 'error')
        assert callable(signals.error.connect)

    def test_progress_signal_exists(self):
        """Test progress signal exists"""
        signals = ArchiveExtractionSignals()

        assert hasattr(signals, 'progress')
        assert callable(signals.progress.connect)

    def test_signals_are_independent(self):
        """Test each signal object has independent signals"""
        signals1 = ArchiveExtractionSignals()
        signals2 = ArchiveExtractionSignals()

        assert signals1.finished is not signals2.finished
        assert signals1.error is not signals2.error
        assert signals1.progress is not signals2.progress


class TestArchiveExtractionWorkerInit:
    """Test ArchiveExtractionWorker initialization"""

    def test_init_basic(self):
        """Test basic worker initialization"""
        mock_coordinator = Mock()
        archive_path = "/path/to/archive.zip"

        worker = ArchiveExtractionWorker(archive_path, mock_coordinator)

        assert worker.archive_path == archive_path
        assert worker.coordinator == mock_coordinator

    def test_init_creates_signals(self):
        """Test initialization creates signals object"""
        mock_coordinator = Mock()

        worker = ArchiveExtractionWorker("/path/to/archive.zip", mock_coordinator)

        assert hasattr(worker, 'signals')
        assert isinstance(worker.signals, ArchiveExtractionSignals)

    def test_init_with_cbz_file(self):
        """Test initialization with CBZ file"""
        mock_coordinator = Mock()
        archive_path = "/path/to/comic.cbz"

        worker = ArchiveExtractionWorker(archive_path, mock_coordinator)

        assert worker.archive_path == archive_path
        assert ".cbz" in worker.archive_path

    def test_init_with_zip_file(self):
        """Test initialization with ZIP file"""
        mock_coordinator = Mock()
        archive_path = "/path/to/archive.zip"

        worker = ArchiveExtractionWorker(archive_path, mock_coordinator)

        assert worker.archive_path == archive_path
        assert ".zip" in worker.archive_path

    def test_init_preserves_coordinator_reference(self):
        """Test coordinator reference is preserved correctly"""
        mock_coordinator = Mock()
        mock_coordinator.process_archive = Mock(return_value=[])

        worker = ArchiveExtractionWorker("/path/to/archive.zip", mock_coordinator)

        assert worker.coordinator is mock_coordinator

    def test_init_multiple_workers_independent(self):
        """Test multiple workers have independent signals"""
        mock_coordinator1 = Mock()
        mock_coordinator2 = Mock()

        worker1 = ArchiveExtractionWorker("/path/to/archive1.zip", mock_coordinator1)
        worker2 = ArchiveExtractionWorker("/path/to/archive2.zip", mock_coordinator2)

        assert worker1.signals is not worker2.signals
        assert worker1.coordinator is not worker2.coordinator


class TestArchiveExtractionWorkerRunSuccess:
    """Test successful archive extraction"""

    def test_run_extracts_successfully(self):
        """Test successful archive extraction"""
        mock_coordinator = Mock()
        folder1 = Path("/extracted/folder1")
        folder2 = Path("/extracted/folder2")
        mock_coordinator.process_archive.return_value = [folder1, folder2]

        worker = ArchiveExtractionWorker("/path/to/archive.zip", mock_coordinator)

        # Mock the signals to track emissions
        finished_spy = Mock()
        worker.signals.finished.connect(finished_spy)

        worker.run()

        # Verify coordinator was called
        mock_coordinator.process_archive.assert_called_once_with("/path/to/archive.zip")
        # Verify finished signal was emitted with string paths
        finished_spy.assert_called_once()
        args = finished_spy.call_args[0]
        assert args[0] == "/path/to/archive.zip"
        assert len(args[1]) == 2
        assert args[1][0] == str(folder1)
        assert args[1][1] == str(folder2)

    def test_run_converts_path_objects_to_strings(self):
        """Test Path objects are converted to strings"""
        mock_coordinator = Mock()
        folder_paths = [Path("/folder1"), Path("/folder2"), Path("/folder3")]
        mock_coordinator.process_archive.return_value = folder_paths

        worker = ArchiveExtractionWorker("/archive.zip", mock_coordinator)

        finished_spy = Mock()
        worker.signals.finished.connect(finished_spy)

        worker.run()

        args = finished_spy.call_args[0]
        result_paths = args[1]

        # All should be strings
        assert all(isinstance(p, str) for p in result_paths)
        assert result_paths == [str(p) for p in folder_paths]

    def test_run_with_single_folder(self):
        """Test extraction with single folder result"""
        mock_coordinator = Mock()
        mock_coordinator.process_archive.return_value = [Path("/single_folder")]

        worker = ArchiveExtractionWorker("/archive.zip", mock_coordinator)

        finished_spy = Mock()
        worker.signals.finished.connect(finished_spy)

        worker.run()

        args = finished_spy.call_args[0]
        assert len(args[1]) == 1
        assert args[1][0] == "/single_folder"

    def test_run_with_many_folders(self):
        """Test extraction with many folders"""
        mock_coordinator = Mock()
        folders = [Path(f"/folder{i}") for i in range(10)]
        mock_coordinator.process_archive.return_value = folders

        worker = ArchiveExtractionWorker("/archive.zip", mock_coordinator)

        finished_spy = Mock()
        worker.signals.finished.connect(finished_spy)

        worker.run()

        args = finished_spy.call_args[0]
        assert len(args[1]) == 10


class TestArchiveExtractionWorkerRunEmpty:
    """Test handling of empty extraction results"""

    def test_run_no_folders_found_empty_list(self):
        """Test handling when no folders are found (empty list)"""
        mock_coordinator = Mock()
        mock_coordinator.process_archive.return_value = []

        worker = ArchiveExtractionWorker("/archive.zip", mock_coordinator)

        error_spy = Mock()
        worker.signals.error.connect(error_spy)

        worker.run()

        # Should emit error signal
        error_spy.assert_called_once()
        args = error_spy.call_args[0]
        assert args[0] == "/archive.zip"
        assert "No folders selected or extraction cancelled" in args[1]

    def test_run_no_folders_found_none(self):
        """Test handling when None is returned"""
        mock_coordinator = Mock()
        mock_coordinator.process_archive.return_value = None

        worker = ArchiveExtractionWorker("/archive.zip", mock_coordinator)

        error_spy = Mock()
        worker.signals.error.connect(error_spy)

        worker.run()

        # Should emit error signal
        error_spy.assert_called_once()
        args = error_spy.call_args[0]
        assert "No folders selected or extraction cancelled" in args[1]

    def test_run_user_cancellation(self):
        """Test handling of user cancellation"""
        mock_coordinator = Mock()
        mock_coordinator.process_archive.return_value = []

        worker = ArchiveExtractionWorker("/archive.zip", mock_coordinator)

        finished_spy = Mock()
        error_spy = Mock()
        worker.signals.finished.connect(finished_spy)
        worker.signals.error.connect(error_spy)

        worker.run()

        # Should emit error, not finished
        error_spy.assert_called_once()
        finished_spy.assert_not_called()


class TestArchiveExtractionWorkerRunErrors:
    """Test error handling during extraction"""

    def test_run_coordinator_exception(self):
        """Test coordinator raising exception"""
        mock_coordinator = Mock()
        mock_coordinator.process_archive.side_effect = Exception("Extraction failed")

        worker = ArchiveExtractionWorker("/archive.zip", mock_coordinator)

        error_spy = Mock()
        worker.signals.error.connect(error_spy)

        worker.run()

        # Should emit error signal
        error_spy.assert_called_once()
        args = error_spy.call_args[0]
        assert args[0] == "/archive.zip"
        assert "Archive extraction failed" in args[1]
        assert "Extraction failed" in args[1]

    def test_run_file_not_found_error(self):
        """Test handling of file not found"""
        mock_coordinator = Mock()
        mock_coordinator.process_archive.side_effect = FileNotFoundError("File not found")

        worker = ArchiveExtractionWorker("/nonexistent/archive.zip", mock_coordinator)

        error_spy = Mock()
        worker.signals.error.connect(error_spy)

        worker.run()

        error_spy.assert_called_once()
        args = error_spy.call_args[0]
        assert "Archive extraction failed" in args[1]

    def test_run_permission_error(self):
        """Test handling of permission error"""
        mock_coordinator = Mock()
        mock_coordinator.process_archive.side_effect = PermissionError("Permission denied")

        worker = ArchiveExtractionWorker("/protected/archive.zip", mock_coordinator)

        error_spy = Mock()
        worker.signals.error.connect(error_spy)

        worker.run()

        error_spy.assert_called_once()
        args = error_spy.call_args[0]
        assert "Archive extraction failed" in args[1]

    def test_run_generic_exception(self):
        """Test handling of generic exception"""
        mock_coordinator = Mock()
        error_msg = "Something went terribly wrong"
        mock_coordinator.process_archive.side_effect = RuntimeError(error_msg)

        worker = ArchiveExtractionWorker("/archive.zip", mock_coordinator)

        error_spy = Mock()
        worker.signals.error.connect(error_spy)

        worker.run()

        error_spy.assert_called_once()
        args = error_spy.call_args[0]
        assert error_msg in args[1]

    def test_run_does_not_emit_finished_on_error(self):
        """Test that finished signal is not emitted on error"""
        mock_coordinator = Mock()
        mock_coordinator.process_archive.side_effect = Exception("Failed")

        worker = ArchiveExtractionWorker("/archive.zip", mock_coordinator)

        finished_spy = Mock()
        error_spy = Mock()
        worker.signals.finished.connect(finished_spy)
        worker.signals.error.connect(error_spy)

        worker.run()

        finished_spy.assert_not_called()
        error_spy.assert_called_once()


class TestArchiveExtractionWorkerSignalEmission:
    """Test signal emission behavior"""

    def test_error_signal_has_archive_path(self):
        """Test error signal includes archive path"""
        mock_coordinator = Mock()
        mock_coordinator.process_archive.side_effect = Exception("Error")
        archive_path = "/path/to/specific/archive.zip"

        worker = ArchiveExtractionWorker(archive_path, mock_coordinator)

        error_spy = Mock()
        worker.signals.error.connect(error_spy)

        worker.run()

        args = error_spy.call_args[0]
        assert args[0] == archive_path

    def test_finished_signal_has_archive_path(self):
        """Test finished signal includes archive path"""
        mock_coordinator = Mock()
        archive_path = "/path/to/specific/archive.zip"
        mock_coordinator.process_archive.return_value = [Path("/folder")]

        worker = ArchiveExtractionWorker(archive_path, mock_coordinator)

        finished_spy = Mock()
        worker.signals.finished.connect(finished_spy)

        worker.run()

        args = finished_spy.call_args[0]
        assert args[0] == archive_path

    def test_error_message_includes_exception_details(self):
        """Test error message includes exception details"""
        mock_coordinator = Mock()
        error_details = "Invalid zip file format"
        mock_coordinator.process_archive.side_effect = Exception(error_details)

        worker = ArchiveExtractionWorker("/archive.zip", mock_coordinator)

        error_spy = Mock()
        worker.signals.error.connect(error_spy)

        worker.run()

        args = error_spy.call_args[0]
        assert error_details in args[1]


class TestArchiveExtractionWorkerEdgeCases:
    """Test edge cases and special scenarios"""

    def test_run_with_empty_string_path(self):
        """Test handling empty string archive path"""
        mock_coordinator = Mock()
        mock_coordinator.process_archive.return_value = [Path("/folder")]

        worker = ArchiveExtractionWorker("", mock_coordinator)

        finished_spy = Mock()
        worker.signals.finished.connect(finished_spy)

        worker.run()

        args = finished_spy.call_args[0]
        assert args[0] == ""

    def test_run_with_special_characters_in_path(self):
        """Test handling special characters in path"""
        mock_coordinator = Mock()
        mock_coordinator.process_archive.return_value = [Path("/folder")]
        archive_path = "/path/to/archive (2024) [special].zip"

        worker = ArchiveExtractionWorker(archive_path, mock_coordinator)

        finished_spy = Mock()
        worker.signals.finished.connect(finished_spy)

        worker.run()

        mock_coordinator.process_archive.assert_called_once_with(archive_path)

    def test_run_with_unicode_in_path(self):
        """Test handling unicode characters in path"""
        mock_coordinator = Mock()
        mock_coordinator.process_archive.return_value = [Path("/folder")]
        archive_path = "/path/to/アーカイブ.zip"

        worker = ArchiveExtractionWorker(archive_path, mock_coordinator)

        finished_spy = Mock()
        worker.signals.finished.connect(finished_spy)

        worker.run()

        args = finished_spy.call_args[0]
        assert args[0] == archive_path

    def test_run_with_very_long_path(self):
        """Test handling very long paths"""
        mock_coordinator = Mock()
        mock_coordinator.process_archive.return_value = [Path("/folder")]
        long_path = "/path/" + "a" * 200 + "/archive.zip"

        worker = ArchiveExtractionWorker(long_path, mock_coordinator)

        finished_spy = Mock()
        worker.signals.finished.connect(finished_spy)

        worker.run()

        mock_coordinator.process_archive.assert_called_once_with(long_path)

    def test_run_multiple_times(self):
        """Test worker can be run multiple times"""
        mock_coordinator = Mock()
        mock_coordinator.process_archive.return_value = [Path("/folder")]

        worker = ArchiveExtractionWorker("/archive.zip", mock_coordinator)

        finished_spy = Mock()
        worker.signals.finished.connect(finished_spy)

        # Run first time
        worker.run()
        first_call_count = finished_spy.call_count

        # Run second time
        worker.run()
        second_call_count = finished_spy.call_count

        assert second_call_count == first_call_count + 1

    def test_run_with_windows_path(self):
        """Test handling Windows-style paths"""
        mock_coordinator = Mock()
        mock_coordinator.process_archive.return_value = [Path("C:\\folder")]
        archive_path = "C:\\Users\\test\\archive.zip"

        worker = ArchiveExtractionWorker(archive_path, mock_coordinator)

        finished_spy = Mock()
        worker.signals.finished.connect(finished_spy)

        worker.run()

        mock_coordinator.process_archive.assert_called_once_with(archive_path)


class TestArchiveExtractionWorkerCoordination:
    """Test interaction with coordinator"""

    def test_run_calls_coordinator_with_correct_path(self):
        """Test coordinator is called with correct archive path"""
        mock_coordinator = Mock()
        mock_coordinator.process_archive.return_value = []
        archive_path = "/specific/path/archive.zip"

        worker = ArchiveExtractionWorker(archive_path, mock_coordinator)
        worker.run()

        mock_coordinator.process_archive.assert_called_once_with(archive_path)

    def test_run_respects_coordinator_return_value(self):
        """Test worker uses coordinator's return value"""
        mock_coordinator = Mock()
        expected_folders = [Path("/f1"), Path("/f2"), Path("/f3")]
        mock_coordinator.process_archive.return_value = expected_folders

        worker = ArchiveExtractionWorker("/archive.zip", mock_coordinator)

        finished_spy = Mock()
        worker.signals.finished.connect(finished_spy)

        worker.run()

        args = finished_spy.call_args[0]
        returned_folders = args[1]

        assert len(returned_folders) == 3
        assert returned_folders == [str(p) for p in expected_folders]

    def test_coordinator_process_archive_called_once(self):
        """Test process_archive is called exactly once"""
        mock_coordinator = Mock()
        mock_coordinator.process_archive.return_value = [Path("/folder")]

        worker = ArchiveExtractionWorker("/archive.zip", mock_coordinator)
        worker.run()

        assert mock_coordinator.process_archive.call_count == 1


class TestArchiveExtractionWorkerIntegration:
    """Integration tests for worker behavior"""

    def test_worker_handles_complex_extraction_flow(self):
        """Test complex extraction flow"""
        mock_coordinator = Mock()
        folders = [Path("/extracted/manga"), Path("/extracted/images")]
        mock_coordinator.process_archive.return_value = folders

        worker = ArchiveExtractionWorker("/large_archive.cbz", mock_coordinator)

        finished_spy = Mock()
        error_spy = Mock()
        worker.signals.finished.connect(finished_spy)
        worker.signals.error.connect(error_spy)

        worker.run()

        # Should emit finished, not error
        finished_spy.assert_called_once()
        error_spy.assert_not_called()

        # Check result structure
        args = finished_spy.call_args[0]
        assert args[0] == "/large_archive.cbz"
        assert len(args[1]) == 2
        assert "/extracted/manga" in args[1]
        assert "/extracted/images" in args[1]

    def test_worker_resilience_to_partial_failure(self):
        """Test worker handles partial failures gracefully"""
        mock_coordinator = Mock()
        mock_coordinator.process_archive.side_effect = ValueError("Corrupted archive")

        worker = ArchiveExtractionWorker("/corrupted.zip", mock_coordinator)

        error_spy = Mock()
        worker.signals.error.connect(error_spy)

        # Should handle without raising
        worker.run()

        error_spy.assert_called_once()
        args = error_spy.call_args[0]
        assert "Corrupted archive" in args[1]
